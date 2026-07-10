"""Characterization + target tests for the §9.3 attribution divergence (AFA-S3-M2/M3).

Ratified by PR #203 (`docs/decisions/afa-synthesis-attribution-canonical.md`, merged
2026-07-05): Antiek has TWO live implementations of the master-spec §9.3 A/B/C math —

  * System 1 — ``substrate/attribution/algorithms.py`` — CLAIM-based: iterates
    ``list[AttributionClaim]``; a chunk cited by N thesis-components is counted N times
    (per-citation multiplicity). Behind the synthesis display path (``compute.py``).
  * System 2 — ``substrate/ad_inventory/attribution.py`` — CHUNK-based: iterates a flat
    ``chunk_to_document`` map; each distinct chunk counts once. Behind the Speak contributor
    split, ``/attribution/compute``, and the durable audit store (``record_attribution``).

Writing the tests forced a precision the decision doc's one-line "unify the math" glossed:
**the divergence has TWO independent causes, closed by two different fixes.**

  (A) MATH-MODULE divergence — two copies of the reduction that can drift: Option B's
      tier clamp (``max(1, 6-tier)`` vs unclamped, bites only at tier >=6, latent) and the
      confidence representation (string ``CONFIDENCE_WEIGHTS`` bucket vs per-chunk float).
      Closed by AFA-S3-M2: make ``algorithms.py`` the single implementation and have
      ``ad_inventory`` delegate to it. NOTE Option A carries NO math-module divergence —
      given equivalent input the two Option-A reductions already agree (pinned below).

  (B) INPUT-SHAPE divergence — System 2's flat ``chunk_to_document`` structurally cannot
      express "chunk cX cited by 2 components", so it loses per-citation multiplicity
      BEFORE any math runs. The doc's headline Option-A example (chunk cited 3x -> +3 vs
      +1) is THIS, not a math-module bug. Math-unification does NOT close it — only the
      caller change does: the synthesis->durable-store path (AFA-S3-M3/M4) must pass claim
      structure (or persist ``compute.py``'s already-claim-based result) instead of
      rebuilding a flat map. Pinned as xfail(strict) below so it flips loudly when M3 lands.

Run (worktree recipe, shared venv):
    PYTHONPATH=<this-worktree> /Users/slimydog/Antiek/platform/.venv/bin/python \
        -m pytest tests/test_attribution_math_unification.py -q
"""

from __future__ import annotations

import pytest

from substrate.attribution.algorithms import (
    AttributionClaim,
    attribution_option_a as claim_option_a,
)
from substrate.ad_inventory.attribution import (
    compute_attribution_option_a as chunk_option_a,
)

# tier is irrelevant to Option A (equal-split); a constant map keeps the fixture honest.
_TIER = {"D1": 1, "D2": 1}


def _singleton_claims(chunk_to_doc: dict[str, str]) -> list[AttributionClaim]:
    """Wrap each distinct chunk as its own singleton-chunk claim — the shape a chunk-based
    caller (Speak: ``chunk_to_document[claim_id] = doc``) maps onto. This is the adapter
    the M2 delegation will use, so pinning its behavior now specifies that delegation."""
    return [
        AttributionClaim(
            claim_index=i, chunk_ids=(cid,), confidence="high",
            chunk_to_document=chunk_to_doc, document_to_tier=_TIER,
        )
        for i, cid in enumerate(chunk_to_doc)
    ]


def test_speak_domain_payouts_unchanged() -> None:
    """PAYOUT-SAFETY INVARIANT (must stay green through the unification). Speak's 1:1
    claim<->chunk domain has no multiplicity, so the two systems already agree. Whatever
    M2 delegation lands must NOT move these numbers — if this goes red, Speak contributor
    payouts shifted; stop and reconsider."""
    chunk_to_doc = {"a1": "D1", "a2": "D2"}
    chunk_shares = chunk_option_a(page_id="p", chunk_to_document=chunk_to_doc).shares
    claim_shares = claim_option_a(_singleton_claims(chunk_to_doc))
    assert chunk_shares == pytest.approx({"D1": 0.5, "D2": 0.5})
    assert claim_shares == pytest.approx(chunk_shares)


def test_option_a_math_agrees_on_equivalent_input() -> None:
    """MATH-MODULE PIN (cause A). Given the SAME facts — each chunk once — the claim-based
    and chunk-based Option-A reductions already produce identical splits, including on an
    uneven fixture (D1 has two distinct chunks, D2 one). This proves Option A has no
    math-module divergence to unify: its only divergence is input-shape (cause B, below).
    The M2 delegation must preserve this equality."""
    chunk_to_doc = {"cX": "D1", "cW": "D1", "cY": "D2"}  # D1: 2 chunks, D2: 1
    chunk_shares = chunk_option_a(page_id="p", chunk_to_document=chunk_to_doc).shares
    claim_shares = claim_option_a(_singleton_claims(chunk_to_doc))
    assert chunk_shares == pytest.approx({"D1": 2 / 3, "D2": 1 / 3})
    assert claim_shares == pytest.approx(chunk_shares)


@pytest.mark.xfail(
    strict=True,
    reason="AFA-S3-M3 not yet built: the synthesis->durable path still passes a flat "
    "chunk map, losing per-citation multiplicity. When it passes claim structure (or "
    "persists compute.py's result), this XPASSES — drop the xfail and assert equality. "
    "NOTE: the M2 math merge alone does NOT flip this; it is the caller-contract fix.",
)
def test_synthesis_multiplicity_preserved_end_to_end() -> None:
    """INPUT-SHAPE divergence (cause B) — the live gap the decision doc names. A synthesis
    where chunk ``cX`` (-> D1) grounds TWO thesis-components and ``cY`` (-> D2) grounds one:

      * System 1, fed the real claim structure: D1 counted per citation -> 2, D2 -> 1,
        so D1 = 2/3.
      * System 2, fed the flat ``chunk_to_document`` that same synthesis collapses to
        (``cX`` appears ONCE): D1 = 1/2.

    They disagree today because the flat shape dropped cX's second citation before the
    math ran. Closed when the synthesis->durable path preserves claim structure (M3)."""
    chunk_to_doc = {"cX": "D1", "cY": "D2"}

    # System 1 — real synthesis claims: cX grounds claim0 AND claim1.
    claims = [
        AttributionClaim(claim_index=0, chunk_ids=("cX",), confidence="high",
                         chunk_to_document=chunk_to_doc, document_to_tier=_TIER),
        AttributionClaim(claim_index=1, chunk_ids=("cX",), confidence="high",
                         chunk_to_document=chunk_to_doc, document_to_tier=_TIER),
        AttributionClaim(claim_index=2, chunk_ids=("cY",), confidence="high",
                         chunk_to_document=chunk_to_doc, document_to_tier=_TIER),
    ]
    claim_shares = claim_option_a(claims)  # {D1: 2/3, D2: 1/3}

    # System 2 — the flat map the durable store receives today (cX once).
    chunk_shares = chunk_option_a(page_id="p", chunk_to_document=chunk_to_doc).shares

    assert claim_shares == pytest.approx(chunk_shares)
