"""Antiek-bench task → model recommendation compose (pure).

Weekly usage → task bests → decision tree pack.
live_router/secrets/meter/backlog/store/suite always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.antiek_bench_task_family_expand_compose import (
    AntiekBenchTaskFamilyExpandCompose,
    AntiekBenchTaskFamilyExpandComposeError,
    compose_antiek_bench_task_family_expand,
)
from substrate.settings_decision_tree_usage_bar_compose import (
    SettingsDecisionTreeUsageBarCompose,
    SettingsDecisionTreeUsageBarComposeError,
    compose_settings_decision_tree_usage_bar,
)


class AntiekBenchTaskModelRecommendationComposeError(ValueError):
    """Fail-closed validation for bench task model recommendation."""


@dataclass(frozen=True)
class TaskModelRecommendation:
    task: str
    recommended_model_id: str
    worked_rate: float | None
    avg_score: float | None
    event_count: int
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "task": self.task,
            "recommended_model_id": self.recommended_model_id,
            "worked_rate": self.worked_rate,
            "avg_score": self.avg_score,
            "event_count": self.event_count,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class AntiekBenchTaskModelRecommendationCompose:
    week_id: str
    focus_task: str
    expand: AntiekBenchTaskFamilyExpandCompose
    task_bests: tuple[dict[str, Any], ...]
    recommendation: TaskModelRecommendation | None
    decision_tree: SettingsDecisionTreeUsageBarCompose
    pack_ready: bool
    live_router_authorized: bool
    secrets_stored: bool
    live_meter_read: bool
    backlog_mutated: bool
    store_mutated: bool
    suite_rewritten: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "week_id": self.week_id,
            "focus_task": self.focus_task,
            "expand": self.expand.to_dict(),
            "task_bests": list(self.task_bests),
            "recommendation": (
                self.recommendation.to_dict() if self.recommendation else None
            ),
            "decision_tree": self.decision_tree.to_dict(),
            "pack_ready": self.pack_ready,
            "live_router_authorized": False,
            "secrets_stored": False,
            "live_meter_read": False,
            "backlog_mutated": False,
            "store_mutated": False,
            "suite_rewritten": False,
            "notes": list(self.notes),
            "authority": (
                "antiek_bench_task_model_recommendation_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AntiekBenchTaskModelRecommendationComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def _derive_task_bests(
    events: list[dict[str, Any]],
    min_events: int,
) -> tuple[list[dict[str, Any]], dict[str, list[TaskModelRecommendation]]]:
    by_task_model: dict[str, dict[str, dict[str, Any]]] = {}
    for e in events:
        if not isinstance(e, dict):
            continue
        task = str(e.get("task", "")).strip()
        mid = str(e.get("model_id", "")).strip()
        if not task or not mid:
            continue
        by_task_model.setdefault(task, {})
        if mid not in by_task_model[task]:
            by_task_model[task][mid] = {
                "model_id": mid,
                "event_count": 0,
                "worked": 0,
                "score_sum": 0.0,
                "score_n": 0,
            }
        a = by_task_model[task][mid]
        a["event_count"] += 1
        if e.get("outcome") == "worked":
            a["worked"] += 1
        score = e.get("score")
        if isinstance(score, (int, float)) and not isinstance(score, bool):
            a["score_sum"] += float(score)
            a["score_n"] += 1

    by_task: dict[str, list[TaskModelRecommendation]] = {}
    bests: list[dict[str, Any]] = []
    for task, models in by_task_model.items():
        recs: list[TaskModelRecommendation] = []
        for a in models.values():
            if a["event_count"] < min_events:
                continue
            worked_rate = (
                a["worked"] / a["event_count"] if a["event_count"] else None
            )
            avg_score = (
                a["score_sum"] / a["score_n"] if a["score_n"] > 0 else None
            )
            wr_s = f"{worked_rate:.2f}" if worked_rate is not None else "n/a"
            if avg_score is not None:
                reason = (
                    f"usage n={a['event_count']} worked_rate={wr_s} "
                    f"avg_score={avg_score:.2f}"
                )
            else:
                reason = f"usage n={a['event_count']} worked_rate={wr_s}"
            recs.append(
                TaskModelRecommendation(
                    task=task,
                    recommended_model_id=a["model_id"],
                    worked_rate=worked_rate,
                    avg_score=avg_score,
                    event_count=a["event_count"],
                    reason=reason,
                )
            )
        recs.sort(
            key=lambda r: (
                r.worked_rate if r.worked_rate is not None else -1.0,
                r.avg_score if r.avg_score is not None else -1.0,
                r.event_count,
            ),
            reverse=True,
        )
        by_task[task] = recs
        if recs:
            top = recs[0]
            bests.append(
                {
                    "task": task,
                    "best_model_id": top.recommended_model_id,
                    "score": top.avg_score,
                }
            )
    return bests, by_task


def compose_antiek_bench_task_model_recommendation(
    *,
    week_id: object,
    focus_task: object,
    events: object,
    models: object,
    daily_cap_usd: object,
    spent_usd: object,
    operator_ack: object,
    selected_model_id: object | None = None,
    projected_cost_usd_high: object | None = None,
    projected_cost_usd_low: object | None = None,
    existing_tasks: object | None = None,
    proposed_new_tasks: object | None = None,
    min_events_per_task: object | None = None,
    min_events_for_recommendation: object | None = None,
) -> AntiekBenchTaskModelRecommendationCompose:
    """Bench usage → model rec → decision tree. Never live-routes."""
    if not isinstance(operator_ack, bool):
        raise AntiekBenchTaskModelRecommendationComposeError(
            "operator_ack must be an explicit boolean"
        )
    week = _require_nonempty(week_id, field="week_id")
    focus = _require_nonempty(focus_task, field="focus_task")
    if not isinstance(events, list):
        raise AntiekBenchTaskModelRecommendationComposeError(
            "events must be an array"
        )
    if not isinstance(models, list) or len(models) == 0:
        raise AntiekBenchTaskModelRecommendationComposeError(
            "models must be a non-empty array"
        )

    min_rec = 2 if min_events_for_recommendation is None else min_events_for_recommendation
    if not isinstance(min_rec, int) or isinstance(min_rec, bool) or min_rec < 1:
        raise AntiekBenchTaskModelRecommendationComposeError(
            "min_events_for_recommendation must be integer ≥ 1"
        )

    notes: list[str] = [
        "live_router_authorized=false — recommendation is advisory only",
        "secrets_stored=false",
        "live_meter_read=false",
        "backlog_mutated=false · store_mutated=false · suite_rewritten=false",
    ]

    existing = [focus] if existing_tasks is None else existing_tasks
    try:
        expand = compose_antiek_bench_task_family_expand(
            week_id=week,
            existing_tasks=existing,
            events=events,
            operator_ack=operator_ack,
            proposed_new_tasks=proposed_new_tasks,
            min_events_per_task=min_events_per_task,
        )
    except AntiekBenchTaskFamilyExpandComposeError as e:
        raise AntiekBenchTaskModelRecommendationComposeError(str(e)) from e
    notes.extend(f"[expand] {n}" for n in expand.notes)

    # Normalize events for derive
    norm_events: list[dict[str, Any]] = []
    for e in events:
        if isinstance(e, dict):
            norm_events.append(e)

    bests, by_task = _derive_task_bests(norm_events, min_rec)
    focus_recs = by_task.get(focus, [])
    recommendation = focus_recs[0] if focus_recs else None
    if recommendation is None:
        notes.append(
            f"no recommendation for focus_task={focus} — need ≥{min_rec} "
            "events per model (no invent)"
        )
    else:
        notes.append(
            f"recommendation={recommendation.recommended_model_id} for {focus} · "
            f"{recommendation.reason}"
        )

    model_ids: set[str] = set()
    for i, m in enumerate(models):
        if not isinstance(m, dict):
            raise AntiekBenchTaskModelRecommendationComposeError(
                f"models[{i}] must be an object"
            )
        model_ids.add(
            _require_nonempty(m.get("model_id"), field=f"models[{i}].model_id")
        )

    if selected_model_id is not None and str(selected_model_id).strip() != "":
        selected = _require_nonempty(selected_model_id, field="selected_model_id")
        if selected not in model_ids:
            raise AntiekBenchTaskModelRecommendationComposeError(
                "selected_model_id must be in models"
            )
    elif (
        recommendation is not None
        and recommendation.recommended_model_id in model_ids
    ):
        selected = recommendation.recommended_model_id
        notes.append("selected_model_id defaulted to recommendation (advisory)")
    else:
        first = models[0]
        assert isinstance(first, dict)
        selected = str(first.get("model_id", "")).strip()
        notes.append(
            "selected_model_id defaulted to models[0] — no usable recommendation "
            "in inventory"
        )

    try:
        decision_tree = compose_settings_decision_tree_usage_bar(
            selected_model_id=selected,
            models=models,
            daily_cap_usd=daily_cap_usd,
            spent_usd=spent_usd,
            operator_ack=operator_ack,
            projected_cost_usd_high=projected_cost_usd_high,
            projected_cost_usd_low=projected_cost_usd_low,
            bench_bests=bests,
            focus_task=focus,
        )
    except SettingsDecisionTreeUsageBarComposeError as e:
        raise AntiekBenchTaskModelRecommendationComposeError(str(e)) from e
    notes.extend(f"[decision] {n}" for n in decision_tree.notes)

    pack_ready = (
        decision_tree.decision_ready is True and operator_ack is True
    )
    if pack_ready:
        notes.append(
            "pack_ready=true — bench→recommendation→decision tree advisory pack; "
            "still no live route"
        )
    else:
        notes.append(
            "pack_ready=false — decision tree or operator_ack gate open"
        )

    notes.extend(
        (
            "live_router_authorized=false",
            "backlog_mutated=false",
            "store_mutated=false",
            "suite_rewritten=false",
        )
    )

    return AntiekBenchTaskModelRecommendationCompose(
        week_id=week,
        focus_task=focus,
        expand=expand,
        task_bests=tuple(bests),
        recommendation=recommendation,
        decision_tree=decision_tree,
        pack_ready=pack_ready,
        live_router_authorized=False,
        secrets_stored=False,
        live_meter_read=False,
        backlog_mutated=False,
        store_mutated=False,
        suite_rewritten=False,
        notes=tuple(notes),
        authority="antiek_bench_task_model_recommendation_compose_advisory",
    )


def format_antiek_bench_task_model_recommendation_summary(
    c: AntiekBenchTaskModelRecommendationCompose,
) -> str:
    rec = (
        c.recommendation.recommended_model_id
        if c.recommendation
        else "none"
    )
    selected = c.decision_tree.driver.decision.selected_model_id
    return (
        f"pack_ready={c.pack_ready} · focus={c.focus_task} · rec={rec} · "
        f"selected={selected} · "
        f"live_router_authorized=false · suite_rewritten=false"
    )


__all__ = [
    "AntiekBenchTaskModelRecommendationCompose",
    "AntiekBenchTaskModelRecommendationComposeError",
    "TaskModelRecommendation",
    "compose_antiek_bench_task_model_recommendation",
    "format_antiek_bench_task_model_recommendation_summary",
]
