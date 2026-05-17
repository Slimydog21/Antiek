"""Tests for middleware/constraint_check/loop.py (Sprint 7 day 3).

Coverage:

A. Spec → Constraint reconstruction:
   1. Round-trip: parameter_extractor.converter output → spec_to_constraint
      → evaluator-compatible Constraint dataclass.
   2. numeric_range stringified min/max coerced to float.
   3. must_include_term stringified case_sensitive coerced to bool.
   4. Invalid strictness on a spec fails loudly at reconstruction
      (the dataclass __post_init__ enforces closed-set membership).

B. parameters_to_extracted_values projection:
   5. scalar parameter → {anchor: value}.
   6. range / categorical / qualitative dropped.
   7. Empty parameter list → empty dict.

C. Loop body — terminal statuses:
   8. No constraints → single_pass + one CONSTRAINT_LOOP_RESOLVED event.
   9. Clean first iteration → single_pass.
   10. Hard violation cleared after one revision → passed +
       CONSTRAINT_REVISION_TRIGGERED + CONSTRAINT_LOOP_RESOLVED.
   11. Synthesizer can't fix it → max_iterations_reached after
       CONSTRAINT_MAX_ITERATIONS iterations.
   12. Regression detection: revision makes hard count strictly
       worse → regressed status.
   13. Soft-only violations don't trigger revision (clean hard-set
       → single_pass).
   14. Synthesizer callable is invoked with (violations, iteration)
       on each revision.

D. Trajectory events:
   15. CONSTRAINT_VIOLATION_FOUND emitted once per violation per
       iteration with correct iteration index.
   16. CONSTRAINT_REVISION_TRIGGERED triggering_constraint_ids
       contains only hard violations.
   17. CONSTRAINT_LOOP_RESOLVED emitted exactly once across all paths.

E. End-to-end via ParameterExtractor → loop integration:
   18. Take a parsed Parameter list, run it through the loop with a
       synth that passes — verifies the spec/extracted_values pipeline.
"""

from __future__ import annotations

import json
import os
import sys
from typing import List

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from middleware.constraint_check import (  # noqa: E402
    ConstraintLoopResult,
    parameters_to_extracted_values,
    run_constraint_loop,
    spec_to_constraint,
    specs_to_constraints,
)
from roles.parameter_extractor import (  # noqa: E402
    parameters_to_constraints,
    parse_parameter_extractor_response,
)
from substrate.event_log import trajectory  # noqa: E402
from substrate.schemas import (  # noqa: E402
    ActionType,
    Claim,
    ConstraintSpec,
    Event,
    MetricValue,
    Parameter,
)


@pytest.fixture(autouse=True)
def _events_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))


def _claim(text: str, *, attr=("r-1",), cid="c-1") -> Claim:
    return Claim(
        claim_id=cid, text=text, confidence="moderate",
        attribution_region_ids=list(attr),
    )


def _spec(
    constraint_id: str, kind: str, strictness: str = "hard",
    config: dict | None = None, description: str = "",
) -> ConstraintSpec:
    return ConstraintSpec(
        constraint_id=constraint_id,
        strictness=strictness,  # type: ignore[arg-type]
        kind=kind,  # type: ignore[arg-type]
        description=description or f"{kind} on {constraint_id}",
        config=config or {},
    )


# ---------------------------------------------------------------------------
# A. spec_to_constraint
# ---------------------------------------------------------------------------


def test_spec_to_constraint_numeric_range_round_trip():
    spec = _spec("c1", "numeric_range", config={
        "field": "training_compute",
        "min": 1e25, "max": 1e26,
    })
    c = spec_to_constraint(spec)
    assert c.constraint_id == "c1"
    assert c.kind == "numeric_range"
    assert c.strictness == "hard"
    assert c.config["min"] == 1e25
    assert c.config["max"] == 1e26


def test_spec_to_constraint_coerces_stringified_floats():
    """The converter may stringify min/max for codegen friendliness.
    spec_to_constraint should restore floats."""
    spec = _spec("c2", "numeric_range", config={
        "field": "x", "min": "0.5", "max": "1.5",
    })
    c = spec_to_constraint(spec)
    assert c.config["min"] == 0.5
    assert c.config["max"] == 1.5


def test_spec_to_constraint_coerces_case_sensitive_string():
    spec = _spec("c3", "must_include_term", config={
        "term": "TSMC", "case_sensitive": "true",
    })
    c = spec_to_constraint(spec)
    assert c.config["case_sensitive"] is True


def test_specs_to_constraints_bulk():
    specs = [
        _spec("c1", "must_attribute"),
        _spec("c2", "must_include_term", config={"term": "x"}),
    ]
    cs = specs_to_constraints(specs)
    assert len(cs) == 2
    assert cs[0].kind == "must_attribute"
    assert cs[1].kind == "must_include_term"


