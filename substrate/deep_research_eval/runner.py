"""Offline eval runner with injectable provider + judge (no network, no wall clock)."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from .dataset import Query, QueryDataset
from .rubric import (
    AXES,
    JUDGE_MODEL_ID,
    RUBRIC_VERSION,
    JudgeScores,
    ResearchReport,
    build_judge_prompt,
    parse_judge_response,
)

# query → ResearchReport (mirrors antiek_bench's injectable ProviderFn pattern).
ProviderFn = Callable[[Query], ResearchReport]
# judge prompt → raw judge response text (parsed strictly by rubric.parse_judge_response).
JudgeFn = Callable[[str], str]

QueryStatus = Literal["MEASURED", "NOT_MEASURED"]
STATUS_MEASURED: QueryStatus = "MEASURED"
STATUS_NOT_MEASURED: QueryStatus = "NOT_MEASURED"

RUN_SCHEMA_VERSION = 1


def _unit_interval(value: object, field: str) -> float:
    """Deserialization guard: same rules as the live judge parser — numeric
    (bools rejected), finite, within [0, 1]. Fail closed on any deviation."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{field} must be a number")
    number = float(value)
    if not math.isfinite(number) or not 0.0 <= number <= 1.0:
        raise ValueError(f"{field} must be finite and within [0, 1]")
    return number


@dataclass(frozen=True)
class QueryScore:
    query_id: str
    status: QueryStatus
    # None exactly when status is NOT_MEASURED (fail closed — no default score).
    judge_scores: JudgeScores | None
    # Mechanical judge-independent signal: fraction of expected_coverage
    # anchors present in the answer text (case-insensitive substring match).
    coverage_hit_rate: float
    hit_anchors: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "query_id": self.query_id,
            "status": self.status,
            "judge_scores": None if self.judge_scores is None else self.judge_scores.as_dict(),
            "coverage_hit_rate": self.coverage_hit_rate,
            "hit_anchors": list(self.hit_anchors),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> QueryScore:
        query_id = data["query_id"]
        if not isinstance(query_id, str) or not query_id:
            raise ValueError("query_id must be a non-empty string")
        raw_status = data["status"]
        if raw_status not in ("MEASURED", "NOT_MEASURED"):
            raise ValueError(f"invalid query status: {raw_status!r}")
        status: QueryStatus = STATUS_MEASURED if raw_status == "MEASURED" else STATUS_NOT_MEASURED
        raw_judge = data["judge_scores"]
        judge_scores: JudgeScores | None = None
        if raw_judge is not None:
            if not isinstance(raw_judge, dict) or set(raw_judge) != set(AXES):
                raise ValueError("judge_scores must carry exactly the rubric axes")
            values = {
                axis: _unit_interval(raw_judge[axis], f"judge_scores[{axis}]") for axis in AXES
            }
            judge_scores = JudgeScores(
                factual_accuracy=values["factual_accuracy"],
                citation_accuracy=values["citation_accuracy"],
                completeness=values["completeness"],
                source_quality=values["source_quality"],
                tool_efficiency=values["tool_efficiency"],
            )
        if (status == STATUS_MEASURED) != (judge_scores is not None):
            raise ValueError("status and judge_scores presence must agree")
        hit_anchors = tuple(str(anchor) for anchor in data["hit_anchors"])
        return cls(
            query_id=query_id,
            status=status,
            judge_scores=judge_scores,
            coverage_hit_rate=_unit_interval(data["coverage_hit_rate"], "coverage_hit_rate"),
            hit_anchors=hit_anchors,
        )


