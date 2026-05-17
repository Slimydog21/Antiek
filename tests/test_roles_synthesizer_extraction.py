"""Tests for roles/synthesizer/ (Sprint 7 day 5).

Coverage:

A. Prompt:
   1. ``render_user_template`` substitutes all 5 placeholders.
   2. ``render_full_prompt`` includes system + user;
      ``extra_user_prefix`` (the revision prefix) threads through.
   3. ``build_revision_prefix`` formats violations into a bulleted
      list the model can act on.
   4. ``build_revision_prefix`` empty list → empty string.

B. Parser — happy path:
   5. Well-formed thesis parses (all 7 top-level fields).
   6. ``insufficient_evidence`` recommendation allows empty
      provenance.

C. Parser — closed-vocabulary failures:
   7. Bad ``implicit_recommendation`` ("undetermined", "medium").
   8. Bad ``confidence`` ("medium" trap).
   9. Bad ``severity_if_manifested``.
   10. ``conviction_level`` out of [0, 1].
   11. ``effective_source_tier=0`` REJECTED.
   12. ``effective_source_tier=6`` rejected.
   13. ``effective_source_tier=True`` (bool) rejected.

D. Parser — tier-hedging discipline (spec §C.3):
   14. Tier 5 component REJECTED (must be excluded).
   15. null-tier without ``hedging_required=True`` rejected.
   16. null-tier without ``confidence="unknown"`` rejected.
   17. Tier 4 with confidence="high" rejected.
   18. Tier 4 without hedging_required rejected.
   19. Tier 3 without hedging_required rejected.
   20. Tier 2 with no hedging_required OK.
   21. Tier 1 with no hedging_required OK.

E. Parser — provenance discipline:
   22. Component with neither chunks NOR paths rejected when
       recommendation is "proceed".
   23. Same component accepted when recommendation is
       "insufficient_evidence".

F. Parser — reasoning_paths_used:
   24. ``support_summary`` <20 chars rejected.
   25. Empty ``path_node_ids`` rejected.
   26. Empty ``reasoning_paths_used`` list OK (typical for
       insufficient_evidence).

G. Drift detection:
   27. CONFIDENCE_LEVELS == schema ConfidenceLevel.
   28. IMPLICIT_RECOMMENDATIONS subset of SynthesisRecommendation
       (the schema also accepts "undetermined" for back-compat).
   29. EXECUTION_RISK_SEVERITIES == ThesisRiskSeverity.
"""

from __future__ import annotations

import json
import os
import sys
import typing

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from roles.synthesizer import (  # noqa: E402
    CONFIDENCE_LEVELS,
    EXECUTION_RISK_SEVERITIES,
    IMPLICIT_RECOMMENDATIONS,
    SUPPORT_SUMMARY_MIN_LENGTH,
    SYNTHESIZER_SYSTEM_PROMPT,
    SynthesizerValidationError,
    build_revision_prefix,
    parse_synthesizer_response,
    render_full_prompt,
    render_user_template,
)
from substrate.schemas import (  # noqa: E402
    ConfidenceLevel,
    SynthesisRecommendation,
    ThesisRiskSeverity,
)


# Minimal Violation lookalike for build_revision_prefix test
class _V:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


# ---------------------------------------------------------------------------
# A. Prompt
# ---------------------------------------------------------------------------


def test_render_user_template_substitutes_all_placeholders():
    s = render_user_template(
        question="Q?", decomposition_block="DEC", evidence_block="EV",
        parameters_block="PAR", substrate_block="SUB",
    )
    for tok in ("Q?", "DEC", "EV", "PAR", "SUB"):
        assert tok in s
    for unsub in (
        "{{question}}", "{{decomposition_block}}",
        "{{evidence_block}}", "{{parameters_block}}",
        "{{substrate_block}}",
    ):
        assert unsub not in s


def test_render_full_prompt_includes_system_and_user():
    p = render_full_prompt(
        question="Q", decomposition_block="D", evidence_block="E",
        parameters_block="P", substrate_block="S",
    )
    assert SYNTHESIZER_SYSTEM_PROMPT in p
    assert "Q" in p


