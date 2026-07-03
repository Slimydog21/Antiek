"""Orchestration: phase_log (Sprint 5 day 3-4 migration).

Direct migration of Researchmaxx ``scripts/phase_log.py`` (480 LOC) —
the JSON-per-investigation state machine + the typed PHASE_* event
mirror. Replaces prose enforcement of the 9-phase protocol with code-
level assertions Phase 9 mechanically gates on.

What shipped:

- ``PhaseLog`` class with enter/exit/verify/assert API (log.py).
- ``PhaseAssertionError`` (types.py).
- ``hash_paths`` deterministic SHA-256 over sorted-path file contents.
- ``emit_phase_enter`` / ``emit_phase_exit`` / ``emit_phase_verify``
  typed emitters; PhaseLog calls them inside a swallow-errors guard
  matching the upstream ``_phase_log_safe`` pattern.

What's deferred:

- Shadow DuckDB writer (the ``phase_log`` DB-table mirror in upstream
  ``phase_runner_shadow.py``). Documented YAGNI hold — the typed
  events ARE the queryable trajectory until a query pattern forces a
  DB mirror. The schema home for any future table is
  ``substrate/graph/schema.py``.
- CLI (status / enter / exit / verify / assert subcommands). Library
  API is enough for module + bridge integration; CLI wires in
  alongside the shadow writer.
- ``_load_shadow_writer`` / ``_shadow_with_locked_con`` flock-sharing
  scaffolding. Same dependency as above.
"""

from .events import emit_phase_enter, emit_phase_exit, emit_phase_verify
from .log import PhaseLog, default_log_dir, hash_paths
from .types import PhaseAssertionError

__all__ = [
    "PhaseLog",
    "PhaseAssertionError",
    "hash_paths",
    "default_log_dir",
    "emit_phase_enter",
    "emit_phase_exit",
    "emit_phase_verify",
]
