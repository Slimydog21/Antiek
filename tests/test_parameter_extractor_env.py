"""Tests for interfaces/research/environments/parameter_extractor_env.py."""

from __future__ import annotations

import json
import os
import sys

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from interfaces.research.environments import (  # noqa: E402
    ParameterExtractorEnvironment,
    ParameterExtractorTask,
)
from skills.verification.rubric import JUDGED, VERIFIABLE, Rubric, RubricResult  # noqa: E402


def _valid_payload() -> dict:
    return {
        "parameters": [
            {
                "semantic_anchor": "training_compute",
                "metric_value": {
                    "value_type": "scalar",
                    "value": 1.2e25,
                    "unit": "FLOP",
                },
                "qualitative_descriptor": None,
                "evidence_status": "observed",
                "source_chunk_ids": ["chunk-1"],
                "constraint_strictness": "hard",
            },
        ],
        "constraints": [
            {
                "constraint_id": "training_compute-hard",
                "strictness": "hard",
                "kind": "numeric_range",
                "description": "training_compute must meet the observed floor",
                "config": {"min": 1.2e25},
            },
        ],
    }


def _valid_policy():
    def policy(task, ctx):
        return json.dumps(_valid_payload()), "stub/param"

    return policy


def _task() -> ParameterExtractorTask:
    return ParameterExtractorTask(
        task_id="p1",
        evidence_block="Evidence cites chunk-1.",
        canonical_source_chunk_ids=["chunk-1"],
    )


def test_parameter_task_and_task_list_round_trip():
    task = _task()
    env = ParameterExtractorEnvironment(tasks=[task])
    assert env.tasks() == [task]


def test_rollout_valid_json_parses():
    env = ParameterExtractorEnvironment(policy_fn=_valid_policy())
    rollout = env.rollout(_task())
    assert rollout.error is None
    assert rollout.parsed_output is not None
    assert rollout.policy_id == "stub/param"


def test_rollout_invalid_json_records_error():
    env = ParameterExtractorEnvironment(policy_fn=lambda task, ctx: ("not json", "bad"))
    rollout = env.rollout(_task())
    assert rollout.parsed_output is None
    assert rollout.error and "json parse failed" in rollout.error


def test_rollout_missing_policy_raises():
    env = ParameterExtractorEnvironment()
    with pytest.raises(RuntimeError, match="no policy_fn"):
        env.rollout(_task())


def test_reward_happy_path_passes_verifiables():
    env = ParameterExtractorEnvironment(policy_fn=_valid_policy())
    reward = env.reward(env.rollout(_task()))
    ids = {result.rubric_id for result in reward.breakdown}
    assert {
        "verifiable.parameter_extractor.schema_validity",
        "verifiable.parameter_extractor.source_citation",
        "verifiable.parameter_extractor.metric_value_consistency",
        "verifiable.parameter_extractor.constraint_derivation",
    } <= ids
    assert reward.passed_all_verifiable is True
    assert reward.total == pytest.approx(1.0)


def test_reward_schema_failure_lowers_score():
    def policy(task, ctx):
        payload = _valid_payload()
        payload["parameters"][0]["constraint_strictness"] = "mandatory"
        return json.dumps(payload), "stub/bad-schema"

    env = ParameterExtractorEnvironment(policy_fn=policy)
    reward = env.reward(env.rollout(_task()))
    schema = next(
        result for result in reward.breakdown
        if result.rubric_id == "verifiable.parameter_extractor.schema_validity"
    )
    assert schema.passed is False
    assert reward.passed_all_verifiable is False


def test_reward_rejects_invalid_source_reference():
    def policy(task, ctx):
        payload = _valid_payload()
        payload["parameters"][0]["source_chunk_ids"] = ["chunk-made-up"]
        return json.dumps(payload), "stub/bad-ref"

    env = ParameterExtractorEnvironment(policy_fn=policy)
    reward = env.reward(env.rollout(_task()))
    citation = next(
        result for result in reward.breakdown
        if result.rubric_id == "verifiable.parameter_extractor.source_citation"
    )
    assert citation.passed is False
    assert citation.details["invalid_refs"] == ["chunk-made-up"]


def test_reward_rejects_metric_value_mismatch():
    def policy(task, ctx):
        payload = _valid_payload()
        payload["parameters"][0]["metric_value"]["value_type"] = "range"
        payload["parameters"][0]["metric_value"]["value"] = 10
        return json.dumps(payload), "stub/bad-metric"

    env = ParameterExtractorEnvironment(policy_fn=policy)
    reward = env.reward(env.rollout(_task()))
    metric = next(
        result for result in reward.breakdown
        if result.rubric_id
        == "verifiable.parameter_extractor.metric_value_consistency"
    )
    assert metric.passed is False
    assert metric.details["invalid_anchors"] == ["training_compute"]


def test_reward_rejects_missing_constraint_for_hard_parameter():
    def policy(task, ctx):
        payload = _valid_payload()
        payload["constraints"] = []
        return json.dumps(payload), "stub/no-constraint"

    env = ParameterExtractorEnvironment(policy_fn=policy)
    reward = env.reward(env.rollout(_task()))
    derivation = next(
        result for result in reward.breakdown
        if result.rubric_id == "verifiable.parameter_extractor.constraint_derivation"
    )
    assert derivation.passed is False
    assert derivation.details["n_strict_parameters"] == 1


class _AlwaysOneRubric(Rubric):
    rubric_id = "judged.parameter_extractor.always_one"
    kind = JUDGED

    def score(self, target, *, context=None):
        return RubricResult(
            rubric_id=self.rubric_id,
            kind=self.kind,
            score=1.0,
            passed=None,
            details={"task_id": getattr((context or {}).get("task"), "task_id", None)},
        )


class _RaisingRubric(Rubric):
    rubric_id = "verifiable.parameter_extractor.raising"
    kind = VERIFIABLE

    def score(self, target, *, context=None):
        raise RuntimeError("intentional scoring failure")


def test_add_rubric_weight_and_scoring():
    env = ParameterExtractorEnvironment(policy_fn=_valid_policy())
    env.add_rubric(_AlwaysOneRubric(), weight=0.10)
    reward = env.reward(env.rollout(_task()))
    assert "judged.parameter_extractor.always_one" in {
        result.rubric_id for result in reward.breakdown
    }
    assert env.weights["judged.parameter_extractor.always_one"] == 0.10


def test_extra_rubric_error_is_captured():
    env = ParameterExtractorEnvironment(policy_fn=_valid_policy())
    env.add_rubric(_RaisingRubric(), weight=0.05)
    reward = env.reward(env.rollout(_task()))
    raised = next(
        result for result in reward.breakdown
        if result.rubric_id == "verifiable.parameter_extractor.raising"
    )
    assert raised.passed is False
    assert "intentional scoring failure" in raised.details["scoring_error"]


def test_default_weights_leave_judged_headroom():
    assert (
        sum(ParameterExtractorEnvironment.DEFAULT_WEIGHTS.values())
        <= 0.90 + 1e-9
    )
