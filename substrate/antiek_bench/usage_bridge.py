"""Bridge workstation outcomes → Antiek-bench usage events for suite rewrite.

When deep-research / twin-promote / collective sessions complete, record
usage-shaped events so ``propose_suite_delta`` can learn weekly task patterns
and propose recursive suite rewrites (operator still approves/promotes).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Sequence

from .store import BenchStore

TaskClass = Literal["distill", "synthesize", "wrestle", "book_qa"]
Outcome = Literal["worked", "failed"]


@dataclass(frozen=True)
class UsageEvent:
    task_class: TaskClass
    outcome: Outcome
    prompt_hint: str = ""
    source: str = "engagement"
    model_id: str | None = None
    week_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_class": self.task_class,
            "outcome": self.outcome,
            "prompt_hint": self.prompt_hint,
            "source": self.source,
            "model_id": self.model_id,
            "week_id": self.week_id,
        }


def classify_engagement_task(
    *,
    has_twins: bool = False,
    has_source_refs: bool = False,
    is_collective: bool = False,
    is_book_asset: bool = False,
) -> TaskClass:
    """Heuristic task_class for usage events from engagement surfaces."""
    if is_book_asset:
        return "book_qa"
    if is_collective:
        return "synthesize"
    if has_source_refs and has_twins:
        return "wrestle"
    if has_twins:
        return "distill"
    return "synthesize"


def record_usage_event(
    event: UsageEvent | dict[str, Any],
    *,
    store: BenchStore,
) -> dict[str, Any]:
    """Append one usage event to the bench store (durable list under usage_events)."""
    row = event.to_dict() if isinstance(event, UsageEvent) else dict(event)
    if "task_class" not in row or "outcome" not in row:
        raise ValueError("usage event requires task_class and outcome")
    existing = store.get_run("_usage_events") or {"events": []}
    events = list(existing.get("events") or [])
    events.append(row)
    payload = {"run_id": "_usage_events", "events": events}
    store.put_run("_usage_events", payload)
    return row


def list_usage_events(*, store: BenchStore) -> list[dict[str, Any]]:
    row = store.get_run("_usage_events")
    if not row:
        return []
    return list(row.get("events") or [])


def record_session_flywheel_usage(
    *,
    store: BenchStore,
    twin_count: int,
    ref_count: int,
    status: str,
    model_id: str | None = None,
    prompt_hint: str = "",
    week_id: str | None = None,
    is_book_asset: bool = False,
) -> dict[str, Any]:
    """Record usage from complete_session_with_context_flywheel outcome."""
    outcome: Outcome = "worked" if status == "complete" else "failed"
    task = classify_engagement_task(
        has_twins=twin_count > 0,
        has_source_refs=ref_count > 0,
        is_book_asset=is_book_asset,
    )
    return record_usage_event(
        UsageEvent(
            task_class=task,
            outcome=outcome,
            prompt_hint=prompt_hint[:280],
            source="session_flywheel",
            model_id=model_id,
            week_id=week_id,
        ),
        store=store,
    )


def propose_from_recorded_usage(
    *,
    store: BenchStore,
    registry: Any = None,
) -> Any:
    """Propose suite rewrite from recorded engagement usage events."""
    from .rewrite import propose_suite_delta

    events = list_usage_events(store=store)
    return propose_suite_delta(events, store=store, registry=registry)


def weekly_usage_summary(*, store: BenchStore) -> dict[str, Any]:
    """Aggregate recorded usage for settings / Antiek-bench display."""
    events = list_usage_events(store=store)
    by_class: dict[str, dict[str, int]] = {}
    for e in events:
        tc = str(e.get("task_class") or "unknown")
        oc = str(e.get("outcome") or "unknown")
        bucket = by_class.setdefault(tc, {"worked": 0, "failed": 0, "total": 0})
        if oc in ("worked", "failed"):
            bucket[oc] += 1
        bucket["total"] += 1
    return {
        "event_count": len(events),
        "by_task_class": by_class,
        "view_format": "html",
    }
