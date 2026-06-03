"""Tests for roles/parameter_extractor/ (Sprint 7 day 2).

Coverage:

A. Prompt:
   1. ``render_user_template`` substitutes evidence_block.
   2. Empty evidence_block falls back to ``(no evidence)``.
   3. ``render_full_prompt`` includes system + user;
      ``extra_user_prefix`` threads through.

B. Parser — normalization:
   4. ``value_type: null`` (JSON) normalized to the literal string
      ``"null"`` (the upstream drift handler).
   5. ``unit: null`` (JSON) normalized to absent.

C. Parser — validation failures:
   6. Garbage text rejected.
   7. Bad ``value_type`` rejected.
   8. Empty ``unit`` string rejected (upstream prohibition).
   9. ``value_type=scalar`` with non-numeric value rejected.
   10. ``value_type=range`` with non-pair value rejected.
   11. ``value_type=range`` with lo > hi rejected.
   12. ``value_type=null`` with numeric value rejected
       (the "over-correction trap").
   13. ``value_type=null`` without qualitative_descriptor rejected.
   14. ``value_type=categorical`` with int value rejected.
   15. Empty ``source_chunk_ids`` rejected (cite-every-claim).
   16. Bad ``constraint_strictness`` rejected.
   17. Bad ``evidence_status`` rejected.
   18. ``True`` (bool subclass of int) NOT accepted as scalar value.

D. Parser — happy paths:
   19. Numeric scalar parameter parsed.
   20. Range parameter parsed.
   21. Categorical (single + list) parameter parsed.
   22. Qualitative parameter parsed.

E. Converter (parameters_to_constraints):
   23. Scalar with unit → numeric_range constraint (min=max=value).
   24. Scalar without unit → DROPPED silently.
   25. Range → numeric_range with both bounds.
   26. Categorical single string → 1 must_include_term.
   27. Categorical list → 1 must_include_term per allowed string.
   28. Qualitative → must_attribute constraint.
   29. Constraint strictness flows through verbatim.

F. Drift detection:
   30. METRIC_VALUE_TYPES == schema MetricValueType Literal.
   31. EVIDENCE_STATUS_VALUES == schema EvidenceStatus Literal.
   32. CONSTRAINT_STRICTNESS_VALUES == schema ConstraintStrictness.
"""

from __future__ import annotations

import json
import os
import sys
import typing

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from roles.parameter_extractor import (  # noqa: E402
    CONSTRAINT_STRICTNESS_VALUES,
    EVIDENCE_STATUS_VALUES,
    METRIC_VALUE_TYPES,
    PARAMETER_EXTRACTOR_SYSTEM_PROMPT,
    ParameterValidationError,
    parameters_to_constraints,
    parse_parameter_extractor_response,
    render_full_prompt,
    render_user_template,
)
from substrate.schemas import (  # noqa: E402
    ConstraintStrictness,
    EvidenceStatus,
    MetricValueType,
)

# ---------------------------------------------------------------------------
# A. Prompt
# ---------------------------------------------------------------------------


def test_render_user_template_substitutes_evidence_block():
    s = render_user_template(evidence_block="[evidence here]")
    assert "[evidence here]" in s
    assert "{{evidence_block}}" not in s


def test_render_user_template_empty_falls_back():
    s = render_user_template(evidence_block="")
    assert "(no evidence)" in s


def test_render_full_prompt_includes_system_and_user():
    p = render_full_prompt(evidence_block="EV")
    assert PARAMETER_EXTRACTOR_SYSTEM_PROMPT in p
    assert "EV" in p


def test_render_full_prompt_extra_prefix_threads_into_user():
    p = render_full_prompt(evidence_block="EV", extra_user_prefix="REGEN")
    sys_end = p.index(PARAMETER_EXTRACTOR_SYSTEM_PROMPT) + len(PARAMETER_EXTRACTOR_SYSTEM_PROMPT)
    regen_idx = p.index("REGEN")
    assert regen_idx > sys_end


# ---------------------------------------------------------------------------
# B-D. Parser
# ---------------------------------------------------------------------------


def _numeric_param(**overrides) -> dict:
    base = {
        "semantic_anchor": "training_compute_budget",
        "metric_value": {"value_type": "scalar", "value": 1e25, "unit": "FLOP"},
        "qualitative_descriptor": None,
        "evidence_status": "observed",
        "source_chunk_ids": ["chunk-1"],
        "constraint_strictness": "hard",
    }
    base.update(overrides)
    return base


def _qualitative_param(**overrides) -> dict:
    base = {
        "semantic_anchor": "regulatory_uncertainty",
        "metric_value": {"value_type": "null"},
        "qualitative_descriptor": "Pending BIS rulemaking",
        "evidence_status": "imputed",
        "source_chunk_ids": ["chunk-3"],
        "constraint_strictness": "soft",
    }
    base.update(overrides)
    return base


