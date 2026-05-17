"""Decomposer environment — verifier-shaped scaffold.

Why this exists
---------------
The "wrap one role as a verifiers environment now, as a forcing
function" recommendation. The Decomposer is the right first target
because its contract is clean:

  Input:  a top-level investigation question
  Output: a list of sub-questions with categories + keywords +
          evidence types
  Rubric: paraphrase guard (cosine ≤ DECOMPOSER_PARAPHRASE_COSINE_MAX
          vs the top question); schema validity; sub-question count
          within [SUB_QUESTIONS_MIN, SUB_QUESTIONS_MAX]; keyword count
          within range.

What this is NOT
----------------
- This is NOT an import of ``verifiers``. The class shapes mirror
  what ``verifiers.Environment / Rollout / Reward`` will need so the
  future refactor is mechanical, not architectural.
- This is NOT wired into ``orchestration/loop_one``. The role pipeline
  keeps running through the dispatch path. This module is the
  parallel "training task harness" view of the same role.

Shape mapping (when ``verifiers`` is taken as a dep)
----------------------------------------------------
  DecomposerTask          → verifiers.Task / dataset row
  DecomposerRollout       → verifiers.Rollout
  DecomposerReward        → verifiers.Reward (composed of rubrics)
  DecomposerEnvironment   → verifiers.Environment

Sprint 9 day 5 port of upstream
``environments/decomposer_env.py``. Antiek adaptations: constants
sourced from ``substrate.constants``; rubric primitives from
``skills.verification.rubric``.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

_PKG_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

from substrate.constants import (  # noqa: E402
    KEYWORDS_MAX,
    KEYWORDS_MIN,
    SUB_QUESTIONS_MAX,
    SUB_QUESTIONS_MIN,
)
from skills.verification.rubric import (  # noqa: E402
    JUDGED,
    VERIFIABLE,
    ParaphraseGuardRubric,
    RubricResult,
)


# ---------------------------------------------------------------------------
# Task / rollout / reward shapes (stdlib-only; mirrors verifiers's API)
# ---------------------------------------------------------------------------


@dataclass
class DecomposerTask:
    """A single training example for the Decomposer environment.

    ``top_question`` is the input the policy sees. ``metadata``
    carries anything else the env needs (sector, source corpus,
    expected difficulty band, etc.)."""

    task_id: str
    top_question: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DecomposerRollout:
    """One sampled policy output for a task.

    ``parsed_output`` is the validated decomposer JSON. ``raw_output``
    is what the policy returned verbatim, useful for trace
    inspection."""

    task: DecomposerTask
    raw_output: str
    parsed_output: Optional[Dict[str, Any]]
    policy_id: str
    error: Optional[str] = None  # parse/validation error, None on success


@dataclass
class DecomposerReward:
    """Composite reward built from named sub-rubrics.

    ``total`` is the weighted sum (normalized to [0, 1]).
    ``breakdown`` keeps every component for later diagnosis —
    critical for Goodhart risk: if ``total`` is high but a key
    sub-rubric is failing, we want to see it."""

    total: float
    passed_all_verifiable: bool
    breakdown: List[RubricResult] = field(default_factory=list)
    weights: Dict[str, float] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------


PolicyFn = Callable[
    ["DecomposerTask", Dict[str, Any]], Tuple[str, str]
]


class DecomposerEnvironment:
    """Verifier-shaped environment for the Decomposer role.

    Usage::

        env = DecomposerEnvironment(policy_fn=my_policy_callable)
        for task in env.tasks():
            rollout = env.rollout(task)
            reward = env.reward(rollout)

    ``policy_fn`` is a callable
    ``(task, env_context) -> (raw_output, policy_id)``. Injecting it
    means this module never imports an LLM client; the same env can
    be exercised with DeepSeek for diagnostic runs and with Qwen for
    actual training, with provenance preserved via ``policy_id``.

    The default weights are deliberately verifiable-heavy. Judged-
    class rubrics (when added) should never exceed 50% of the
    composite without explicit override — per the Goodhart risk on
    judge bias.
    """

    DEFAULT_WEIGHTS: Dict[str, float] = {
        "verifiable.decomposer.paraphrase_guard": 0.35,
        "verifiable.decomposer.schema_validity": 0.20,
        "verifiable.decomposer.subq_count_bounds": 0.20,
        "verifiable.decomposer.keyword_count_bounds": 0.10,
        # 15% headroom reserved for future judged rubric(s) injected
        # via add_rubric(judged_rubric_instance, weight=0.15).
    }

    def __init__(
        self,
        policy_fn: Optional[PolicyFn] = None,
        tasks: Optional[List[DecomposerTask]] = None,
        weights: Optional[Dict[str, float]] = None,
    ):
        self.policy_fn = policy_fn
        self._tasks: List[DecomposerTask] = list(tasks or [])
        self.weights = dict(weights or self.DEFAULT_WEIGHTS)
        self.paraphrase_rubric = ParaphraseGuardRubric()
        self._extra_rubrics: List[Any] = []

    # ── Task surface ──

    def add_task(self, task: DecomposerTask) -> None:
        self._tasks.append(task)

    def tasks(self) -> List[DecomposerTask]:
        return list(self._tasks)

    # ── Rollout ──

    def rollout(self, task: DecomposerTask) -> DecomposerRollout:
        """Run the policy on a task. Returns a ``DecomposerRollout``.
        JSON parse failures land in ``rollout.error`` rather than
        raising — the reward path treats parse failure as a verifiable
        rubric miss."""
        if self.policy_fn is None:
            raise RuntimeError(
                "DecomposerEnvironment.rollout: no policy_fn provided. "
                "Inject one when constructing the env."
            )
        raw, policy_id = self.policy_fn(task, {"task_id": task.task_id})
        parsed: Optional[Dict[str, Any]] = None
        err: Optional[str] = None
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError) as e:
            err = f"json parse failed: {e!r}"
        return DecomposerRollout(
            task=task,
            raw_output=raw,
            parsed_output=parsed,
            policy_id=policy_id,
            error=err,
        )

    # ── Reward ──

    def reward(self, rollout: DecomposerRollout) -> DecomposerReward:
        breakdown: List[RubricResult] = []

        # 1. Paraphrase guard (only meaningful when parsed_output is valid)
        if (
            rollout.parsed_output
            and "decomposition" in rollout.parsed_output
        ):
            sub_qs = [
                d.get("sub_question", "")
                for d in rollout.parsed_output["decomposition"]
            ]
            pg = self.paraphrase_rubric.score({
                "top_question": rollout.task.top_question,
                "sub_questions": sub_qs,
            })
            pg.policy_id_scored = rollout.policy_id
            breakdown.append(pg)
        else:
            breakdown.append(RubricResult(
                rubric_id="verifiable.decomposer.paraphrase_guard",
                kind=VERIFIABLE, score=0.0, passed=False,
                details={"skipped_reason": "parsed_output missing/invalid"},
                policy_id_scored=rollout.policy_id,
            ))

        # 2. Schema validity (parse success is the proxy)
        schema_ok = (
            rollout.parsed_output is not None and rollout.error is None
        )
        breakdown.append(RubricResult(
            rubric_id="verifiable.decomposer.schema_validity",
            kind=VERIFIABLE, score=1.0 if schema_ok else 0.0,
            passed=schema_ok,
            details={"parse_error": rollout.error},
            policy_id_scored=rollout.policy_id,
        ))

        # 3. Sub-question count bounds
        n_subq = 0
        if (
            rollout.parsed_output
            and "decomposition" in rollout.parsed_output
        ):
            n_subq = len(rollout.parsed_output["decomposition"])
        in_bounds = SUB_QUESTIONS_MIN <= n_subq <= SUB_QUESTIONS_MAX
        breakdown.append(RubricResult(
            rubric_id="verifiable.decomposer.subq_count_bounds",
            kind=VERIFIABLE, score=1.0 if in_bounds else 0.0,
            passed=in_bounds,
            details={
                "n_sub_questions": n_subq,
                "min": SUB_QUESTIONS_MIN, "max": SUB_QUESTIONS_MAX,
            },
            policy_id_scored=rollout.policy_id,
        ))

        # 4. Keyword count bounds
        n_kw = 0
        if (
            rollout.parsed_output
            and isinstance(rollout.parsed_output.get("keywords"), list)
        ):
            n_kw = len(rollout.parsed_output["keywords"])
        kw_ok = KEYWORDS_MIN <= n_kw <= KEYWORDS_MAX
        breakdown.append(RubricResult(
            rubric_id="verifiable.decomposer.keyword_count_bounds",
            kind=VERIFIABLE, score=1.0 if kw_ok else 0.0,
            passed=kw_ok,
            details={
                "n_keywords": n_kw,
                "min": KEYWORDS_MIN, "max": KEYWORDS_MAX,
            },
            policy_id_scored=rollout.policy_id,
        ))

        # 5. Any extra rubrics injected (e.g. a judged coherence rubric).
        # Scoring errors are captured into the breakdown rather than raised
        # so a misbehaving judged rubric can't tank the whole training step.
        for r in self._extra_rubrics:
            try:
                result = r.score(
                    rollout.parsed_output,
                    context={"top_question": rollout.task.top_question},
                )
            except Exception as e:
                result = RubricResult(
                    rubric_id=getattr(r, "rubric_id", "unknown"),
                    kind=getattr(r, "kind", VERIFIABLE),
                    score=0.0, passed=False,
                    details={"scoring_error": repr(e)},
                    policy_id_scored=rollout.policy_id,
                )
            else:
                result.policy_id_scored = rollout.policy_id
            breakdown.append(result)

        # Weighted composite. Unknown rubric_ids contribute 0.
        total = 0.0
        used_weight = 0.0
        for br in breakdown:
            w = self.weights.get(br.rubric_id, 0.0)
            total += w * br.score
            used_weight += w
        if used_weight > 0:
            total = total / used_weight

        verifiable_passed = all(
            br.passed for br in breakdown
            if br.kind == VERIFIABLE and br.passed is not None
        )
        return DecomposerReward(
            total=total,
            passed_all_verifiable=verifiable_passed,
            breakdown=breakdown,
            weights=dict(self.weights),
        )

    # ── Extension hook for judged rubrics ──

    def add_rubric(self, rubric: Any, *, weight: float = 0.0) -> None:
        """Inject an additional rubric (verifiable or judged) into
        the composite. ``DEFAULT_WEIGHTS`` reserves 15% headroom for
        a judged rubric; callers that exceed that should reweight
        explicitly so the verifiable signals don't get drowned out
        (Goodhart risk)."""
        self._extra_rubrics.append(rubric)
        if weight:
            self.weights[rubric.rubric_id] = weight


# ---------------------------------------------------------------------------
# Smoke / sanity CLI
# ---------------------------------------------------------------------------


def _smoke() -> DecomposerReward:
    """Self-test using a synthetic policy that returns a hand-built
    valid decomposition. Exercises the reward path end-to-end with no
    LLM call."""
    env = DecomposerEnvironment()

    def fake_policy(
        task: DecomposerTask, ctx: Dict[str, Any],
    ) -> Tuple[str, str]:
        payload = {
            "decomposition": [
                {
                    "sub_question": f"Aspect {i} of {task.top_question[:20]}",
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
        return json.dumps(payload), "synthetic-policy/v0"

    env.policy_fn = fake_policy
    task = DecomposerTask(
        task_id="smoke-0",
        top_question="What forces shape the deep-tech bench in 2026?",
    )
    rollout = env.rollout(task)
    reward = env.reward(rollout)

    print(f"raw_output[:120]={rollout.raw_output[:120]!r}")
    print(f"parse error={rollout.error}")
    print(
        f"composite reward={reward.total:.3f} "
        f"passed_all_verifiable={reward.passed_all_verifiable}"
    )
    print("breakdown:")
    for br in reward.breakdown:
        passed = "" if br.passed is None else (
            " PASS" if br.passed else " FAIL"
        )
        print(f"  {br.rubric_id:<55} score={br.score:.2f}{passed}")
    return reward


def main() -> None:
    import argparse
    p = argparse.ArgumentParser(
        description="Decomposer environment (verifier-shaped scaffold)",
    )
    p.add_argument(
        "--smoke", action="store_true",
        help="Run the synthetic-policy smoke test and print scores",
    )
    args = p.parse_args()
    if args.smoke:
        _smoke()
    else:
        print(
            "Pass --smoke to exercise the env with a synthetic policy. "
            "Wiring to a real LLM policy is a separate concern.",
        )


if __name__ == "__main__":
    main()
