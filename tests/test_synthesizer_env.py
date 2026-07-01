"""Tests for interfaces/research/environments/synthesizer_env.py."""

from __future__ import annotations

import json
import os
import sys

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from interfaces.research.environments import (  # noqa: E402
    SynthesizerEnvironment,
    SynthesizerTask,
)
from skills.verification.rubric import (  # noqa: E402
    JUDGED,
    VERIFIABLE,
    Rubric,
    RubricResult,
)


def _valid_payload() -> dict:
    return {
        "thesis_summary": "Quantum substrate thesis with primary support.",
        "implicit_recommendation": "proceed",
        "thesis_components": [
            {
                "claim": "Primary sources support the quantum substrate thesis.",
                "confidence": "high",
                "supporting_chunk_ids": ["chunk-1"],
                "supporting_path_indices": [],
                "confidence_basis": "Tier-1 source and corroborating filing.",
                "effective_source_tier": 1,
                "hedging_required": False,
            },
        ],
        "falsification_conditions": [
            {
                "condition": "The measured signal falls below the threshold.",
                "specific_observable": "Published Q4 benchmark below threshold.",
                "timeframe": "within 12 months",
            },
        ],
        "execution_risks": [
            {
                "risk": "Manufacturing scale-up slips.",
                "severity_if_manifested": "moderate",
            },
        ],
        "constraint_compliance": {
            "hard_constraints_satisfied": True,
            "soft_constraints_violated": [],
            "violations_justified": [],
        },
        "reasoning_paths_used": [],
        "conviction_level": 0.72,
    }


def _valid_policy():
    def policy(task, ctx):
        return json.dumps(_valid_payload()), "stub/synth"

    return policy


def test_synthesizer_task_and_task_list_round_trip():
    task = SynthesizerTask(task_id="s1", question="What is X?")
    env = SynthesizerEnvironment(tasks=[task])
    assert env.tasks() == [task]


def test_rollout_valid_json_parses():
    env = SynthesizerEnvironment(policy_fn=_valid_policy())
    rollout = env.rollout(SynthesizerTask(task_id="s1", question="Q?"))
    assert rollout.error is None
    assert rollout.parsed_output is not None
    assert rollout.policy_id == "stub/synth"


def test_rollout_invalid_json_records_error():
    env = SynthesizerEnvironment(policy_fn=lambda task, ctx: ("not json", "bad"))
    rollout = env.rollout(SynthesizerTask(task_id="s1", question="Q?"))
    assert rollout.parsed_output is None
    assert rollout.error and "json parse failed" in rollout.error


def test_rollout_missing_policy_raises():
    env = SynthesizerEnvironment()
    with pytest.raises(RuntimeError, match="no policy_fn"):
        env.rollout(SynthesizerTask(task_id="s1", question="Q?"))


def test_reward_happy_path_passes_all_verifiables():
    env = SynthesizerEnvironment(policy_fn=_valid_policy())
    rollout = env.rollout(SynthesizerTask(task_id="s1", question="Q?"))
    reward = env.reward(rollout)
    ids = {result.rubric_id for result in reward.breakdown}
    assert {
        "verifiable.synthesizer.schema_validity",
        "verifiable.synthesizer.citation_provenance",
        "verifiable.synthesizer.falsification_nonempty",
        "verifiable.synthesizer.recommendation_coherence",
    } <= ids
    assert reward.passed_all_verifiable is True
    assert reward.total == pytest.approx(1.0)


def test_reward_schema_failure_lowers_score():
    def policy(task, ctx):
        payload = _valid_payload()
        payload["implicit_recommendation"] = "strong_buy"
        return json.dumps(payload), "stub/bad-schema"

    env = SynthesizerEnvironment(policy_fn=policy)
    reward = env.reward(env.rollout(SynthesizerTask(task_id="s1", question="Q?")))
    schema = next(
        result for result in reward.breakdown
        if result.rubric_id == "verifiable.synthesizer.schema_validity"
    )
    assert schema.passed is False
    assert reward.passed_all_verifiable is False


def test_reward_missing_citation_fails_citation_rubric():
    def policy(task, ctx):
        payload = _valid_payload()
        payload["thesis_components"][0]["supporting_chunk_ids"] = []
        return json.dumps(payload), "stub/no-citation"

    env = SynthesizerEnvironment(policy_fn=policy)
    reward = env.reward(env.rollout(SynthesizerTask(task_id="s1", question="Q?")))
    citation = next(
        result for result in reward.breakdown
        if result.rubric_id == "verifiable.synthesizer.citation_provenance"
    )
    assert citation.passed is False
    assert citation.score == 0.0


def test_reward_insufficient_evidence_allows_empty_thesis():
    def policy(task, ctx):
        payload = _valid_payload()
        payload["thesis_summary"] = ""
        payload["implicit_recommendation"] = "insufficient_evidence"
        payload["thesis_components"] = []
        payload["falsification_conditions"] = []
        payload["execution_risks"] = []
        payload["constraint_compliance"]["hard_constraints_satisfied"] = False
        return json.dumps(payload), "stub/insufficient"

    env = SynthesizerEnvironment(policy_fn=policy)
    reward = env.reward(env.rollout(SynthesizerTask(task_id="s1", question="Q?")))
    by_id = {result.rubric_id: result for result in reward.breakdown}
    assert by_id["verifiable.synthesizer.schema_validity"].passed is True
    assert by_id["verifiable.synthesizer.falsification_nonempty"].passed is True
    assert by_id["verifiable.synthesizer.recommendation_coherence"].passed is True
    assert by_id["verifiable.synthesizer.citation_provenance"].passed is False


class _AlwaysOneRubric(Rubric):
    rubric_id = "judged.synthesizer.always_one"
    kind = JUDGED

    def score(self, target, *, context=None):
        return RubricResult(
            rubric_id=self.rubric_id,
            kind=self.kind,
            score=1.0,
            passed=None,
            details={"question": (context or {}).get("question")},
        )


class _RaisingRubric(Rubric):
    rubric_id = "verifiable.synthesizer.raising"
    kind = VERIFIABLE

    def score(self, target, *, context=None):
        raise RuntimeError("intentional scoring failure")


def test_add_rubric_weight_and_scoring():
    env = SynthesizerEnvironment(policy_fn=_valid_policy())
    env.add_rubric(_AlwaysOneRubric(), weight=0.10)
    reward = env.reward(env.rollout(SynthesizerTask(task_id="s1", question="Q?")))
    ids = {result.rubric_id for result in reward.breakdown}
    assert "judged.synthesizer.always_one" in ids
    assert env.weights["judged.synthesizer.always_one"] == 0.10


def test_extra_rubric_error_is_captured():
    env = SynthesizerEnvironment(policy_fn=_valid_policy())
    env.add_rubric(_RaisingRubric(), weight=0.05)
    reward = env.reward(env.rollout(SynthesizerTask(task_id="s1", question="Q?")))
    raised = next(
        result for result in reward.breakdown
        if result.rubric_id == "verifiable.synthesizer.raising"
    )
    assert raised.passed is False
    assert "intentional scoring failure" in raised.details["scoring_error"]


def test_default_weights_leave_judged_headroom():
    assert sum(SynthesizerEnvironment.DEFAULT_WEIGHTS.values()) <= 0.90 + 1e-9
