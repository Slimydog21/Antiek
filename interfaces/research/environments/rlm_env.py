"""Full RLM loop environment — verifier-shaped scaffold."""

from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

_PKG_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

from interfaces.research.rlm_repl import ReplSummary, RLMRepl  # noqa: E402
from orchestration.rlm import (  # noqa: E402
    RLMEventEmitter,
    create_session,
    run_loop_with_timeout,
)
from skills.verification.rubric import VERIFIABLE, RubricResult  # noqa: E402
from substrate.schemas.events import Event  # noqa: E402


@dataclass
class RLMTask:
    task_id: str
    prompt: str
    source_text: str = ""
    investigation_id: str = "rlm-env"
    root_role: str = "wrestler"
    document_id: str | None = None
    max_iterations: int = 4
    timeout_s: float = 1.0
    iteration_cost_usd: Decimal = Decimal("0.00")
    expected_terms: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RLMRollout:
    task: RLMTask
    final_answer: str
    status: str
    iterations: int
    policy_id: str
    repl_snapshot: dict[str, Any]
    event_action_types: list[str] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)
    error: str | None = None


@dataclass
class RLMReward:
    total: float
    passed_all_verifiable: bool
    breakdown: list[RubricResult] = field(default_factory=list)
    weights: dict[str, float] = field(default_factory=dict)


PolicyFn = Callable[["RLMTask", ReplSummary], tuple[str, str]]


class RLMEnvironment:
    """Verifier-shaped environment for a complete RLM REPL loop."""

    DEFAULT_WEIGHTS: dict[str, float] = {
        "verifiable.rlm.completed_status": 0.25,
        "verifiable.rlm.answer_extracted": 0.20,
        "verifiable.rlm.iteration_budget": 0.15,
        "verifiable.rlm.corpus_is_variable": 0.15,
        "verifiable.rlm.lifecycle_events": 0.15,
        # 10% headroom for judged final-answer quality.
    }

    def __init__(
        self,
        policy_fn: PolicyFn | None = None,
        tasks: list[RLMTask] | None = None,
        weights: dict[str, float] | None = None,
        *,
        auto_ratify: bool = True,
    ) -> None:
        self.policy_fn = policy_fn
        self._tasks = list(tasks or [])
        self.weights = dict(weights or self.DEFAULT_WEIGHTS)
        self.auto_ratify = auto_ratify
        self._extra_rubrics: list[Any] = []

    def add_task(self, task: RLMTask) -> None:
        self._tasks.append(task)

    def tasks(self) -> list[RLMTask]:
        return list(self._tasks)

    def rollout(self, task: RLMTask) -> RLMRollout:
        if self.policy_fn is None:
            raise RuntimeError(
                "RLMEnvironment.rollout: no policy_fn provided. "
                "Inject one when constructing the env."
            )
        try:
            return asyncio.run(self._rollout_async(task))
        except RuntimeError as exc:
            if "asyncio.run() cannot be called" in str(exc):
                raise RuntimeError(
                    "RLMEnvironment.rollout cannot run inside an active event loop; "
                    "call _rollout_async from async harnesses."
                ) from exc
            raise

    async def _rollout_async(self, task: RLMTask) -> RLMRollout:
        seen: list[Event] = []

        async def broadcast(event: Event) -> None:
            seen.append(event)

        with _ratified_if_enabled(self.auto_ratify):
            session = create_session(
                investigation_id=task.investigation_id,
                root_role=task.root_role,
                document_id=task.document_id,
            )

        repl = RLMRepl(
            corpus={"prompt": task.prompt, "source_text": task.source_text},
            max_iterations=task.max_iterations,
        )
        emitter = RLMEventEmitter(
            broadcast,
            investigation_id=task.investigation_id,
            document_id=task.document_id,
            param_version="rlm-env",
        )
        policy_ids: list[str] = []

        def generate_code(summary: ReplSummary) -> str:
            code, policy_id = self.policy_fn(task, summary)
            policy_ids.append(policy_id)
            return code

        try:
            result = await run_loop_with_timeout(
                repl=repl,
                generate_code=generate_code,
                session=session,
                emitter=emitter,
                max_iterations=task.max_iterations,
                timeout_s=task.timeout_s,
                cost_usd=task.iteration_cost_usd,
                iteration_summary=lambda summary, _code: (
                    f"rlm env iteration {summary.iteration + 1}"
                ),
            )
        except Exception as exc:
            return RLMRollout(
                task=task,
                final_answer=repl.final_answer(),
                status="failed",
                iterations=session.state.iteration_count,
                policy_id=policy_ids[-1] if policy_ids else "<unknown>",
                repl_snapshot=repl.snapshot(),
                event_action_types=[_event_action_type(event) for event in seen],
                events=seen,
                error=repr(exc),
            )

        return RLMRollout(
            task=task,
            final_answer=result.final_answer,
            status=result.status,
            iterations=result.iterations,
            policy_id=policy_ids[-1] if policy_ids else "<unknown>",
            repl_snapshot=repl.snapshot(),
            event_action_types=[_event_action_type(event) for event in seen],
            events=seen,
        )

    def reward(self, rollout: RLMRollout) -> RLMReward:
        breakdown = [
            _score_completed_status(rollout),
            _score_answer_extracted(rollout),
            _score_iteration_budget(rollout),
            _score_corpus_is_variable(rollout),
            _score_lifecycle_events(rollout),
        ]

        for rubric in self._extra_rubrics:
            try:
                result = rubric.score(rollout, context={"task": rollout.task})
            except Exception as exc:
                result = RubricResult(
                    rubric_id=getattr(rubric, "rubric_id", "unknown"),
                    kind=getattr(rubric, "kind", VERIFIABLE),
                    score=0.0,
                    passed=False,
                    details={"scoring_error": repr(exc)},
                    policy_id_scored=rollout.policy_id,
                )
            else:
                result.policy_id_scored = rollout.policy_id
            breakdown.append(result)

        total = 0.0
        used_weight = 0.0
        for result in breakdown:
            weight = self.weights.get(result.rubric_id, 0.0)
            total += weight * result.score
            used_weight += weight
        if used_weight > 0:
            total = total / used_weight

        verifiable_passed = all(
            result.passed
            for result in breakdown
            if result.kind == VERIFIABLE and result.passed is not None
        )
        return RLMReward(
            total=total,
            passed_all_verifiable=verifiable_passed,
            breakdown=breakdown,
            weights=dict(self.weights),
        )

    def add_rubric(self, rubric: Any, *, weight: float = 0.0) -> None:
        self._extra_rubrics.append(rubric)
        if weight:
            self.weights[rubric.rubric_id] = weight