def test_value_type_json_null_normalized_to_literal_string():
    """The upstream drift handler: a JSON-null value_type signals
    qualitative, normalized to the literal four-character "null"."""
    payload = _qualitative_param()
    payload["metric_value"]["value_type"] = None  # JSON null
    out = parse_parameter_extractor_response(
        json.dumps({"parameters": [payload]}),
    )
    assert out.parameters[0].metric_value.value_type == "null"


def test_unit_json_null_normalized_to_absent():
    payload = _qualitative_param()
    payload["metric_value"]["unit"] = None
    out = parse_parameter_extractor_response(
        json.dumps({"parameters": [payload]}),
    )
    assert out.parameters[0].metric_value.unit is None


def test_garbage_text_rejected():
    with pytest.raises(ParameterValidationError, match="parseable JSON"):
        parse_parameter_extractor_response("not json")


def test_bad_value_type_rejected():
    payload = _numeric_param()
    payload["metric_value"]["value_type"] = "fabricated"
    with pytest.raises(ParameterValidationError, match="value_type"):
        parse_parameter_extractor_response(json.dumps({"parameters": [payload]}))


def test_empty_unit_rejected():
    payload = _numeric_param()
    payload["metric_value"]["unit"] = ""
    with pytest.raises(ParameterValidationError, match="empty string is forbidden"):
        parse_parameter_extractor_response(json.dumps({"parameters": [payload]}))


def test_scalar_with_non_numeric_value_rejected():
    payload = _numeric_param()
    payload["metric_value"]["value"] = "not a number"
    with pytest.raises(ParameterValidationError, match="scalar value_type requires"):
        parse_parameter_extractor_response(json.dumps({"parameters": [payload]}))


def test_range_with_non_pair_rejected():
    payload = _numeric_param()
    payload["metric_value"]["value_type"] = "range"
    payload["metric_value"]["value"] = [1.0, 2.0, 3.0]
    with pytest.raises(ParameterValidationError, match="range value_type requires"):
        parse_parameter_extractor_response(json.dumps({"parameters": [payload]}))


def test_range_with_lo_greater_than_hi_rejected():
    payload = _numeric_param()
    payload["metric_value"]["value_type"] = "range"
    payload["metric_value"]["value"] = [10.0, 1.0]
    with pytest.raises(ParameterValidationError, match="lo > hi"):
        parse_parameter_extractor_response(json.dumps({"parameters": [payload]}))


def test_null_value_type_with_numeric_value_rejected():
    """The over-correction trap: value_type=null with value=number."""
    payload = _qualitative_param()
    payload["metric_value"]["value_type"] = "null"
    payload["metric_value"]["value"] = 42
    with pytest.raises(ParameterValidationError, match="over-correction trap"):
        parse_parameter_extractor_response(json.dumps({"parameters": [payload]}))


def test_qualitative_without_descriptor_rejected():
    payload = _qualitative_param()
    payload["qualitative_descriptor"] = ""  # empty
    with pytest.raises(ParameterValidationError, match="qualitative_descriptor"):
        parse_parameter_extractor_response(json.dumps({"parameters": [payload]}))


def test_categorical_with_int_value_rejected():
    payload = _numeric_param()
    payload["metric_value"]["value_type"] = "categorical"
    payload["metric_value"]["value"] = 42
    with pytest.raises(ParameterValidationError, match="categorical value_type requires"):
        parse_parameter_extractor_response(json.dumps({"parameters": [payload]}))


def test_empty_source_chunk_ids_rejected():
    payload = _numeric_param()
    payload["source_chunk_ids"] = []
    with pytest.raises(ParameterValidationError, match="cite-every-claim"):
        parse_parameter_extractor_response(json.dumps({"parameters": [payload]}))


def test_bad_constraint_strictness_rejected():
    payload = _numeric_param()
    payload["constraint_strictness"] = "mandatory"
    with pytest.raises(ParameterValidationError, match="constraint_strictness"):
        parse_parameter_extractor_response(json.dumps({"parameters": [payload]}))


def test_bad_evidence_status_rejected():
    payload = _numeric_param()
    payload["evidence_status"] = "guessed"
    with pytest.raises(ParameterValidationError, match="evidence_status"):
        parse_parameter_extractor_response(json.dumps({"parameters": [payload]}))


def test_bool_value_not_accepted_as_scalar():
    """bool ⊂ int — defend against True/False slipping through."""
    payload = _numeric_param()
    payload["metric_value"]["value"] = True
    with pytest.raises(ParameterValidationError, match="scalar"):
        parse_parameter_extractor_response(json.dumps({"parameters": [payload]}))


# ---------------------------------------------------------------------------
# D. Parser happy paths
# ---------------------------------------------------------------------------


def test_scalar_parameter_parsed():
    out = parse_parameter_extractor_response(
        json.dumps({"parameters": [_numeric_param()]}),
    )
    assert len(out.parameters) == 1
    p = out.parameters[0]
    assert p.metric_value.value_type == "scalar"
    assert p.metric_value.value == 1e25
    assert p.metric_value.unit == "FLOP"


def test_range_parameter_parsed():
    payload = _numeric_param(
        metric_value={"value_type": "range", "value": [0.05, 0.15], "unit": "%"},
    )
    out = parse_parameter_extractor_response(
        json.dumps({"parameters": [payload]}),
    )
    assert out.parameters[0].metric_value.value == [0.05, 0.15]


