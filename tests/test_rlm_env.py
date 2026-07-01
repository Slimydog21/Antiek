"""Tests for interfaces/research/environments/rlm_env.py."""

from __future__ import annotations

import os
import sys

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from interfaces.research.environments import RLMEnvironment, RLMTask  # noqa: E402
from skills.verification.rubric import JUDGED, VERIFIABLE, Rubric, RubricResult  # noqa: E402


def _task() -> RLMTask:
    return RLMTask(
        task_id="rlm-1",
        prompt="Summarize the supplied corpus.",
        source_text="Antiek uses recursive language model loops.",
        max_iterations=3,
        expected_terms=["Antiek", "recursive"],
    )


def _two_step_policy(task, summary):
    if summary.iteration == 0:
        return "scratch = source_text", "stub/rlm"
    return (
        "answer['content'] = 'Antiek uses recursive loops.'\n"
        "answer['ready'] = True",
        "stub/rlm",
    )


def test_rlm_task_and_task_list_round_trip():
    task = _task()
    env = RLMEnvironment(tasks=[task])
    assert env.tasks() == [task]


def test_rollout_runs_full_loop_and_rewards_happy_path():
    env = RLMEnvironment(policy_fn=_two_step_policy)
    rollout = env.rollout(_task())
    reward = env.reward(rollout)
    ids = {result.rubric_id for result in reward.breakdown}
    assert {
        "verifiable.rlm.completed_status",
        "verifiable.rlm.answer_extracted",
        "verifiable.rlm.iteration_budget",
        "verifiable.rlm.corpus_is_variable",
        "verifiable.rlm.lifecycle_events",
    } <= ids
    assert rollout.status == "completed"
    assert rollout.iterations == 2
    assert rollout.event_action_types == [
        "rlm.iteration",
        "rlm.iteration",
        "rlm.session_completed",
    ]
    assert reward.passed_all_verifiable is True
    assert reward.total == pytest.approx(1.0)


def test_rollout_missing_policy_raises():
    env = RLMEnvironment()
    with pytest.raises(RuntimeError, match="no policy_fn"):
        env.rollout(_task())


def test_reward_rejects_missing_expected_answer_term():
    def policy(task, summary):
        return (
            "answer['content'] = 'Generic loops.'\nanswer['ready'] = True",
            "stub/generic",
        )

    env = RLMEnvironment(policy_fn=policy)
    reward = env.reward(env.rollout(_task()))
    answer = next(
        result for result in reward.breakdown
        if result.rubric_id == "verifiable.rlm.answer_extracted"
    )
    assert answer.passed is False
    assert answer.details["missing_expected_terms"] == ["Antiek", "recursive"]


def test_reward_captures_repl_failure_status_and_event():
    def policy(task, summary):
        return "answer['content'] = str(1 / 0)", "stub/failing"

    env = RLMEnvironment(policy_fn=policy)
    rollout = env.rollout(_task())
    reward = env.reward(rollout)
    status = next(
        result for result in reward.breakdown
        if result.rubric_id == "verifiable.rlm.completed_status"
    )
    lifecycle = next(
        result for result in reward.breakdown
        if result.rubric_id == "verifiable.rlm.lifecycle_events"
    )
    assert rollout.status == "failed"
    assert status.passed is False
    assert lifecycle.passed is True
    assert rollout.event_action_types == ["rlm.session_failed"]


def test_reward_rejects_iteration_cap_without_work():
    def policy(task, summary):
        return "x = 1", "stub/capped"

    env = RLMEnvironment(policy_fn=policy)
    rollout = env.rollout(RLMTask(task_id="cap", prompt="p", max_iterations=0))
    reward = env.reward(rollout)
    budget = next(
        result for result in reward.breakdown
        if result.rubric_id == "verifiable.rlm.iteration_budget"
    )
    assert rollout.status == "completed"
    assert rollout.iterations == 0
    assert budget.passed is False


class _AlwaysOneRubric(Rubric):
    rubric_id = "judged.rlm.always_one"
    kind = JUDGED

    def score(self, target, *, context=None):
        return RubricResult(
            rubric_id=self.rubric_id,
            kind=self.kind,
            score=1.0,
            passed=None,
            details={"status": target.status},
        )


class _RaisingRubric(Rubric):
    rubric_id = "verifiable.rlm.raising"
    kind = VERIFIABLE

    def score(self, target, *, context=None):
        raise RuntimeError("intentional scoring failure")


def test_add_rubric_weight_and_scoring():
    env = RLMEnvironment(policy_fn=_two_step_policy)
    env.add_rubric(_AlwaysOneRubric(), weight=0.10)
    reward = env.reward(env.rollout(_task()))
    assert "judged.rlm.always_one" in {
        result.rubric_id for result in reward.breakdown
    }
    assert env.weights["judged.rlm.always_one"] == 0.10


def test_extra_rubric_error_is_captured():
    env = RLMEnvironment(policy_fn=_two_step_policy)
    env.add_rubric(_RaisingRubric(), weight=0.05)
    reward = env.reward(env.rollout(_task()))
    raised = next(
        result for result in reward.breakdown
        if result.rubric_id == "verifiable.rlm.raising"
    )
    assert raised.passed is False
    assert "intentional scoring failure" in raised.details["scoring_error"]


def test_default_weights_leave_judged_headroom():
    assert sum(RLMEnvironment.DEFAULT_WEIGHTS.values()) <= 0.90 + 1e-9
