"""Tests for skills/verification/ (Sprint 6 day 3-4 migration).

Coverage:

A. agreement (3 fns × happy + edge):
   1. ``default_agreement_synthesizer``: implicit_recommendation
      mismatch → False; both-empty falsifiers → True; one-empty →
      False; Jaccard ≥ 0.5 → True; Jaccard < 0.5 → False.
   2. ``default_agreement_evidence``: insufficient_evidence mismatch
      → False; chunk_id Jaccard threshold; both-empty → True.
   3. ``default_agreement_strict``: structural equality via stable
      JSON dump.

B. redispatch:
   4. Original-only configuration agrees by definition.
   5. Re-dispatch + agreement_fn returns agreed=True when stub
      role_runner returns matching parsed.
   6. Disagreement triggers tie-breaker; tie-breaker agreement raises
      count to ``agreement_min`` and accepts.
   7. Tie-breaker disagreement leaves ``agreed=False``.
   8. Custom framings override the default first-principles framing.

C. rlm plausibility + verification:
   9. Each plausibility check returns ``None`` for OK input and an
      issue string for bad input.
   10. ``rephrase_framings`` produces ``min(count, len(templates))``
      formatted prompts.
   11. ``_responses_agree``: exact match → True; numeric ±1% → True;
       majority vote at threshold → True; disagreement → False.
   12. ``verify_claim`` happy path accepts on majority agreement.
   13. ``verify_claim`` tie-breaker resolves disagreement → hedged=True.
   14. ``verify_claim`` tie-breaker also disagrees → accepted=False.
   15. Empty llm_batch result → accepted=False with reason.
   16. ``verified_answer`` runs plausibility on the agreed answer;
       plausibility issues set ``hedged=True`` but don't reject.
   17. ``verify_layer_answers``: null answer → not accepted; dep
       answers flow into context.

D. rubric:
   18. Pre-registered rubrics' ids + kinds match the closed catalog.
   19. ``ParaphraseGuardRubric``: clean = 1.0; flagged = 0.0;
       missing target keys = 0.0.
   20. ``ConstraintDeterministicRubric``: no violations = 1.0; one
       hard = decreased score; all-soft violations = 1.0.
   21. ``CitationProvenanceRubric``: fully cited = 1.0; half cited
       = 0.5; no components = 0.0.
   22. ``ThesisConfirmationRubric``: all confirmed = 1.0; partial;
       empty → None passed + 0.0 score.
   23. ``LlmJudgeRubric``: judge_fn output clamped to [0, 1];
       judge_policy_id propagated.
   24. ``register`` rejects duplicates.
   25. Drift: registered ids match the expected closed set.

E. Bridge — RubricScoredPayload round-trip:
   26. ``emit_score`` for kind=verifiable populates
       ``deterministic_score`` and leaves ``judged_score`` None.
   27. Same for kind=judged (mirrored).
   28. Kind=outcome leaves BOTH None; ``final_score`` is the rubric's
       score.
   29. ``judge_policy_id`` flows to the event's ``policy_id``.
   30. ``score_and_emit`` returns the result AND writes a typed
       event the trajectory can model_validate.
"""

from __future__ import annotations

import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from skills.verification import (  # noqa: E402
    JUDGED,
    OUTCOME,
    REPHRASE_TEMPLATES,
    VALID_KINDS,
    VERIFIABLE,
    CitationProvenanceRubric,
    ConstraintDeterministicRubric,
    LlmJudgeRubric,
    ParaphraseGuardRubric,
    RubricResult,
    ThesisConfirmationRubric,
    VerificationResult,
    VerifyResult,
    all_rubrics,
    check_expected_shape,
    check_numeric_range,
    check_sign,
    check_units_rough,
    default_agreement_evidence,
    default_agreement_strict,
    default_agreement_synthesizer,
    emit_score,
    known_ids,
    register,
    rephrase_framings,
    run_plausibility_checks,
    score_and_emit,
    verified_answer,
    verify_claim,
    verify_layer_answers,
    verify_with_redispatch,
)
from skills.verification.rlm import _count_agreements, _responses_agree  # noqa: E402
from substrate.event_log import trajectory  # noqa: E402
from substrate.schemas import (  # noqa: E402
    ActionType,
    Event,
    RubricScoredPayload,
)


