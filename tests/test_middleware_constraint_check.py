"""Tests for middleware/constraint_check/ (Sprint 4 day 3-4).

Coverage:

1. ``Constraint`` rejects unknown strictness + kind at construction
   (closed sets enforced).
2. ``evaluate_constraints`` for each kind:
   - numeric_range: in-range / below-min / above-max / missing-field /
     non-numeric / missing 'field' config.
   - must_include_term: matched / unmatched / case-sensitive opt-in.
   - must_attribute: emits one violation per unattributed claim;
     fully-attributed claim list produces zero violations.
3. ``build_constraint_check_result`` shape matches Researchmaxx spec.
4. ``should_escalate`` for every non-converging status + at least
   one converging status.
5. Emit helpers round-trip through Event.model_validate with the
   typed payload + role="constraint_checker".
6. Equivalence between the schema's Literal sets and the module's
   ``CONSTRAINT_KINDS`` / ``CONSTRAINT_STRICTNESS_VALUES`` /
   ``NON_CONVERGING_STATUSES`` — a drift between them would let
   bad values slip through one layer.
"""

from __future__ import annotations

import os
import sys
import typing

import pytest
from pydantic import ValidationError

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from middleware.constraint_check import (  # noqa: E402
    CONSTRAINT_KINDS,
    CONSTRAINT_STRICTNESS_VALUES,
    NON_CONVERGING_STATUSES,
    Constraint,
    Violation,
    build_constraint_check_result,
    emit_constraint_loop_resolved,
    emit_constraint_revision_triggered,
    emit_constraint_violation_found,
    evaluate_constraints,
    should_escalate,
)
from substrate.event_log import trajectory  # noqa: E402
from substrate.schemas import (  # noqa: E402
    ActionType,
    Claim,
    ConstraintKind,
    ConstraintLoopResolvedPayload,
    ConstraintLoopStatus,
    ConstraintRevisionTriggeredPayload,
    ConstraintStrictness,
    ConstraintViolationFoundPayload,
    Event,
)


@pytest.fixture(autouse=True)
def _events_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))


# ---------------------------------------------------------------------------
# 1. Constraint dataclass validates closed sets
# ---------------------------------------------------------------------------


def test_constraint_accepts_known_strictness_and_kind():
    c = Constraint(
        constraint_id="c", strictness="hard", kind="must_attribute",
        description="every claim must cite source",
    )
    assert c.strictness == "hard"
    assert c.kind == "must_attribute"


def test_constraint_rejects_unknown_strictness():
    with pytest.raises(ValueError, match="strictness"):
        Constraint(
            constraint_id="c", strictness="mandatory", kind="must_attribute",
            description="x",
        )


def test_constraint_rejects_unknown_kind():
    with pytest.raises(ValueError, match="kind"):
        Constraint(
            constraint_id="c", strictness="hard", kind="totally_made_up",
            description="x",
        )


# ---------------------------------------------------------------------------
# 2a. numeric_range checker
# ---------------------------------------------------------------------------


def _numeric_constraint(*, field="x", lo=0.0, hi=100.0, strictness="hard"):
    return Constraint(
        constraint_id=f"c-{field}",
        strictness=strictness,
        kind="numeric_range",
        description=f"{field} in [{lo}, {hi}]",
        config={"field": field, "min": lo, "max": hi},
    )


def test_numeric_range_in_bounds_no_violation():
    c = _numeric_constraint(field="x", lo=0, hi=100)
    vs = evaluate_constraints([c], [], extracted_values={"x": 42})
    assert vs == []


def test_numeric_range_below_min():
    c = _numeric_constraint(field="x", lo=10, hi=100)
    vs = evaluate_constraints([c], [], extracted_values={"x": 5})
    assert len(vs) == 1
    assert "x=5" in vs[0].reason and "min=10" in vs[0].reason


def test_numeric_range_above_max():
    c = _numeric_constraint(field="x", lo=0, hi=10)
    vs = evaluate_constraints([c], [], extracted_values={"x": 11})
    assert len(vs) == 1
    assert "x=11" in vs[0].reason and "max=10" in vs[0].reason


def test_numeric_range_missing_field_in_extracted_values():
    """The extractor was supposed to surface this field; it didn't.
    Constraint-checker flags it loudly rather than passing the
    synthesis through with the field silently missing."""
    c = _numeric_constraint(field="growth_rate", lo=0, hi=1)
    vs = evaluate_constraints([c], [], extracted_values={"other": 5})
    assert len(vs) == 1
    assert "no 'growth_rate'" in vs[0].reason


