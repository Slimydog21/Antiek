"""Tests for middleware/outcomes/ (Sprint 5 day 2-3).

Coverage:

1. Dataclass inputs reject unknown enum values at construction.
2. ``build_outcome_record`` projects the legacy INPUT_SCHEMA shape
   and validates per-element enums.
3. ``build_outcome_record`` requires observer (envelope or payload).
4. Emit helpers round-trip through ``Event.model_validate`` with the
   typed payload + envelope synthesis_id + role.
5. ``emit_rubric_scored`` enforces [0, 1] score bounds.
6. Drift detection — module sets equal schema Literal sets.
"""

from __future__ import annotations

import os
import sys
import typing

import pytest
from pydantic import ValidationError

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from middleware.outcomes import (  # noqa: E402
    ACTUAL_DECISIONS,
    DECISION_RECOMMENDATIONS,
    EXECUTION_RISK_SEVERITIES,
    PROCEED_OUTCOMES,
    THESIS_OUTCOME_STATUSES,
    DecisionAlignmentInput,
    ExecutionRiskOutcomeInput,
    OutcomeRecord,
    ThesisOutcomeInput,
    build_outcome_record,
    emit_outcome_recorded,
    emit_rubric_scored,
)
from substrate.event_log import trajectory  # noqa: E402
from substrate.schemas import (  # noqa: E402
    ActionType,
    ActualDecision,
    DecisionRecommendation,
    Event,
    ExecutionRiskSeverity,
    OutcomeRecordedPayload,
    ProceedOutcome,
    RubricScoredPayload,
    ThesisOutcomeStatus,
)


@pytest.fixture(autouse=True)
def _events_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))


# ---------------------------------------------------------------------------
# 1. Dataclass enum validation
# ---------------------------------------------------------------------------


def test_thesis_outcome_rejects_unknown_status():
    with pytest.raises(ValueError, match="outcome"):
        ThesisOutcomeInput(thesis_claim="x", outcome="maybe")


def test_execution_risk_outcome_rejects_unknown_severity():
    with pytest.raises(ValueError, match="severity_actual"):
        ExecutionRiskOutcomeInput(risk="x", manifested=True, severity_actual="extreme")


def test_decision_alignment_rejects_unknown_recommendation():
    with pytest.raises(ValueError, match="agent_implicit_recommendation"):
        DecisionAlignmentInput(
            agent_implicit_recommendation="maybe",
            actual_decision="proceed",
        )


def test_decision_alignment_rejects_unknown_actual_decision():
    with pytest.raises(ValueError, match="actual_decision"):
        DecisionAlignmentInput(
            agent_implicit_recommendation="proceed",
            actual_decision="maybe",
        )


def test_decision_alignment_rejects_unknown_proceed_outcome():
    with pytest.raises(ValueError, match="thesis_outcome_when_proceeded"):
        DecisionAlignmentInput(
            agent_implicit_recommendation="proceed",
            actual_decision="proceed",
            thesis_outcome_when_proceeded="amazing",
        )


# ---------------------------------------------------------------------------
# 2. build_outcome_record — projection from INPUT_SCHEMA shape
# ---------------------------------------------------------------------------


def _full_payload() -> dict:
    return {
        "thesis_outcomes": [
            {
                "thesis_claim": "ARR grew >80% YoY",
                "outcome": "confirmed",
                "evidence": "92% per Q3 letter",
                "evidence_chunk_ids": ["chunk-9"],
            },
        ],
        "falsification_outcomes": [
            {"condition": "ARR < 50%", "occurred": False, "evidence": ""},
        ],
        "execution_risk_outcomes": [
            {
                "risk": "talent flight",
                "manifested": True,
                "severity_actual": "moderate",
                "evidence": "two VPs left in Q2",
            },
        ],
        "decision_alignment": {
            "agent_implicit_recommendation": "proceed",
            "actual_decision": "proceed",
            "decision_outcome_at_observation": "thesis held",
            "thesis_outcome_when_proceeded": "confirmed",
        },
    }


def test_build_outcome_record_projects_full_payload():
    r = build_outcome_record(
        synthesis_id="syn-1", payload=_full_payload(),
        observer="Faisal", notes="quarterly review",
    )
    assert isinstance(r, OutcomeRecord)
    assert r.synthesis_id == "syn-1"
    assert r.observer == "Faisal"
    assert r.notes == "quarterly review"
    assert len(r.thesis_outcomes) == 1 and r.thesis_outcomes[0].outcome == "confirmed"
    assert r.thesis_outcomes[0].evidence_chunk_ids == ("chunk-9",)
    assert len(r.falsification_outcomes) == 1 and r.falsification_outcomes[0].occurred is False
    assert len(r.execution_risk_outcomes) == 1
    assert r.execution_risk_outcomes[0].severity_actual == "moderate"
    assert r.decision_alignment is not None
    assert r.decision_alignment.thesis_outcome_when_proceeded == "confirmed"


def test_build_outcome_record_requires_observer():
    with pytest.raises(ValueError, match="observer"):
        build_outcome_record(synthesis_id="s", payload={})


