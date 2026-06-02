"""Tests for interfaces/research/environments/decomposer_env.py
(Sprint 9 day 5).

Coverage:

A. Task / Rollout / Reward shapes:
   1. DecomposerTask construction.
   2. add_task/tasks round-trip.

B. Rollout:
   3. Valid JSON parses and lands in parsed_output.
   4. Invalid JSON sets rollout.error, parsed_output=None.
   5. Missing policy_fn raises.

C. Reward — happy path (valid decomposition):
   6. All four verifiable rubrics fire.
   7. passed_all_verifiable=True when bounds + parse + paraphrase
      all hold (via injected stub embedder threaded in via target).
   8. Weighted composite normalizes to used_weight.

D. Reward — degraded paths:
   9. JSON parse failure: schema_validity=0, paraphrase skipped.
   10. Sub-question count below SUB_QUESTIONS_MIN fails subq bound.
   11. Sub-question count above SUB_QUESTIONS_MAX fails subq bound.
   12. Keyword count below KEYWORDS_MIN fails keyword bound.
   13. Empty parsed_output fails all four verifiables coherently.

E. Extra-rubric injection:
   14. add_rubric appends to breakdown.
   15. add_rubric with weight registers the weight.
   16. Scoring-error from injected rubric captured into breakdown, not
       raised.

F. End-to-end:
   17. tasks() returns the constructor-passed list.
   18. DEFAULT_WEIGHTS sums to <=1.0 (substrate-invariant assertion).
"""

from __future__ import annotations

import json
import os
import sys

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from interfaces.research.environments import (
    DecomposerEnvironment,
    DecomposerTask,
)
from skills.verification.rubric import (
    JUDGED,
    VERIFIABLE,
    Rubric,
    RubricResult,
)
from substrate.constants import (
    KEYWORDS_MIN,
    SUB_QUESTIONS_MAX,
    SUB_QUESTIONS_MIN,
)

# ---------------------------------------------------------------------------
# Stub embedder so the paraphrase rubric can run without sentence-transformers
# ---------------------------------------------------------------------------


class _StubEmbedder:
    """Returns a deterministic near-orthogonal vector per text so distinct
    strings score cosine ≈ 0 (never tripping the paraphrase guard) while an
    identical string scores 1.0 (a real duplicate SHOULD be flagged).

    Uses a STABLE hash (hashlib) seeding a per-text RNG of Gaussian
    components — NOT Python's builtin ``hash()``, which is randomized per
    process (PYTHONHASHSEED). The old one-hot-on-``hash()%64`` design collided
    two distinct sub-questions onto the same basis vector for some seeds,
    making the happy-path reward test seed-flaky (passed in isolation, failed
    under other seeds). Gaussian vectors in 64-dim are near-orthogonal for
    distinct seeds (E[cosine]=0), so distinct strings stay well below any
    paraphrase threshold, deterministically."""

    def encode(self, text: str) -> list[float]:
        import hashlib
        import random

        seed = int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8], "big")
        rng = random.Random(seed)
        return [rng.gauss(0.0, 1.0) for _ in range(64)]


@pytest.fixture
def env_with_paraphrase_stub():
    """An env whose paraphrase rubric uses a deterministic stub
    embedder so tests don't require sentence-transformers."""
    env = DecomposerEnvironment()
    real_score = env.paraphrase_rubric.score
    stub = _StubEmbedder()

    def patched_score(target, *, context=None):
        if isinstance(target, dict) and target.get("embedder") is None:
            target = dict(target)
            target["embedder"] = stub
        return real_score(target, context=context)

    env.paraphrase_rubric.score = patched_score  # type: ignore[assignment]
    return env


# ---------------------------------------------------------------------------
# Policy helpers
# ---------------------------------------------------------------------------


def _valid_payload(top_question: str) -> dict:
    return {
        "decomposition": [
            {
                "sub_question": f"Aspect {i} of analysis",
                "category": "context",
                "evidence_type_required": "any",
            }
            for i in range(SUB_QUESTIONS_MIN)
        ],
        "keywords": [
            {"keyword": f"kw{i}", "synonyms": []}
            for i in range(KEYWORDS_MIN)
        ],
    }


def _valid_policy():
    def policy(task, ctx):
        return json.dumps(_valid_payload(task.top_question)), "stub/v0"
    return policy


# ---------------------------------------------------------------------------
# A. Task / Rollout / Reward shapes
# ---------------------------------------------------------------------------


def test_decomposer_task_construction():
    t = DecomposerTask(
        task_id="t-1", top_question="What is X?", metadata={"sector": "deep-tech"},
    )
    assert t.task_id == "t-1"
    assert t.top_question == "What is X?"
    assert t.metadata == {"sector": "deep-tech"}


