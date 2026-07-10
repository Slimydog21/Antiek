"""Per-source earn split for a synthesis ad-asset (AFA-S3-M3, money-math core).

When the per-frame pipeline attributes ad cents to a *synthesis* asset (a composed
research page grounded in many source documents), those cents must be split across the
**source documents' IP holders** — the drivers of the content value — not paid to "the
synthesis", which owns nothing. This module is that split, isolated as a **pure function**
(no DB, no escrow write) so the money-math can be exhaustively tested on its own and a
future maintainer can read every cent's path. The DB resolution (synthesis_id → claims +
provenance) and the escrow write live elsewhere; this function only decides the split.

Three invariants it exists to hold — each load-bearing, none removable without loss:

1. **Per-citation multiplicity is preserved (closes AFA divergence Cause B).** It consumes
   the CLAIM-based §9.3 math (``substrate/attribution/algorithms.py``), so a source that
   grounds three thesis-components earns three citations' weight — not one. A flat
   chunk→document map would silently collapse that to one (the input-shape bug the
   decision doc names); taking claims structurally prevents it.

2. **The EARN gate — NOT the display gate (closes the §9.10 trap from PR #203).** The
   synthesis *display* attribution (``compute.py``) drops BOTH ``personal_reading`` and
   ``restricted_pending_opt_in``. The *earn* path must drop only ``personal_reading``
   (earns nothing, ever) and **retain** ``restricted_pending_opt_in`` — a gated-but-public
   work that DOES accrue to its pre-onboarded holder's escrow (master-spec §9.10). Reusing
   the display gate here would zero escrow for exactly the rights holders §9.10 serves.
   The gate is derived from the same ``retrieval_gate`` constants as every other surface,
   so it cannot drift from them.

3. **Conservation to the cent.** The sum of the per-source cents equals the input cents
   (via ``apportion_cents``, the shared largest-remainder primitive) — no cent minted, no
   cent lost in the recursion. A fully-gated synthesis (every source ``personal_reading``,
   or no attributable claim) yields an empty split; the caller routes the un-splittable
   remainder to the house rather than inventing an owner (honest zero).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from substrate.attribution.algorithms import (
    ALGORITHMS,
    AttributionClaim,
)
from substrate.graph.retrieval_gate import PERSONAL_ONLY_CONTENT_CLASSES

from .frame_attention import apportion_cents

# The EARN exclusion is PERSONAL_ONLY only — the deliberate mirror of the display gate.
# `restricted_pending_opt_in` is INTENTIONALLY absent: it earns to escrow (§9.10). Sourced
# from retrieval_gate so it tracks the canonical vocabulary and cannot drift.
EARN_EXCLUDED_CONTENT_CLASSES = PERSONAL_ONLY_CONTENT_CLASSES


@dataclass(frozen=True)
class SourceEarnLine:
    """One source document's slice of a synthesis asset's ad cents.

    ``ip_holder_id`` is ``None`` when the source document has no resolved owner — an honest
    "unknown owner" the caller must NOT accrue to escrow (it becomes house revenue), never
    an invented holder. ``share`` is the pre-rounding attribution weight (for audit);
    ``cents`` is the conserved integer payout."""

    document_id: str
    ip_holder_id: str | None
    share: float
    cents: int


def earn_split_for_synthesis(
    *,
    claims: list[AttributionClaim],
    doc_to_content_class: Mapping[str, str | None],
    doc_to_ip_holder: Mapping[str, str | None],
    total_cents: int,
    algorithm: str = "B",
) -> list[SourceEarnLine]:
    """Split ``total_cents`` across a synthesis's source documents by earn-gated §9.3
    attribution. Pure: no DB, no escrow write.

    Args:
        claims: the synthesis's thesis-components as ``AttributionClaim``s (claim-based, so
            per-citation multiplicity is preserved). Each carries its ``chunk_to_document``
            and ``document_to_tier`` maps, as ``compute.py`` builds them.
        doc_to_content_class: document_id → content_class, for the earn gate.
        doc_to_ip_holder: document_id → ip_holder_id (or None for unowned).
        total_cents: the synthesis asset's ad cents to split (non-negative).
        algorithm: "A" | "B" | "C" — the §9.3 option (default "B", the payout default).

    Returns:
        One ``SourceEarnLine`` per source document that survives the earn gate and receives
        a positive attribution share, sorted by document_id for deterministic output. A
        line with ``share > 0`` may still round to ``cents == 0`` in a small window (e.g.
        1 cent split three ways → 1/0/0); that is honest largest-remainder rounding, and
        the escrow caller skips 0-cent lines. Empty when nothing is attributable (no
        surviving source, or ``total_cents == 0``) — the caller routes the remainder to
        the house rather than inventing an owner.

    Raises:
        ValueError: on a negative ``total_cents`` or an unknown ``algorithm`` — a payout
            must never silently proceed on a malformed input.
    """
    if total_cents < 0:
        raise ValueError(f"total_cents must be non-negative, got {total_cents}")
    algo = ALGORITHMS.get(algorithm)
    if algo is None:
        raise ValueError(
            f"unknown algorithm {algorithm!r}; expected one of {sorted(ALGORITHMS)}"
        )

    # EARN gate: drop personal_reading source documents (they never earn), RETAIN
    # restricted_pending_opt_in (it earns to escrow, §9.10). Rebuild each claim over the
    # gated chunk→document map so an excluded document contributes zero citations — never
    # a zero-weighted-but-present ghost that would distort normalization.
    excluded_docs = {
        d for d, cc in doc_to_content_class.items()
        if cc in EARN_EXCLUDED_CONTENT_CLASSES
    }
    if excluded_docs:
        gated_claims: list[AttributionClaim] = []
        for c in claims:
            gated_c2d = {
                cid: d for cid, d in c.chunk_to_document.items()
                if d not in excluded_docs
            }
            gated_claims.append(
                AttributionClaim(
                    claim_index=c.claim_index,
                    chunk_ids=c.chunk_ids,
                    confidence=c.confidence,
                    chunk_to_document=gated_c2d,
                    document_to_tier=c.document_to_tier,
                    load_bearing_weight=c.load_bearing_weight,
                )
            )
        claims = gated_claims

    shares = algo(claims)  # document_id → share in [0, 1], summing to ~1.0 (or empty)
    if not shares or total_cents == 0:
        return []

    cents_by_doc = apportion_cents(shares, total_cents)
    lines = [
        SourceEarnLine(
            document_id=doc_id,
            ip_holder_id=doc_to_ip_holder.get(doc_id),
            share=shares[doc_id],
            cents=cents_by_doc.get(doc_id, 0),
        )
        for doc_id in sorted(shares)
    ]
    # Conservation guard (defensive, hard-to-vary). We have already excluded the empty-
    # shares and zero-cents cases above, so ``apportion_cents`` MUST have distributed every
    # cent across these documents. This asserts that no cent was minted or lost — catching,
    # loudly, any future change that lets an unnormalized (e.g. all-zero) weight vector reach
    # the largest-remainder primitive, whose degenerate branch silently returns all-zeros.
    distributed = sum(ln.cents for ln in lines)
    if distributed != total_cents:  # pragma: no cover - guards an invariant, never hit today
        raise AssertionError(
            f"earn split did not conserve: distributed {distributed} of {total_cents} cents "
            f"across {len(lines)} sources (shares summed to {sum(shares.values()):.6f})"
        )
    return lines


def resolve_and_split_synthesis_earn(
    synthesis_id: str,
    total_cents: int,
    *,
    db_path: str | None = None,
    algorithm: str = "B",
) -> list[SourceEarnLine]:
    """DB-backed entry point: resolve a synthesis's provenance and split ``total_cents``
    across its source documents' IP holders by earn-gated §9.3 attribution.

    Reuses ``compute.py``'s ``_resolve_synthesis_provenance`` — the SAME provenance
    resolution the display attribution uses — so the earn and display surfaces cannot
    drift on how they read the chunk→document→ip_holder chain; they differ only on the
    gate (this path applies the §9.10 earn gate inside :func:`earn_split_for_synthesis`,
    retaining ``restricted_pending_opt_in``; the display path drops it). Read-only; writes
    no escrow — the caller accrues each returned line.

    Raises ``ValueError`` if the synthesis does not exist (propagated from the resolver),
    or on a malformed ``total_cents`` / ``algorithm`` (from the pure split)."""
    # Imported lazily: the ad_inventory package must not hard-depend on the attribution
    # package at import time (keeps the module graph acyclic; the coupling is a runtime
    # provenance read, not a structural dependency).
    from substrate.attribution.compute import (
        _build_claims,
        _resolve_synthesis_provenance,
    )

    prov = _resolve_synthesis_provenance(synthesis_id, db_path=db_path)
    claims = _build_claims(prov.thesis_components, prov.chunk_to_doc, prov.doc_to_tier)
    return earn_split_for_synthesis(
        claims=claims,
        doc_to_content_class=prov.doc_to_content_class,
        doc_to_ip_holder=prov.doc_to_ip_holder,
        total_cents=total_cents,
        algorithm=algorithm,
    )


__all__ = [
    "EARN_EXCLUDED_CONTENT_CLASSES",
    "SourceEarnLine",
    "earn_split_for_synthesis",
    "resolve_and_split_synthesis_earn",
]
