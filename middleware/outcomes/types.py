"""Outcome dataclasses (input shape for the recorder).

Outcomes are produced by a separate process (manual or partially
automated) — not by the agent — and the cadence is quarterly review of
open investigations (Researchmaxx spec §E.2). The shapes here mirror
the four list/object types on ``OutcomeRecordedPayload`` so the
recorder can hand the same structures to the typed-event emitter
without an adapter layer.

Validation lives at construction time: enum-like fields are checked
against the closed sets below. Bad inputs raise ``ValueError`` loudly
rather than slipping through to a Pydantic failure later.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Closed sets — must agree with the schemas-side Literal types.
# Validated by named test in tests/test_middleware_outcomes.py.

THESIS_OUTCOME_STATUSES: frozenset[str] = frozenset({
    "confirmed", "partially_confirmed", "disconfirmed", "unresolved",
})

EXECUTION_RISK_SEVERITIES: frozenset[str] = frozenset({
    "critical", "high", "moderate", "low", "none",
})

DECISION_RECOMMENDATIONS: frozenset[str] = frozenset({
    "proceed", "pass", "conditional",
})

ACTUAL_DECISIONS: frozenset[str] = frozenset({
    "proceed", "pass", "conditional", "not_observed",
})

PROCEED_OUTCOMES: frozenset[str] = frozenset({
    "confirmed", "partially_confirmed", "disconfirmed", "not_observed",
})


@dataclass(frozen=True)
class ThesisOutcomeInput:
    thesis_claim: str
    outcome: str  # one of THESIS_OUTCOME_STATUSES
    evidence: str = ""
    evidence_chunk_ids: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.outcome not in THESIS_OUTCOME_STATUSES:
            raise ValueError(
                f"outcome must be one of {sorted(THESIS_OUTCOME_STATUSES)}, "
                f"got {self.outcome!r}"
            )


@dataclass(frozen=True)
class FalsificationOutcomeInput:
    condition: str
    occurred: bool
    evidence: str = ""


@dataclass(frozen=True)
class ExecutionRiskOutcomeInput:
    risk: str
    manifested: bool
    severity_actual: str  # one of EXECUTION_RISK_SEVERITIES
    evidence: str = ""

    def __post_init__(self) -> None:
        if self.severity_actual not in EXECUTION_RISK_SEVERITIES:
            raise ValueError(
                f"severity_actual must be one of "
                f"{sorted(EXECUTION_RISK_SEVERITIES)}, "
                f"got {self.severity_actual!r}"
            )


@dataclass(frozen=True)
class DecisionAlignmentInput:
    agent_implicit_recommendation: str  # one of DECISION_RECOMMENDATIONS
    actual_decision: str                 # one of ACTUAL_DECISIONS
    decision_outcome_at_observation: str = ""
    thesis_outcome_when_proceeded: str = "not_observed"  # one of PROCEED_OUTCOMES

    def __post_init__(self) -> None:
        if self.agent_implicit_recommendation not in DECISION_RECOMMENDATIONS:
            raise ValueError(
                f"agent_implicit_recommendation must be one of "
                f"{sorted(DECISION_RECOMMENDATIONS)}, "
                f"got {self.agent_implicit_recommendation!r}"
            )
        if self.actual_decision not in ACTUAL_DECISIONS:
            raise ValueError(
                f"actual_decision must be one of {sorted(ACTUAL_DECISIONS)}, "
                f"got {self.actual_decision!r}"
            )
        if self.thesis_outcome_when_proceeded not in PROCEED_OUTCOMES:
            raise ValueError(
                f"thesis_outcome_when_proceeded must be one of "
                f"{sorted(PROCEED_OUTCOMES)}, "
                f"got {self.thesis_outcome_when_proceeded!r}"
            )


@dataclass(frozen=True)
class OutcomeRecord:
    """One observation row about an archived synthesis.

    Aggregates the four sub-list/object inputs plus envelope fields.
    The ``record()`` function in ``recorder.py`` produces one of these
    from a JSON payload (the legacy ``INPUT_SCHEMA`` shape); the emit
    helper in ``events.py`` translates it to a typed event.
    """

    outcome_id: str
    synthesis_id: str
    observer: str
    thesis_outcomes: tuple[ThesisOutcomeInput, ...] = field(default_factory=tuple)
    falsification_outcomes: tuple[FalsificationOutcomeInput, ...] = field(default_factory=tuple)
    execution_risk_outcomes: tuple[ExecutionRiskOutcomeInput, ...] = field(default_factory=tuple)
    decision_alignment: DecisionAlignmentInput | None = None
    notes: str | None = None