def test_add_task_and_tasks_round_trip():
    env = DecomposerEnvironment()
    t1 = DecomposerTask(task_id="t-1", top_question="Q1")
    t2 = DecomposerTask(task_id="t-2", top_question="Q2")
    env.add_task(t1)
    env.add_task(t2)
    assert [t.task_id for t in env.tasks()] == ["t-1", "t-2"]


# ---------------------------------------------------------------------------
# B. Rollout
# ---------------------------------------------------------------------------


def test_rollout_valid_json():
    env = DecomposerEnvironment(policy_fn=_valid_policy())
    task = DecomposerTask(task_id="t", top_question="Q?")
    r = env.rollout(task)
    assert r.error is None
    assert r.parsed_output is not None
    assert "decomposition" in r.parsed_output
    assert r.policy_id == "stub/v0"


def test_rollout_invalid_json():
    def bad_policy(task, ctx): return "not json at all {{{", "stub/bad"
    env = DecomposerEnvironment(policy_fn=bad_policy)
    r = env.rollout(DecomposerTask(task_id="t", top_question="Q"))
    assert r.parsed_output is None
    assert r.error is not None
    assert "json parse failed" in r.error


def test_rollout_missing_policy_fn_raises():
    env = DecomposerEnvironment()
    with pytest.raises(RuntimeError, match="no policy_fn"):
        env.rollout(DecomposerTask(task_id="t", top_question="Q"))


# ---------------------------------------------------------------------------
# C. Reward — happy path
# ---------------------------------------------------------------------------


def test_reward_all_four_verifiables_fire(env_with_paraphrase_stub):
    env = env_with_paraphrase_stub
    env.policy_fn = _valid_policy()
    r = env.rollout(DecomposerTask(task_id="t", top_question="What is X?"))
    reward = env.reward(r)
    rubric_ids = [b.rubric_id for b in reward.breakdown]
    assert "verifiable.decomposer.paraphrase_guard" in rubric_ids
    assert "verifiable.decomposer.schema_validity" in rubric_ids
    assert "verifiable.decomposer.subq_count_bounds" in rubric_ids
    assert "verifiable.decomposer.keyword_count_bounds" in rubric_ids


def test_reward_passed_all_verifiable_true_on_happy_path(env_with_paraphrase_stub):
    env = env_with_paraphrase_stub
    env.policy_fn = _valid_policy()
    r = env.rollout(DecomposerTask(task_id="t", top_question="What is X?"))
    reward = env.reward(r)
    assert reward.passed_all_verifiable is True
    assert reward.total == pytest.approx(1.0)


def test_reward_total_normalizes_by_used_weight(env_with_paraphrase_stub):
    env = env_with_paraphrase_stub
    env.policy_fn = _valid_policy()
    # Only schema_validity is in weights; total should equal schema score.
    env.weights = {"verifiable.decomposer.schema_validity": 0.5}
    r = env.rollout(DecomposerTask(task_id="t", top_question="Q"))
    reward = env.reward(r)
    schema = next(
        b for b in reward.breakdown
        if b.rubric_id == "verifiable.decomposer.schema_validity"
    )
    assert reward.total == pytest.approx(schema.score)


# ---------------------------------------------------------------------------
# D. Reward — degraded paths
# ---------------------------------------------------------------------------


def test_reward_json_parse_failure(env_with_paraphrase_stub):
    env = env_with_paraphrase_stub
    env.policy_fn = lambda t, c: ("nope", "stub/bad")
    r = env.rollout(DecomposerTask(task_id="t", top_question="Q"))
    reward = env.reward(r)
    schema = next(
        b for b in reward.breakdown
        if b.rubric_id == "verifiable.decomposer.schema_validity"
    )
    paraphrase = next(
        b for b in reward.breakdown
        if b.rubric_id == "verifiable.decomposer.paraphrase_guard"
    )
    assert schema.score == 0.0
    assert paraphrase.score == 0.0
    assert paraphrase.details["skipped_reason"].startswith(
        "parsed_output missing"
    )
    assert reward.passed_all_verifiable is False


def test_reward_subq_below_min_fails(env_with_paraphrase_stub):
    env = env_with_paraphrase_stub

    def low_subq(t, c):
        payload = _valid_payload(t.top_question)
        payload["decomposition"] = payload["decomposition"][:1]
        return json.dumps(payload), "stub/v0"
    env.policy_fn = low_subq
    r = env.rollout(DecomposerTask(task_id="t", top_question="Q"))
    reward = env.reward(r)
    subq = next(
        b for b in reward.breakdown
        if b.rubric_id == "verifiable.decomposer.subq_count_bounds"
    )
    assert subq.passed is False
    assert subq.details["n_sub_questions"] == 1
    assert subq.details["min"] == SUB_QUESTIONS_MIN