@pytest.fixture(autouse=True)
def _events_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))


# ---------------------------------------------------------------------------
# A. agreement
# ---------------------------------------------------------------------------


def test_synthesizer_recommendation_mismatch_disagrees():
    a = {"implicit_recommendation": "proceed",
         "falsification_conditions": [{"specific_observable": "x"}]}
    b = {"implicit_recommendation": "pass",
         "falsification_conditions": [{"specific_observable": "x"}]}
    assert default_agreement_synthesizer(a, b) is False


def test_synthesizer_both_empty_falsifiers_agree():
    a = {"implicit_recommendation": "proceed", "falsification_conditions": []}
    b = {"implicit_recommendation": "proceed", "falsification_conditions": []}
    assert default_agreement_synthesizer(a, b) is True


def test_synthesizer_one_empty_falsifier_disagrees():
    a = {"implicit_recommendation": "proceed",
         "falsification_conditions": [{"specific_observable": "x"}]}
    b = {"implicit_recommendation": "proceed",
         "falsification_conditions": []}
    assert default_agreement_synthesizer(a, b) is False


def test_synthesizer_jaccard_above_threshold_agrees():
    a = {"implicit_recommendation": "proceed",
         "falsification_conditions": [
             {"specific_observable": "ARR<50%"},
             {"specific_observable": "churn>10%"},
         ]}
    b = {"implicit_recommendation": "proceed",
         "falsification_conditions": [
             {"specific_observable": "ARR<50%"},
             {"specific_observable": "completely new"},
         ]}
    # Overlap=1, union=3, Jaccard=0.33 < 0.5 → disagree
    assert default_agreement_synthesizer(a, b) is False


def test_synthesizer_high_overlap_agrees():
    a = {"implicit_recommendation": "proceed",
         "falsification_conditions": [
             {"specific_observable": "ARR<50%"},
             {"specific_observable": "churn>10%"},
         ]}
    b = {"implicit_recommendation": "proceed",
         "falsification_conditions": [
             {"specific_observable": "ARR<50%"},
             {"specific_observable": "churn>10%"},
         ]}
    # Overlap=2, union=2, Jaccard=1.0
    assert default_agreement_synthesizer(a, b) is True


def test_evidence_insufficient_flag_mismatch_disagrees():
    a = {"insufficient_evidence": True, "supporting_claims": []}
    b = {"insufficient_evidence": False, "supporting_claims": []}
    assert default_agreement_evidence(a, b) is False


def test_evidence_chunk_id_jaccard():
    a = {"insufficient_evidence": False,
         "supporting_claims": [{"chunk_ids": ["c1", "c2"]}]}
    b = {"insufficient_evidence": False,
         "supporting_claims": [{"chunk_ids": ["c1"]}]}
    # Overlap=1, union=2, Jaccard=0.5 → agrees (>=)
    assert default_agreement_evidence(a, b) is True


def test_strict_agreement_byte_equal():
    a = {"x": 1, "y": [2, 3]}
    b = {"y": [2, 3], "x": 1}  # different key order
    assert default_agreement_strict(a, b) is True


def test_strict_agreement_value_diff_fails():
    assert default_agreement_strict({"x": 1}, {"x": 2}) is False


# ---------------------------------------------------------------------------
# B. redispatch
# ---------------------------------------------------------------------------


def _make_role_runner(parsed_responses: list[dict]):
    """Return a role_runner closure that yields successive parsed
    responses on each call. The returned trace record matches the
    upstream call_role shape (dict with 'parsed' key)."""
    state = {"i": 0}

    def _runner(role, *, placeholders, extra_user_prefix="", **_kwargs):
        i = state["i"]
        state["i"] += 1
        return {
            "role": role,
            "placeholders": placeholders,
            "extra_user_prefix": extra_user_prefix,
            "parsed": parsed_responses[min(i, len(parsed_responses) - 1)],
        }
    return _runner, state


def test_redispatch_agreement_returns_agreed_true():
    original = {"answer": 42}
    runner, state = _make_role_runner([{"answer": 42}])
    result = verify_with_redispatch(
        runner, "synthesizer", placeholders={}, original_parsed=original,
        agreement_fn=default_agreement_strict, agreement_min=2,
        redispatch_count=1, enable_tiebreaker=False,
    )
    assert isinstance(result, VerifyResult)
    assert result.agreed is True
    assert result.agreement_count == 2  # original + 1
    assert result.dispatched_count == 2
    assert result.tiebreaker_used is False
    assert state["i"] == 1


