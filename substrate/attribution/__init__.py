"""IP attribution telemetry (Sprint 16 phase 1 — master spec §9.8).

Three attribution algorithms (A: equal-split, B: confidence×tier,
C: load-bearing weighted — Option C requires an LLM pass and is
stubbed at uniform weight today). Phase 1 is telemetry-only: no
payouts, no UI changes. The event log records ``PAGE_ATTRIBUTION_COMPUTED``
per synthesis so the operator can compare the three options on real
syntheses and decide which becomes the default for Phase 2.
"""

from .algorithms import (
    ALGORITHMS,
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

__all__ = [
    "ALGORITHMS",
    "CONFIDENCE_WEIGHTS",
    "AttributionClaim",
    "AttributionResult",
    "SynthesisAttributionResult",
    "attribution_option_a",
    "attribution_option_b",
    "attribution_option_c",
    "compute_attribution_for_synthesis",
]