def _result(
    rubric_id: str,
    passed: bool,
    policy_id: str,
    details: dict[str, Any],
) -> RubricResult:
    return RubricResult(
        rubric_id=rubric_id,
        kind=VERIFIABLE,
        score=1.0 if passed else 0.0,
        passed=passed,
        details=details,
        policy_id_scored=policy_id,
    )


def _score_completed_status(rollout: RLMRollout) -> RubricResult:
    passed = rollout.status == "completed" and rollout.error is None
    return _result(
        "verifiable.rlm.completed_status",
        passed,
        rollout.policy_id,
        {"status": rollout.status, "error": rollout.error},
    )


def _score_answer_extracted(rollout: RLMRollout) -> RubricResult:
    answer = rollout.final_answer.strip()
    missing_terms = [
        term for term in rollout.task.expected_terms
        if term.lower() not in answer.lower()
    ]
    passed = bool(answer) and not missing_terms
    return _result(
        "verifiable.rlm.answer_extracted",
        passed,
        rollout.policy_id,
        {
            "answer_len": len(rollout.final_answer),
            "missing_expected_terms": missing_terms,
        },
    )


def _score_iteration_budget(rollout: RLMRollout) -> RubricResult:
    passed = 0 < rollout.iterations <= rollout.task.max_iterations
    return _result(
        "verifiable.rlm.iteration_budget",
        passed,
        rollout.policy_id,
        {
            "iterations": rollout.iterations,
            "max_iterations": rollout.task.max_iterations,
        },
    )


def _score_corpus_is_variable(rollout: RLMRollout) -> RubricResult:
    variable_names = set(rollout.repl_snapshot.get("variable_names") or [])
    expected = {"prompt", "source_text"}
    passed = expected.issubset(variable_names)
    return _result(
        "verifiable.rlm.corpus_is_variable",
        passed,
        rollout.policy_id,
        {"variable_names": sorted(variable_names)},
    )


def _score_lifecycle_events(rollout: RLMRollout) -> RubricResult:
    actions = rollout.event_action_types
    passed = bool(actions) and actions[-1] == "rlm.session_completed"
    if rollout.status == "cost_capped":
        passed = bool(actions) and actions[-1] == "rlm.session_completed"
    elif rollout.status in {"failed", "timeout"}:
        passed = bool(actions) and actions[-1] == "rlm.session_failed"
    return _result(
        "verifiable.rlm.lifecycle_events",
        passed,
        rollout.policy_id,
        {"event_action_types": actions},
    )


def _event_action_type(event: Event) -> str:
    action_type = event.payload.action_type
    return str(action_type.value) if hasattr(action_type, "value") else str(action_type)


@contextmanager
def _ratified_if_enabled(enabled: bool):
    if not enabled:
        yield
        return
    old = os.environ.get("ANTIEK_RLM_RATIFIED")
    os.environ["ANTIEK_RLM_RATIFIED"] = "1"
    try:
        yield
    finally:
        if old is None:
            os.environ.pop("ANTIEK_RLM_RATIFIED", None)
        else:
            os.environ["ANTIEK_RLM_RATIFIED"] = old


__all__ = [
    "RLMEnvironment",
    "RLMReward",
    "RLMRollout",
    "RLMTask",
]
