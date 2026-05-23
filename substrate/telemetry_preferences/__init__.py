"""Per-user per-category telemetry preferences (Sprint 22 Phase 6).

Per master-spec §13.3: *"Privacy dashboard as first-class product
surface. Real-time view of every telemetry collected from the user's
private graph, with toggles per category."*

This module is the substrate-side of the toggle. The
`PrivacyDashboard` UI consumes the GET endpoint; the user flips a
toggle; the PUT/PATCH endpoint writes through to this module. The
DP shuffler queries `is_enabled(user_id, surface_name)` before
emitting any telemetry.

Discipline:
- Default for opt-in-required surfaces (per `EpsilonRegistry`
  `opt_in_required=True`) is FALSE — user must affirmatively opt in
- Default for non-opt-in surfaces is TRUE — non-PII low-sensitivity
  telemetry runs unless the user opts out
- Forbidden surfaces (`opt_in_required=False`, sensitivity=forbidden,
  ε=0) cannot be toggled on; the substrate refuses to write any
  signal regardless of preference
"""

from .preferences import (
    UserTelemetryPreferences,
    PreferenceStore,
    InMemoryPreferenceStore,
    SqlitePreferenceStore,
    is_enabled,
    set_preference,
    list_preferences,
    apply_defaults_from_registry,
)

__all__ = [
    "InMemoryPreferenceStore",
    "PreferenceStore",
    "SqlitePreferenceStore",
    "UserTelemetryPreferences",
    "apply_defaults_from_registry",
    "is_enabled",
    "list_preferences",
    "set_preference",
]
