"""Speak SPR-05 — cross-interviewee verification / story-hardening.

The operator wants to "verify true stories by hardening them across
interviewees." The honest version is CORROBORATION, not proof:

  • when ≥2 INDEPENDENT interviewees attest the same claim, confidence
    rises and the claim is marked ``multiply_attested`` — corroborated,
    never "proven true" (the cardinal rule: N people can share a false
    memory, and the system cannot detect that);
  • when interviewees conflict, the contradiction is flagged with both
    sources, and the minority view is preserved, not suppressed.

These labels feed two consumers:
  • the publish gate (SPR-01): a third-party claim is publishable only
    if ``multiply_attested`` or operator-attested; ``contradicted`` is
    never publishable;
  • the compounding interviewer (SPR-04): single-sourced claims and
    contradictions are what it probes next.

Reuses, not forks: contradiction maps onto the grounder's CONTRADICTED
verdict idea; confidence weighting echoes the confidence × (6 − tier)
discipline. Clustering uses embeddings to PROPOSE candidate matches and
an equivalence check to CONFIRM them (filtering embedding-noise false
clusters) — embeddings narrow, the check decides.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .events import (
    SPEAK_CLAIM_CONTRADICTED,
    SPEAK_CLAIM_MULTIPLY_ATTESTED,
    record_speak_event,
)
from .ids import new_cluster_id
from .independence import count_independent
from .schema import ensure_speak_schema
from .third_party import ClaimRecord, list_claims

# Type aliases for the injectable checks.
EquivalenceFn = Callable[[str, str], bool]
ContradictionFn = Callable[[str, str], bool]
IndependenceKeyFn = Callable[[ClaimRecord], str | None]


def confidence_for(independent_attesters: int) -> float:
    """Confidence as a function of INDEPENDENT attestation. Monotonic,
    asymptotic, and — deliberately — never reaches 1.0. Corroboration
    raises confidence; it never proves truth.

        1 attester  → 0.50
        2 attesters → 0.70
        3 attesters → 0.82
        4 attesters → 0.89   (… approaching, capped strictly below 1.0)

    The 0.95 cap is load-bearing: no amount of corroboration ever yields
    certainty. Multiply-attested is corroborated, not proven.
    """
    n = max(1, independent_attesters)
    return min(0.95, round(1.0 - 0.5 * (0.6 ** (n - 1)), 4))


def _default_equivalence(a: str, b: str, *, jaccard_threshold: float = 0.6) -> bool:
    """Token-Jaccard equivalence — the default confirmation check.
    Deliberately conservative: it confirms two claims are *the same
    claim*, filtering embedding false-positives. A grounder-backed
    semantic check can be injected for production."""
    ta = set(a.lower().split())
    tb = set(b.lower().split())
    if not ta or not tb:
        return False
    inter = len(ta & tb)
    union = len(ta | tb)
    return (inter / union) >= jaccard_threshold if union else False


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


@dataclass
class Cluster:
    cluster_id: str
    project_id: str
    canonical_text: str
    label: str  # 'single_sourced' | 'multiply_attested' | 'contradicted'
    confidence: float
    independent_attesters: int
    member_claim_ids: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Clustering (M1)
# ---------------------------------------------------------------------------


def _union_find_clusters(
    claims: list[ClaimRecord],
    *,
    embedder: Any | None,
    equivalence: EquivalenceFn,
    similarity_threshold: float,
) -> list[list[ClaimRecord]]:
    """Group equivalent claims. Embeddings (if given) narrow candidate
    pairs by cosine ≥ threshold; the equivalence check confirms each
    pair before merging (so embedding noise can't create false
    clusters). Union-find over confirmed pairs."""
    n = len(claims)
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        parent[find(i)] = find(j)

    embeddings: list[list[float]] | None = None
    if embedder is not None:
        embeddings = [embedder.encode(c.text) for c in claims]

    for i in range(n):
        for j in range(i + 1, n):
            if embeddings is not None:
                if _cosine(embeddings[i], embeddings[j]) < similarity_threshold:
                    continue  # embeddings say "not a candidate"
            if equivalence(claims[i].text, claims[j].text):
                union(i, j)

    groups: dict[int, list[ClaimRecord]] = {}
    for idx, claim in enumerate(claims):
        groups.setdefault(find(idx), []).append(claim)
    return list(groups.values())


# ---------------------------------------------------------------------------
# The main pass (M1–M5)
# ---------------------------------------------------------------------------


def corroborate_project(
    con: Any,
    project_id: str,
    *,
    embedder: Any | None = None,
    equivalence: EquivalenceFn | None = None,
    contradiction: ContradictionFn | None = None,
    independence_key_for: IndependenceKeyFn | None = None,
    similarity_threshold: float = 0.82,
) -> list[Cluster]:
    """Cluster the project's claims, mark corroboration / contradiction,
    and write the verification state the publish gate + interviewer read.

    - ``embedder`` (optional): narrows candidate pairs by cosine.
    - ``equivalence`` (default token-Jaccard): confirms a candidate pair
      is the same claim.
    - ``contradiction`` (default: none): given two equivalent-topic
      claim texts, returns True if they CONFLICT. A grounder-backed
      detector is injected in production.
    - ``independence_key_for`` (default: interviewee): the shared-origin
      key for a claim's attestation; equal keys count as one attester.
    """
    ensure_speak_schema(con)
    equivalence = equivalence or _default_equivalence
    claims = list_claims(con, project_id)
    if not claims:
        return []

    groups = _union_find_clusters(
        claims, embedder=embedder, equivalence=equivalence,
        similarity_threshold=similarity_threshold,
    )

    # Clear prior clusters for an idempotent recompute.
    con.execute("DELETE FROM speak_corroboration_members WHERE cluster_id IN "
                "(SELECT cluster_id FROM speak_corroboration_clusters WHERE project_id = ?)",
                [project_id])
    con.execute("DELETE FROM speak_corroboration_clusters WHERE project_id = ?", [project_id])

    out: list[Cluster] = []
    for group in groups:
        canonical = max(group, key=lambda c: len(c.text)).text
        members = [{
            "claim_id": c.claim_id,
            "interview_id": c.interview_id,
            "independence_key": (independence_key_for(c) if independence_key_for else None),
            "stance": "attests",
        } for c in group]

        # Contradiction: any pair within the topic-cluster that conflicts.
        is_contradicted = False
        if contradiction is not None:
            for i in range(len(group)):
                for j in range(i + 1, len(group)):
                    if contradiction(group[i].text, group[j].text):
                        is_contradicted = True
                        members[j]["stance"] = "contradicts"
        independent = count_independent(members)

        if is_contradicted:
            label, confidence = "contradicted", confidence_for(1)
        elif independent >= 2:
            label, confidence = "multiply_attested", confidence_for(independent)
        else:
            label, confidence = "single_sourced", confidence_for(1)

        cluster_id = new_cluster_id(project_id, canonical)
        con.execute(
            "INSERT INTO speak_corroboration_clusters "
            "(cluster_id, project_id, canonical_text, label, confidence, independent_attesters) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [cluster_id, project_id, canonical, label, confidence, independent],
        )
        for m in members:
            con.execute(
                "INSERT INTO speak_corroboration_members "
                "(cluster_id, claim_id, interview_id, stance, independence_key) "
                "VALUES (?, ?, ?, ?, ?)",
                [cluster_id, m["claim_id"], m["interview_id"], m["stance"],
                 m["independence_key"]],
            )

        # Write the verification state the SPR-01 publish gate reads.
        # NEVER write 'true' — only corroborated / contradicted.
        _apply_verification(con, group, label, confidence)

        if label == "multiply_attested":
            record_speak_event(SPEAK_CLAIM_MULTIPLY_ATTESTED,
                               {"cluster_id": cluster_id, "independent_attesters": independent,
                                "confidence": confidence}, project_id=project_id)
        elif label == "contradicted":
            record_speak_event(SPEAK_CLAIM_CONTRADICTED,
                               {"cluster_id": cluster_id,
                                "claim_ids": [c.claim_id for c in group]}, project_id=project_id)

        out.append(Cluster(
            cluster_id=cluster_id, project_id=project_id, canonical_text=canonical,
            label=label, confidence=confidence, independent_attesters=independent,
            member_claim_ids=[c.claim_id for c in group],
        ))
    return out


def _apply_verification(con: Any, group: list[ClaimRecord], label: str, confidence: float) -> None:
    """Project the cluster label onto each member claim's verification —
    but only for third-party claims (first-party claims need no
    corroboration) and never overriding an explicit operator attestation
    or downgrading below what's already publishable inadvertently."""
    for c in group:
        if not c.is_third_party:
            continue
        if c.verification == "operator_attested":
            continue  # operator's explicit call stands
        if label == "multiply_attested":
            con.execute(
                "UPDATE speak_claims SET verification = 'multiply_attested', "
                "confidence = ?, updated_at = CURRENT_TIMESTAMP WHERE claim_id = ?",
                [confidence, c.claim_id],
            )
        elif label == "contradicted":
            con.execute(
                "UPDATE speak_claims SET verification = 'contradicted', "
                "updated_at = CURRENT_TIMESTAMP WHERE claim_id = ?",
                [c.claim_id],
            )
        # single_sourced → leave 'unverified' (still not publishable).


