"""Outcomes middleware (Sprint 5 day 2-3 migration).

Direct migration of Researchmaxx ``scripts/outcomes.py`` (273 LOC) —
the record() function, INPUT_SCHEMA shape, and the four observation
payload types.

What shipped:

- ``OutcomeRecord`` + 4 input dataclasses with closed-set validation
  (types.py).
- ``build_outcome_record`` pure transformation from raw JSON payload
  to validated ``OutcomeRecord`` (recorder.py).
- ``emit_outcome_recorded`` + ``emit_rubric_scored`` typed-event
  emitters (events.py). ``synthesis_id`` flows through the event
  envelope, not the payload.

What's deferred:

- DB writer (the upstream Researchmaxx ``record()`` writes to the
  DuckDB ``outcomes`` table). ``substrate/init_db.py`` hasn't been
  extended to that table yet; persistence wires in next slice.
- The rubric scorer itself — only its emit helper ships now so the
  substrate is round-trippable end-to-end as soon as the scorer
  lands.
- CLI parity with ``scripts/outcomes.py`` (``record``,
  ``record-decision``, ``list``, ``schema`` subcommands). The pure
  functions here are sufficient for module + bridge integration; the
  CLI is operator-facing and wires in alongside the DB writer.
"""

from .events import emit_outcome_recorded, emit_rubric_scored
from .recorder import build_outcome_record
from .types import (
    ACTUAL_DECISIONS,
    DECISION_RECOMMENDATIONS,
    EXECUTION_RISK_SEVERITIES,
    PROCEED_OUTCOMES,
    THESIS_OUTCOME_STATUSES,
    DecisionAlignmentInput,
    ExecutionRiskOutcomeInput,
    FalsificationOutcomeInput,
    OutcomeRecord,
    ThesisOutcomeInput,
)

__all__ = [
    "THESIS_OUTCOME_STATUSES",
    "EXECUTION_RISK_SEVERITIES",
    "DECISION_RECOMMENDATIONS",
    "ACTUAL_DECISIONS",
    "PROCEED_OUTCOMES",
    "ThesisOutcomeInput",
    "FalsificationOutcomeInput",
    "ExecutionRiskOutcomeInput",
    "DecisionAlignmentInput",
    "OutcomeRecord",
    "build_outcome_record",
    "emit_outcome_recorded",
    "emit_rubric_scored",
]
