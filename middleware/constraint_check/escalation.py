"""Constraint-loop escalation (ported from Researchmaxx
``constraint_escalation.py``, ~140 LOC of the salvageable 416).

Two pieces ship in Sprint 4 day 3-4:

1. ``build_constraint_check_result`` — structures the loop's full
   outcome so it lands verbatim in the archive's
   ``metadata.constraint_check_result``. Same shape the Researchmaxx
   spec calls for so a migrated trajectory's archive rows stay
   queryable without an adapter.
2. ``should_escalate`` — boolean for "is this terminal status one
   that warrants human review?"

DEFERRED for a later turn:

- ``escalate_to_kanban`` — shells out to ``hermes kanban`` CLI.
  Sprint 6+ when the operator's research-board integration is wired.
- ``escalate_phase_postcondition_failure`` — depends on
  phase_runner/phase_log migration (Sprint 6).

The kanban-CLI shellout in Researchmaxx is best-effort + idempotent
on synthesis_id; the same pattern lands when we wire it. For now,
the un-converging status is captured in the archived synthesis
``constraint_check_result`` blob and the
``ConstraintLoopResolvedPayload`` event — both queryable.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

# Statuses that warrant escalation (mapping to the orchestrate.py
# vocabulary preserved verbatim from Researchmaxx so a migrated
# backtest filter ``status NOT IN ('passed', 'single_pass')`` works
# unchanged).
NON_CONVERGING_STATUSES: frozenset[str] = frozenset({
    "regressed",
    "max_iterations_reached",
    "escalated",
    "preflight_failed",
})


def build_constraint_check_result(
    *,
    status: str,
    history: Iterable[dict[str, Any]] | None = None,
    final_violations: Iterable[dict[str, Any]] | None = None,
    total_iterations: int = 0,
    preflight_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Produce the structured ``constraint_check_result`` blob to embed
    in the archived synthesis metadata. Shape matches the Researchmaxx
    spec verbatim so a downstream query knows exactly what to expect
    (final_status, iterations_used, final_violations, iteration_history,
    preflight_result)."""
    history_list = list(history) if history is not None else []
    violations_list = list(final_violations) if final_violations is not None else []
    return {
        "final_status": status,
        "iterations_used": int(total_iterations),
        "final_violations": violations_list,
        "iteration_history": history_list,
        "preflight_result": preflight_result,
    }


def should_escalate(status: str) -> bool:
    """``True`` when the terminal status warrants human review.
    Operator decides whether to wire to kanban / Slack / silent log."""
    return status in NON_CONVERGING_STATUSES