def test_render_full_prompt_extra_user_prefix_threads_in_user_portion():
    p = render_full_prompt(
        question="Q", decomposition_block="D", evidence_block="E",
        parameters_block="P", substrate_block="S",
        extra_user_prefix="REVISION",
    )
    sys_end = p.index(SYNTHESIZER_SYSTEM_PROMPT) + len(SYNTHESIZER_SYSTEM_PROMPT)
    rev_idx = p.index("REVISION")
    assert rev_idx > sys_end


def test_build_revision_prefix_formats_violation_bullets():
    out = build_revision_prefix([
        _V(constraint_id="c-1", constraint_kind="must_attribute",
           strictness="hard", reason="claim X has no attribution",
           target_claim_id="cl-3"),
    ])
    assert "Constraint-loop revision" in out
    assert "'c-1'" in out
    assert "must_attribute" in out
    assert "'cl-3'" in out
    assert "claim X has no attribution" in out


def test_build_revision_prefix_empty_returns_empty():
    assert build_revision_prefix([]) == ""


# ---------------------------------------------------------------------------
# B. Parser happy path
# ---------------------------------------------------------------------------


def _good_thesis(**overrides) -> dict:
    base = {
        "thesis_summary": "X is well-supported by primary evidence.",
        "implicit_recommendation": "proceed",
        "thesis_components": [
            {
                "claim": "X is observable in primary sources.",
                "confidence": "high",
                "confidence_basis": "two SEC filings + one peer-reviewed paper",
                "supporting_chunk_ids": ["chunk-1", "chunk-2"],
                "supporting_path_indices": [0],
                "effective_source_tier": 1,
                "hedging_required": False,
            },
        ],
        "falsification_conditions": [
            {
                "condition": "ARR growth falls below 80% YoY",
                "specific_observable": "Q4 financial disclosure",
                "timeframe": "within 4 quarters",
            },
        ],
        "execution_risks": [
            {
                "risk": "Key engineering team attrition",
                "severity_if_manifested": "high",
                "leading_indicator": "voluntary departure rate",
            },
        ],
        "constraint_compliance": {
            "hard_constraints_satisfied": True,
            "soft_constraints_violated": [],
            "violations_justified": [],
        },
        "reasoning_paths_used": [
            {
                "path_node_ids": ["n-1", "n-2"],
                "path_edge_ids": ["e-1"],
                "support_summary": "Path grounds the primary claim about X.",
            },
        ],
        "conviction_level": 0.75,
    }
    base.update(overrides)
    return base


def test_parser_happy_path():
    out = parse_synthesizer_response(json.dumps(_good_thesis()))
    assert out.thesis_summary == "X is well-supported by primary evidence."
    assert out.implicit_recommendation == "proceed"
    assert len(out.thesis_components) == 1
    assert len(out.falsification_conditions) == 1
    assert len(out.execution_risks) == 1
    assert len(out.reasoning_paths_used) == 1
    assert out.conviction_level == 0.75
    assert out.constraint_compliance.hard_constraints_satisfied is True


def test_parser_insufficient_evidence_allows_empty_provenance():
    payload = _good_thesis(
        implicit_recommendation="insufficient_evidence",
        thesis_components=[{
            "claim": "Evidence is silent on the core question.",
            "confidence": "unknown",
            "supporting_chunk_ids": [],
            "supporting_path_indices": [],
            "effective_source_tier": None,
            "hedging_required": True,
        }],
        reasoning_paths_used=[],
    )
    out = parse_synthesizer_response(json.dumps(payload))
    assert out.implicit_recommendation == "insufficient_evidence"


# ---------------------------------------------------------------------------
# C. Parser — closed-vocabulary failures
# ---------------------------------------------------------------------------


def test_parser_bad_recommendation_undetermined_rejected():
    payload = _good_thesis(implicit_recommendation="undetermined")
    with pytest.raises(SynthesizerValidationError, match="implicit_recommendation"):
        parse_synthesizer_response(json.dumps(payload))


