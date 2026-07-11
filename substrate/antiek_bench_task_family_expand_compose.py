"""Antiek-bench task-family expand compose (pure).

backlog_mutated, store_mutated, suite_rewritten always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from substrate.antiek_bench_weekly_usage_learn_compose import (
    AntiekBenchWeeklyUsageLearnCompose,
    AntiekBenchWeeklyUsageLearnComposeError,
    compose_antiek_bench_weekly_usage_learn,
)

FamilySource = Literal["existing", "proposed_new", "usage_learn"]


class AntiekBenchTaskFamilyExpandComposeError(ValueError):
    """Fail-closed validation for task-family expand."""


@dataclass(frozen=True)
class TaskFamilyExpandItem:
    task: str
    source: FamilySource
    expand_recommended: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "task": self.task,
            "source": self.source,
            "expand_recommended": self.expand_recommended,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class AntiekBenchTaskFamilyExpandCompose:
    week_id: str
    learn: AntiekBenchWeeklyUsageLearnCompose
    families: tuple[TaskFamilyExpandItem, ...]
    family_count: int
    new_proposed_count: int
    expand_recommended_count: int
    expand_ready: bool
    backlog_mutated: bool
    store_mutated: bool
    suite_rewritten: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "week_id": self.week_id,
            "learn": self.learn.to_dict(),
            "families": [f.to_dict() for f in self.families],
            "family_count": self.family_count,
            "new_proposed_count": self.new_proposed_count,
            "expand_recommended_count": self.expand_recommended_count,
            "expand_ready": self.expand_ready,
            "backlog_mutated": False,
            "store_mutated": False,
            "suite_rewritten": False,
            "notes": list(self.notes),
            "authority": "antiek_bench_task_family_expand_compose_advisory",
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AntiekBenchTaskFamilyExpandComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_antiek_bench_task_family_expand(
    *,
    week_id: object,
    existing_tasks: object,
    events: object,
    operator_ack: object,
    proposed_new_tasks: object | None = None,
    min_events_per_task: object | None = None,
) -> AntiekBenchTaskFamilyExpandCompose:
    """Compose task-family expansion intent. Never mutates bench suite."""
    if not isinstance(operator_ack, bool):
        raise AntiekBenchTaskFamilyExpandComposeError(
            "operator_ack must be an explicit boolean"
        )
    week = _require_nonempty(week_id, field="week_id")
    if not isinstance(existing_tasks, list):
        raise AntiekBenchTaskFamilyExpandComposeError(
            "existing_tasks must be an array"
        )

    notes: list[str] = [
        "backlog_mutated=false — no bench backlog write",
        "store_mutated=false — no bench store write",
        "suite_rewritten=false — rewrite is intent only",
    ]

    existing: list[str] = []
    seen: set[str] = set()
    for i, raw in enumerate(existing_tasks):
        t = _require_nonempty(raw, field=f"existing_tasks[{i}]")
        if t in seen:
            raise AntiekBenchTaskFamilyExpandComposeError(
                f"duplicate existing_tasks: {t}"
            )
        seen.add(t)
        existing.append(t)

    proposed: list[dict[str, Any]] = []
    if proposed_new_tasks is not None:
        if not isinstance(proposed_new_tasks, list):
            raise AntiekBenchTaskFamilyExpandComposeError(
                "proposed_new_tasks must be an array when set"
            )
        for i, p in enumerate(proposed_new_tasks):
            if not isinstance(p, dict):
                raise AntiekBenchTaskFamilyExpandComposeError(
                    f"proposed_new_tasks[{i}] must be an object"
                )
            task = _require_nonempty(
                p.get("task"), field=f"proposed_new_tasks[{i}].task"
            )
            if task in seen:
                notes.append(
                    f"proposed_new_tasks[{i}] {task} already exists — treat as usage expand only"
                )
            desc = p.get("description")
            if desc is not None:
                desc = _require_nonempty(
                    desc, field=f"proposed_new_tasks[{i}].description"
                )
            proposed.append({"task": task, "description": desc})

    try:
        learn = compose_antiek_bench_weekly_usage_learn(
            week_id=week,
            events=events,
            operator_ack=operator_ack,
            min_events_per_task=min_events_per_task,
        )
    except AntiekBenchWeeklyUsageLearnComposeError as e:
        raise AntiekBenchTaskFamilyExpandComposeError(str(e)) from e
    notes.extend(learn.notes)

    learn_expand: dict[str, str] = {}
    for prop in learn.proposals:
        if prop.emphasis in ("expand_failure_cases", "expand_success_cases"):
            learn_expand[prop.task] = prop.reason

    families: list[TaskFamilyExpandItem] = []
    for t in existing:
        reason = learn_expand.get(t)
        families.append(
            TaskFamilyExpandItem(
                task=t,
                source="existing",
                expand_recommended=reason is not None,
                reason=reason
                or "hold_stable — no expand signal from weekly learn",
            )
        )

    new_proposed_count = 0
    for p in proposed:
        if p["task"] in existing:
            continue
        new_proposed_count += 1
        learn_reason = learn_expand.get(p["task"])
        if learn_reason:
            reason = learn_reason
        elif p.get("description"):
            reason = f"platform expansion: {p['description']}"
        else:
            reason = (
                "platform expansion — new task family proposed (caller-supplied)"
            )
        families.append(
            TaskFamilyExpandItem(
                task=str(p["task"]),
                source="proposed_new",
                expand_recommended=True,
                reason=reason,
            )
        )

    for task, reason in learn_expand.items():
        if any(f.task == task for f in families):
            continue
        families.append(
            TaskFamilyExpandItem(
                task=task,
                source="usage_learn",
                expand_recommended=True,
                reason=reason,
            )
        )

    expand_recommended_count = sum(1 for f in families if f.expand_recommended)
    notes.append(
        f"family_count={len(families)} · new_proposed={new_proposed_count} · expand_recommended={expand_recommended_count}"
    )

    expand_ready = operator_ack and (
        expand_recommended_count > 0 or new_proposed_count > 0
    )
    if not operator_ack:
        notes.append("expand_ready=false — operator_ack required")
    elif not expand_ready:
        notes.append(
            "expand_ready=false — no expand recommendations or new families"
        )
    else:
        notes.append(
            "expand_ready=true — expansion intent only; suite_rewritten=false"
        )

    if learn.backlog_mutated is not False or learn.store_mutated is not False:
        raise AntiekBenchTaskFamilyExpandComposeError(
            "invariant: learn honesty flags must remain false"
        )

    notes.extend(
        (
            "backlog_mutated=false",
            "store_mutated=false",
            "suite_rewritten=false",
        )
    )

    return AntiekBenchTaskFamilyExpandCompose(
        week_id=week,
        learn=learn,
        families=tuple(families),
        family_count=len(families),
        new_proposed_count=new_proposed_count,
        expand_recommended_count=expand_recommended_count,
        expand_ready=expand_ready,
        backlog_mutated=False,
        store_mutated=False,
        suite_rewritten=False,
        notes=tuple(notes),
        authority="antiek_bench_task_family_expand_compose_advisory",
    )


def format_antiek_bench_task_family_expand_summary(
    c: AntiekBenchTaskFamilyExpandCompose,
) -> str:
    return (
        f"expand_ready={c.expand_ready} · families={c.family_count} · "
        f"new={c.new_proposed_count} · expand_rec={c.expand_recommended_count} · "
        f"backlog_mutated=false · store_mutated=false · suite_rewritten=false"
    )


__all__ = [
    "AntiekBenchTaskFamilyExpandCompose",
    "AntiekBenchTaskFamilyExpandComposeError",
    "TaskFamilyExpandItem",
    "compose_antiek_bench_task_family_expand",
    "format_antiek_bench_task_family_expand_summary",
]