def test_reward_subq_above_max_fails(env_with_paraphrase_stub):
    env = env_with_paraphrase_stub

    def high_subq(t, c):
        payload = _valid_payload(t.top_question)
        payload["decomposition"] = (
            payload["decomposition"]
            + [{"sub_question": f"extra{i}", "category": "c",
                "evidence_type_required": "any"}
               for i in range(SUB_QUESTIONS_MAX)]
        )
        return json.dumps(payload), "stub/v0"
    env.policy_fn = high_subq
    r = env.rollout(DecomposerTask(task_id="t", top_question="Q"))
    reward = env.reward(r)
    subq = next(
        b for b in reward.breakdown
        if b.rubric_id == "verifiable.decomposer.subq_count_bounds"
    )
    assert subq.passed is False
    assert subq.details["n_sub_questions"] > SUB_QUESTIONS_MAX


def test_reward_keyword_below_min_fails(env_with_paraphrase_stub):
    env = env_with_paraphrase_stub

    def low_kw(t, c):
        payload = _valid_payload(t.top_question)
        payload["keywords"] = payload["keywords"][:1]
        return json.dumps(payload), "stub/v0"
    env.policy_fn = low_kw
    r = env.rollout(DecomposerTask(task_id="t", top_question="Q"))
    reward = env.reward(r)
    kw = next(
        b for b in reward.breakdown
        if b.rubric_id == "verifiable.decomposer.keyword_count_bounds"
    )
    assert kw.passed is False
    assert kw.details["n_keywords"] == 1


def test_reward_empty_parsed_output(env_with_paraphrase_stub):
    env = env_with_paraphrase_stub
    env.policy_fn = lambda t, c: (json.dumps({}), "stub/v0")
    r = env.rollout(DecomposerTask(task_id="t", top_question="Q"))
    reward = env.reward(r)
    by_id = {b.rubric_id: b for b in reward.breakdown}
    # Parse succeeded so schema_validity passes.
    assert by_id["verifiable.decomposer.schema_validity"].passed is True
    # But decomposition + keywords are absent → bounds + paraphrase fail.
    assert by_id["verifiable.decomposer.paraphrase_guard"].passed is False
    assert by_id["verifiable.decomposer.subq_count_bounds"].passed is False
    assert by_id["verifiable.decomposer.keyword_count_bounds"].passed is False
    assert reward.passed_all_verifiable is False


# ---------------------------------------------------------------------------
# E. Extra-rubric injection
# ---------------------------------------------------------------------------


class _AlwaysOneRubric(Rubric):
    rubric_id = "judged.decomposer.always_one"
    kind = JUDGED

    def score(self, target, *, context=None):
        return RubricResult(
            rubric_id=self.rubric_id, kind=self.kind,
            score=1.0, passed=None,
            details={"saw_top_question": (context or {}).get("top_question")},
        )


class _RaisingRubric(Rubric):
    rubric_id = "verifiable.decomposer.raising"
    kind = VERIFIABLE

    def score(self, target, *, context=None):
        raise RuntimeError("intentional scoring failure")


def test_add_rubric_appends_to_breakdown(env_with_paraphrase_stub):
    env = env_with_paraphrase_stub
    env.policy_fn = _valid_policy()
    env.add_rubric(_AlwaysOneRubric(), weight=0.15)
    r = env.rollout(DecomposerTask(task_id="t", top_question="Q"))
    reward = env.reward(r)
    rubric_ids = [b.rubric_id for b in reward.breakdown]
    assert "judged.decomposer.always_one" in rubric_ids


def test_add_rubric_registers_weight(env_with_paraphrase_stub):
    env = env_with_paraphrase_stub
    env.add_rubric(_AlwaysOneRubric(), weight=0.15)
    assert env.weights["judged.decomposer.always_one"] == 0.15


def test_add_rubric_scoring_error_captured(env_with_paraphrase_stub):
    env = env_with_paraphrase_stub
    env.policy_fn = _valid_policy()
    env.add_rubric(_RaisingRubric(), weight=0.05)
    r = env.rollout(DecomposerTask(task_id="t", top_question="Q"))
    reward = env.reward(r)
    raised = next(
        b for b in reward.breakdown
        if b.rubric_id == "verifiable.decomposer.raising"
    )
    assert raised.passed is False
    assert "intentional scoring failure" in raised.details["scoring_error"]


# ---------------------------------------------------------------------------
# F. End-to-end / invariants
# ---------------------------------------------------------------------------


def test_constructor_seeds_tasks():
    tasks = [
        DecomposerTask(task_id=f"t{i}", top_question=f"Q{i}")
        for i in range(3)
    ]
    env = DecomposerEnvironment(tasks=tasks)
    assert [t.task_id for t in env.tasks()] == ["t0", "t1", "t2"]


def test_default_weights_sum_under_one():
    # 0.35 + 0.20 + 0.20 + 0.10 = 0.85; the 0.15 headroom is reserved
    # for judged rubric injection. Substrate invariant: never default
    # to overweighting beyond the verifiable signal.
    assert sum(DecomposerEnvironment.DEFAULT_WEIGHTS.values()) <= 0.85 + 1e-9
