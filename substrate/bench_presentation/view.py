"""Antiek-bench weekly presentation (pure view).

Operator vision: show in Settings which models scored best on which tasks
for a given week. This module **presents** injected weekly records — it does
not run the bench, own ``substrate/antiek_bench``, or dispatch models.

Honesty:
* Missing week / empty runs → ``best_by_task`` empty, scores null where absent
* Never invent numeric scores
* Authority remains advisory (display only)
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class TaskModelScore:
    task: str
    model_id: str
    score: float | None
    """None when not measured for this task/week."""
    n_runs: int = 0
    notes: str = ""


@dataclass(frozen=True)
class WeeklyBenchView:
    week_id: str
    """ISO week label e.g. 2026-W28; empty if unknown."""
    authority: str
    best_by_task: dict[str, str]
    """task → model_id of highest measured score (ties: stable by model_id)."""
    scores: list[TaskModelScore]
    incomplete: bool
    """True when any score is null or week has zero measured runs."""
    notes: list[str] = field(default_factory=list)


def _finite_score(raw: Any) -> float | None:
    if raw is None:
        return None
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return None
    if v != v:  # NaN
        return None
    return v


def present_weekly_bench(
    records: Sequence[Mapping[str, Any]] | None,
    *,
    week_id: str = "",
) -> WeeklyBenchView:
    """Build a Settings-facing view from injected weekly run records.

    Each record may carry: ``task``, ``model_id`` / ``model``, ``score``,
    optional ``n_runs``, optional ``notes``. Unknown/missing scores stay null.
    """
    notes: list[str] = [
        "authority=advisory — presentation only; not production dispatch",
        "does not read substrate/antiek_bench; callers inject records",
    ]
    rows = list(records or [])
    week = (week_id or "").strip()
    if not week:
        notes.append("week_id unknown")
    if not rows:
        notes.append("no runs injected for this week — scores empty (not zero-faked)")
        return WeeklyBenchView(
            week_id=week,
            authority="advisory",
            best_by_task={},
            scores=[],
            incomplete=True,
            notes=notes,
        )

    scores: list[TaskModelScore] = []
    incomplete = False
    # Aggregate best measured score per task.
    best: dict[str, tuple[float, str]] = {}

    for rec in rows:
        task = str(rec.get("task") or "general").strip() or "general"
        model = str(rec.get("model_id") or rec.get("model") or "").strip()
        if not model:
            incomplete = True
            notes.append("skipped record with empty model_id")
            continue
        score = _finite_score(rec.get("score"))
        n_runs = int(rec.get("n_runs") or 0)
        if score is None:
            incomplete = True
        scores.append(
            TaskModelScore(
                task=task,
                model_id=model,
                score=score,
                n_runs=n_runs,
                notes=str(rec.get("notes") or ""),
            )
        )
        if score is not None:
            prev = best.get(task)
            if prev is None or score > prev[0] or (score == prev[0] and model < prev[1]):
                best[task] = (score, model)

    best_by_task = {t: mid for t, (_s, mid) in sorted(best.items())}
    if incomplete:
        notes.append("incomplete week: at least one null/unmeasured score")

    # Stable order for presentation.
    scores.sort(key=lambda s: (s.task, s.model_id))

    return WeeklyBenchView(
        week_id=week,
        authority="advisory",
        best_by_task=best_by_task,
        scores=scores,
        incomplete=incomplete or not best_by_task,
        notes=notes,
    )


def weekly_view_to_dict(view: WeeklyBenchView) -> dict[str, Any]:
    return {
        "week_id": view.week_id,
        "authority": view.authority,
        "best_by_task": dict(view.best_by_task),
        "incomplete": view.incomplete,
        "notes": list(view.notes),
        "scores": [
            {
                "task": s.task,
                "model_id": s.model_id,
                "score": s.score,
                "n_runs": s.n_runs,
                "notes": s.notes,
            }
            for s in view.scores
        ],
    }


__all__ = [
    "TaskModelScore",
    "WeeklyBenchView",
    "present_weekly_bench",
    "weekly_view_to_dict",
]
