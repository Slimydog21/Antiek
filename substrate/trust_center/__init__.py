"""Trust Center publication backend (Sprint 22 §13.7 surface).

The `/trust-center` API endpoint should pull its DP epsilon budgets
from the live EpsilonRegistry rather than hardcoding three surfaces.
The React PrivacyDashboard documents this contract explicitly:
"any future telemetry surface that registers with the EpsilonRegistry
appears here automatically." This module makes that contract real.

Exports:
- default_registry() — memoized process-singleton EpsilonRegistry
  pre-populated with the three baseline surfaces (skill-invocation,
  source-tier, query-content). Other substrate modules call
  `default_registry().register(...)` and their surfaces appear in
  /trust-center on the next request.
- build_publication() — assembles the full TrustCenterPublication
  payload: DP budgets from the registry, deletion SLA from §13.3,
  substrate controls + compliance frameworks from §13.7 + §16.2.
"""

from .default_registry import (
    DEFAULT_CANCELLATION_WINDOW_DAYS,
    DEFAULT_DELETION_SLA_DAYS,
    default_registry,
    reset_default_registry,
)
from .publication import (
    TrustCenterPayload,
    build_publication,
    list_surface_descriptions,
)

__all__ = [
    "DEFAULT_CANCELLATION_WINDOW_DAYS",
    "DEFAULT_DELETION_SLA_DAYS",
    "TrustCenterPayload",
    "build_publication",
    "default_registry",
    "list_surface_descriptions",
    "reset_default_registry",
]
