"""IP attribution telemetry (Sprint 16 phase 1 — master spec §9.8).

Three attribution algorithms (A: equal-split, B: confidence×tier,
C: load-bearing weighted — Option C requires an LLM pass and is
stubbed at uniform weight today). Phase 1 is telemetry-only: no
payouts, no UI changes. The event log records ``PAGE_ATTRIBUTION_COMPUTED``
per synthesis so the operator can compare the three options on real
syntheses and decide which becomes the default for Phase 2.

``recursion`` adds the layer above: one metered attention-second on a
synthesis splits across the ``ip_holder_id`` of every document it sourced
plus its author, with an explicit unattributed remainder, capped depth and
integer conservation. Still telemetry — §9.0 is open and nothing here
moves money.
"""

from .algorithms import (
    ALGORITHMS,
    ATTRIBUTION_SHARE_MATH_VERSION,
    CONFIDENCE_WEIGHTS,
    AttributionClaim,
    attribution_option_a,
    attribution_option_b,
    attribution_option_c,
)
from .compute import (
    AttributionResult,
    SynthesisAttributionResult,
    compute_attribution_for_synthesis,
)
from .recursion import (
    ATTRIBUTION_RECURSION_VERSION,
    AUTHOR_SHARE_FIXED,
    AUTHOR_SHARE_POLICY,
    MAX_RECURSION_DEPTH,
    UNITS_PER_ATTENTION_SECOND,
    AttributionShare,
    DisplayGatedProvenanceResolver,
    StaticProvenanceResolver,
    SynthesisAttributionSplit,
    SynthesisProvenance,
    compute_recursive_attribution,
    replay,
    split_attention,
)

__all__ = [
    "ALGORITHMS",
    "ATTRIBUTION_RECURSION_VERSION",
    "ATTRIBUTION_SHARE_MATH_VERSION",
    "AUTHOR_SHARE_FIXED",
    "AUTHOR_SHARE_POLICY",
    "CONFIDENCE_WEIGHTS",
    "MAX_RECURSION_DEPTH",
    "UNITS_PER_ATTENTION_SECOND",
    "AttributionClaim",
    "AttributionResult",
    "AttributionShare",
    "DisplayGatedProvenanceResolver",
    "StaticProvenanceResolver",
    "SynthesisAttributionResult",
    "SynthesisAttributionSplit",
    "SynthesisProvenance",
    "attribution_option_a",
    "attribution_option_b",
    "attribution_option_c",
    "compute_attribution_for_synthesis",
    "compute_recursive_attribution",
    "replay",
    "split_attention",
]
