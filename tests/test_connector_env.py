"""Tests for interfaces/research/environments/connector_env.py."""

from __future__ import annotations

import json
import os
import sys

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from interfaces.research.environments import (  # noqa: E402
    ConnectorEnvironment,
    ConnectorTask,
)
from skills.verification.rubric import JUDGED, VERIFIABLE, Rubric, RubricResult  # noqa: E402


def _valid_payload() -> dict:
    return {
        "keyword_mappings": [
            {
                "keyword": "photonic",
                "matched_node_id": "node-a",
                "matched_node_label": "Photonic",
                "matched_node_type": "concept",
                "similarity": 0.9,
                "low_confidence": False,
            },
        ],
        "selected_algorithm": "top_n_shortest_paths",
        "algorithm_rationale": "Shortest paths preserve citation legibility.",
        "paths": [
            {
                "path_nodes": ["node-a", "node-b"],
                "path_relations": ["enables"],
                "depth": 1,
                "avg_confidence": 0.8,
                "node_labels": ["Photonic", "Interconnect"],
                "edge_ids": ["edge-1"],
            },
        ],
        "natural_language_relationships": [
            {
                "text": "Photonic substrates enable interconnect advances.",
                "source_path_index": 0,
            },
        ],
    }


def _valid_policy():
    def policy(task, ctx):
        return json.dumps(_valid_payload()), "stub/connector"

    return policy


def test_connector_task_and_task_list_round_trip():
    task = ConnectorTask(task_id="c1", seed_pairs=[{"a": "b"}])
    env = ConnectorEnvironment(tasks=[task])
    assert env.tasks() == [task]


def test_rollout_valid_json_parses():
    env = ConnectorEnvironment(policy_fn=_valid_policy())
    rollout = env.rollout(ConnectorTask(task_id="c1"))
    assert rollout.error is None
    assert rollout.parsed_output is not None
    assert rollout.policy_id == "stub/connector"


def test_rollout_invalid_json_records_error():
    env = ConnectorEnvironment(policy_fn=lambda task, ctx: ("not json", "bad"))
    rollout = env.rollout(ConnectorTask(task_id="c1"))
    assert rollout.parsed_output is None
    assert rollout.error and "json parse failed" in rollout.error


def test_rollout_missing_policy_raises():
    env = ConnectorEnvironment()
    with pytest.raises(RuntimeError, match="no policy_fn"):
        env.rollout(ConnectorTask(task_id="c1"))


def test_reward_happy_path_passes_verifiables():
    env = ConnectorEnvironment(policy_fn=_valid_policy())
    reward = env.reward(env.rollout(ConnectorTask(task_id="c1")))
    ids = {result.rubric_id for result in reward.breakdown}
    assert {
        "verifiable.connector.schema_validity",
        "verifiable.connector.mapping_or_path_present",
        "verifiable.connector.path_shape",
        "verifiable.connector.relationship_coverage",
    } <= ids
    assert reward.passed_all_verifiable is True
    assert reward.total == pytest.approx(1.0)


def test_reward_schema_failure_lowers_score():
    def policy(task, ctx):
        payload = _valid_payload()
        payload["selected_algorithm"] = "magic"
        return json.dumps(payload), "stub/bad-schema"

    env = ConnectorEnvironment(policy_fn=policy)
    reward = env.reward(env.rollout(ConnectorTask(task_id="c1")))
    schema = next(
        result for result in reward.breakdown
        if result.rubric_id == "verifiable.connector.schema_validity"
    )
    assert schema.passed is False
    assert reward.passed_all_verifiable is False


def test_reward_fails_empty_mapping_and_paths():
    def policy(task, ctx):
        payload = _valid_payload()
        payload["keyword_mappings"] = []
        payload["paths"] = []
        payload["natural_language_relationships"] = []
        return json.dumps(payload), "stub/empty"

    env = ConnectorEnvironment(policy_fn=policy)
    reward = env.reward(env.rollout(ConnectorTask(task_id="c1")))
    present = next(
        result for result in reward.breakdown
        if result.rubric_id == "verifiable.connector.mapping_or_path_present"
    )
    assert present.passed is False


def test_reward_fails_bad_path_shape():
    def policy(task, ctx):
        payload = _valid_payload()
        payload["paths"][0]["depth"] = 7
        return json.dumps(payload), "stub/bad-path"

    env = ConnectorEnvironment(policy_fn=policy)
    reward = env.reward(env.rollout(ConnectorTask(task_id="c1")))
    path_shape = next(
        result for result in reward.breakdown
        if result.rubric_id == "verifiable.connector.path_shape"
    )
    assert path_shape.passed is False
    assert path_shape.details["n_valid_paths"] == 0


def test_reward_fails_missing_relationship_for_path():
    def policy(task, ctx):
        payload = _valid_payload()
        payload["natural_language_relationships"] = []
        return json.dumps(payload), "stub/no-nl"

    env = ConnectorEnvironment(policy_fn=policy)
    reward = env.reward(env.rollout(ConnectorTask(task_id="c1")))
    coverage = next(
        result for result in reward.breakdown
        if result.rubric_id == "verifiable.connector.relationship_coverage"
    )
    assert coverage.passed is False
    assert coverage.details["covered_indices"] == []


class _AlwaysOneRubric(Rubric):
    rubric_id = "judged.connector.always_one"
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
    rubric_id = "verifiable.connector.raising"
    kind = VERIFIABLE

    def score(self, target, *, context=None):
        raise RuntimeError("intentional scoring failure")


def test_add_rubric_weight_and_scoring():
    env = ConnectorEnvironment(policy_fn=_valid_policy())
    env.add_rubric(_AlwaysOneRubric(), weight=0.10)
    reward = env.reward(env.rollout(ConnectorTask(task_id="c1")))
    assert "judged.connector.always_one" in {
        result.rubric_id for result in reward.breakdown
    }
    assert env.weights["judged.connector.always_one"] == 0.10


def test_extra_rubric_error_is_captured():
    env = ConnectorEnvironment(policy_fn=_valid_policy())
    env.add_rubric(_RaisingRubric(), weight=0.05)
    reward = env.reward(env.rollout(ConnectorTask(task_id="c1")))
    raised = next(
        result for result in reward.breakdown
        if result.rubric_id == "verifiable.connector.raising"
    )
    assert raised.passed is False
    assert "intentional scoring failure" in raised.details["scoring_error"]


def test_default_weights_leave_judged_headroom():
    assert sum(ConnectorEnvironment.DEFAULT_WEIGHTS.values()) <= 0.90 + 1e-9