def test_build_outcome_record_takes_observer_from_payload_when_kwarg_missing():
    r = build_outcome_record(
        synthesis_id="s", payload={"observer": "in-payload"},
    )
    assert r.observer == "in-payload"


def test_build_outcome_record_kwarg_overrides_payload_observer():
    r = build_outcome_record(
        synthesis_id="s",
        payload={"observer": "in-payload"},
        observer="kwarg-wins",
    )
    assert r.observer == "kwarg-wins"


def test_build_outcome_record_propagates_per_element_validation():
    bad_payload = {
        "observer": "f",
        "thesis_outcomes": [{"thesis_claim": "x", "outcome": "totally_unknown"}],
    }
    with pytest.raises(ValueError, match="outcome"):
        build_outcome_record(synthesis_id="s", payload=bad_payload)


def test_build_outcome_record_handles_empty_payload():
    r = build_outcome_record(
        synthesis_id="s", payload={"observer": "f"},
    )
    assert r.thesis_outcomes == ()
    assert r.falsification_outcomes == ()
    assert r.execution_risk_outcomes == ()
    assert r.decision_alignment is None


# ---------------------------------------------------------------------------
# 3. emit_outcome_recorded round-trip
# ---------------------------------------------------------------------------


def test_emit_outcome_recorded_round_trips():
    r = build_outcome_record(
        synthesis_id="syn-7", payload=_full_payload(), observer="Faisal",
    )
    eid = emit_outcome_recorded(investigation_id="inv-o", record=r)
    rows = trajectory("inv-o")
    assert len(rows) == 1
    e = Event.model_validate(rows[0])
    assert e.event_id == eid
    assert e.action_type == ActionType.OUTCOME_RECORDED.value
    assert e.synthesis_id == "syn-7"
    assert e.role == "outcome_recorder"
    assert isinstance(e.payload, OutcomeRecordedPayload)
    p = e.payload
    assert p.outcome_id == r.outcome_id
    assert p.observer == "Faisal"
    assert len(p.thesis_outcomes) == 1
    assert p.thesis_outcomes[0].outcome == "confirmed"
    assert p.decision_alignment is not None
    assert p.decision_alignment.thesis_outcome_when_proceeded == "confirmed"


def test_emit_outcome_recorded_with_no_decision_alignment():
    r = build_outcome_record(
        synthesis_id="syn-8", payload={"observer": "f"},
    )
    eid = emit_outcome_recorded(investigation_id="inv-o2", record=r)
    e = Event.model_validate(trajectory("inv-o2")[0])
    assert eid == e.event_id
    assert e.payload.decision_alignment is None


# ---------------------------------------------------------------------------
# 4. emit_rubric_scored round-trip + bounds
# ---------------------------------------------------------------------------


def test_emit_rubric_scored_round_trips():
    eid = emit_rubric_scored(
        investigation_id="inv-r",
        synthesis_id="syn-r",
        rubric_id="rubric-v1",
        final_score=0.82,
        deterministic_score=0.9,
        judged_score=0.7,
        target_claim_id="cl-1",
        notes="strong on attribution, weak on falsification",
    )
    e = Event.model_validate(trajectory("inv-r")[0])
    assert e.event_id == eid
    assert e.action_type == ActionType.RUBRIC_SCORED.value
    assert e.synthesis_id == "syn-r"
    assert e.role == "rubric_scorer"
    assert isinstance(e.payload, RubricScoredPayload)
    assert e.payload.final_score == pytest.approx(0.82)
    assert e.payload.deterministic_score == pytest.approx(0.9)
    assert e.payload.target_claim_id == "cl-1"


def test_emit_rubric_scored_allows_purely_judged():
    emit_rubric_scored(
        investigation_id="inv-rj", synthesis_id="syn-rj",
        rubric_id="r", final_score=0.5, judged_score=0.5,
    )
    e = Event.model_validate(trajectory("inv-rj")[0])
    assert e.payload.deterministic_score is None


def test_emit_rubric_scored_rejects_out_of_range_score():
    with pytest.raises(ValidationError):
        emit_rubric_scored(
            investigation_id="inv-bad", synthesis_id="syn-bad",
            rubric_id="r", final_score=1.5,
        )


# ---------------------------------------------------------------------------
# 5. Drift detection — module sets vs schema Literal sets
# ---------------------------------------------------------------------------


def test_thesis_outcome_statuses_match_schema_literal():
    assert set(typing.get_args(ThesisOutcomeStatus)) == THESIS_OUTCOME_STATUSES


def test_execution_risk_severities_match_schema_literal():
    assert set(typing.get_args(ExecutionRiskSeverity)) == EXECUTION_RISK_SEVERITIES


def test_decision_recommendations_match_schema_literal():
    assert set(typing.get_args(DecisionRecommendation)) == DECISION_RECOMMENDATIONS


def test_actual_decisions_match_schema_literal():
    assert set(typing.get_args(ActualDecision)) == ACTUAL_DECISIONS


def test_proceed_outcomes_match_schema_literal():
    assert set(typing.get_args(ProceedOutcome)) == PROCEED_OUTCOMES