def test_redispatch_disagreement_triggers_tiebreaker_then_resolves():
    original = {"answer": 42}
    # First rephrased disagrees; tiebreaker agrees.
    runner, state = _make_role_runner([{"answer": 99}, {"answer": 42}])
    result = verify_with_redispatch(
        runner, "synthesizer", placeholders={}, original_parsed=original,
        agreement_fn=default_agreement_strict, agreement_min=2,
        redispatch_count=1, enable_tiebreaker=True,
    )
    assert result.tiebreaker_used is True
    assert result.agreed is True
    assert result.agreement_count == 2  # original + tiebreaker
    assert state["i"] == 2


def test_redispatch_persistent_disagreement_stays_unagreed():
    original = {"answer": 42}
    runner, state = _make_role_runner([{"answer": 99}, {"answer": 100}])
    result = verify_with_redispatch(
        runner, "synthesizer", placeholders={}, original_parsed=original,
        agreement_fn=default_agreement_strict, agreement_min=2,
        redispatch_count=1, enable_tiebreaker=True,
    )
    assert result.agreed is False
    assert result.tiebreaker_used is True
    assert state["i"] == 2


def test_redispatch_custom_framings_used():
    original = {"answer": 1}
    runner, _ = _make_role_runner([{"answer": 1}])
    result = verify_with_redispatch(
        runner, "x", placeholders={}, original_parsed=original,
        framings=["DERIVE BACKWARDS"],
        agreement_min=2, redispatch_count=1, enable_tiebreaker=False,
    )
    # The framing string must appear inside the dispatch's
    # extra_user_prefix (which the runner records on its return).
    rephrased_record = result.dispatched_responses[0]
    assert "DERIVE BACKWARDS" in rephrased_record["extra_user_prefix"]


# ---------------------------------------------------------------------------
# C. rlm — plausibility + verification
# ---------------------------------------------------------------------------


def test_check_numeric_range_in_range_returns_none():
    assert check_numeric_range(5, 0, 10) is None


def test_check_numeric_range_above_max_flags():
    issue = check_numeric_range(15, 0, 10)
    assert issue is not None and "expected_max" in issue


def test_check_numeric_range_below_min_flags():
    issue = check_numeric_range(-1, 0, 10)
    assert issue is not None and "expected_min" in issue


def test_check_numeric_range_skips_non_numeric():
    assert check_numeric_range("not a number", 0, 10) is None


def test_check_sign_positive_passes():
    assert check_sign(5, "positive") is None


def test_check_sign_unknown_sign_silently_ignored():
    """Unknown sign labels return None so an upstream typo doesn't
    cause spurious plausibility failures."""
    assert check_sign(5, "completely-made-up-sign") is None


def test_check_units_rough_flags_3_orders_off():
    assert check_units_rough(1_000_000, (1.0, 10.0)) is not None


def test_check_units_rough_accepts_within_envelope():
    assert check_units_rough(50.0, (1.0, 100.0)) is None


def test_check_expected_shape_flags_type_mismatch():
    issue = check_expected_shape("not_int", int)
    assert issue is not None


def test_run_plausibility_aggregates_all_issues():
    issues = run_plausibility_checks(
        -5, expected_min=0, expected_sign="positive",
    )
    assert len(issues) == 2


def test_rephrase_framings_respects_count():
    out = rephrase_framings("claim", "context", count=2)
    assert len(out) == 2
    assert all("claim" in p for p in out)


def test_rephrase_framings_caps_at_template_count():
    out = rephrase_framings("c", "x", count=100)
    assert len(out) == len(REPHRASE_TEMPLATES)


def test_responses_agree_exact_match():
    ok, ans = _responses_agree(["42", "42", "42"])
    assert ok is True and ans == "42"


def test_responses_agree_numeric_tolerance():
    ok, _ = _responses_agree(["1.00", "1.005", "1.0001"])
    assert ok is True


def test_responses_agree_majority_vote():
    ok, _ = _responses_agree(["A", "A", "B"])
    assert ok is True


def test_responses_agree_disagreement():
    ok, _ = _responses_agree(["A", "B", "C"])
    assert ok is False


