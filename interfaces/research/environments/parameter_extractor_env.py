"""Parameter Extractor environment — verifier-shaped scaffold."""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

_PKG_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

from skills.verification.rubric import VERIFIABLE, RubricResult  # noqa: E402
from substrate.schemas import ParameterExtractDeliveredPayload  # noqa: E402


@dataclass
class ParameterExtractorTask:
    task_id: str
    evidence_block: str
    canonical_source_chunk_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ParameterExtractorRollout:
    task: ParameterExtractorTask
    raw_output: str
    parsed_output: dict[str, Any] | None
    policy_id: str
    error: str | None = None


@dataclass
class ParameterExtractorReward:
    total: float
    passed_all_verifiable: bool
    breakdown: list[RubricResult] = field(default_factory=list)
    weights: dict[str, float] = field(default_factory=dict)


PolicyFn = Callable[["ParameterExtractorTask", dict[str, Any]], tuple[str, str]]


class ParameterExtractorEnvironment:
    """Verifier-shaped environment for the Parameter Extractor role."""

    DEFAULT_WEIGHTS: dict[str, float] = {
        "verifiable.parameter_extractor.schema_validity": 0.30,
        "verifiable.parameter_extractor.source_citation": 0.25,
        "verifiable.parameter_extractor.metric_value_consistency": 0.25,
        "verifiable.parameter_extractor.constraint_derivation": 0.10,
        # 10% headroom for a judged parameter-importance rubric.
    }

    def __init__(
        self,
        policy_fn: PolicyFn | None = None,
        tasks: list[ParameterExtractorTask] | None = None,
        weights: dict[str, float] | None = None,
    ) -> None:
        self.policy_fn = policy_fn
        self._tasks = list(tasks or [])
        self.weights = dict(weights or self.DEFAULT_WEIGHTS)
        self._extra_rubrics: list[Any] = []

    def add_task(self, task: ParameterExtractorTask) -> None:
        self._tasks.append(task)

    def tasks(self) -> list[ParameterExtractorTask]:
        return list(self._tasks)

    def rollout(self, task: ParameterExtractorTask) -> ParameterExtractorRollout:
        if self.policy_fn is None:
            raise RuntimeError(
                "ParameterExtractorEnvironment.rollout: no policy_fn provided. "
                "Inject one when constructing the env."
            )
        raw, policy_id = self.policy_fn(task, {"task_id": task.task_id})
        parsed: dict[str, Any] | None = None
        err: str | None = None
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError) as exc:
            err = f"json parse failed: {exc!r}"
        return ParameterExtractorRollout(
            task=task,
            raw_output=raw,
            parsed_output=parsed,
            policy_id=policy_id,
            error=err,
        )

    def reward(
        self,
        rollout: ParameterExtractorRollout,
    ) -> ParameterExtractorReward:
        breakdown: list[RubricResult] = []

        schema_ok = False
        schema_error = rollout.error
        if rollout.parsed_output is not None and rollout.error is None:
            try:
                ParameterExtractDeliveredPayload.model_validate(
                    rollout.parsed_output,
                )
            except Exception as exc:
                schema_error = repr(exc)
            else:
                schema_ok = True
        breakdown.append(_result(
            "verifiable.parameter_extractor.schema_validity",
            schema_ok,
            rollout.policy_id,
            {"parse_error": schema_error},
        ))

        breakdown.append(_score_source_citation(rollout))
        breakdown.append(_score_metric_value_consistency(rollout))
        breakdown.append(_score_constraint_derivation(rollout))

        for rubric in self._extra_rubrics:
            try:
                result = rubric.score(
                    rollout.parsed_output,
                    context={"task": rollout.task},
                )
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
        return ParameterExtractorReward(
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


def _parameters(parsed: dict[str, Any] | None) -> list[dict[str, Any]]:
    return [
        parameter
        for parameter in (parsed or {}).get("parameters", []) or []
        if isinstance(parameter, dict)
    ]


def _score_source_citation(
    rollout: ParameterExtractorRollout,
) -> RubricResult:
    params = _parameters(rollout.parsed_output)
    canonical = set(rollout.task.canonical_source_chunk_ids)
    cited = 0
    invalid_refs: list[str] = []
    for parameter in params:
        refs = parameter.get("source_chunk_ids") or []
        if refs:
            cited += 1
        if canonical:
            invalid_refs.extend(str(ref) for ref in refs if ref not in canonical)
    passed = bool(params) and cited == len(params) and not invalid_refs
    return _result(
        "verifiable.parameter_extractor.source_citation",
        passed,
        rollout.policy_id,
        {
            "n_parameters": len(params),
            "n_cited": cited,
            "invalid_refs": invalid_refs,
        },
    )


def _score_metric_value_consistency(
    rollout: ParameterExtractorRollout,
) -> RubricResult:
    params = _parameters(rollout.parsed_output)
    invalid: list[str] = []
    for parameter in params:
        anchor = str(parameter.get("semantic_anchor") or "<unknown>")
        metric = parameter.get("metric_value") or {}
        if not isinstance(metric, dict):
            invalid.append(anchor)
            continue
        value_type = metric.get("value_type")
        value = metric.get("value")
        if not _metric_value_matches(value_type, value):
            invalid.append(anchor)
    passed = bool(params) and not invalid
    return _result(
        "verifiable.parameter_extractor.metric_value_consistency",
        passed,
        rollout.policy_id,
        {"n_parameters": len(params), "invalid_anchors": invalid},
    )


def _metric_value_matches(value_type: Any, value: Any) -> bool:
    if value_type == "scalar":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if value_type == "range":
        return (
            isinstance(value, list)
            and len(value) == 2
            and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in value)
            and value[0] <= value[1]
        )
    if value_type == "categorical":
        return isinstance(value, str) or (
            isinstance(value, list) and all(isinstance(v, str) for v in value)
        )
    if value_type == "null":
        return value is None
    return False


def _score_constraint_derivation(
    rollout: ParameterExtractorRollout,
) -> RubricResult:
    params = _parameters(rollout.parsed_output)
    constraints = (rollout.parsed_output or {}).get("constraints") or []
    strict_params = [
        parameter
        for parameter in params
        if parameter.get("constraint_strictness") in {"hard", "target"}
    ]
    passed = len(constraints) >= len(strict_params)
    return _result(
        "verifiable.parameter_extractor.constraint_derivation",
        passed,
        rollout.policy_id,
        {
            "n_strict_parameters": len(strict_params),
            "n_constraints": len(constraints),
        },
    )


__all__ = [
    "ParameterExtractorEnvironment",
    "ParameterExtractorReward",
    "ParameterExtractorRollout",
    "ParameterExtractorTask",
]