# ---------------------------------------------------------------------------
# B. parameters_to_extracted_values
# ---------------------------------------------------------------------------


def _param(anchor: str, *, value_type="scalar", value=None, unit="x") -> Parameter:
    return Parameter(
        semantic_anchor=anchor,
        metric_value=MetricValue(
            value_type=value_type,  # type: ignore[arg-type]
            value=value, unit=unit,
        ),
        qualitative_descriptor=None if value_type != "null" else "desc",
        evidence_status="observed",
        source_chunk_ids=["c1"],
        constraint_strictness="hard",
    )


def test_extracted_values_pulls_scalar_anchors():
    params = [
        _param("training_compute", value=1e25),
        _param("gross_margin", value=0.7, unit="%"),
    ]
    out = parameters_to_extracted_values(params)
    assert out == {"training_compute": 1e25, "gross_margin": 0.7}


def test_extracted_values_drops_non_scalar():
    """range / categorical / qualitative parameters can't be checked
    by the numeric_range checker, so they shouldn't surface."""
    params = [
        _param("range_p", value_type="range", value=[1.0, 2.0]),
        _param(
            "cat_p", value_type="categorical", value="us_only", unit=None,
        ),
        _param(
            "qual_p", value_type="null", value=None, unit=None,
        ),
    ]
    out = parameters_to_extracted_values(params)
    assert out == {}


def test_extracted_values_empty_list_empty_dict():
    assert parameters_to_extracted_values([]) == {}


# ---------------------------------------------------------------------------
# C. Loop body — terminal statuses
# ---------------------------------------------------------------------------


def _never_called(violations, iteration) -> List[Claim]:
    raise AssertionError("synthesizer_callable should not be invoked")


def test_loop_no_constraints_single_pass():
    inv = "inv-loop-none"
    result = run_constraint_loop(
        investigation_id=inv,
        initial_claims=[_claim("hello")],
        constraints=[],
        synthesizer_callable=_never_called,
    )
    assert isinstance(result, ConstraintLoopResult)
    assert result.final_status == "single_pass"
    assert result.total_iterations == 1
    assert result.passed is True
    assert result.iteration_history == []

    # Exactly one CONSTRAINT_LOOP_RESOLVED event.
    rows = trajectory(inv)
    resolved = [r for r in rows
                if r["action_type"] == ActionType.CONSTRAINT_LOOP_RESOLVED.value]
    assert len(resolved) == 1
    e = Event.model_validate(resolved[0])
    assert e.payload.final_status == "single_pass"


def test_loop_clean_first_iteration_is_single_pass():
    inv = "inv-loop-clean1"
    # must_attribute with a fully-attributed claim → no violations.
    spec = _spec("c-attr", "must_attribute")
    result = run_constraint_loop(
        investigation_id=inv,
        initial_claims=[_claim("attributed", attr=["r-1"])],
        constraints=[spec],
        synthesizer_callable=_never_called,
    )
    assert result.final_status == "single_pass"
    assert result.total_iterations == 1
    assert result.final_violations == []


def test_loop_passed_after_one_revision():
    """First iteration has a hard violation; synthesizer returns
    fixed claims; second iteration is clean → passed."""
    inv = "inv-loop-passed"
    spec = _spec("c-attr", "must_attribute")
    # Initial claim with NO attribution → violation.
    bad_claim = _claim("unattributed", attr=[], cid="c-bad")

    def fix(violations, iteration):
        # The synth returns a clean attributed claim.
        return [_claim("now-attributed", attr=["r-fix"], cid="c-fix")]

    result = run_constraint_loop(
        investigation_id=inv,
        initial_claims=[bad_claim],
        constraints=[spec],
        synthesizer_callable=fix,
    )
    assert result.final_status == "passed"
    assert result.total_iterations == 2
    assert result.final_violations == []
    assert result.final_claims[0].claim_id == "c-fix"

    rows = trajectory(inv)
    # Should see: 1 violation (iter 0), 1 revision triggered, 1 resolved
    violations = [r for r in rows
                  if r["action_type"] == ActionType.CONSTRAINT_VIOLATION_FOUND.value]
    revisions = [r for r in rows
                 if r["action_type"] == ActionType.CONSTRAINT_REVISION_TRIGGERED.value]
    resolved = [r for r in rows
                if r["action_type"] == ActionType.CONSTRAINT_LOOP_RESOLVED.value]
    assert len(violations) == 1
    assert len(revisions) == 1
    assert len(resolved) == 1
    assert Event.model_validate(resolved[0]).payload.final_status == "passed"


