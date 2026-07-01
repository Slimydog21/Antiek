"""Tests for interfaces/research/environments/evidence_retriever_env.py."""

from __future__ import annotations

import json
import os
import sys

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from interfaces.research.environments import (  # noqa: E402
    EvidenceRetrieverEnvironment,
    EvidenceRetrieverTask,
)
from skills.verification.rubric import JUDGED, VERIFIABLE, Rubric, RubricResult  # noqa: E402


def _task() -> EvidenceRetrieverTask:
    return EvidenceRetrieverTask(
        task_id="e1",
        sub_question="What evidence supports the claim?",
        chunks_block="[chunk-1] primary evidence",
        subgraph_block="[edge-1] supports",
        canonical_chunk_ids=["chunk-1"],
        canonical_edge_ids=["edge-1"],
    )


def _valid_payload() -> dict:
    return {
        "sub_question": "What evidence supports the claim?",
        "answer": "Tier-1 evidence supports the claim.",
        "supporting_claims": [
            {
                "claim": "The claim is supported by the cited evidence.",
                "evidence_type": "direct",
                "chunk_ids": ["chunk-1"],
                "edge_ids": ["edge-1"],
                "source_tier_min": 1,
                "confidence": "high",
                "confidence_basis": "Direct citation to primary evidence.",
            },
        ],
        "evidentiary_gaps": [],
        "insufficient_evidence": False,
    }


def _valid_policy():
    def policy(task, ctx):
        return json.dumps(_valid_payload()), "stub/evidence"

    return policy


def test_evidence_task_and_task_list_round_trip():
    task = _task()
    env = EvidenceRetrieverEnvironment(tasks=[task])
    assert env.tasks() == [task]


def test_rollout_valid_json_parses():
    env = EvidenceRetrieverEnvironment(policy_fn=_valid_policy())
    rollout = env.rollout(_task())
    assert rollout.error is None
    assert rollout.parsed_output is not None
    assert rollout.policy_id == "stub/evidence"


def test_rollout_invalid_json_records_error():
    env = EvidenceRetrieverEnvironment(policy_fn=lambda task, ctx: ("nope", "bad"))
    rollout = env.rollout(_task())
    assert rollout.parsed_output is None
    assert rollout.error and "json parse failed" in rollout.error


def test_rollout_missing_policy_raises():
    env = EvidenceRetrieverEnvironment()
    with pytest.raises(RuntimeError, match="no policy_fn"):
        env.rollout(_task())


def test_reward_happy_path_passes_verifiables():
    env = EvidenceRetrieverEnvironment(policy_fn=_valid_policy())
    reward = env.reward(env.rollout(_task()))
    ids = {result.rubric_id for result in reward.breakdown}
    assert {
        "verifiable.evidence_retriever.schema_validity",
        "verifiable.evidence_retriever.sub_question_echo",
        "verifiable.evidence_retriever.claim_citations",
        "verifiable.evidence_retriever.insufficient_evidence_coherence",
    } <= ids
    assert reward.passed_all_verifiable is True
    assert reward.total == pytest.approx(1.0)


def test_reward_schema_failure_lowers_score():
    def policy(task, ctx):
        payload = _valid_payload()
        payload["supporting_claims"][0]["confidence"] = "certain"
        return json.dumps(payload), "stub/bad-schema"

    env = EvidenceRetrieverEnvironment(policy_fn=policy)
    reward = env.reward(env.rollout(_task()))
    schema = next(
        result for result in reward.breakdown
        if result.rubric_id == "verifiable.evidence_retriever.schema_validity"
    )
    assert schema.passed is False
    assert reward.passed_all_verifiable is False


def test_reward_rejects_sub_question_mismatch():
    def policy(task, ctx):
        payload = _valid_payload()
        payload["sub_question"] = "A different question"
        return json.dumps(payload), "stub/mismatch"

    env = EvidenceRetrieverEnvironment(policy_fn=policy)
    reward = env.reward(env.rollout(_task()))
    echo = next(
        result for result in reward.breakdown
        if result.rubric_id == "verifiable.evidence_retriever.sub_question_echo"
    )
    assert echo.passed is False


def test_reward_rejects_invalid_chunk_reference():
    def policy(task, ctx):
        payload = _valid_payload()
        payload["supporting_claims"][0]["chunk_ids"] = ["chunk-made-up"]
        return json.dumps(payload), "stub/bad-ref"

    env = EvidenceRetrieverEnvironment(policy_fn=policy)
    reward = env.reward(env.rollout(_task()))
    citations = next(
        result for result in reward.breakdown
        if result.rubric_id == "verifiable.evidence_retriever.claim_citations"
    )
    assert citations.passed is False
    assert citations.details["invalid_chunk_refs"] == ["chunk-made-up"]


def test_reward_accepts_coherent_insufficient_evidence():
    def policy(task, ctx):
        payload = _valid_payload()
        payload["answer"] = "Insufficient evidence in the supplied context."
        payload["supporting_claims"] = []
        payload["evidentiary_gaps"] = [
            {
                "gap_description": "No primary source covers the claim.",
                "additional_retrieval_suggested": "Search primary filings.",
            },
        ]
        payload["insufficient_evidence"] = True
        return json.dumps(payload), "stub/insufficient"

    env = EvidenceRetrieverEnvironment(policy_fn=policy)
    reward = env.reward(env.rollout(_task()))
    coherence = next(
        result for result in reward.breakdown
        if result.rubric_id
        == "verifiable.evidence_retriever.insufficient_evidence_coherence"
    )
    assert coherence.passed is True


def test_reward_rejects_incoherent_insufficient_evidence():
    def policy(task, ctx):
        payload = _valid_payload()
        payload["insufficient_evidence"] = True
        return json.dumps(payload), "stub/incoherent"

    env = EvidenceRetrieverEnvironment(policy_fn=policy)
    reward = env.reward(env.rollout(_task()))
    coherence = next(
        result for result in reward.breakdown
        if result.rubric_id
        == "verifiable.evidence_retriever.insufficient_evidence_coherence"
    )
    assert coherence.passed is False


class _AlwaysOneRubric(Rubric):
    rubric_id = "judged.evidence_retriever.always_one"
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
    rubric_id = "verifiable.evidence_retriever.raising"
    kind = VERIFIABLE

    def score(self, target, *, context=None):
        raise RuntimeError("intentional scoring failure")


def test_add_rubric_weight_and_scoring():
    env = EvidenceRetrieverEnvironment(policy_fn=_valid_policy())
    env.add_rubric(_AlwaysOneRubric(), weight=0.10)
    reward = env.reward(env.rollout(_task()))
    assert "judged.evidence_retriever.always_one" in {
        result.rubric_id for result in reward.breakdown
    }
    assert env.weights["judged.evidence_retriever.always_one"] == 0.10


def test_extra_rubric_error_is_captured():
    env = EvidenceRetrieverEnvironment(policy_fn=_valid_policy())
    env.add_rubric(_RaisingRubric(), weight=0.05)
    reward = env.reward(env.rollout(_task()))
    raised = next(
        result for result in reward.breakdown
        if result.rubric_id == "verifiable.evidence_retriever.raising"
    )
    assert raised.passed is False
    assert "intentional scoring failure" in raised.details["scoring_error"]


def test_default_weights_leave_judged_headroom():
    assert sum(EvidenceRetrieverEnvironment.DEFAULT_WEIGHTS.values()) <= 0.90 + 1e-9