def test_parser_confidence_medium_rejected():
    payload = _good_thesis()
    payload["thesis_components"][0]["confidence"] = "medium"
    with pytest.raises(SynthesizerValidationError, match="confidence"):
        parse_synthesizer_response(json.dumps(payload))


def test_parser_bad_severity_rejected():
    payload = _good_thesis()
    payload["execution_risks"][0]["severity_if_manifested"] = "catastrophic"
    with pytest.raises(SynthesizerValidationError, match="severity_if_manifested"):
        parse_synthesizer_response(json.dumps(payload))


def test_parser_conviction_out_of_range_rejected():
    payload = _good_thesis(conviction_level=1.5)
    with pytest.raises(SynthesizerValidationError, match="conviction_level"):
        parse_synthesizer_response(json.dumps(payload))


def test_parser_effective_source_tier_zero_rejected():
    payload = _good_thesis()
    payload["thesis_components"][0]["effective_source_tier"] = 0
    with pytest.raises(SynthesizerValidationError, match="effective_source_tier"):
        parse_synthesizer_response(json.dumps(payload))


def test_parser_effective_source_tier_six_rejected():
    payload = _good_thesis()
    payload["thesis_components"][0]["effective_source_tier"] = 6
    with pytest.raises(SynthesizerValidationError, match="effective_source_tier"):
        parse_synthesizer_response(json.dumps(payload))


def test_parser_effective_source_tier_bool_rejected():
    payload = _good_thesis()
    payload["thesis_components"][0]["effective_source_tier"] = True
    with pytest.raises(SynthesizerValidationError, match="bool"):
        parse_synthesizer_response(json.dumps(payload))


# ---------------------------------------------------------------------------
# D. Parser — tier-hedging discipline
# ---------------------------------------------------------------------------


def test_tier_5_component_rejected():
    payload = _good_thesis()
    payload["thesis_components"][0]["effective_source_tier"] = 5
    with pytest.raises(SynthesizerValidationError, match="Tier 5"):
        parse_synthesizer_response(json.dumps(payload))


def test_null_tier_without_hedging_required_rejected():
    payload = _good_thesis()
    payload["thesis_components"][0]["effective_source_tier"] = None
    payload["thesis_components"][0]["hedging_required"] = False
    payload["thesis_components"][0]["confidence"] = "unknown"
    with pytest.raises(SynthesizerValidationError, match="hedging_required"):
        parse_synthesizer_response(json.dumps(payload))


def test_null_tier_without_unknown_confidence_rejected():
    payload = _good_thesis()
    payload["thesis_components"][0]["effective_source_tier"] = None
    payload["thesis_components"][0]["hedging_required"] = True
    payload["thesis_components"][0]["confidence"] = "moderate"
    with pytest.raises(SynthesizerValidationError, match="unknown"):
        parse_synthesizer_response(json.dumps(payload))


def test_null_tier_with_unknown_and_hedging_ok():
    payload = _good_thesis()
    payload["thesis_components"][0]["effective_source_tier"] = None
    payload["thesis_components"][0]["hedging_required"] = True
    payload["thesis_components"][0]["confidence"] = "unknown"
    out = parse_synthesizer_response(json.dumps(payload))
    assert out.thesis_components[0].effective_source_tier is None


def test_tier_4_high_confidence_rejected():
    payload = _good_thesis()
    payload["thesis_components"][0]["effective_source_tier"] = 4
    payload["thesis_components"][0]["hedging_required"] = True
    payload["thesis_components"][0]["confidence"] = "high"
    with pytest.raises(SynthesizerValidationError, match="Tier 4|confidence"):
        parse_synthesizer_response(json.dumps(payload))


def test_tier_4_without_hedging_rejected():
    payload = _good_thesis()
    payload["thesis_components"][0]["effective_source_tier"] = 4
    payload["thesis_components"][0]["hedging_required"] = False
    payload["thesis_components"][0]["confidence"] = "low"
    with pytest.raises(SynthesizerValidationError, match="hedging_required"):
        parse_synthesizer_response(json.dumps(payload))