@dataclass(frozen=True)
class EvalRun:
    run_id: str
    week_id: str
    run_id_seed: str
    dataset_id: str
    dataset_version: str
    rubric_version: str
    judge_model_id: str
    scores: tuple[QueryScore, ...]
    mean_axis_scores: dict[str, float]
    # Mean over MEASURED queries only; 0.0 when nothing was measured (and the
    # run is then incomplete, so nothing downstream may treat 0.0 as a score).
    mean_judge_score: float
    mean_coverage_hit_rate: float
    measured_count: int
    complete: bool

    @property
    def comparability_key(self) -> tuple[str, str, str]:
        """(dataset id@version, rubric version, judge model). Runs with
        different keys must never be compared (I-9)."""
        return (
            f"{self.dataset_id}@{self.dataset_version}",
            self.rubric_version,
            self.judge_model_id,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": RUN_SCHEMA_VERSION,
            "run_id": self.run_id,
            "week_id": self.week_id,
            "run_id_seed": self.run_id_seed,
            "dataset_id": self.dataset_id,
            "dataset_version": self.dataset_version,
            "rubric_version": self.rubric_version,
            "judge_model_id": self.judge_model_id,
            "comparability_key": list(self.comparability_key),
            "scores": [score.to_dict() for score in self.scores],
            "mean_axis_scores": dict(self.mean_axis_scores),
            "mean_judge_score": self.mean_judge_score,
            "mean_coverage_hit_rate": self.mean_coverage_hit_rate,
            "measured_count": self.measured_count,
            "complete": self.complete,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvalRun:
        """Tamper-evident deserialization: aggregates and completeness are
        RECOMPUTED from the per-query scores and must equal the stored values;
        run_id must equal its deterministic recomputation. Fail closed."""
        if data.get("schema_version") != RUN_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported eval run schema: {data.get('schema_version')!r} "
                f"(expected {RUN_SCHEMA_VERSION})"
            )
        scores_raw = data["scores"]
        if not isinstance(scores_raw, list):
            raise ValueError("scores must be a list")
        scores = tuple(QueryScore.from_dict(row) for row in scores_raw)
        recomputed = _aggregate(scores)

        stored_axis_raw = data["mean_axis_scores"]
        if not isinstance(stored_axis_raw, dict):
            raise ValueError("mean_axis_scores must be an object")
        stored_axis = {
            str(k): _stored_number(v, f"mean_axis_scores[{k}]")
            for k, v in stored_axis_raw.items()
        }
        stored_mean_judge = _stored_number(data["mean_judge_score"], "mean_judge_score")
        stored_mean_coverage = _stored_number(
            data["mean_coverage_hit_rate"], "mean_coverage_hit_rate"
        )
        stored_measured = data["measured_count"]
        if isinstance(stored_measured, bool) or not isinstance(stored_measured, int):
            raise ValueError("measured_count must be an integer")
        stored_complete = data["complete"]
        if not isinstance(stored_complete, bool):
            raise ValueError("complete must be a boolean")
        if (
            stored_axis != recomputed.mean_axis_scores
            or stored_mean_judge != recomputed.mean_judge_score
            or stored_mean_coverage != recomputed.mean_coverage_hit_rate
            or stored_measured != recomputed.measured_count
            or stored_complete is not recomputed.complete
        ):
            raise ValueError(
                "stored aggregates do not match recomputation from scores (tampered or corrupt)"
            )

        run = cls(
            run_id=str(data["run_id"]),
            week_id=str(data["week_id"]),
            run_id_seed=str(data["run_id_seed"]),
            dataset_id=str(data["dataset_id"]),
            dataset_version=str(data["dataset_version"]),
            rubric_version=str(data["rubric_version"]),
            judge_model_id=str(data["judge_model_id"]),
            scores=scores,
            mean_axis_scores=recomputed.mean_axis_scores,
            mean_judge_score=recomputed.mean_judge_score,
            mean_coverage_hit_rate=recomputed.mean_coverage_hit_rate,
            measured_count=recomputed.measured_count,
            complete=recomputed.complete,
        )
        if list(run.comparability_key) != list(data["comparability_key"]):
            raise ValueError("stored comparability_key does not match run identity")
        expected_run_id = _run_id(run.week_id, run.run_id_seed, run.comparability_key, run.scores)
        if run.run_id != expected_run_id:
            raise ValueError("stored run_id does not match deterministic identity")
        return run


def _stored_number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{field} must be a number")
    return float(value)


@dataclass(frozen=True)
class _Aggregates:
    mean_axis_scores: dict[str, float]
    mean_judge_score: float
    mean_coverage_hit_rate: float
    measured_count: int
    complete: bool


