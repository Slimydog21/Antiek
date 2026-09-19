"""Explicit, account-qualified corroboration over admitted interview claims."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Literal

from runtime.db_lock import LockedConnection

from .authority import InterviewAccountAuthority
from .consent import consent_state


class CorroborationConflict(RuntimeError):
    pass


@dataclass(frozen=True)
class CorroborationMember:
    claim_id: str
    stance: Literal["attests", "contradicts"]


@dataclass(frozen=True)
class CanonicalCorroboration:
    cluster_id: str
    project_id: str
    canonical_claim_id: str
    canonical_text: str
    label: str
    confidence: float
    independent_attesters: int
    members: tuple[CorroborationMember, ...]


def _begin_if_needed(con: LockedConnection) -> bool:
    if con.transaction_active:
        return False
    con.execute("BEGIN TRANSACTION")
    return True


def _confidence(count: int) -> float:
    return min(0.95, 1.0 - (0.5 ** max(1, count)))


def _cluster_id(
    authority: InterviewAccountAuthority,
    project_id: str,
    canonical_claim_id: str,
    members: tuple[CorroborationMember, ...],
) -> str:
    material = "\0".join(
        [authority.account_digest, project_id, canonical_claim_id]
        + [f"{member.claim_id}:{member.stance}" for member in members]
    )
    digest = hashlib.sha256(b"antiek-corroboration-v1\0" + material.encode()).hexdigest()
    return f"ivco-{digest[:32]}"


def record_corroboration(
    con: LockedConnection,
    authority: InterviewAccountAuthority,
    *,
    project_id: str,
    canonical_claim_id: str,
    members: list[CorroborationMember],
) -> CanonicalCorroboration:
    """Record an operator-confirmed equivalence/contradiction cluster.

    Missing origin evidence intentionally shares one ``unknown_origin`` bucket.
    It can never turn multiple unattributed claims into independent attestation.
    """
    if not isinstance(con, LockedConnection):
        raise TypeError("canonical corroboration requires a LockedConnection")
    normalized = tuple(sorted(members, key=lambda member: member.claim_id))
    if not normalized or len({member.claim_id for member in normalized}) != len(normalized):
        raise ValueError("corroboration members must be non-empty and unique")
    if canonical_claim_id not in {member.claim_id for member in normalized}:
        raise ValueError("canonical claim must be a cluster member")
    if next(m for m in normalized if m.claim_id == canonical_claim_id).stance != "attests":
        raise ValueError("canonical claim must attest")
    placeholders = ", ".join("?" for _ in normalized)
    rows = con.execute(
        "SELECT claim_id, text, subject_ref, about_subject, is_third_party, "
        "independence_key, verification, interview_id, source_document_id "
        "FROM interview_claims_authority "
        "WHERE account_digest = ? AND owner_user_id = ? AND project_id = ? "
        f"AND claim_id IN ({placeholders})",
        [authority.account_digest, authority.account_id, project_id]
        + [member.claim_id for member in normalized],
    ).fetchall()
    if len(rows) != len(normalized):
        raise ValueError("one or more canonical claims were not found")
    by_id = {str(row[0]): row for row in rows}
    for row in rows:
        scopes = consent_state(con, authority, interview_id=str(row[7]))
        if "record" not in scopes:
            raise CorroborationConflict("record consent is not currently granted")
        if (bool(row[3]) or row[2] is not None) and "attribute" not in scopes:
            raise CorroborationConflict("attribute consent is not currently granted")
    subject_shapes = {(row[2], bool(row[3])) for row in rows}
    if len(subject_shapes) != 1:
        raise CorroborationConflict("claims with different subject identity cannot be clustered")
    canonical_text = str(by_id[canonical_claim_id][1])
    attesting = [
        by_id[member.claim_id]
        for member in normalized
        if member.stance == "attests"
    ]
    explicit_origins = {str(row[5]) for row in attesting if row[5]}
    admitted_sources = {(str(row[7]), str(row[8])) for row in attesting if row[5]}
    # Origin labels are operator assertions, not evidence by themselves. Both
    # distinct labels and distinct admitted interview-answer sources are needed.
    independent = max(1, min(len(explicit_origins), len(admitted_sources)))
    contradicted = any(member.stance == "contradicts" for member in normalized)
    label = (
        "contradicted" if contradicted
        else "multiply_attested" if independent >= 2
        else "single_sourced"
    )
    confidence = _confidence(1 if contradicted else independent)
    cluster_id = _cluster_id(authority, project_id, canonical_claim_id, normalized)
    expected = (
        project_id, authority.account_id, canonical_claim_id, canonical_text,
        label, confidence, independent,
    )
    owns_transaction = _begin_if_needed(con)
    try:
        occupied = con.execute(
            "SELECT claim_id, cluster_id FROM interview_corroboration_members_authority "
            "WHERE account_digest = ? AND claim_id IN (" + placeholders + ") "
            "AND cluster_id <> ?",
            [authority.account_digest]
            + [member.claim_id for member in normalized]
            + [cluster_id],
        ).fetchone()
        if occupied is not None:
            raise CorroborationConflict(
                f"claim {occupied[0]} is already assigned to corroboration cluster "
                f"{occupied[1]}"
            )
        existing = con.execute(
            "SELECT project_id, owner_user_id, canonical_claim_id, canonical_text, label, "
            "confidence, independent_attesters FROM "
            "interview_corroboration_clusters_authority "
            "WHERE account_digest = ? AND cluster_id = ?",
            [authority.account_digest, cluster_id],
        ).fetchone()
        if existing is None:
            con.execute(
                "INSERT INTO interview_corroboration_clusters_authority "
                "(account_digest, cluster_id, project_id, owner_user_id, canonical_claim_id, "
                "canonical_text, label, confidence, independent_attesters) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [authority.account_digest, cluster_id, *expected],
            )
            for member in normalized:
                con.execute(
                    "INSERT INTO interview_corroboration_members_authority "
                    "(account_digest, cluster_id, claim_id, stance, independence_key) "
                    "VALUES (?, ?, ?, ?, ?)",
                    [authority.account_digest, cluster_id, member.claim_id, member.stance,
                     by_id[member.claim_id][5]],
                )
        elif tuple(existing) != expected:
            raise CorroborationConflict("canonical corroboration identity conflicts")
        if label in {"multiply_attested", "contradicted"}:
            for member in normalized:
                # Contradiction is directional: the counterclaim does not become
                # contradicted merely because it disputes the canonical claim.
                if label == "contradicted" and member.stance == "contradicts":
                    continue
                if not bool(by_id[member.claim_id][4]):
                    continue
                if str(by_id[member.claim_id][6]) == "operator_attested":
                    continue
                con.execute(
                    "UPDATE interview_claims_authority SET verification = ?, confidence = ?, "
                    "updated_at = CURRENT_TIMESTAMP WHERE account_digest = ? AND claim_id = ?",
                    [label, confidence, authority.account_digest, member.claim_id],
                )
        if owns_transaction:
            con.execute("COMMIT")
    except BaseException:
        if owns_transaction:
            con.execute("ROLLBACK")
        raise
    return CanonicalCorroboration(
        cluster_id=cluster_id, project_id=project_id,
        canonical_claim_id=canonical_claim_id, canonical_text=canonical_text,
        label=label, confidence=confidence, independent_attesters=independent,
        members=normalized,
    )


__all__ = [
    "CanonicalCorroboration", "CorroborationConflict", "CorroborationMember",
    "record_corroboration",
]
