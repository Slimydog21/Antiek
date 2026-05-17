"""Constraint-check middleware (Sprint 4 day 3-4 migration).

Lineage note: the Researchmaxx ``constraint_check.py`` real
implementation (~2,000 LOC) was corrupted upstream and only an
emergency no-op stub remains. We build fresh from the spec §B and
preserve the salvageable Researchmaxx ``constraint_escalation.py``
helpers verbatim.

What shipped:

- ``Constraint`` + ``Violation`` dataclasses (constraints.py).
- ``evaluate_constraints`` pure function with 3 checker kinds:
  numeric_range, must_include_term, must_attribute (evaluation.py).
- ``build_constraint_check_result`` + ``should_escalate`` ported
  from Researchmaxx (escalation.py).
- 3 emit helpers for CONSTRAINT_VIOLATION_FOUND /
  CONSTRAINT_REVISION_TRIGGERED / CONSTRAINT_LOOP_RESOLVED
  (events.py).

What's deferred:

- The constraint-loop machinery (iterate, re-invoke synthesizer,
  terminate with status). Waits for Sprint 5 — parameter_extractor
  extraction will surface real constraint sources to feed it.
- Wrestling-bridge wiring (claims-fail-constraints affordance on
  ClaimCard). Same Sprint 5 dependency.
- ``escalate_to_kanban`` + ``escalate_phase_postcondition_failure``
  CLI shellouts. Wires in Sprint 6+ when phase_runner migrates.
"""

from .constraints import (
    CONSTRAINT_KINDS,
    CONSTRAINT_STRICTNESS_VALUES,
    Constraint,
    Violation,
)
from .escalation import (
    NON_CONVERGING_STATUSES,
    build_constraint_check_result,
    should_escalate,
)
from .evaluation import evaluate_constraints
from .events import (
    emit_constraint_loop_resolved,
    emit_constraint_revision_triggered,
    emit_constraint_violation_found,
)
from .loop import (
    ConstraintLoopResult,
    SynthesizerCallable,
    parameters_to_extracted_values,
    run_constraint_loop,
    spec_to_constraint,
    specs_to_constraints,
)

__all__ = [
    "Constraint",
    "Violation",
    "CONSTRAINT_STRICTNESS_VALUES",
    "CONSTRAINT_KINDS",
    "evaluate_constraints",
    "NON_CONVERGING_STATUSES",
    "build_constraint_check_result",
    "should_escalate",
    "emit_constraint_violation_found",
    "emit_constraint_revision_triggered",
    "emit_constraint_loop_resolved",
    # Loop (Sprint 7 day 3)
    "ConstraintLoopResult",
    "SynthesizerCallable",
    "spec_to_constraint",
    "specs_to_constraints",
    "parameters_to_extracted_values",
    "run_constraint_loop",
]