def test_tier_4_with_low_and_hedging_ok():
    payload = _good_thesis()
    payload["thesis_components"][0]["effective_source_tier"] = 4
    payload["thesis_components"][0]["hedging_required"] = True
    payload["thesis_components"][0]["confidence"] = "low"
    out = parse_synthesizer_response(json.dumps(payload))
    assert out.thesis_components[0].effective_source_tier == 4


def test_tier_3_without_hedging_rejected():
    payload = _good_thesis()
    payload["thesis_components"][0]["effective_source_tier"] = 3
    payload["thesis_components"][0]["hedging_required"] = False
    with pytest.raises(SynthesizerValidationError, match="hedging_required"):
        parse_synthesizer_response(json.dumps(payload))


def test_tier_2_without_hedging_ok():
    payload = _good_thesis()
    payload["thesis_components"][0]["effective_source_tier"] = 2
    payload["thesis_components"][0]["hedging_required"] = False
    payload["thesis_components"][0]["confidence"] = "moderate"
    out = parse_synthesizer_response(json.dumps(payload))
    assert out.thesis_components[0].hedging_required is False


def test_tier_1_without_hedging_ok():
    out = parse_synthesizer_response(json.dumps(_good_thesis()))
    assert out.thesis_components[0].effective_source_tier == 1
    assert out.thesis_components[0].hedging_required is False


# ---------------------------------------------------------------------------
# E. Parser — provenance discipline
# ---------------------------------------------------------------------------


def test_component_with_no_provenance_rejected_under_proceed():
    payload = _good_thesis()
    payload["thesis_components"][0]["supporting_chunk_ids"] = []
    payload["thesis_components"][0]["supporting_path_indices"] = []
    with pytest.raises(SynthesizerValidationError, match="provenance"):
        parse_synthesizer_response(json.dumps(payload))


def test_path_only_provenance_ok():
    """Path citations alone are sufficient — no chunks required if
    a graph path grounds the claim."""
    payload = _good_thesis()
    payload["thesis_components"][0]["supporting_chunk_ids"] = []
    payload["thesis_components"][0]["supporting_path_indices"] = [0, 2]
    out = parse_synthesizer_response(json.dumps(payload))
    assert out.thesis_components[0].supporting_path_indices == (0, 2)


# ---------------------------------------------------------------------------
# F. Parser — reasoning_paths_used
# ---------------------------------------------------------------------------


def test_support_summary_below_minimum_length_rejected():
    payload = _good_thesis()
    payload["reasoning_paths_used"][0]["support_summary"] = "too short"  # 9 < 20
    with pytest.raises(SynthesizerValidationError, match="support_summary"):
        parse_synthesizer_response(json.dumps(payload))


def test_empty_path_node_ids_rejected():
    payload = _good_thesis()
    payload["reasoning_paths_used"][0]["path_node_ids"] = []
    with pytest.raises(SynthesizerValidationError, match="path_node_ids"):
        parse_synthesizer_response(json.dumps(payload))


def test_empty_reasoning_paths_ok():
    payload = _good_thesis(reasoning_paths_used=[])
    out = parse_synthesizer_response(json.dumps(payload))
    assert out.reasoning_paths_used == ()


def test_support_summary_min_length_documented():
    """The 20-char floor is the upstream prompt's explicit value."""
    assert SUPPORT_SUMMARY_MIN_LENGTH == 20


# ---------------------------------------------------------------------------
# G. Drift detection
# ---------------------------------------------------------------------------


def test_confidence_levels_match_schema_literal():
    assert CONFIDENCE_LEVELS == set(typing.get_args(ConfidenceLevel))


def test_implicit_recommendations_subset_of_schema_recommendation():
    """The synthesizer emits the 4-value vocabulary; the schema's
    SynthesisRecommendation accepts those PLUS 'undetermined' for
    archive back-compat."""
    schema_vals = set(typing.get_args(SynthesisRecommendation))
    assert IMPLICIT_RECOMMENDATIONS.issubset(schema_vals)
    assert "insufficient_evidence" in schema_vals  # Sprint 7 day 5 addition


def test_execution_risk_severities_match_thesis_severity_literal():
    assert EXECUTION_RISK_SEVERITIES == set(typing.get_args(ThesisRiskSeverity))