def test_categorical_single_parameter_parsed():
    payload = _numeric_param(
        metric_value={"value_type": "categorical", "value": "us_only"},
    )
    out = parse_parameter_extractor_response(
        json.dumps({"parameters": [payload]}),
    )
    assert out.parameters[0].metric_value.value == "us_only"


def test_categorical_list_parameter_parsed():
    payload = _numeric_param(
        metric_value={"value_type": "categorical", "value": ["us", "canada"]},
    )
    out = parse_parameter_extractor_response(
        json.dumps({"parameters": [payload]}),
    )
    assert out.parameters[0].metric_value.value == ["us", "canada"]


def test_qualitative_parameter_parsed():
    out = parse_parameter_extractor_response(
        json.dumps({"parameters": [_qualitative_param()]}),
    )
    p = out.parameters[0]
    assert p.metric_value.value_type == "null"
    assert p.metric_value.value is None
    assert p.qualitative_descriptor == "Pending BIS rulemaking"


# ---------------------------------------------------------------------------
# E. Converter
# ---------------------------------------------------------------------------


def _parse_one(payload: dict):
    return parse_parameter_extractor_response(
        json.dumps({"parameters": [payload]}),
    ).parameters[0]


def test_converter_scalar_with_unit_becomes_numeric_range():
    p = _parse_one(_numeric_param())
    constraints = parameters_to_constraints([p])
    assert len(constraints) == 1
    c = constraints[0]
    assert c.kind == "numeric_range"
    assert c.strictness == "hard"
    assert c.config["field"] == "training_compute_budget"
    assert c.config["min"] == c.config["max"] == 1e25


def test_converter_scalar_without_unit_dropped():
    """The upstream prompt forbids empty-string unit AND the parser
    won't accept it. A truly unitless scalar would parse as None
    unit; the converter drops it because a unitless scalar is too
    ambiguous to gate on."""
    payload = _numeric_param(
        metric_value={"value_type": "scalar", "value": 100.0},
    )
    p = _parse_one(payload)
    assert p.metric_value.unit is None
    assert parameters_to_constraints([p]) == []


def test_converter_range_becomes_numeric_range_with_both_bounds():
    payload = _numeric_param(
        metric_value={"value_type": "range", "value": [10.0, 20.0], "unit": "%"},
    )
    p = _parse_one(payload)
    constraints = parameters_to_constraints([p])
    assert len(constraints) == 1
    c = constraints[0]
    assert c.kind == "numeric_range"
    assert c.config["min"] == 10.0
    assert c.config["max"] == 20.0


def test_converter_categorical_single_becomes_must_include_term():
    payload = _numeric_param(
        metric_value={"value_type": "categorical", "value": "us_only"},
    )
    p = _parse_one(payload)
    constraints = parameters_to_constraints([p])
    assert len(constraints) == 1
    c = constraints[0]
    assert c.kind == "must_include_term"
    assert c.config["term"] == "us_only"


def test_converter_categorical_list_becomes_one_constraint_per_term():
    payload = _numeric_param(
        metric_value={"value_type": "categorical", "value": ["us", "canada", "mexico"]},
    )
    p = _parse_one(payload)
    constraints = parameters_to_constraints([p])
    assert len(constraints) == 3
    terms = sorted(c.config["term"] for c in constraints)
    assert terms == ["canada", "mexico", "us"]


def test_converter_qualitative_becomes_must_attribute():
    p = _parse_one(_qualitative_param())
    constraints = parameters_to_constraints([p])
    assert len(constraints) == 1
    c = constraints[0]
    assert c.kind == "must_attribute"
    assert c.strictness == "soft"
    assert "regulatory_uncertainty" in c.description
    assert "Pending BIS rulemaking" in c.description


def test_converter_strictness_flows_through():
    """A target-strictness parameter produces a target-strictness
    constraint."""
    payload = _numeric_param(constraint_strictness="target")
    p = _parse_one(payload)
    constraints = parameters_to_constraints([p])
    assert constraints[0].strictness == "target"


def test_converter_mixed_batch_produces_mixed_constraints():
    out = parse_parameter_extractor_response(json.dumps({
        "parameters": [
            _numeric_param(),
            _qualitative_param(),
        ],
    }))
    constraints = parameters_to_constraints(out.parameters)
    kinds = {c.kind for c in constraints}
    assert kinds == {"numeric_range", "must_attribute"}


# ---------------------------------------------------------------------------
# F. Drift detection
# ---------------------------------------------------------------------------


def test_metric_value_types_match_schema_literal():
    assert set(typing.get_args(MetricValueType)) == METRIC_VALUE_TYPES


def test_evidence_status_values_match_schema_literal():
    assert set(typing.get_args(EvidenceStatus)) == EVIDENCE_STATUS_VALUES


def test_constraint_strictness_match_schema_literal():
    assert set(typing.get_args(ConstraintStrictness)) == CONSTRAINT_STRICTNESS_VALUES