def test_numeric_range_non_numeric_value():
    c = _numeric_constraint(field="x", lo=0, hi=100)
    vs = evaluate_constraints([c], [], extracted_values={"x": "not-a-number"})
    assert len(vs) == 1
    assert "not numeric" in vs[0].reason


def test_numeric_range_missing_field_key_in_config():
    c = Constraint(
        constraint_id="c", strictness="hard", kind="numeric_range",
        description="malformed", config={"min": 0, "max": 100},
    )
    vs = evaluate_constraints([c], [], extracted_values={"x": 5})
    assert len(vs) == 1
    assert "'field' key" in vs[0].reason


# ---------------------------------------------------------------------------
# 2b. must_include_term checker
# ---------------------------------------------------------------------------


def _claim(text: str, *, attr=("r-1",), cid="c-1") -> Claim:
    return Claim(
        claim_id=cid, text=text, confidence="moderate",
        attribution_region_ids=list(attr),
    )


def test_must_include_term_match_no_violation():
    c = Constraint(
        constraint_id="t", strictness="soft", kind="must_include_term",
        description="must mention X",
        config={"term": "quantum"},
    )
    vs = evaluate_constraints([c], [_claim("quantum computing is hard")])
    assert vs == []


def test_must_include_term_no_match():
    c = Constraint(
        constraint_id="t", strictness="soft", kind="must_include_term",
        description="must mention X",
        config={"term": "quantum"},
    )
    vs = evaluate_constraints([c], [_claim("weather forecast tomorrow")])
    assert len(vs) == 1
    assert "quantum" in vs[0].reason


def test_must_include_term_default_is_case_insensitive():
    c = Constraint(
        constraint_id="t", strictness="soft", kind="must_include_term",
        description="x",
        config={"term": "Quantum"},
    )
    vs = evaluate_constraints([c], [_claim("a quantum claim")])
    assert vs == []


def test_must_include_term_case_sensitive_opt_in_rejects_mismatched_case():
    c = Constraint(
        constraint_id="t", strictness="soft", kind="must_include_term",
        description="x",
        config={"term": "Quantum", "case_sensitive": True},
    )
    vs = evaluate_constraints([c], [_claim("a quantum claim")])
    assert len(vs) == 1


def test_must_include_term_missing_term_in_config():
    c = Constraint(
        constraint_id="t", strictness="soft", kind="must_include_term",
        description="x", config={},
    )
    vs = evaluate_constraints([c], [_claim("anything")])
    assert len(vs) == 1
    assert "'term' key" in vs[0].reason


# ---------------------------------------------------------------------------
# 2c. must_attribute checker
# ---------------------------------------------------------------------------


def test_must_attribute_satisfied_when_all_claims_have_attribution():
    c = Constraint(
        constraint_id="a", strictness="hard", kind="must_attribute",
        description="every claim sourced",
    )
    claims = [
        _claim("claim 1", cid="c-1", attr=["r-1"]),
        _claim("claim 2", cid="c-2", attr=["r-2", "r-3"]),
    ]
    assert evaluate_constraints([c], claims) == []


def test_must_attribute_emits_one_violation_per_unattributed_claim():
    c = Constraint(
        constraint_id="a", strictness="hard", kind="must_attribute",
        description="every claim sourced",
    )
    claims = [
        _claim("ok", cid="c-1", attr=["r-1"]),
        _claim("bad 1", cid="c-2", attr=[]),
        _claim("bad 2", cid="c-3", attr=[]),
    ]
    vs = evaluate_constraints([c], claims)
    assert len(vs) == 2
    assert {v.target_claim_id for v in vs} == {"c-2", "c-3"}
    assert all(v.constraint_kind == "must_attribute" for v in vs)


# ---------------------------------------------------------------------------
# 2d. evaluate_constraints — multiple constraints
# ---------------------------------------------------------------------------


def test_evaluate_multiple_constraints_preserves_order():
    c1 = Constraint(
        constraint_id="first", strictness="hard", kind="must_attribute",
        description="x",
    )
    c2 = Constraint(
        constraint_id="second", strictness="soft", kind="must_include_term",
        description="x", config={"term": "ZZZ"},
    )
    vs = evaluate_constraints([c1, c2], [_claim("body", attr=[])])
    assert len(vs) == 2
    assert vs[0].constraint_id == "first"
    assert vs[1].constraint_id == "second"


# ---------------------------------------------------------------------------
# 3. build_constraint_check_result
# ---------------------------------------------------------------------------


