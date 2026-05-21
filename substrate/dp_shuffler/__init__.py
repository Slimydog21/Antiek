"""Differential privacy shuffler substrate plumbing (master-spec §13.3).

Sprint 19+ substrate plumbing; dashboard UI deferred to Sprint 22+ per
§13.10. The shuffler model (local randomization on-device + third-party
shuffler stripping identifiers before aggregation) is the
architecturally correct pattern. Local-DP alone requires materially
higher ε to achieve same utility because each user contributes only
one noisy sample.

Per-surface ε budgets per master-spec §13.3 (and Apple's deployed
parameters as reference):
- Skill-invocation frequency: ε = 2/day (low sensitivity)
- Source-tier preference signals: ε = 1/day (medium, opt-in)
- Query-content telemetry: do NOT collect under DP at any ε that
  preserves utility — E2E encryption with no learning, or no
  collection.

The expert consensus band from §13.3:
- ε < 1: strong privacy
- ε ∈ [1, 10]: various degrees of better than nothing
- ε > 10: not a meaningful privacy guarantee in itself

The substrate MUST refuse to register a surface with ε > 10 per the
§16.2 REJECT list ("No epsilon > 10 on any DP claim").
"""

from .epsilon_registry import (
    EpsilonRegistry,
    EpsilonRegistryError,
    SurfaceConfig,
    register_surface,
)
from .shuffler import (
    LocalRandomizer,
    NoisyAggregate,
    ShufflerError,
    aggregate_with_dp,
    randomized_response,
)

__all__ = [
    "EpsilonRegistry",
    "EpsilonRegistryError",
    "LocalRandomizer",
    "NoisyAggregate",
    "ShufflerError",
    "SurfaceConfig",
    "aggregate_with_dp",
    "randomized_response",
    "register_surface",
]
