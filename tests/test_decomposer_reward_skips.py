"""A skipped rubric does not count against the decomposer's reward.

``ParaphraseGuardRubric`` reports ``passed=None`` ("embedder unavailable")
when it cannot run. ``DecomposerEnvironment.reward`` used to weight that skip
as a zero score while still counting its weight, so a rollout that passed
every rubric that could run scored 0.5882 instead of 1.0. A skipped rubric is
now left out of both the weighted sum and ``used_weight``; a rubric that
failed or errored (``passed=False``) still counts as zero.

Only a VERIFIABLE rubric's ``passed=None`` means "did not run". Judged
rubrics report ``passed=None`` with a real score on every call, so they
always count, including a judged zero.
"""

from __future__ import annotations

import json

import pytest

from interfaces.research.environments import DecomposerEnvironment, DecomposerTask
from skills.verification.rubric import JUDGED, VERIFIABLE, LlmJudgeRubric, RubricResult
from substrate.constants import KEYWORDS_MIN, SUB_QUESTIONS_MIN

PARAPHRASE = "verifiable.decomposer.paraphrase_guard"


def _valid_policy(task, ctx):
    payload = {
        "decomposition": [
            {"sub_question": f"Aspect {i} of analysis", "category": "context",
             "evidence_type_required": "any"}
            for i in range(SUB_QUESTIONS_MIN)
        ],
        "keywords": [{"keyword": f"kw{i}", "synonyms": []} for i in range(KEYWORDS_MIN)],
    }
    return json.dumps(payload), "stub/v0"


def _skipped(target, *, context=None):
    return RubricResult(
        rubric_id=PARAPHRASE, kind=VERIFIABLE, score=0.0, passed=None,
        details={"skipped_reason": "embedder unavailable: ImportError()"},
    )


@pytest.fixture
def env():
    e = DecomposerEnvironment(policy_fn=_valid_policy)
    e.paraphrase_rubric.score = _skipped  # type: ignore[assignment]
    return e


def test_a_skipped_rubric_leaves_a_perfect_rollout_at_full_reward(env):
    reward = env.reward(env.rollout(DecomposerTask(task_id="t", top_question="Q")))
    skipped = next(b for b in reward.breakdown if b.rubric_id == PARAPHRASE)
    assert skipped.passed is None  # still reported, for transparency
    assert reward.total == pytest.approx(1.0)
    assert reward.passed_all_verifiable is True


def test_a_failed_rubric_still_counts_as_zero(env):
    def failed(target, *, context=None):
        return RubricResult(rubric_id=PARAPHRASE, kind=VERIFIABLE, score=0.0,
                            passed=False, details={})

    env.paraphrase_rubric.score = failed  # type: ignore[assignment]
    reward = env.reward(env.rollout(DecomposerTask(task_id="t", top_question="Q")))
    weights = env.weights
    expected = (sum(weights.values()) - weights[PARAPHRASE]) / sum(weights.values())
    assert reward.total == pytest.approx(expected)
    assert reward.total < 1.0


def test_every_weighted_rubric_skipped_scores_zero_without_dividing_by_zero(env):
    """Only the skipped paraphrase rubric carries weight: nothing is left to
    score, so the total is 0.0 rather than a division by zero."""
    env.weights = {PARAPHRASE: 1.0}
    reward = env.reward(env.rollout(DecomposerTask(task_id="t", top_question="Q")))
    assert reward.total == 0.0


JUDGE = "judged.decomposer.coherence"


def _perfect_verifiables_with_judge(env, grade: float, weight: float = 0.15):
    """Paraphrase passes; one judged rubric grades ``grade`` at ``weight``."""
    def passes(target, *, context=None):
        return RubricResult(rubric_id=PARAPHRASE, kind=VERIFIABLE, score=1.0,
                            passed=True, details={})

    env.paraphrase_rubric.score = passes  # type: ignore[assignment]
    env.add_rubric(LlmJudgeRubric(rubric_id=JUDGE, judge_fn=lambda t, c: (grade, {}),
                                  judge_policy_id="stub-judge"), weight=weight)
    return env.reward(env.rollout(DecomposerTask(task_id="t", top_question="Q")))


@pytest.mark.parametrize("grade", [0.0, 0.4, 0.5])
def test_a_judged_rubric_always_counts_even_with_passed_none(env, grade):
    reward = _perfect_verifiables_with_judge(env, grade)
    judged = next(b for b in reward.breakdown if b.rubric_id == JUDGE)
    assert judged.kind == JUDGED and judged.passed is None
    base = sum(w for k, w in env.weights.items() if k != JUDGE)
    expected = (base * 1.0 + 0.15 * grade) / (base + 0.15)
    assert reward.total == pytest.approx(expected)
    if grade < 1.0:
        assert reward.total < 1.0  # a judged zero never yields a perfect reward


def test_a_judged_only_composite_scores_the_grade(env):
    env.weights = {}
    reward = _perfect_verifiables_with_judge(env, 0.25, weight=1.0)
    assert reward.total == pytest.approx(0.25)