# ---------------------------------------------------------------------------
# Feeds for the compounding interviewer (SPR-04) — M5
# ---------------------------------------------------------------------------


def claims_needing_corroboration(con: Any, project_id: str) -> list[ClaimRecord]:
    """Single-sourced third-party claims the interviewer should probe
    other interviewees to corroborate."""
    return [
        c for c in list_claims(con, project_id, third_party_only=True)
        if c.verification == "unverified"
    ]


def contradictions(con: Any, project_id: str) -> list[Cluster]:
    """Contradicted clusters — surfaced for probing + blocked from
    publishing. Both sides preserved (the members table keeps stance)."""
    rows = con.execute(
        "SELECT cluster_id, project_id, canonical_text, label, confidence, "
        "independent_attesters FROM speak_corroboration_clusters "
        "WHERE project_id = ? AND label = 'contradicted'",
        [project_id],
    ).fetchall()
    out: list[Cluster] = []
    for r in rows:
        members = con.execute(
            "SELECT claim_id FROM speak_corroboration_members WHERE cluster_id = ?",
            [r[0]],
        ).fetchall()
        out.append(Cluster(
            cluster_id=r[0], project_id=r[1], canonical_text=r[2], label=r[3],
            confidence=float(r[4]), independent_attesters=int(r[5]),
            member_claim_ids=[m[0] for m in members],
        ))
    return out
