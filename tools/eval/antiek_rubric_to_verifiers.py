"""Adapter from Antiek rubric scores to a Verifiers-compatible shape.

Prime-style eval runners want one scalar reward. Antiek keeps a richer
rubric contract: deterministic score, judged score, and final score.
This module makes the scalar explicit while preserving the full split
in metadata so downstream tooling can audit what moved.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any


ScoreFn = Callable[[Any, Any], "AntiekRubricScore"]


@dataclass(frozen=True)
class AntiekRubricScore:
    deterministic_score: float
    judged_score: float | None
    final_score: float
    notes: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_unit_interval(self.deterministic_score, field="deterministic_score")
        if self.judged_score is not None:
            _validate_unit_interval(self.judged_score, field="judged_score")
        _validate_unit_interval(self.final_score, field="final_score")

    def to_verifiers_result(self) -> dict[str, Any]:
        return {
            "reward": self.final_score,
            "info": {
                "deterministic_score": self.deterministic_score,
                "judged_score": self.judged_score,
                "final_score": self.final_score,
                "notes": self.notes,
                "metadata": self.metadata,
            },
        }


@dataclass(frozen=True)
class VerifiersRubricAdapter:
    score_fn: ScoreFn

    def score(self, completion: Any, reference: Any) -> dict[str, Any]:
        return self.score_fn(completion, reference).to_verifiers_result()

    def reward(self, completion: Any, reference: Any) -> float:
        return float(self.score(completion, reference)["reward"])


def adapt_antiek_rubric(score_fn: ScoreFn) -> VerifiersRubricAdapter:
    return VerifiersRubricAdapter(score_fn=score_fn)


def parameter_extractor_rubric(completion: Any, reference: Any) -> AntiekRubricScore:
    """Score a parameter_extractor completion against one fixture row.

    The deterministic score is F1 over normalized parameter signatures:
    name/anchor, value, and units. No LLM judge is invoked here; callers
    that add a judged component should wrap this result and set
    ``judged_score`` explicitly.
    """
    expected = _parameter_signatures(_expected_parameters(reference))
    predicted = _parameter_signatures(_completion_parameters(completion))
    matched = len(predicted & expected)
    precision = matched / len(predicted) if predicted else 0.0
    recall = matched / len(expected) if expected else 1.0 if not predicted else 0.0
    deterministic = (
        0.0
        if precision + recall == 0.0
        else 2.0 * precision * recall / (precision + recall)
    )
    return AntiekRubricScore(
        deterministic_score=deterministic,
        judged_score=None,
        final_score=deterministic,
        notes=f"parameter signature F1: {matched}/{len(expected)} expected matched",
        metadata={
            "matched": matched,
            "predicted": len(predicted),
            "expected": len(expected),
            "precision": precision,
            "recall": recall,
        },
    )


def parameter_extractor_verifiers_adapter() -> VerifiersRubricAdapter:
    return adapt_antiek_rubric(parameter_extractor_rubric)


def _completion_parameters(completion: Any) -> list[Mapping[str, Any]]:
    if isinstance(completion, str):
        try:
            raw = json.loads(completion)
        except json.JSONDecodeError:
            return []
    else:
        raw = completion
    if isinstance(raw, Mapping):
        parameters = raw.get("parameters", [])
    else:
        parameters = raw
    if not isinstance(parameters, list):
        return []
    return [p for p in parameters if isinstance(p, Mapping)]


def _expected_parameters(reference: Any) -> list[Mapping[str, Any]]:
    if not isinstance(reference, Mapping):
        return []
    parameters = reference.get("expected_parameters", [])
    if not isinstance(parameters, list):
        return []
    return [p for p in parameters if isinstance(p, Mapping)]


def _parameter_signatures(parameters: list[Mapping[str, Any]]) -> set[tuple[str, str, str]]:
    return {
        (
            _normalize_text(str(p.get("name") or p.get("semantic_anchor") or "")),
            _normalize_value(_extract_value(p)),
            _normalize_text(str(p.get("units") or _metric_value(p).get("unit") or "")),
        )
        for p in parameters
        if p.get("name") or p.get("semantic_anchor")
    }


def _metric_value(parameter: Mapping[str, Any]) -> Mapping[str, Any]:
    metric = parameter.get("metric_value")
    return metric if isinstance(metric, Mapping) else {}


def _extract_value(parameter: Mapping[str, Any]) -> Any:
    metric = _metric_value(parameter)
    return metric.get("value") if "value" in metric else parameter.get("value")


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _normalize_value(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.12g}"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return _normalize_text(str(value))


def _validate_unit_interval(value: float, *, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{field} must be a number in [0, 1]")
    number = float(value)
    if not math.isfinite(number) or number < 0.0 or number > 1.0:
        raise ValueError(f"{field} must be a number in [0, 1]")


__all__ = [
    "AntiekRubricScore",
    "VerifiersRubricAdapter",
    "adapt_antiek_rubric",
    "parameter_extractor_rubric",
    "parameter_extractor_verifiers_adapter",
]