def _aggregate(scores: tuple[QueryScore, ...]) -> _Aggregates:
    """Single source of truth for run aggregates — used by ``run_eval`` and
    re-used by ``EvalRun.from_dict`` so stored aggregates cannot be forged."""
    per_axis: dict[str, list[float]] = {axis: [] for axis in AXES}
    judge_means: list[float] = []
    for score in scores:
        if score.judge_scores is not None:
            for axis, value in score.judge_scores.as_dict().items():
                per_axis[axis].append(value)
            judge_means.append(score.judge_scores.mean())
    mean_axis_scores = {
        axis: round(sum(values) / len(values), 6) if values else 0.0
        for axis, values in per_axis.items()
    }
    mean_judge_score = round(sum(judge_means) / len(judge_means), 6) if judge_means else 0.0
    mean_coverage_hit_rate = (
        round(sum(score.coverage_hit_rate for score in scores) / len(scores), 6)
        if scores
        else 0.0
    )
    measured_count = len(judge_means)
    return _Aggregates(
        mean_axis_scores=mean_axis_scores,
        mean_judge_score=mean_judge_score,
        mean_coverage_hit_rate=mean_coverage_hit_rate,
        measured_count=measured_count,
        complete=bool(scores) and measured_count == len(scores),
    )


def _coverage(answer_text: str, anchors: tuple[str, ...]) -> tuple[float, tuple[str, ...]]:
    if not anchors:
        return (0.0, ())
    text = answer_text.lower()
    hits = tuple(anchor for anchor in anchors if anchor.lower() in text)
    return (round(len(hits) / float(len(anchors)), 6), hits)


def _run_id(
    week_id: str,
    run_id_seed: str,
    comparability_key: tuple[str, str, str],
    scores: tuple[QueryScore, ...],
) -> str:
    """Deterministic run identity: hash of inputs + outcomes, no wall clock."""
    material = json.dumps(
        [
            week_id,
            run_id_seed,
            list(comparability_key),
            [
                [
                    score.query_id,
                    score.status,
                    None if score.judge_scores is None else score.judge_scores.as_dict(),
                    score.coverage_hit_rate,
                ]
                for score in scores
            ],
        ],
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(f"deep-research-eval:v1:{material}".encode()).hexdigest()[:16]
    return f"dre_{digest}"


def run_eval(
    dataset: QueryDataset,
    provider: ProviderFn,
    judge: JudgeFn,
    *,
    run_id_seed: str,
    week_id: str,
) -> EvalRun:
    """Score every dataset query with ``provider`` + single-call ``judge``.

    Never hits the network — both callables are injected. A judge response
    that fails the strict parser marks that query ``NOT_MEASURED`` and the
    aggregate run incomplete (fail closed).
    """
    wid = (week_id or "").strip()
    if not wid:
        raise ValueError("week_id is required")
    seed = (run_id_seed or "").strip()
    if not seed:
        raise ValueError("run_id_seed is required")

    scores: list[QueryScore] = []
    for query in dataset.queries:
        report = provider(query)
        if not isinstance(report, ResearchReport):
            raise TypeError("provider must return a ResearchReport")
        coverage_hit_rate, hit_anchors = _coverage(report.answer_text, query.expected_coverage)
        raw_judgment = judge(build_judge_prompt(query, report))
        if not isinstance(raw_judgment, str):
            raise TypeError("judge must return str")
        judge_scores = parse_judge_response(raw_judgment)
        status: QueryStatus = (
            STATUS_MEASURED if judge_scores is not None else STATUS_NOT_MEASURED
        )
        scores.append(
            QueryScore(
                query_id=query.query_id,
                status=status,
                judge_scores=judge_scores,
                coverage_hit_rate=coverage_hit_rate,
                hit_anchors=hit_anchors,
            )
        )

    frozen_scores = tuple(scores)
    aggregates = _aggregate(frozen_scores)
    comparability_key = (dataset.dataset_key, RUBRIC_VERSION, JUDGE_MODEL_ID)
    return EvalRun(
        run_id=_run_id(wid, seed, comparability_key, frozen_scores),
        week_id=wid,
        run_id_seed=seed,
        dataset_id=dataset.dataset_id,
        dataset_version=dataset.version,
        rubric_version=RUBRIC_VERSION,
        judge_model_id=JUDGE_MODEL_ID,
        scores=frozen_scores,
        mean_axis_scores=aggregates.mean_axis_scores,
        mean_judge_score=aggregates.mean_judge_score,
        mean_coverage_hit_rate=aggregates.mean_coverage_hit_rate,
        measured_count=aggregates.measured_count,
        complete=aggregates.complete,
    )