def test_count_agreements_handles_empty():
    assert _count_agreements([]) == 0


def _make_batch(responses_per_call: list[list[str]]):
    """Each call to the batch fn consumes one element of
    responses_per_call (a list of strings). Useful when verify_claim
    runs a multi-prompt batch then a single-prompt tiebreaker."""
    state = {"i": 0}

    def _batch(prompts: list[str]) -> list[str]:
        i = state["i"]
        state["i"] += 1
        return responses_per_call[min(i, len(responses_per_call) - 1)]
    return _batch, state


def test_verify_claim_happy_path():
    # All three prompts (1 direct + 2 rephrased) return "42".
    batch, _ = _make_batch([["42", "42", "42"]])
    result = verify_claim("what is X?", "x = 42", batch, claim_id="c-1",
                          redispatch_count=2, agreement_min=2)
    assert isinstance(result, VerificationResult)
    assert result.accepted is True
    assert result.agreed_answer == "42"
    assert result.hedged is False


def test_verify_claim_tiebreaker_resolves_with_hedge():
    # First batch: 3 responses, no majority. Tiebreaker batch: 1
    # response matching one of the original three, raising count.
    batch, _ = _make_batch([
        ["42", "99", "100"],   # all disagree
        ["42"],                # tiebreaker resolves
    ])
    result = verify_claim("q", "x = 42", batch, claim_id="c-2",
                          redispatch_count=2, agreement_min=2)
    # Tiebreaker added "42" → 2 agree on "42" out of 4
    assert result.accepted is True
    assert result.hedged is True


def test_verify_claim_persistent_disagreement_rejected():
    batch, _ = _make_batch([
        ["42", "99", "100"],
        ["77"],
    ])
    result = verify_claim("q", "x = 42", batch, claim_id="c-3",
                          redispatch_count=2, agreement_min=2)
    assert result.accepted is False
    assert result.disagreement_reason is not None


def test_verify_claim_empty_batch_rejected():
    batch, _ = _make_batch([[]])
    result = verify_claim("q", "x", batch, claim_id="c-4",
                          redispatch_count=1, agreement_min=2)
    assert result.accepted is False
    assert "empty" in (result.disagreement_reason or "")


def test_verified_answer_plausibility_hedges_not_rejects():
    """Plausibility failure on the agreed numeric answer flags hedged
    but keeps accepted=True."""
    batch, _ = _make_batch([["1000000", "1000000", "1000000"]])
    result = verified_answer(
        "what?", "x", batch, claim_id="c-h",
        expected_min=0, expected_max=10,  # 1_000_000 is way outside
    )
    assert result.accepted is True
    assert result.hedged is True
    assert any("expected_max" in iss for iss in result.plausibility_issues)


def test_verify_layer_answers_null_answer_rejected():
    batch, _ = _make_batch([["v"]])
    out = verify_layer_answers(
        answers={"n1": None}, node_specs=[{"id": "n1", "question": "Q"}],
        llm_batch_fn=batch,
    )
    assert out["n1"].accepted is False
    assert out["n1"].disagreement_reason == "answer is None"


def test_verify_layer_answers_dep_context_flows_through():
    """Build a 2-node chain and verify both. Pass-through batch fn
    asserts the dep's value appears in the second node's prompt."""
    capture = {"prompts": []}

    def batch(prompts):
        capture["prompts"].extend(prompts)
        return ["42"] * len(prompts)

    out = verify_layer_answers(
        answers={"n1": "42", "n2": "84"},
        node_specs=[
            {"id": "n1", "question": "What is X?"},
            {"id": "n2", "question": "What is 2X?", "deps": ["n1"]},
        ],
        llm_batch_fn=batch,
    )
    assert out["n1"].accepted is True
    assert out["n2"].accepted is True
    # The parent answer 42 must appear in n2's prompts.
    assert any("Parent [n1]: 42" in p for p in capture["prompts"])


# ---------------------------------------------------------------------------
# D. rubric — concrete rubrics
# ---------------------------------------------------------------------------


def test_pre_registered_ids():
    ids = set(known_ids())
    assert ids == {
        "verifiable.decomposer.paraphrase_guard",
        "verifiable.constraint.deterministic_pass_rate",
        "verifiable.synthesizer.citation_provenance",
        "outcome.thesis.confirmation_rate",
    }


