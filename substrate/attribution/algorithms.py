"""Attribution algorithm implementations (Sprint 16 phase 1).

Three options from the master spec §9.3:

- **A — equal split per chunk citation**. Each chunk citation
  contributes 1 unit. Document's share is its chunks' citations /
  total citations.

- **B — confidence × source-tier weighted**. Each chunk's contribution
  is ``claim_confidence_weight * (6 - source_tier)``. Higher-confidence
  claims grounded in higher-tier sources contribute more.

- **C — load-bearing weighted (deferred)**. Requires an LLM pass
  per claim ("if this claim were removed, would the thesis change?").
  Phase 2 work. Stubbed here so the API surface is stable.

All three return ``Mapping[document_id, float]`` with shares summing
to 1.0 (subject to floating-point rounding). Documents with zero
citations are excluded from the result.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

# Map ConfidenceLevel ("very_high" / "high" / "low" / "very_low") to a
# numeric weight for the math. The synthesizer's 4-value scale (not
# the parameter_extractor's). Values picked to spread enough that
# very_high outranks very_low ~4x.
CONFIDENCE_WEIGHTS: dict[str, float] = {
    "very_high": 1.0,
    "high": 0.75,
    "low": 0.4,
    "very_low": 0.2,
}


@dataclass(frozen=True)
class AttributionClaim:
    """One claim from a thesis ready for attribution math.

    ``chunk_to_document`` maps each cited chunk to its origin document
    so the algorithms don't need to re-query DuckDB per chunk.
    """

    claim_index: int
    chunk_ids: tuple[str, ...]
    confidence: str  # "very_high" / "high" / "low" / "very_low"
    chunk_to_document: Mapping[str, str]
    document_to_tier: Mapping[str, int]  # 1..5
    load_bearing_weight: float = 1.0  # used by Option C only


def _normalize(shares: Mapping[str, float]) -> dict[str, float]:
    """Scale so shares sum to 1.0. Empty input → empty output."""
    total = sum(shares.values())
    if total <= 0:
        return {}
    return {k: v / total for k, v in shares.items()}


def attribution_option_a(
    claims: Iterable[AttributionClaim],
) -> dict[str, float]:
    """Equal-split-per-chunk-citation.

    Each chunk citation contributes exactly one unit, regardless of
    confidence or tier. A document with three cited chunks gets three
    units; a document with one cited chunk gets one. The result is
    the per-document share of all citations on the page."""
    raw: dict[str, float] = defaultdict(float)
    for claim in claims:
        for chunk_id in claim.chunk_ids:
            doc_id = claim.chunk_to_document.get(chunk_id)
            if not doc_id:
                continue
            raw[doc_id] += 1.0
    return _normalize(raw)


def attribution_option_b(
    claims: Iterable[AttributionClaim],
) -> dict[str, float]:
    """Confidence × source-tier weighted.

    Each chunk citation contributes
    ``confidence_weight * (6 - source_tier)``. ``source_tier`` is the
    document's tier (1 = primary / authoritative, 5 = unsupported).
    Higher tiers contribute less; very-high-confidence claims with
    tier-1 sources contribute most."""
    raw: dict[str, float] = defaultdict(float)
    for claim in claims:
        cw = CONFIDENCE_WEIGHTS.get(claim.confidence, 0.4)
        for chunk_id in claim.chunk_ids:
            doc_id = claim.chunk_to_document.get(chunk_id)
            if not doc_id:
                continue
            tier = claim.document_to_tier.get(doc_id, 5)
            tier_factor = max(1, 6 - int(tier))
            raw[doc_id] += cw * tier_factor
    return _normalize(raw)


def attribution_option_c(
    claims: Iterable[AttributionClaim],
) -> dict[str, float]:
    """Load-bearing-ness weighted.

    Each chunk citation contributes ``confidence_weight * (6 -
    source_tier) * load_bearing_weight``. The load_bearing_weight is
    set externally by an LLM pass (Phase 2 work). When all claims
    have ``load_bearing_weight=1.0`` (the default), this reduces to
    Option B."""
    raw: dict[str, float] = defaultdict(float)
    for claim in claims:
        cw = CONFIDENCE_WEIGHTS.get(claim.confidence, 0.4)
        for chunk_id in claim.chunk_ids:
            doc_id = claim.chunk_to_document.get(chunk_id)
            if not doc_id:
                continue
            tier = claim.document_to_tier.get(doc_id, 5)
            tier_factor = max(1, 6 - int(tier))
            raw[doc_id] += cw * tier_factor * claim.load_bearing_weight
    return _normalize(raw)


ALGORITHMS = {
    "A": attribution_option_a,
    "B": attribution_option_b,
    "C": attribution_option_c,
}
