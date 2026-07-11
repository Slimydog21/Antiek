"""Antiek-bench weekly usage-learn compose (pure).

backlog_mutated and store_mutated always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

UsageOutcome = Literal["worked", "failed", "mixed", "unknown"]
VALID_OUTCOME = frozenset(("worked", "failed", "mixed", "unknown"))
Emphasis = Literal[
    "expand_failure_cases", "expand_success_cases", "hold_stable"
]


class AntiekBenchWeeklyUsageLearnComposeError(ValueError):
    """Fail-closed validation for weekly usage learn."""


@dataclass(frozen=True)
class SubBenchmarkRewriteProposal:
    task: str
    reason: str
    emphasis: Emphasis
    event_count: int
    failed_count: int
    worked_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "task": self.task,
            "reason": self.reason,
            "emphasis": self.emphasis,
            "event_count": self.event_count,
            "failed_count": self.failed_count,
            "worked_count": self.worked_count,
        }


@dataclass(frozen=True)
class AntiekBenchWeeklyUsageLearnCompose:
    week_id: str
    event_count: int
    task_count: int
    proposals: tuple[SubBenchmarkRewriteProposal, ...]
    proposal_count: int
    learn_ready: bool
    backlog_mutated: bool
    store_mutated: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "week_id": self.week_id,
            "event_count": self.event_count,
            "task_count": self.task_count,
            "proposals": [p.to_dict() for p in self.proposals],
            "proposal_count": self.proposal_count,
            "learn_ready": self.learn_ready,
            "backlog_mutated": False,
            "store_mutated": False,
            "notes": list(self.notes),
            "authority": "antiek_bench_weekly_usage_learn_compose_advisory",
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AntiekBenchWeeklyUsageLearnComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_antiek_bench_weekly_usage_learn(
    *,
    week_id: object,
    events: object,
    operator_ack: object,
    min_events_per_task: object | None = None,
) -> AntiekBenchWeeklyUsageLearnCompose:
    """Propose sub-benchmark rewrites from weekly usage. Never mutates store."""
    if not isinstance(operator_ack, bool):
        raise AntiekBenchWeeklyUsageLearnComposeError(
            "operator_ack must be an explicit boolean"
        )
    wid = _require_nonempty(week_id, field="week_id")
    if not isinstance(events, list):
        raise AntiekBenchWeeklyUsageLearnComposeError("events must be an array")

    min_events = 3 if min_events_per_task is None else min_events_per_task
    if not isinstance(min_events, int) or isinstance(min_events, bool) or min_events < 1:
        raise AntiekBenchWeeklyUsageLearnComposeError(
            "min_events_per_task must be a positive integer"
        )

    notes: list[str] = [
        "backlog_mutated=false — rewrite proposals are advisory only",
        "store_mutated=false — Antiek-bench store not written",
        "usage events are caller-supplied only (no invent)",
    ]

    by_task: dict[str, dict[str, int]] = {}
    seen: set[str] = set()
    for i, e in enumerate(events):
        if not isinstance(e, dict):
            raise AntiekBenchWeeklyUsageLearnComposeError(
                f"events[{i}] must be an object"
            )
        eid = _require_nonempty(e.get("event_id"), field=f"events[{i}].event_id")
        if eid in seen:
            raise AntiekBenchWeeklyUsageLearnComposeError(
                f"duplicate event_id: {eid}"
            )
        seen.add(eid)
        task = _require_nonempty(e.get("task"), field=f"events[{i}].task")
        _require_nonempty(e.get("model_id"), field=f"events[{i}].model_id")
        outcome = e.get("outcome")
        if outcome not in VALID_OUTCOME:
            raise AntiekBenchWeeklyUsageLearnComposeError(
                f"events[{i}].outcome must be worked|failed|mixed|unknown"
            )
        score = e.get("score")
        if score is not None:
            if not isinstance(score, (int, float)) or isinstance(score, bool):
                raise AntiekBenchWeeklyUsageLearnComposeError(
                    f"events[{i}].score must be finite in [0,1] when set"
                )
            sf = float(score)
            if sf != sf or sf < 0 or sf > 1:
                raise AntiekBenchWeeklyUsageLearnComposeError(
                    f"events[{i}].score must be finite in [0,1] when set"
                )
        agg = by_task.setdefault(
            task, {"worked": 0, "failed": 0, "mixed": 0, "unknown": 0, "count": 0}
        )
        agg["count"] += 1
        agg[str(outcome)] += 1

    event_count = len(events)
    task_count = len(by_task)
    notes.append(f"event_count={event_count} · task_count={task_count}")

    proposals: list[SubBenchmarkRewriteProposal] = []
    for task, agg in by_task.items():
        if agg["count"] < min_events:
            notes.append(
                f"task={task} skipped (events={agg['count']} < min={min_events})"
            )
            continue
        worked = agg["worked"]
        failed = agg["failed"]
        count = agg["count"]
        if failed > worked:
            emphasis: Emphasis = "expand_failure_cases"
            reason = f"failed={failed} > worked={worked} over {count} events"
        elif worked > failed and worked >= (count + 1) // 2:
            emphasis = "hold_stable"
            reason = f"worked={worked} dominates over {count} events"
        elif worked > 0 and failed == 0:
            emphasis = "expand_success_cases"
            reason = f"all non-fail outcomes worked={worked} over {count} events"
        else:
            emphasis = "expand_failure_cases"
            reason = (
                f"mixed/unknown heavy over {count} events "
                f"(failed={failed} worked={worked})"
            )
        proposals.append(
            SubBenchmarkRewriteProposal(
                task=task,
                reason=reason,
                emphasis=emphasis,
                event_count=count,
                failed_count=failed,
                worked_count=worked,
            )
        )

    proposals.sort(key=lambda p: p.task)
    proposal_count = len(proposals)
    notes.append(f"proposal_count={proposal_count}")

    learn_ready = operator_ack and proposal_count >= 1
    if not operator_ack:
        notes.append("learn_ready=false — operator_ack required")
    elif proposal_count == 0:
        notes.append(
            "learn_ready=false — no tasks met min_events threshold (no invent proposals)"
        )
    else:
        notes.append(
            "learn_ready=true — advisory rewrite proposals ready for operator review"
        )
    notes.extend(("backlog_mutated=false", "store_mutated=false"))

    return AntiekBenchWeeklyUsageLearnCompose(
        week_id=wid,
        event_count=event_count,
        task_count=task_count,
        proposals=tuple(proposals),
        proposal_count=proposal_count,
        learn_ready=learn_ready,
        backlog_mutated=False,
        store_mutated=False,
        notes=tuple(notes),
        authority="antiek_bench_weekly_usage_learn_compose_advisory",
    )


__all__ = [
    "AntiekBenchWeeklyUsageLearnCompose",
    "AntiekBenchWeeklyUsageLearnComposeError",
    "SubBenchmarkRewriteProposal",
    "compose_antiek_bench_weekly_usage_learn",
]
