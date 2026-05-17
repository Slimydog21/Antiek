"""Emit helpers for OUTCOME_RECORDED and RUBRIC_SCORED.

Mirrors middleware/constraint_check/events.py — pure functions that
take an ``OutcomeRecord`` (or scalar rubric fields) and call
``substrate.event_log.emit_typed`` with the right Pydantic payload.

``synthesis_id`` lives on the event envelope, not the payload, so it is
passed as an ``emit_typed`` kwarg in both helpers.

The rubric scorer is a downstream consumer of OutcomeRecorded; it is
deferred to a later slice but its emit helper ships now so the
substrate is round-trippable end-to-end as soon as the scorer
implementation lands.
"""

from __future__ import annotations

import os
import sys
from typing import Optional

try:
    from ...event_log import emit_typed
    from ...schemas import (
        DecisionAlignment,
        ExecutionRiskOutcome,
        FalsificationOutcome,
        OutcomeRecordedPayload,
        RubricScoredPayload,
        ThesisOutcome,
    )
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from substrate.event_log import emit_typed  # type: ignore[no-redef]
    from substrate.schemas import (  # type: ignore[no-redef]
        DecisionAlignment,
        ExecutionRiskOutcome,
        FalsificationOutcome,
        OutcomeRecordedPayload,
        RubricScoredPayload,
        ThesisOutcome,
    )

from .types import OutcomeRecord


def emit_outcome_recorded(
    *,
    investigation_id: str,
    record: OutcomeRecord,
    parent_event_id: Optional[str] = None,
) -> Optional[str]:
    """Emit exactly one OUTCOME_RECORDED event for the given observation.

    The four list/object fields are projected to their Pydantic shapes
    here (the dataclass inputs are validated; the Pydantic models
    enforce Literal closure a second time at write).
    """
    thesis = [
        ThesisOutcome(
            thesis_claim=t.thesis_claim,
            outcome=t.outcome,  # type: ignore[arg-type]
            evidence=t.evidence,
            evidence_chunk_ids=list(t.evidence_chunk_ids),
        )
        for t in record.thesis_outcomes
    ]
    falsifications = [
        FalsificationOutcome(
            condition=f.condition,
            occurred=f.occurred,
            evidence=f.evidence,
        )
        for f in record.falsification_outcomes
    ]
    risks = [
        ExecutionRiskOutcome(
            risk=r.risk,
            manifested=r.manifested,
            severity_actual=r.severity_actual,  # type: ignore[arg-type]
            evidence=r.evidence,
        )
        for r in record.execution_risk_outcomes
    ]
    da = record.decision_alignment
    decision = (
        DecisionAlignment(
            agent_implicit_recommendation=da.agent_implicit_recommendation,  # type: ignore[arg-type]
            actual_decision=da.actual_decision,  # type: ignore[arg-type]
            decision_outcome_at_observation=da.decision_outcome_at_observation,
            thesis_outcome_when_proceeded=da.thesis_outcome_when_proceeded,  # type: ignore[arg-type]
        )
        if da is not None
        else None
    )
    return emit_typed(
        investigation_id,
        OutcomeRecordedPayload(
            outcome_id=record.outcome_id,
            observer=record.observer,
            thesis_outcomes=thesis,
            falsification_outcomes=falsifications,
            execution_risk_outcomes=risks,
            decision_alignment=decision,
            notes=record.notes or "",
        ),
        parent_event_id=parent_event_id,
        synthesis_id=record.synthesis_id,
        role="outcome_recorder",
    )


def emit_rubric_scored(
    *,
    investigation_id: str,
    synthesis_id: str,
    rubric_id: str,
    final_score: float,
    deterministic_score: Optional[float] = None,
    judged_score: Optional[float] = None,
    target_claim_id: Optional[str] = None,
    notes: str = "",
    parent_event_id: Optional[str] = None,
) -> Optional[str]:
    """Emit one RUBRIC_SCORED event for an archived synthesis.

    ``final_score`` is always required; ``deterministic_score`` and
    ``judged_score`` may be None for purely-judged or purely-
    deterministic rubrics respectively (Pydantic-level constraint).
    Scores are in [0, 1]; out-of-range values raise at validation."""
    return emit_typed(
        investigation_id,
        RubricScoredPayload(
            rubric_id=rubric_id,
            target_claim_id=target_claim_id,
            deterministic_score=deterministic_score,
            judged_score=judged_score,
            final_score=float(final_score),
            notes=notes,
        ),
        parent_event_id=parent_event_id,
        synthesis_id=synthesis_id,
        role="rubric_scorer",
    )
