"""Loop 1 orchestrator (Sprint 8 day 3).

The gap-closer for the Antiek substrate: chains the 5 role bridges
through the 9-phase state machine in response to a cold question
posted as ``INVESTIGATION_START_REQUESTED``. Emits
``INVESTIGATION_COMPLETED`` (or ``INVESTIGATION_FAILED``) when the
run terminates.

Modules:

- ``coordinator`` — async event-await primitive. ``broadcast_emit``
  posts a typed event AND broadcasts it through the broadcaster (so
  bridge handlers fire). ``InvestigationCoordinator.wait_for(...)``
  awaits the next event of a given action type for a specific
  investigation.

- ``orchestrator`` — ``_run_investigation`` async coroutine that
  drives phases 1-9; ``make_loop_one_handler`` /
  ``register_handlers`` wire the entry point into the broadcaster.

Phase flow (verbatim from the operator's Day 3 brief):

  Phase 1  → decompose.requested → wait delivered
  Phase 2  → evidence.retrieve.requested × N → wait all
  Phase 3  → parameter_extract.requested → wait
  Phase 4  → connector.requested → wait
  Phase 5  → structural pass-through (constraint loop is in synth)
  Phase 6  → synthesize.requested → wait (loop converges inside)
  Phase 7  → skills.domain.master_md.generate_master_md
  Phase 8  → skills.domain.extract.extract_and_patch
  Phase 9  → assert_ready_for_completion + emit completed
"""

from .coordinator import (
    DEFAULT_AWAITED_ACTION_TYPES,
    InvestigationCoordinator,
    broadcast_emit,
)
from .orchestrator import (
    DEFAULT_ROLE_TIMEOUT,
    PER_EVIDENCE_TIMEOUT,
    SYNTHESIZER_TIMEOUT,
    InvestigationContext,
    make_loop_one_handler,
    register_handlers,
    run_synthesis_tail_from_pack,
)

__all__ = [
    # coordinator
    "DEFAULT_AWAITED_ACTION_TYPES",
    "InvestigationCoordinator",
    "broadcast_emit",
    # orchestrator
    "DEFAULT_ROLE_TIMEOUT",
    "PER_EVIDENCE_TIMEOUT",
    "SYNTHESIZER_TIMEOUT",
    "InvestigationContext",
    "make_loop_one_handler",
    "register_handlers",
    "run_synthesis_tail_from_pack",
]
