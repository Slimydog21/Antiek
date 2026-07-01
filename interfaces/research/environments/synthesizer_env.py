"""Synthesizer environment — verifier-shaped scaffold.

Sprint 14 extends the decomposer environment pattern to the other
orchestrate.py roles. This module is the training-task view of the
Synthesizer role: a policy receives the already-rendered synthesis input
blocks and returns the canonical thesis JSON.

It intentionally mirrors ``DecomposerEnvironment`` instead of importing
``verifiers`` directly. The future ``verifiers.Environment`` migration
should be mechanical: Task, Rollout, Reward, Environment.
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

from skills.verification.rubric import (  # noqa: E402
    VERIFIABLE,
    CitationProvenanceRubric,
    RubricResult,
)
from substrate.schemas import SynthesizeDeliveredPayload  # noqa: E402


@dataclass
class SynthesizerTask:
    """A single training example for the Synthesizer environment."""

    task_id: str
    question: str
    decomposition_block: str = ""
    evidence_block: str = ""
    parameters_block: str = ""
    substrate_block: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SynthesizerRollout:
    """One sampled policy output for a synthesis task."""

    task: SynthesizerTask
    raw_output: str
    parsed_output: dict[str, Any] | None
    policy_id: str
    error: str | None = None


@dataclass
class SynthesizerReward:
    """Composite reward built from named sub-rubrics."""

    total: float
    passed_all_verifiable: bool
    breakdown: list[RubricResult] = field(default_factory=list)
    weights: dict[str, float] = field(default_factory=dict)


PolicyFn = Callable[["SynthesizerTask", dict[str, Any]], tuple[str, str]]


class SynthesizerEnvironment:
    """Verifier-shaped environment for the Synthesizer role."""

    DEFAULT_WEIGHTS: dict[str, float] = {
        "verifiable.synthesizer.schema_validity": 0.30,
        "verifiable.synthesizer.citation_provenance": 0.30,
        "verifiable.synthesizer.falsification_nonempty": 0.20,
        "verifiable.synthesizer.recommendation_coherence": 0.10,
        # 10% headroom reserved for a judged synthesis-quality rubric.
    }

    def __init__(
        self,
        policy_fn: PolicyFn | None = None,
        tasks: list[SynthesizerTask] | None = None,
        weights: dict[str, float] | None = None,
    ) -> None:
        self.policy_fn = policy_fn
        self._tasks = list(tasks or [])
        self.weights = dict(weights or self.DEFAULT_WEIGHTS)
        self.citation_rubric = CitationProvenanceRubric()
        self._extra_rubrics: list[Any] = []

    def add_task(self, task: SynthesizerTask) -> None:
        self._tasks.append(task)

    def tasks(self) -> list[SynthesizerTask]:
        return list(self._tasks)

    def rollout(self, task: SynthesizerTask) -> SynthesizerRollout:
        if self.policy_fn is None:
            raise RuntimeError(
                "SynthesizerEnvironment.rollout: no policy_fn provided. "
                "Inject one when constructing the env."
            )
        raw, policy_id = self.policy_fn(task, {"task_id": task.task_id})
        parsed: dict[str, Any] | None = None
        err: str | None = None
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError) as exc:
            err = f"json parse failed: {exc!r}"
        return SynthesizerRollout(
            task=task,
            raw_output=raw,
            parsed_output=parsed,
            policy_id=policy_id,
            error=err,
        )

    def reward(self, rollout: SynthesizerRollout) -> SynthesizerReward:
        breakdown: list[RubricResult] = []

        schema_ok = False
        schema_error = rollout.error
        if rollout.parsed_output is not None and rollout.error is None:
            try:
                SynthesizeDeliveredPayload.model_validate(rollout.parsed_output)
            except Exception as exc:
                schema_error = repr(exc)
            else:
                schema_ok = True
        breakdown.append(RubricResult(
            rubric_id="verifiable.synthesizer.schema_validity",
            kind=VERIFIABLE,
            score=1.0 if schema_ok else 0.0,
            passed=schema_ok,
            details={"parse_error": schema_error},
            policy_id_scored=rollout.policy_id,
        ))

        thesis_for_citations = _citation_rubric_target(rollout.parsed_output)
        citation = self.citation_rubric.score(thesis_for_citations)
        citation.policy_id_scored = rollout.policy_id
        breakdown.append(citation)

        falsification = _score_falsification_nonempty(
            rollout.parsed_output,
            rollout.policy_id,
        )
        breakdown.append(falsification)

        recommendation = _score_recommendation_coherence(
            rollout.parsed_output,
            rollout.policy_id,
        )
        breakdown.append(recommendation)

        for rubric in self._extra_rubrics:
            try:
                result = rubric.score(
                    rollout.parsed_output,
                    context={"question": rollout.task.question},
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
        return SynthesizerReward(
            total=total,
            passed_all_verifiable=verifiable_passed,
            breakdown=breakdown,
            weights=dict(self.weights),
        )

    def add_rubric(self, rubric: Any, *, weight: float = 0.0) -> None:
        self._extra_rubrics.append(rubric)
        if weight:
            self.weights[rubric.rubric_id] = weight


def _citation_rubric_target(parsed: dict[str, Any] | None) -> dict[str, Any]:
    if not parsed:
        return {}
    components = []
    for component in parsed.get("thesis_components", []) or []:
        if not isinstance(component, dict):
            continue
        normalized = dict(component)
        normalized["chunk_ids"] = list(
            component.get("supporting_chunk_ids")
            or component.get("chunk_ids")
            or []
        )
        components.append(normalized)
    target = dict(parsed)
    target["thesis_components"] = components
    return target


def _score_falsification_nonempty(
    parsed: dict[str, Any] | None,
    policy_id: str,
) -> RubricResult:
    recommendation = (parsed or {}).get("implicit_recommendation")
    falsifications = (parsed or {}).get("falsification_conditions") or []
    passed = bool(falsifications) or recommendation == "insufficient_evidence"
    return RubricResult(
        rubric_id="verifiable.synthesizer.falsification_nonempty",
        kind=VERIFIABLE,
        score=1.0 if passed else 0.0,
        passed=passed,
        details={
            "n_falsification_conditions": len(falsifications),
            "implicit_recommendation": recommendation,
        },
        policy_id_scored=policy_id,
    )


def _score_recommendation_coherence(
    parsed: dict[str, Any] | None,
    policy_id: str,
) -> RubricResult:
    recommendation = (parsed or {}).get("implicit_recommendation")
    components = (parsed or {}).get("thesis_components") or []
    insufficient = recommendation == "insufficient_evidence"
    passed = (
        insufficient and not components
    ) or (
        recommendation in {"proceed", "pass", "conditional", "undetermined"}
        and bool(components)
    )
    return RubricResult(
        rubric_id="verifiable.synthesizer.recommendation_coherence",
        kind=VERIFIABLE,
        score=1.0 if passed else 0.0,
        passed=passed,
        details={
            "implicit_recommendation": recommendation,
            "n_thesis_components": len(components),
        },
        policy_id_scored=policy_id,
    )


__all__ = [
    "SynthesizerEnvironment",
    "SynthesizerReward",
    "SynthesizerRollout",
    "SynthesizerTask",
]
