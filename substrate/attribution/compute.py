"""Attribution computation pipeline.

Reads a synthesis row + its thesis_components from DuckDB, resolves
chunk→document + document→source_tier, runs the three attribution
algorithms in parallel, and (optionally) emits a
``PAGE_ATTRIBUTION_COMPUTED`` event with the result.

This module is the public entry point used by the API and by Phase
2 batch jobs. Algorithm internals live in ``algorithms.py``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Mapping, Optional

import duckdb

from substrate.event_log import emit_typed
from substrate.graph import default_db_path, ensure_initialized

from .algorithms import (
    ALGORITHMS,
    AttributionClaim,
    attribution_option_a,
    attribution_option_b,
    attribution_option_c,
)


@dataclass(frozen=True)
class AttributionResult:
    """One algorithm's per-document share map.

    ``shares`` keys are ``document_id``; values are share-of-total
    (sum to 1.0 modulo float rounding). ``document_titles`` is a
    parallel map for human readability; not load-bearing."""

    algorithm: str  # "A" | "B" | "C"
    shares: Mapping[str, float]
    document_titles: Mapping[str, str]
    document_count: int
    claim_count: int


@dataclass(frozen=True)
class SynthesisAttributionResult:
    """All three algorithms' results for one synthesis."""

    synthesis_id: str
    target_question: str
    option_a: AttributionResult
    option_b: AttributionResult
    option_c: AttributionResult


def _build_claims(
    con: duckdb.DuckDBPyConnection,
    thesis_components: list[dict],
    chunk_to_doc: Mapping[str, str],
    doc_to_tier: Mapping[str, int],
) -> list[AttributionClaim]:
    """Convert the synthesizer's thesis_components into the math-side
    shape. Skip components that don't cite any chunks (analogy-only
    claims aren't attributable to documents)."""
    claims: list[AttributionClaim] = []
    for i, comp in enumerate(thesis_components):
        chunk_ids = list(comp.get("supporting_chunk_ids") or [])
        if not chunk_ids:
            continue
        claims.append(AttributionClaim(
            claim_index=i,
            chunk_ids=tuple(chunk_ids),
            confidence=comp.get("confidence", "low"),
            chunk_to_document=chunk_to_doc,
            document_to_tier=doc_to_tier,
        ))
    return claims


def compute_attribution_for_synthesis(
    synthesis_id: str,
    *,
    db_path: Optional[str] = None,
    emit_event: bool = False,
    investigation_id: Optional[str] = None,
) -> SynthesisAttributionResult:
    """Compute attribution for one archived synthesis. Returns all
    three algorithms' results.

    When ``emit_event`` is true, emits a
    ``PAGE_ATTRIBUTION_COMPUTED`` event tagged to ``investigation_id``
    (defaults to the synthesis's investigation_id). The phase-1
    pipeline uses ``emit_event=True``; ad-hoc analytic dashboards
    use ``emit_event=False`` to compute without writing to the log."""
    resolved = db_path or default_db_path()
    ensure_initialized(resolved)
    con = duckdb.connect(resolved, read_only=True)
    try:
        row = con.execute(
            "SELECT synthesis_id, target_question, thesis, investigation_id "
            "FROM syntheses WHERE synthesis_id = ?",
            [synthesis_id],
        ).fetchone()
        if row is None:
            raise ValueError(f"synthesis {synthesis_id!r} not found")
        _, target_question, thesis_json, syn_inv_id = row
        if not thesis_json:
            thesis = {}
        else:
            try:
                thesis = json.loads(thesis_json)
            except (TypeError, ValueError):
                thesis = {}
        thesis_components = thesis.get("thesis_components") or []

        all_chunk_ids: set[str] = set()
        for comp in thesis_components:
            for cid in comp.get("supporting_chunk_ids") or []:
                all_chunk_ids.add(cid)
        if all_chunk_ids:
            placeholders = ",".join("?" for _ in all_chunk_ids)
            chunk_rows = con.execute(
                f"SELECT chunk_id, document_id FROM chunks "
                f"WHERE chunk_id IN ({placeholders})",
                list(all_chunk_ids),
            ).fetchall()
        else:
            chunk_rows = []
        chunk_to_doc: dict[str, str] = {r[0]: r[1] for r in chunk_rows}

        doc_ids = set(chunk_to_doc.values())
        if doc_ids:
            placeholders = ",".join("?" for _ in doc_ids)
            doc_rows = con.execute(
                f"SELECT document_id, source_tier, title FROM documents "
                f"WHERE document_id IN ({placeholders})",
                list(doc_ids),
            ).fetchall()
        else:
            doc_rows = []
        doc_to_tier: dict[str, int] = {r[0]: int(r[1]) for r in doc_rows}
        doc_to_title: dict[str, str] = {r[0]: (r[2] or "") for r in doc_rows}
    finally:
        con.close()

    claims = _build_claims(None, thesis_components, chunk_to_doc, doc_to_tier)

    a_shares = attribution_option_a(claims)
    b_shares = attribution_option_b(claims)
    c_shares = attribution_option_c(claims)

    def _r(algo: str, shares: dict[str, float]) -> AttributionResult:
        return AttributionResult(
            algorithm=algo,
            shares=shares,
            document_titles={k: doc_to_title.get(k, "") for k in shares.keys()},
            document_count=len(shares),
            claim_count=len(claims),
        )

    result = SynthesisAttributionResult(
        synthesis_id=synthesis_id,
        target_question=target_question or "",
        option_a=_r("A", a_shares),
        option_b=_r("B", b_shares),
        option_c=_r("C", c_shares),
    )

    if emit_event:
        from substrate.schemas import PageAttributionComputedPayload
        payload = PageAttributionComputedPayload(
            synthesis_id=synthesis_id,
            algorithm_shares={
                "A": dict(a_shares),
                "B": dict(b_shares),
                "C": dict(c_shares),
            },
            claim_count=len(claims),
            document_count=max(
                len(a_shares), len(b_shares), len(c_shares),
            ),
        )
        emit_typed(
            investigation_id or syn_inv_id or "__operator__",
            payload,
            synthesis_id=synthesis_id,
            role="attribution",
            policy_id="attribution/phase1",
        )

    return result


__all__ = [
    "AttributionResult",
    "SynthesisAttributionResult",
    "compute_attribution_for_synthesis",
    "ALGORITHMS",
]
