"""Persisted research-tier routing for cold-investigation role bridges."""

from __future__ import annotations

from collections import OrderedDict
from threading import RLock

from substrate.dispatch.research_tier import RESEARCH_TIERS, resolve_research_tier
from substrate.event_log import trajectory
from substrate.schemas import ActionType

_CACHE_LIMIT = 2048
_VALID_OVERRIDE_CACHE: OrderedDict[str, tuple[str, str]] = OrderedDict()
_CACHE_LOCK = RLock()


def persisted_research_tier_override(
    investigation_id: str,
) -> tuple[str | None, str | None]:
    """Resolve immutable start metadata once, otherwise preserve role config.

    The positive-only bounded cache avoids re-reading and sorting the complete
    trajectory for every parallel evidence dispatch. Investigation ids are
    immutable routing identities; 2,048 entries bounds process memory while
    retaining active/recent work. Missing metadata and read failures are never
    cached, so a transient event-log race cannot erase an explicit choice for
    the lifetime of the process.
    """
    with _CACHE_LOCK:
        cached = _VALID_OVERRIDE_CACHE.get(investigation_id)
        if cached is not None:
            _VALID_OVERRIDE_CACHE.move_to_end(investigation_id)
            return cached
    try:
        rows = trajectory(investigation_id)
    except Exception:  # pragma: no cover - routing must degrade to config
        return None, None

    start_action = ActionType.INVESTIGATION_START_REQUESTED.value
    for row in rows:
        if row.get("action_type") != start_action:
            continue
        payload = row.get("payload")
        tier = payload.get("research_tier") if isinstance(payload, dict) else None
        if tier not in RESEARCH_TIERS:
            return None, None
        target = resolve_research_tier(tier)
        resolved = (target.provider, target.model)
        with _CACHE_LOCK:
            _VALID_OVERRIDE_CACHE[investigation_id] = resolved
            _VALID_OVERRIDE_CACHE.move_to_end(investigation_id)
            if len(_VALID_OVERRIDE_CACHE) > _CACHE_LIMIT:
                _VALID_OVERRIDE_CACHE.popitem(last=False)
        return resolved
    return None, None


def clear_research_tier_override_cache() -> None:
    """Test/process-lifecycle hook; production routing never mutates entries."""
    with _CACHE_LOCK:
        _VALID_OVERRIDE_CACHE.clear()


__all__ = [
    "clear_research_tier_override_cache",
    "persisted_research_tier_override",
]
