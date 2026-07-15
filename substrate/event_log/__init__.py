"""Typed event log — the on-policy RL trajectory substrate.

See ``events.py`` for emit/seal/query operations.
Payload schemas (the discriminated union) live in ``substrate/schemas/events.py``;
this package re-exports ``ActionType`` and ``Event`` for back-compat with
callers that import directly from ``substrate.event_log``.
"""

# Keep ANTIEK_PARAM_VERSION importable here too — many call sites read it
# alongside ActionType.
from ..constants import ANTIEK_PARAM_VERSION  # noqa: E402
from ..schemas.events import (  # re-exported from the canonical schema source
    DEFAULT_POLICY_ID,
    EVENT_SCHEMA_VERSION,
    ActionType,
    Event,
)
from .events import (
    EventEmitter,
    PhysicalTrajectoryError,
    action_counts,
    append_persisted_event,
    default_events_dir,
    emit_typed,
    emit_worker_identity,
    iter_physical_events,
    log_event,
    query_worker_identity,
    seal_investigation,
    trajectory,
    validate_trajectory,
)

__all__ = [
    "ANTIEK_PARAM_VERSION",
    "EVENT_SCHEMA_VERSION",
    "DEFAULT_POLICY_ID",
    "ActionType",
    "Event",
    "EventEmitter",
    "PhysicalTrajectoryError",
    "action_counts",
    "append_persisted_event",
    "default_events_dir",
    "emit_typed",
    "emit_worker_identity",
    "log_event",
    "iter_physical_events",
    "query_worker_identity",
    "seal_investigation",
    "trajectory",
    "validate_trajectory",
]
