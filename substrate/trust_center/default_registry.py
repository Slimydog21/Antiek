"""Process-singleton EpsilonRegistry pre-populated with the §13.3 baseline.

The three baseline surfaces match the values that the /trust-center
endpoint hardcoded before Sprint 22:
- skill_invocation_frequency: ε = 2/day (low sensitivity)
- source_tier_preference_signals: ε = 1/day (medium, opt-in)
- query_content_telemetry: ε = 0 (forbidden — Antiek chooses no collection)

Tests call `reset_default_registry()` to get a fresh baseline.
"""

from __future__ import annotations

import threading
from typing import Optional

from substrate.dp_shuffler.epsilon_registry import (
    EpsilonRegistry,
    SurfaceConfig,
)


DEFAULT_DELETION_SLA_DAYS = 30  # per master-spec §13.3
DEFAULT_CANCELLATION_WINDOW_DAYS = 7  # per master-spec §13.3


_BASELINE_SURFACES: tuple[SurfaceConfig, ...] = (
    SurfaceConfig(
        surface_name="skill_invocation_frequency",
        epsilon_per_day=2.0,
        sensitivity="low",
        description=(
            "Which substrate skills fire and at what rate. Low sensitivity; "
            "the DP randomizer ensures no single invocation is identifying."
        ),
        opt_in_required=False,
    ),
    SurfaceConfig(
        surface_name="source_tier_preference_signals",
        epsilon_per_day=1.0,
        sensitivity="medium",
        description=(
            "Which source tiers (Tier 1 = peer-reviewed primary, "
            "Tier 5 = anonymous) you accept versus reject. The shuffled "
            "aggregate informs the dispatch router's tier hints."
        ),
        opt_in_required=True,
    ),
    SurfaceConfig(
        surface_name="query_content_telemetry",
        epsilon_per_day=0.0,
        sensitivity="forbidden",
        description=(
            "The text of your research queries and the content of your "
            "private notes. Per master-spec §13.3: NOT COLLECTED at any "
            "ε that preserves utility — Antiek chooses no collection."
        ),
        opt_in_required=False,
    ),
)


_lock = threading.Lock()
_singleton: Optional[EpsilonRegistry] = None


def _build_baseline() -> EpsilonRegistry:
    reg = EpsilonRegistry()
    for surface in _BASELINE_SURFACES:
        reg.register(surface)
    return reg


def default_registry() -> EpsilonRegistry:
    """Return the process-wide registry, building it on first call."""
    global _singleton
    with _lock:
        if _singleton is None:
            _singleton = _build_baseline()
        return _singleton


def reset_default_registry() -> EpsilonRegistry:
    """Tear down + rebuild the singleton. For tests + admin-reset.

    Production code does not call this; calling it under load drops
    any operator-registered surfaces. Callers re-register their
    surfaces after a reset."""
    global _singleton
    with _lock:
        _singleton = _build_baseline()
        return _singleton