def test_loop_max_iterations_reached_when_unfixable():
    inv = "inv-loop-max"
    spec = _spec("c-attr", "must_attribute")

    def cant_fix(violations, iteration):
        # The synth keeps returning unattributed claims.
        return [_claim(f"still-bad-{iteration}", attr=[], cid=f"c-{iteration}")]

    result = run_constraint_loop(
        investigation_id=inv,
        initial_claims=[_claim("seed", attr=[], cid="c-seed")],
        constraints=[spec],
        synthesizer_callable=cant_fix,
        max_iterations=3,
    )
    assert result.final_status == "max_iterations_reached"
    assert result.total_iterations == 3
    assert len(result.final_violations) >= 1

    # 3 iterations × 1 violation each = 3 violation events;
    # 2 revisions (iter 0 + iter 1); 1 resolved.
    rows = trajectory(inv)
    violations = [r for r in rows
                  if r["action_type"] == ActionType.CONSTRAINT_VIOLATION_FOUND.value]
    revisions = [r for r in rows
                 if r["action_type"] == ActionType.CONSTRAINT_REVISION_TRIGGERED.value]
    resolved = [r for r in rows
                if r["action_type"] == ActionType.CONSTRAINT_LOOP_RESOLVED.value]
    assert len(violations) == 3
    assert len(revisions) == 2
    assert len(resolved) == 1
    assert Event.model_validate(resolved[0]).payload.final_status == "max_iterations_reached"


def test_loop_regression_detected():
    """Revision returns MORE hard violations → regressed."""
    inv = "inv-loop-regress"
    spec = _spec("c-attr", "must_attribute")

    def worse(violations, iteration):
        # Return two bad claims where there was one — strictly worse.
        return [
            _claim("worse-1", attr=[], cid="c-w1"),
            _claim("worse-2", attr=[], cid="c-w2"),
        ]

    result = run_constraint_loop(
        investigation_id=inv,
        initial_claims=[_claim("seed", attr=[], cid="c-seed")],
        constraints=[spec],
        synthesizer_callable=worse,
        max_iterations=3,
    )
    assert result.final_status == "regressed"
    assert result.total_iterations == 2  # iter 0 + iter 1 (worse)

    rows = trajectory(inv)
    resolved = [r for r in rows
                if r["action_type"] == ActionType.CONSTRAINT_LOOP_RESOLVED.value]
    assert len(resolved) == 1
    assert Event.model_validate(resolved[0]).payload.final_status == "regressed"


def test_loop_soft_only_violations_do_not_trigger_revision():
    """A soft violation is reported but does not gate the loop —
    the loop terminates with single_pass after iteration 0."""
    inv = "inv-loop-soft"
    spec = _spec("c-soft", "must_attribute", strictness="soft")
    result = run_constraint_loop(
        investigation_id=inv,
        initial_claims=[_claim("unattributed", attr=[], cid="c-soft")],
        constraints=[spec],
        synthesizer_callable=_never_called,
    )
    assert result.final_status == "single_pass"
    assert result.total_iterations == 1
    # Violation IS emitted (soft violations still count for reporting)
    assert len(result.final_violations) == 1
    assert result.final_violations[0].strictness == "soft"


def test_loop_synthesizer_callable_receives_violations_and_iteration():
    """The synthesizer callable must be invoked with the current
    violations and the iteration index."""
    inv = "inv-loop-args"
    spec = _spec("c-attr", "must_attribute")
    seen: list[tuple[int, int]] = []

    def capture(violations, iteration):
        seen.append((iteration, len(violations)))
        # Return the same bad claim so loop runs to max.
        return [_claim("still-bad", attr=[], cid="c-cap")]

    run_constraint_loop(
        investigation_id=inv,
        initial_claims=[_claim("seed", attr=[], cid="c-seed")],
        constraints=[spec],
        synthesizer_callable=capture,
        max_iterations=3,
    )
    # Called on iter 0 + iter 1 (revisions); iter 2 is terminal.
    assert seen == [(0, 1), (1, 1)]


# ---------------------------------------------------------------------------
# D. Trajectory events
# ---------------------------------------------------------------------------


def test_violation_events_carry_iteration_index():
    inv = "inv-loop-iters"
    spec = _spec("c-attr", "must_attribute")

    def cant_fix(violations, iteration):
        return [_claim("nope", attr=[], cid=f"c-{iteration}")]

    run_constraint_loop(
        investigation_id=inv,
        initial_claims=[_claim("seed", attr=[], cid="c-s")],
        constraints=[spec],
        synthesizer_callable=cant_fix,
        max_iterations=3,
    )
    rows = trajectory(inv)
    violations = [
        Event.model_validate(r).payload
        for r in rows
        if r["action_type"] == ActionType.CONSTRAINT_VIOLATION_FOUND.value
    ]
    iterations = [v.iteration for v in violations]
    assert iterations == [0, 1, 2]


