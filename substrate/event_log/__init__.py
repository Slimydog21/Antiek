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
    PhysicalEventObservation,
    PhysicalEventPage,
    PhysicalStorageCursor,
    PhysicalTrajectoryError,
    action_counts,
    default_events_dir,
    emit_typed,
    emit_worker_identity,
    iter_physical_events,
    log_event,
    normalize_semantic_event,
    physical_event_sha256,
    query_worker_identity,
    read_physical_event_page,
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
    "PhysicalEventObservation",
    "PhysicalEventPage",
    "PhysicalStorageCursor",
    "PhysicalTrajectoryError",
    "action_counts",
    "default_events_dir",
    "emit_typed",
    "emit_worker_identity",
    "iter_physical_events",
    "log_event",
    "normalize_semantic_event",
    "physical_event_sha256",
    "read_physical_event_page",
    "query_worker_identity",
    "seal_investigation",
    "trajectory",
    "validate_trajectory",
]
