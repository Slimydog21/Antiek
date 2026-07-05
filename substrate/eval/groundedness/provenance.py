"""Read claim→chunk provenance from the EXISTING store — never a parallel one.

The claim→chunk links already exist: every load-bearing claim is a
``ThesisComponent`` whose ``supporting_chunk_ids`` cite the chunks it
rests on (``substrate/schemas/events.py``). The chunk TEXT lives in the
substrate ``chunks`` table (``runtime/db_lock.connect_read`` →
``SELECT text FROM chunks``). This module joins the two so the scorer
gets ``(claim, cited_chunk_ids, chunk_texts)`` tuples without inventing a
second provenance store (Rigor card 4: use the existing provenance).

Two resolution paths, both read-only:

- ``resolve_synthesis_claims(payload, chunk_text_for)`` — given a
  ``SynthesizeDeliveredPayload`` and a chunk-text resolver, build the
  scorer's input. The resolver is injected so the OFFLINE harness can
  resolve from a chunk-text map carried IN the trace fixture (no live DB
  needed), while the live path resolves from the DB.
- ``duckdb_chunk_text_resolver(db_path)`` — the live resolver: one
  read-only query over the existing ``chunks`` table.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

# (claim, cited_chunk_ids, chunk_texts)
ClaimChunks = tuple[str, list[str], list[str]]

# A chunk-text resolver maps a chunk_id to its text (or None if unknown).
ChunkTextResolver = Callable[[str], str | None]


def _components(payload: Any) -> list[Any]:
    return list(getattr(payload, "thesis_components", None) or [])


def resolve_synthesis_claims(
    payload: Any,
    chunk_text_for: ChunkTextResolver,
) -> list[ClaimChunks]:
    """Project a synthesis payload + a chunk-text resolver into the
    scorer's ``(claim, cited_chunk_ids, chunk_texts)`` input.

    Reads the EXISTING claim→chunk links off each ThesisComponent's
    ``supporting_chunk_ids``. A chunk_id the resolver can't resolve is
    dropped from ``chunk_texts`` (but kept in ``cited_chunk_ids`` so the
    verdict records what was cited) — an unresolvable citation makes the
    claim *less* grounded, which is the honest behaviour."""
    out: list[ClaimChunks] = []
    for comp in _components(payload):
        claim = getattr(comp, "claim", None)
        if not isinstance(claim, str):
            continue
        chunk_ids = [
            str(cid) for cid in (getattr(comp, "supporting_chunk_ids", None) or [])
        ]
        texts: list[str] = []
        for cid in chunk_ids:
            t = chunk_text_for(cid)
            if t:
                texts.append(t)
        out.append((claim, chunk_ids, texts))
    return out


def mapping_chunk_text_resolver(chunk_texts: Mapping[str, str]) -> ChunkTextResolver:
    """Resolver backed by an in-memory map. Used by the OFFLINE harness
    when the trace fixture carries the chunk text inline (so the eval is
    truly offline — no live DB required)."""

    def _resolve(chunk_id: str) -> str | None:
        return chunk_texts.get(chunk_id)

    return _resolve


def duckdb_chunk_text_resolver(
    db_path: str,
    *,
    chunk_ids: Sequence[str] | None = None,
) -> ChunkTextResolver:
    """Live resolver: read chunk text from the EXISTING ``chunks`` table
    through the read-only connection funnel (``runtime/db_lock``). Loads
    the requested chunk_ids once into a dict so per-claim resolution is
    O(1) and the DB connection is short-lived (read-only — safe alongside
    the single writer)."""
    import os

    from runtime.db_lock import connect_read

    resolved: dict[str, str] = {}
    path = os.path.expanduser(db_path)
    con = connect_read(path)
    try:
        if chunk_ids:
            ids = list({str(c) for c in chunk_ids})
            placeholders = ",".join("?" for _ in ids)
            rows = con.execute(
                f"SELECT chunk_id, text FROM chunks WHERE chunk_id IN ({placeholders})",
                ids,
            ).fetchall()
        else:
            rows = con.execute("SELECT chunk_id, text FROM chunks").fetchall()
        for chunk_id, text in rows:
            if text is not None:
                resolved[str(chunk_id)] = str(text)
    finally:
        con.close()

    def _resolve(chunk_id: str) -> str | None:
        return resolved.get(chunk_id)

    return _resolve


# ---------------------------------------------------------------------------
# SPR-03: semantic-support audit (not id-presence).
# ---------------------------------------------------------------------------


# The three support verdicts, kept distinct so a maintainer can tell a data
# error from a groundedness failure (rigor #5 of the SPR-03 spec — collapsing
# them would hide which problem is happening and send a debugger down the
# wrong path). ``str`` mixin so JSON/event serialization compares directly.
SUPPORTED = "supported"
UNRESOLVED_ID = "unresolved_id"  # a cited chunk_id that resolves to no text — a DATA error (fix the resolver/store)
RESOLVED_BUT_UNSUPPORTED = "resolved_but_unsupported"  # the chunk text loaded but does NOT entail the claim — a GROUNDEDNESS failure (the model hallucinated)


class ClaimSupportVerdict:
    """One claim's support verdict. Kept as a small class (not a tuple) so
    the field names are self-documenting in events/audit output.

    Attributes:
        claim: the assertion text.
        cited_chunk_ids: every id the claim cited (incl. unresolved ones).
        unresolved_ids: the subset that resolved to NO text — a data
            problem (the resolver returned None / the id isn't in the store).
        resolved_texts: the chunk texts that DID resolve.
        score: the entailment score over the resolved texts (None if no
            text resolved — an honest unknown, not 0.0).
        supported: True iff the score cleared the supported_threshold.
        verdict: SUPPORTED | UNRESOLVED_ID | RESOLVED_BUT_UNSUPPORTED.
            UNRESOLVED_ID takes precedence (a data error is the more
            actionable signal — fix it first, then re-judge groundedness).
    """

    __slots__ = (
        "claim", "cited_chunk_ids", "unresolved_ids", "resolved_texts",
        "score", "supported", "verdict",
    )

    def __init__(
        self,
        *,
        claim: str,
        cited_chunk_ids: list[str],
        unresolved_ids: list[str],
        resolved_texts: list[str],
        score: float | None,
        supported: bool,
        verdict: str,
    ) -> None:
        self.claim = claim
        self.cited_chunk_ids = cited_chunk_ids
        self.unresolved_ids = unresolved_ids
        self.resolved_texts = resolved_texts
        self.score = score
        self.supported = supported
        self.verdict = verdict

    def as_dict(self) -> dict[str, Any]:
        return {
            "claim": self.claim,
            "cited_chunk_ids": list(self.cited_chunk_ids),
            "unresolved_ids": list(self.unresolved_ids),
            "resolved_text_count": len(self.resolved_texts),
            "score": self.score,
            "supported": self.supported,
            "verdict": self.verdict,
        }


def audit_claim_support(
    payload: Any,
    chunk_text_for: ChunkTextResolver,
    *,
    backend: Any | None = None,
    threshold: float | None = None,
) -> list[ClaimSupportVerdict]:
    """Audit each claim's SEMANTIC support against its cited chunks —
    distinct from id-resolution. This is the SPR-03 close of the
    write-time provenance gap: a claim whose ``supporting_chunk_ids``
    RESOLVE but whose chunk texts do not ENTAIL the claim is the exact
    "densely-cited hallucination" failure the substrate-as-source-of-truth
    invariant must catch — and it is invisible to presence-only checks.

    Three verdicts per claim (rigor #5 — keep them distinct):

    - ``UNRESOLVED_ID``: ≥1 cited id resolved to no text. A DATA error
      (the id isn't in the store / the resolver failed). Fix the resolver,
      not the model. Score is None (an honest unknown, not 0.0).
    - ``RESOLVED_BUT_UNSUPPORTED``: all cited ids resolved, but the
      entailment score is below threshold. A GROUNDEDNESS failure (the
      model hallucinated against real evidence). The SPR-02 backend
      catches this where lexical overlap can't.
    - ``SUPPORTED``: all ids resolved AND the score cleared threshold.

    ``backend`` defaults to SPR-02's NLI backend when available (the
    validated signal); falls back to lexical only if NLI is unavailable
    (and the caller opts in by passing lexical explicitly — enforcing on
    lexical silently is a non-goal). ``threshold`` defaults to
    ``DEFAULT_SUPPORTED_THRESHOLD`` (the same one the scorer + harness
    use — rigor #4: no parallel threshold)."""
    from substrate.eval.groundedness.scorer import (
        DEFAULT_SUPPORTED_THRESHOLD,
        score_claim,
    )

    if threshold is None:
        threshold = DEFAULT_SUPPORTED_THRESHOLD
    if backend is None:
        backend = _default_audit_backend()

    out: list[ClaimSupportVerdict] = []
    for claim_text, cited_ids, chunk_texts in resolve_synthesis_claims(
        payload, chunk_text_for
    ):
        # The id-resolution axis: re-derive which cited ids resolved to text.
        unresolved = [
            cid for cid in cited_ids
            if not (chunk_text_for(cid) or "").strip()
        ]
        if unresolved:
            # A data error takes precedence — fix the resolver first, then
            # re-judge groundedness. Scoring a claim with missing evidence
            # would conflate "we lost the chunk" with "the model lied".
            out.append(ClaimSupportVerdict(
                claim=claim_text,
                cited_chunk_ids=list(cited_ids),
                unresolved_ids=unresolved,
                resolved_texts=list(chunk_texts),
                score=None,
                supported=False,
                verdict=UNRESOLVED_ID,
            ))
            continue
        # All ids resolved — score semantic support.
        verdict = score_claim(
            claim_text, chunk_texts, cited_chunk_ids=cited_ids, backend=backend
        )
        out.append(ClaimSupportVerdict(
            claim=claim_text,
            cited_chunk_ids=list(cited_ids),
            unresolved_ids=[],
            resolved_texts=list(chunk_texts),
            score=verdict.score,
            supported=verdict.supported,
            verdict=SUPPORTED if verdict.supported else RESOLVED_BUT_UNSUPPORTED,
        ))
    return out


def _default_audit_backend() -> Any:
    """The default backend for the support audit: SPR-02's NLI when
    available (the validated signal), else lexical. The fallback to
    lexical is honest (the audit still runs) but a caller that needs the
    gate-grade signal should pass the NLI backend explicitly — lexical
    misses the densely-cited class the audit exists to catch."""
    try:
        from substrate.eval.groundedness.nli_backend import nli_entailment_score
        # Probe availability (raises NLIModelUnavailable if not cached).
        nli_entailment_score("probe", ["probe text"])
        return nli_entailment_score
    except Exception:
        from substrate.eval.groundedness.scorer import lexical_entailment_score
        return lexical_entailment_score

