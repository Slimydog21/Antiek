"""Production routing for the DP shuffler (§13.3 + §13.7).

Pre-registers the canonical telemetry surfaces with their ε budgets
and provides ``record_telemetry`` — the single entry point that
collection sites call. Each call:

1. Validates the surface is registered (refuse if not).
2. Enforces opt-in if the surface requires it.
3. Runs randomized response at the surface's ε.
4. Emits ``dp.routed`` to the trajectory with the noisy result.

The aggregator downstream reads the ``dp.routed`` stream and
debiases via the recorded ε. No surface, no collection — the
substrate refuses to route through an unregistered surface, so a
new collection point that forgets to register fails at the API
boundary rather than leaking unmetered data.

Canonical surfaces per master-spec §13.3:

- ``skill_invocation_frequency`` — ε=2/day, low sensitivity.
  Per-skill counts of how often the operator invokes a particular
  skill. Aggregated daily.
- ``source_tier_preference`` — ε=1/day, medium sensitivity, opt-in.
  Per-source-tier counts of which tiers the operator favors. Opt-in
  because the operator's tier preferences correlate to research
  domain.

Query-content telemetry is registered with ``sensitivity="forbidden"``
and ε=0 — the substrate refuses to route it through DP at all per
§13.3 ("either E2E encryption with no learning, or no collection").
"""

from __future__ import annotations

import math
import os
import random
from datetime import datetime, timezone
from typing import Any, Optional

from substrate.dp_shuffler.epsilon_registry import (
    EpsilonRegistry,
    EpsilonRegistryError,
    SurfaceConfig,
    register_surface,
)
from substrate.dp_shuffler.shuffler import LocalRandomizer


# ── Singleton registry, pre-populated on import ──────────────────────


_PRODUCTION_REGISTRY: EpsilonRegistry = EpsilonRegistry()


def _bootstrap_surfaces() -> None:
    """Register the canonical surfaces from §13.3. Idempotent.

    Called at module import; tests can re-call after re-instantiating
    the registry.
    """
    if _PRODUCTION_REGISTRY.surfaces:
        return
    register_surface(
        _PRODUCTION_REGISTRY,
        surface_name="skill_invocation_frequency",
        epsilon_per_day=2.0,
        sensitivity="low",
        description=(
            "Per-skill counts of how often the operator invokes a "
            "particular skill. Aggregated daily across users."
        ),
        opt_in_required=False,
    )
    register_surface(
        _PRODUCTION_REGISTRY,
        surface_name="source_tier_preference",
        epsilon_per_day=1.0,
        sensitivity="medium",
        description=(
            "Per-source-tier counts of which tiers the operator "
            "favors. Opt-in because tier preferences correlate to "
            "research domain."
        ),
        opt_in_required=True,
    )
    # Forbidden surface so any attempt to register query-content via
    # the canonical name fails fast.
    register_surface(
        _PRODUCTION_REGISTRY,
        surface_name="query_content_telemetry",
        epsilon_per_day=0.0,
        sensitivity="forbidden",
        description=(
            "DO NOT COLLECT. Listed so attempts to route query-content "
            "through the shuffler fail at registration time per §13.3."
        ),
        opt_in_required=False,
    )


_bootstrap_surfaces()


def get_production_registry() -> EpsilonRegistry:
    """Return the singleton registry. Mutable; production code MUST
    NOT add surfaces at runtime (the registry exists to prevent
    that). Tests use this to inspect state."""
    return _PRODUCTION_REGISTRY


def reset_production_registry_for_tests() -> None:
    """Drop all registered surfaces and re-bootstrap. Test-only."""
    _PRODUCTION_REGISTRY.surfaces.clear()
    _bootstrap_surfaces()


class TelemetryRefused(Exception):
    """Raised when ``record_telemetry`` cannot route the call.

    Possible causes:
    - Surface is not registered.
    - Surface is forbidden (e.g. query_content_telemetry).
    - Surface requires opt-in and the caller indicated no opt-in.
    """


def record_telemetry(
    *,
    surface_name: str,
    true_value: bool,
    investigation_id: str = "__operator__",
    opt_in_granted: bool = False,
    emit_event_fn: Optional[Any] = None,
    rng: random.Random | None = None,
) -> bool:
    """Route a single telemetry sample through the production
    shuffler.

    Returns the noisy boolean (the value that gets aggregated). The
    original ``true_value`` never appears in the event log; only
    whether RR fired the noise coin appears (``was_flipped``).

    ``emit_event_fn`` is injectable for tests; production passes
    ``None`` and the function uses ``substrate.event_log.emit_typed``.
    """
    config = _PRODUCTION_REGISTRY.surfaces.get(surface_name)
    if config is None:
        raise TelemetryRefused(
            f"surface {surface_name!r} is not registered in the "
            "production registry. Add it via register_surface() at "
            "module import — runtime registration is forbidden."
        )
    if config.sensitivity == "forbidden":
        raise TelemetryRefused(
            f"surface {surface_name!r} is marked forbidden per §13.3 "
            "(no DP routing). Use E2E encryption with no learning, or "
            "no collection."
        )
    if config.opt_in_required and not opt_in_granted:
        raise TelemetryRefused(
            f"surface {surface_name!r} requires opt-in per §13.3; "
            "caller passed opt_in_granted=False"
        )

    rng = rng or random.SystemRandom()
    randomizer = LocalRandomizer(epsilon=config.epsilon_per_day)
    noisy_value = randomizer.randomize(true_value, rng=rng)
    was_flipped = noisy_value != true_value

    # Emit dp.routed.
    from substrate.schemas.events import DPRoutedPayload

    payload = DPRoutedPayload(
        surface_name=surface_name,
        epsilon=config.epsilon_per_day,
        sensitivity=config.sensitivity,  # type: ignore[arg-type]
        was_flipped=was_flipped,
        stage="local_randomized",
    )
    if emit_event_fn is None:
        from substrate.event_log import emit_typed
        emit_typed(investigation_id, payload)
    else:
        emit_event_fn(payload)
    return noisy_value


def daily_epsilon_used(
    *,
    surface_name: str,
    events: list[dict],
    day_iso: Optional[str] = None,
) -> float:
    """Sum the per-event ε for one surface on one day.

    Used by the Trust Center (§13.7) to publish "today's running ε
    per surface" without exposing per-sample values.
    """
    target_day = (
        day_iso
        or datetime.now(timezone.utc).date().isoformat()
    )
    total = 0.0
    for ev in events:
        payload = ev.get("payload") or {}
        if payload.get("action_type") != "dp.routed":
            continue
        if payload.get("surface_name") != surface_name:
            continue
        ts = ev.get("emitted_at") or ev.get("created_at") or ""
        if not isinstance(ts, str) or not ts.startswith(target_day):
            continue
        epsilon = payload.get("epsilon")
        if isinstance(epsilon, (int, float)):
            total += float(epsilon)
    return total