def test_revision_triggering_ids_filter_to_hard_only():
    inv = "inv-loop-trig"
    hard_spec = _spec("c-hard", "must_attribute", strictness="hard")
    soft_spec = _spec("c-soft", "must_attribute", strictness="soft")

    def fix(violations, iteration):
        return [_claim("ok", attr=["r-1"], cid="c-fix")]

    run_constraint_loop(
        investigation_id=inv,
        initial_claims=[_claim("bad", attr=[], cid="c-bad")],
        constraints=[hard_spec, soft_spec],
        synthesizer_callable=fix,
    )
    rows = trajectory(inv)
    triggers = [
        Event.model_validate(r).payload
        for r in rows
        if r["action_type"] == ActionType.CONSTRAINT_REVISION_TRIGGERED.value
    ]
    assert len(triggers) == 1
    # triggering_constraint_ids must list ONLY hard violations.
    # Same claim violated both specs, but the soft one shouldn't
    # appear in the trigger list.
    assert "c-hard" in triggers[0].triggering_constraint_ids
    assert "c-soft" not in triggers[0].triggering_constraint_ids


def test_loop_resolved_emitted_exactly_once_in_all_paths():
    """No matter which terminal status fires, exactly one
    CONSTRAINT_LOOP_RESOLVED event lands."""
    scenarios = [
        # (description, initial_claims, constraints, synth_callable)
        ("no constraints", [_claim("x")], [], _never_called),
        ("clean", [_claim("ok", attr=["r-1"])], [_spec("c1", "must_attribute")], _never_called),
        ("max-iter", [_claim("bad", attr=[], cid="c0")],
         [_spec("c1", "must_attribute")],
         lambda vs, i: [_claim("still-bad", attr=[], cid="cN")]),
        ("regression", [_claim("bad", attr=[], cid="c0")],
         [_spec("c1", "must_attribute")],
         lambda vs, i: [_claim("a", attr=[], cid="cA"),
                        _claim("b", attr=[], cid="cB")]),
    ]
    for i, (desc, claims, specs, synth) in enumerate(scenarios):
        inv = f"inv-resolved-{i}"
        run_constraint_loop(
            investigation_id=inv,
            initial_claims=claims,
            constraints=specs,
            synthesizer_callable=synth,
            max_iterations=3,
        )
        resolved = [
            r for r in trajectory(inv)
            if r["action_type"] == ActionType.CONSTRAINT_LOOP_RESOLVED.value
        ]
        assert len(resolved) == 1, f"{desc}: expected 1 resolved event"


# ---------------------------------------------------------------------------
# E. End-to-end through parameter_extractor
# ---------------------------------------------------------------------------


def test_end_to_end_through_parameter_extractor():
    """Parse a Parameter Extractor LLM response, convert to specs,
    project extracted_values, run the loop with a passing synth.

    Verifies the full ConstraintSpec ↔ Constraint pipeline."""
    inv = "inv-e2e"
    response = {"parameters": [{
        "semantic_anchor": "training_compute",
        "metric_value": {"value_type": "scalar", "value": 5e25, "unit": "FLOP"},
        "qualitative_descriptor": None,
        "evidence_status": "observed",
        "source_chunk_ids": ["chunk-1"],
        "constraint_strictness": "hard",
    }]}
    parsed = parse_parameter_extractor_response(json.dumps(response))
    # converter (the bridge does this at emit time)
    constraints = parameters_to_constraints(parsed.parameters)

    # Reconstruct Parameter payloads (the bridge does this for the
    # delivered payload) so the loop's extracted_values can populate.
    parameters_payload = [
        Parameter(
            semantic_anchor=p.semantic_anchor,
            metric_value=MetricValue(
                value_type=p.metric_value.value_type,  # type: ignore[arg-type]
                value=p.metric_value.value, unit=p.metric_value.unit,
            ),
            qualitative_descriptor=p.qualitative_descriptor,
            evidence_status=p.evidence_status,  # type: ignore[arg-type]
            source_chunk_ids=list(p.source_chunk_ids),
            constraint_strictness=p.constraint_strictness,  # type: ignore[arg-type]
        )
        for p in parsed.parameters
    ]

    result = run_constraint_loop(
        investigation_id=inv,
        initial_claims=[_claim("compute is 5e25 FLOP", attr=["r-1"])],
        constraints=constraints,
        parameters=parameters_payload,
        synthesizer_callable=_never_called,
    )
    # numeric_range constraint with degenerate min=max=5e25, extracted
    # value 5e25 → no violation → single_pass.
    assert result.final_status == "single_pass"
    assert result.final_violations == []