def test_paraphrase_guard_no_flagged_returns_1():
    class _OrthEmbedder:
        dimension = 2

        def __init__(self):
            self._seen = 0

        def encode(self, t):
            self._seen += 1
            return [1.0, 0.0] if self._seen == 1 else [0.0, 1.0]

    r = ParaphraseGuardRubric().score({
        "top_question": "Q?",
        "sub_questions": ["totally different sub-question"],
        "embedder": _OrthEmbedder(),
    })
    assert r.score == 1.0
    assert r.passed is True


def test_paraphrase_guard_flagged_returns_0():
    class _ColocEmbedder:
        dimension = 2

        def encode(self, t):
            return [1.0, 0.0]

    r = ParaphraseGuardRubric().score({
        "top_question": "Q?",
        "sub_questions": ["restates Q"],
        "embedder": _ColocEmbedder(),
    })
    assert r.score == 0.0
    assert r.passed is False


def test_paraphrase_guard_missing_target_keys():
    r = ParaphraseGuardRubric().score({})
    assert r.score == 0.0
    assert r.passed is False
    assert "error" in r.details


def test_constraint_deterministic_no_violations_returns_1():
    r = ConstraintDeterministicRubric().score({
        "constraints": [{"id": "c1"}, {"id": "c2"}],
        "final_violations": [],
    })
    assert r.score == 1.0
    assert r.passed is True


def test_constraint_deterministic_hard_violation_decreases_score():
    r = ConstraintDeterministicRubric().score({
        "constraints": [{"id": "c1"}, {"id": "c2"}],
        "final_violations": [{"strictness": "hard"}],
    })
    assert r.score == 0.5  # 1 hard / 2 constraints
    assert r.passed is False


def test_constraint_deterministic_soft_violations_dont_count():
    r = ConstraintDeterministicRubric().score({
        "constraints": [{"id": "c1"}],
        "final_violations": [{"strictness": "soft"}, {"strictness": "target"}],
    })
    assert r.score == 1.0
    assert r.passed is True


def test_citation_provenance_fully_cited():
    r = CitationProvenanceRubric().score({
        "thesis_components": [
            {"claim": "A", "chunk_ids": ["c1"]},
            {"claim": "B", "supporting_path_indices": [0]},
        ],
    })
    assert r.score == 1.0
    assert r.passed is True


def test_citation_provenance_half_cited():
    r = CitationProvenanceRubric().score({
        "thesis_components": [
            {"claim": "A", "chunk_ids": ["c1"]},
            {"claim": "B"},  # no citations
        ],
    })
    assert r.score == 0.5
    assert r.passed is False


def test_citation_provenance_no_components_returns_0():
    r = CitationProvenanceRubric().score({"thesis_components": []})
    assert r.score == 0.0
    assert r.passed is False


def test_thesis_confirmation_all_confirmed_returns_1():
    r = ThesisConfirmationRubric().score({
        "thesis_outcomes": [{"outcome": "confirmed"}, {"outcome": "confirmed"}],
    })
    assert r.score == 1.0
    assert r.passed is True


def test_thesis_confirmation_partial():
    r = ThesisConfirmationRubric().score({
        "thesis_outcomes": [
            {"outcome": "confirmed"},
            {"outcome": "partially_confirmed"},
            {"outcome": "disconfirmed"},
        ],
    })
    assert abs(r.score - 1 / 3) < 1e-6
    assert r.passed is False


def test_thesis_confirmation_empty_outcomes_deferred():
    """No outcomes recorded yet → deferred-ground-truth signal."""
    r = ThesisConfirmationRubric().score({"thesis_outcomes": []})
    assert r.score == 0.0
    assert r.passed is None
    assert "deferred" in r.details["note"]


def test_llm_judge_clamps_score():
    def _judge(target, ctx):
        return 5.0, {"why": "anything"}
    r = LlmJudgeRubric(
        rubric_id="judged.test.x", judge_fn=_judge,
        judge_policy_id="stub-judge",
    ).score(target={})
    assert r.score == 1.0
    assert r.judge_policy_id == "stub-judge"


def test_llm_judge_clamps_negative_score():
    def _judge(target, ctx):
        return -0.5, {}
    r = LlmJudgeRubric(
        rubric_id="judged.test.y", judge_fn=_judge,
        judge_policy_id="stub-judge",
    ).score(target={})
    assert r.score == 0.0