def test_build_constraint_check_result_has_full_shape():
    r = build_constraint_check_result(
        status="max_iterations_reached",
        history=[{"iter": 1, "violations": []}],
        final_violations=[{"kind": "x"}],
        total_iterations=3,
        preflight_result={"satisfiable": True},
    )
    assert r == {
        "final_status": "max_iterations_reached",
        "iterations_used": 3,
        "final_violations": [{"kind": "x"}],
        "iteration_history": [{"iter": 1, "violations": []}],
        "preflight_result": {"satisfiable": True},
    }


def test_build_constraint_check_result_handles_none_lists():
    r = build_constraint_check_result(status="single_pass")
    assert r["iteration_history"] == []
    assert r["final_violations"] == []


# ---------------------------------------------------------------------------
# 4. should_escalate
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", sorted(NON_CONVERGING_STATUSES))
def test_should_escalate_for_every_non_converging_status(status):
    assert should_escalate(status) is True


@pytest.mark.parametrize("status", ["single_pass", "passed", "draft", ""])
def test_should_not_escalate_for_converging_or_unknown_statuses(status):
    assert should_escalate(status) is False


# ---------------------------------------------------------------------------
# 5. Emit helpers round-trip typed
# ---------------------------------------------------------------------------


def test_emit_constraint_violation_found_round_trips():
    v = Violation(
        constraint_id="c-1", constraint_kind="must_attribute",
        strictness="hard", reason="missing attribution",
        target_claim_id="cl-7",
    )
    eid = emit_constraint_violation_found(
        investigation_id="inv-cv", iteration=2, violation=v,
    )
    rows = trajectory("inv-cv")
    assert len(rows) == 1
    e = Event.model_validate(rows[0])
    assert e.event_id == eid
    assert e.action_type == ActionType.CONSTRAINT_VIOLATION_FOUND.value
    assert isinstance(e.payload, ConstraintViolationFoundPayload)
    p = e.payload
    assert p.constraint_id == "c-1"
    assert p.strictness == "hard"
    assert p.constraint_kind == "must_attribute"
    assert p.iteration == 2
    assert p.target_claim_id == "cl-7"
    assert p.reason == "missing attribution"
    assert e.role == "constraint_checker"


def test_emit_constraint_revision_triggered_round_trips():
    eid = emit_constraint_revision_triggered(
        investigation_id="inv-rev", iteration=1,
        triggering_constraint_ids=["c-1", "c-2"],
    )
    e = Event.model_validate(trajectory("inv-rev")[0])
    assert e.event_id == eid
    assert isinstance(e.payload, ConstraintRevisionTriggeredPayload)
    assert e.payload.triggering_constraint_ids == ["c-1", "c-2"]


def test_emit_constraint_loop_resolved_round_trips():
    eid = emit_constraint_loop_resolved(
        investigation_id="inv-end",
        final_status="passed", total_iterations=2,
        final_violation_count=0,
    )
    e = Event.model_validate(trajectory("inv-end")[0])
    assert e.event_id == eid
    assert isinstance(e.payload, ConstraintLoopResolvedPayload)
    assert e.payload.final_status == "passed"
    assert e.payload.total_iterations == 2


def test_emit_constraint_loop_resolved_rejects_unknown_final_status():
    """The Pydantic Literal on ConstraintLoopStatus enforces the closed
    set. A typo or new status would fail loudly at emit time."""
    with pytest.raises(ValidationError):
        emit_constraint_loop_resolved(
            investigation_id="inv-bad",
            final_status="archived",  # not in ConstraintLoopStatus
            total_iterations=1, final_violation_count=0,
        )


# ---------------------------------------------------------------------------
# 6. Drift detection — module sets must match schema Literal sets
# ---------------------------------------------------------------------------


def test_constraint_kinds_match_schema_literal():
    """CONSTRAINT_KINDS in middleware/constraint_check/constraints.py
    MUST equal ConstraintKind from substrate/schemas. Drift would let
    the evaluator produce a kind the payload validator would reject."""
    assert CONSTRAINT_KINDS == set(typing.get_args(ConstraintKind))


def test_constraint_strictness_matches_schema_literal():
    assert CONSTRAINT_STRICTNESS_VALUES == set(typing.get_args(ConstraintStrictness))


def test_non_converging_statuses_are_subset_of_loop_status():
    """Every status the escalation module considers non-converging
    MUST also be a valid ConstraintLoopStatus — the same value can't
    be a valid loop terminal in one layer and unknown in the other."""
    all_loop_statuses = set(typing.get_args(ConstraintLoopStatus))
    assert NON_CONVERGING_STATUSES <= all_loop_statuses
