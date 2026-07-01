"""Connector environment — verifier-shaped scaffold.

Sprint 14 rolls the orchestrate.py roles into training-task harnesses.
The Connector role is the graph-reasoning bridge: given keyword mappings
and seed pairs, it returns confirmed mappings, traversal paths, and
natural-language relationship renderings.
"""

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
from substrate.schemas import ConnectorDeliveredPayload  # noqa: E402


@dataclass
class ConnectorTask:
    """A single training example for the Connector environment."""

    task_id: str
    keyword_mappings: list[dict[str, Any]] = field(default_factory=list)
    seed_pairs: list[dict[str, Any]] = field(default_factory=list)
    algorithm: str = "top_n_shortest_paths"
    max_paths_per_pair: int = 5
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ConnectorRollout:
    """One sampled Connector output."""

    task: ConnectorTask
    raw_output: str
    parsed_output: dict[str, Any] | None
    policy_id: str
    error: str | None = None


@dataclass
class ConnectorReward:
    """Composite reward for Connector outputs."""

    total: float
    passed_all_verifiable: bool
    breakdown: list[RubricResult] = field(default_factory=list)
    weights: dict[str, float] = field(default_factory=dict)


PolicyFn = Callable[["ConnectorTask", dict[str, Any]], tuple[str, str]]


class ConnectorEnvironment:
    """Verifier-shaped environment for the Connector role."""

    DEFAULT_WEIGHTS: dict[str, float] = {
        "verifiable.connector.schema_validity": 0.30,
        "verifiable.connector.mapping_or_path_present": 0.25,
        "verifiable.connector.path_shape": 0.20,
        "verifiable.connector.relationship_coverage": 0.15,
        # 10% headroom for judged relationship quality.
    }

    def __init__(
        self,
        policy_fn: PolicyFn | None = None,
        tasks: list[ConnectorTask] | None = None,
        weights: dict[str, float] | None = None,
    ) -> None:
        self.policy_fn = policy_fn
        self._tasks = list(tasks or [])
        self.weights = dict(weights or self.DEFAULT_WEIGHTS)
        self._extra_rubrics: list[Any] = []

    def add_task(self, task: ConnectorTask) -> None:
        self._tasks.append(task)

    def tasks(self) -> list[ConnectorTask]:
        return list(self._tasks)

    def rollout(self, task: ConnectorTask) -> ConnectorRollout:
        if self.policy_fn is None:
            raise RuntimeError(
                "ConnectorEnvironment.rollout: no policy_fn provided. "
                "Inject one when constructing the env."
            )
        raw, policy_id = self.policy_fn(task, {"task_id": task.task_id})
        parsed: dict[str, Any] | None = None
        err: str | None = None
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError) as exc:
            err = f"json parse failed: {exc!r}"
        return ConnectorRollout(
            task=task,
            raw_output=raw,
            parsed_output=parsed,
            policy_id=policy_id,
            error=err,
        )

    def reward(self, rollout: ConnectorRollout) -> ConnectorReward:
        breakdown: list[RubricResult] = []

        schema_ok = False
        schema_error = rollout.error
        if rollout.parsed_output is not None and rollout.error is None:
            try:
                ConnectorDeliveredPayload.model_validate(rollout.parsed_output)
            except Exception as exc:
                schema_error = repr(exc)
            else:
                schema_ok = True
        breakdown.append(_result(
            "verifiable.connector.schema_validity",
            schema_ok,
            rollout.policy_id,
            {"parse_error": schema_error},
        ))

        breakdown.append(_score_mapping_or_path_present(
            rollout.parsed_output,
            rollout.policy_id,
        ))
        breakdown.append(_score_path_shape(
            rollout.parsed_output,
            rollout.policy_id,
        ))
        breakdown.append(_score_relationship_coverage(
            rollout.parsed_output,
            rollout.policy_id,
        ))

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
        return ConnectorReward(
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


def _score_mapping_or_path_present(
    parsed: dict[str, Any] | None,
    policy_id: str,
) -> RubricResult:
    mappings = (parsed or {}).get("keyword_mappings") or []
    paths = (parsed or {}).get("paths") or []
    passed = bool(mappings or paths)
    return _result(
        "verifiable.connector.mapping_or_path_present",
        passed,
        policy_id,
        {"n_keyword_mappings": len(mappings), "n_paths": len(paths)},
    )


def _score_path_shape(
    parsed: dict[str, Any] | None,
    policy_id: str,
) -> RubricResult:
    paths = (parsed or {}).get("paths") or []
    valid = 0
    for path in paths:
        if not isinstance(path, dict):
            continue
        nodes = path.get("path_nodes") or []
        relations = path.get("path_relations") or []
        depth = path.get("depth")
        if len(nodes) >= 2 and len(relations) == max(0, len(nodes) - 1) and depth == len(relations):
            valid += 1
    passed = not paths or valid == len(paths)
    return _result(
        "verifiable.connector.path_shape",
        passed,
        policy_id,
        {"n_paths": len(paths), "n_valid_paths": valid},
    )


def _score_relationship_coverage(
    parsed: dict[str, Any] | None,
    policy_id: str,
) -> RubricResult:
    paths = (parsed or {}).get("paths") or []
    rels = (parsed or {}).get("natural_language_relationships") or []
    indices = {
        rel.get("source_path_index")
        for rel in rels
        if isinstance(rel, dict) and isinstance(rel.get("source_path_index"), int)
    }
    expected = set(range(len(paths)))
    passed = not paths or expected.issubset(indices)
    return _result(
        "verifiable.connector.relationship_coverage",
        passed,
        policy_id,
        {
            "n_paths": len(paths),
            "n_relationships": len(rels),
            "covered_indices": sorted(indices),
        },
    )


__all__ = [
    "ConnectorEnvironment",
    "ConnectorReward",
    "ConnectorRollout",
    "ConnectorTask",
]