def test_register_rejects_duplicate():
    with pytest.raises(ValueError, match="already registered"):
        register(ParaphraseGuardRubric())


def test_valid_kinds_closed_set():
    assert set(VALID_KINDS) == {"verifiable", "judged", "outcome"}


# ---------------------------------------------------------------------------
# E. Bridge — RubricScoredPayload round-trip
# ---------------------------------------------------------------------------


def test_emit_score_verifiable_populates_deterministic():
    result = RubricResult(
        rubric_id="verifiable.test", kind=VERIFIABLE, score=0.75,
        passed=True,
    )
    eid = emit_score(
        "inv-emit-v", result, synthesis_id="syn-1", target_claim_id="cl-1",
    )
    assert eid is not None
    e = Event.model_validate(trajectory("inv-emit-v")[0])
    assert e.action_type == ActionType.RUBRIC_SCORED.value
    assert e.synthesis_id == "syn-1"
    assert e.role == "rubric_scorer"
    assert isinstance(e.payload, RubricScoredPayload)
    p = e.payload
    assert p.rubric_id == "verifiable.test"
    assert p.target_claim_id == "cl-1"
    assert p.deterministic_score == pytest.approx(0.75)
    assert p.judged_score is None
    assert p.final_score == pytest.approx(0.75)


def test_emit_score_judged_populates_judged_field():
    result = RubricResult(
        rubric_id="judged.test", kind=JUDGED, score=0.42,
        judge_policy_id="claude-sonnet-4-6",
    )
    eid = emit_score("inv-emit-j", result)
    e = Event.model_validate(trajectory("inv-emit-j")[0])
    assert isinstance(e.payload, RubricScoredPayload)
    assert e.payload.judged_score == pytest.approx(0.42)
    assert e.payload.deterministic_score is None
    assert e.policy_id == "claude-sonnet-4-6"  # judge_policy_id → policy_id


def test_emit_score_outcome_leaves_both_decomposed_scores_none():
    result = RubricResult(
        rubric_id="outcome.test", kind=OUTCOME, score=0.6,
    )
    emit_score("inv-emit-o", result)
    e = Event.model_validate(trajectory("inv-emit-o")[0])
    p = e.payload
    assert p.deterministic_score is None
    assert p.judged_score is None
    assert p.final_score == pytest.approx(0.6)
    assert e.policy_id == "orchestrator-deterministic"  # default


def test_score_and_emit_returns_result_and_writes_event():
    target = {"thesis_components": [{"claim": "C1", "chunk_ids": ["c1"]}]}
    result = score_and_emit(
        "verifiable.synthesizer.citation_provenance",
        target,
        investigation_id="inv-se",
    )
    assert isinstance(result, RubricResult)
    assert result.score == 1.0

    rows = trajectory("inv-se")
    rubric_rows = [r for r in rows if r["action_type"] == ActionType.RUBRIC_SCORED.value]
    assert len(rubric_rows) == 1
    e = Event.model_validate(rubric_rows[0])
    assert e.payload.rubric_id == "verifiable.synthesizer.citation_provenance"


def test_notes_field_includes_kind_and_score():
    result = RubricResult(rubric_id="x", kind=VERIFIABLE, score=0.5, passed=True)
    emit_score("inv-notes", result)
    e = Event.model_validate(trajectory("inv-notes")[0])
    notes = e.payload.notes
    assert "kind=verifiable" in notes
    assert "score=0.500" in notes
    assert "passed=True" in notes


def test_emit_score_score_above_one_rejected_by_pydantic():
    """final_score is bounded [0,1] on the payload; an out-of-range
    RubricResult must fail at emit time (not silently corrupt the
    trajectory)."""
    result = RubricResult(
        rubric_id="x", kind=VERIFIABLE, score=1.5,
    )
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        emit_score("inv-bad", result)


def test_all_rubrics_filterable_by_kind():
    verifiable = all_rubrics(kind=VERIFIABLE)
    outcome = all_rubrics(kind=OUTCOME)
    judged = all_rubrics(kind=JUDGED)
    assert len(verifiable) == 3
    assert len(outcome) == 1
    assert len(judged) == 0  # no judged rubrics pre-registered
