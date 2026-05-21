"""Tier-1 behavior store.

Schema-distinct from ``substrate/event_log/`` (IP/audit) and from
``substrate/graph/`` (knowledge graph). The behavior store is the
substrate for on-policy RL training data — opt-in consent,
DP-shuffled on egress.

Wave 2 surfaces (SPR-04+) call ``emit_behavior_event``. Everything
else is internal.

Sprint: SPR-01 (Wrestle Evolution, Wave 1 substrate).
See ``substrate/behavior/PRIVACY.md`` for the privacy posture and
``substrate/behavior/SCHEMA_NOTES.md`` for the divergence from the
event_log.
"""

from .api import (
    DEFAULT_USER_ID,
    InvalidEventType,
    SchemaValidationError,
    emit_behavior_event,
)
from .consent import (
    CURRENT_CONSENT_VERSION,
    ConsentState,
    active_consent_version,
    get_consent_state,
    grant_consent,
    is_consent_active,
    revoke_consent,
)
from .export import (
    EXPORT_DELTA,
    EXPORT_EPSILON_PER_BATCH,
    EXPORT_SURFACE_NAME,
    ExportResult,
    OperatorRoleRequired,
    ShuffledEvent,
    export_training_batch,
    query_raw,
)
from .schema import (
    MIGRATION_FILES,
    default_db_path,
    init_behavior_schema,
    init_behavior_schema_at_path,
    list_behavior_tables,
)
from .taxonomy import (
    ALL_BEHAVIOR_EVENT_TYPES,
    BEHAVIOR_TAXONOMY_VERSION,
    BehaviorEventType,
)

__all__ = [
    "ALL_BEHAVIOR_EVENT_TYPES",
    "BEHAVIOR_TAXONOMY_VERSION",
    "BehaviorEventType",
    "CURRENT_CONSENT_VERSION",
    "ConsentState",
    "DEFAULT_USER_ID",
    "EXPORT_DELTA",
    "EXPORT_EPSILON_PER_BATCH",
    "EXPORT_SURFACE_NAME",
    "ExportResult",
    "InvalidEventType",
    "MIGRATION_FILES",
    "OperatorRoleRequired",
    "SchemaValidationError",
    "ShuffledEvent",
    "active_consent_version",
    "default_db_path",
    "emit_behavior_event",
    "export_training_batch",
    "get_consent_state",
    "grant_consent",
    "init_behavior_schema",
    "init_behavior_schema_at_path",
    "is_consent_active",
    "list_behavior_tables",
    "query_raw",
    "revoke_consent",
]
