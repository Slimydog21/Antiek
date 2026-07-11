"""Recursive Antiek-bench proposal from usage outcomes (advisory).

Operator vision: each week, learn what worked / didn't from platform usage
and propose rewritten sub-benchmark weights (and optional new task foci)
for the next week. This module only **proposes** — it does not mutate the
authoritative antiek_bench package, run live judges, or dispatch models.

Inputs are injected:
* ``usage_events`` — per-task outcomes observed in production (success bool)
* optional ``prior_weights`` — last week's task weights (annotation only)

Honesty:
* Empty / unusable usage → incomplete, no invented weights
* ``success`` must be real bool (strings never invent outcomes)
* Failure-driven mass only (successes do not outrank failures)
* Published weights sum to exactly 1.0 when non-empty
* Authority always ``advisory``
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class TaskWeightProposal:
    task: str
    weight: float
    """Fraction of next week's bench mass for this task (sums to 1.0)."""
    prior_weight: float | None
    n_success: int
    n_failure: int
    rationale: str


@dataclass(frozen=True)
class UsageLearnProposal:
    week_id: str
    authority: str
    incomplete: bool
    task_weights: list[TaskWeightProposal]
    suggested_new_tasks: list[str]
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "week_id": self.week_id,
            "authority": self.authority,
            "incomplete": self.incomplete,
            "notes": list(self.notes),
            "suggested_new_tasks": list(self.suggested_new_tasks),
            "task_weights": [
                {
                    "task": t.task,
                    "weight": t.weight,
                    "prior_weight": t.prior_weight,
                    "n_success": t.n_success,
                    "n_failure": t.n_failure,
                    "rationale": t.rationale,
                }
                for t in self.task_weights
            ],
        }


def _as_bool_success(raw: Any) -> bool | None:
    """Only real booleans count — never invent outcomes from strings."""
    if isinstance(raw, bool):
        return raw
    return None


def _normalize_exact(weights: dict[str, float]) -> dict[str, float]:
    """Round to 6 dp then adjust the largest residual so sum is exactly 1.0."""
    if not weights:
        return {}
    rounded = {t: round(w, 6) for t, w in weights.items()}
    total = sum(rounded.values())
    if total <= 0:
        return rounded
    # Force exact 1.0 by correcting the max-weight task
    drift = round(1.0 - total, 6)
    if drift != 0.0:
        top = max(rounded.items(), key=lambda kv: (kv[1], kv[0]))[0]
        rounded[top] = round(rounded[top] + drift, 6)
    return rounded


def propose_next_week_weights(
    usage_events: Sequence[Mapping[str, Any]] | None,
    *,
    week_id: str = "",
    prior_weights: Mapping[str, float] | None = None,
    min_weight: float = 0.05,
) -> UsageLearnProposal:
    """Propose next-week sub-benchmark weights from usage outcomes.

    Heuristic (transparent, not ML):
    * Mass for task t = ``n_failure + 1`` (Laplace). Successes do **not** add
      mass — failure concentration drives up-weighting.
    * ``prior_weights`` only annotate tasks that appear in usable usage.
    * Unknown/non-bool success flags are ignored (do not invent outcomes).
    """
    notes: list[str] = [
        "authority=advisory — proposal only; does not mutate antiek_bench",
        "weights derived from injected usage outcomes, not live provider calls",
    ]
    week = (week_id or "").strip()
    events = list(usage_events or [])
    if not events:
        notes.append("no usage events — incomplete proposal (not inventing weights)")
        return UsageLearnProposal(
            week_id=week,
            authority="advisory",
            incomplete=True,
            task_weights=[],
            suggested_new_tasks=[],
            notes=notes,
        )

    success: dict[str, int] = {}
    failure: dict[str, int] = {}
    unknown_flags = 0
    for ev in events:
        task = str(ev.get("task") or "general").strip() or "general"
        ok = _as_bool_success(ev.get("success") if "success" in ev else ev.get("ok"))
        if ok is None:
            unknown_flags += 1
            continue
        if ok:
            success[task] = success.get(task, 0) + 1
        else:
            failure[task] = failure.get(task, 0) + 1

    if unknown_flags:
        notes.append(f"ignored {unknown_flags} events with non-boolean success")

    # Only tasks with at least one usable outcome (not prior-only invention).
    tasks = sorted(set(success) | set(failure))
    if not tasks:
        notes.append("no usable success/failure outcomes — incomplete")
        return UsageLearnProposal(
            week_id=week,
            authority="advisory",
            incomplete=True,
            task_weights=[],
            suggested_new_tasks=[],
            notes=notes,
        )

    # Failure-driven mass only.
    raw_mass: dict[str, float] = {
        t: float(failure.get(t, 0)) + 1.0 for t in tasks
    }
    total = sum(raw_mass.values()) or 1.0
    weights = {t: raw_mass[t] / total for t in tasks}

    if min_weight > 0 and len(tasks) * min_weight < 1.0:
        for t in tasks:
            weights[t] = max(weights[t], min_weight)
        s2 = sum(weights.values())
        weights = {t: weights[t] / s2 for t in tasks}

    weights = _normalize_exact(weights)

    proposals: list[TaskWeightProposal] = []
    for t in tasks:
        n_s = success.get(t, 0)
        n_f = failure.get(t, 0)
        prior = None
        if prior_weights and t in prior_weights:
            try:
                prior = float(prior_weights[t])
            except (TypeError, ValueError):
                prior = None
        if n_f > n_s:
            rationale = (
                f"up-weighted: failures={n_f} > successes={n_s} "
                f"(stress underperforming task)"
            )
        elif n_f == 0 and n_s > 0:
            rationale = f"stable: only successes={n_s}; Laplace base mass only"
        else:
            rationale = f"balanced: successes={n_s} failures={n_f}"
        proposals.append(
            TaskWeightProposal(
                task=t,
                weight=weights[t],
                prior_weight=prior,
                n_success=n_s,
                n_failure=n_f,
                rationale=rationale,
            )
        )
    proposals.sort(key=lambda p: (-p.weight, p.task))

    suggested: list[str] = []
    for p in proposals:
        total_t = p.n_success + p.n_failure
        if total_t >= 3 and p.n_failure >= 2 and p.n_failure >= p.n_success:
            suggested.append(f"{p.task}::edge_cases")
            notes.append(
                f"suggested sub-benchmark {p.task}::edge_cases from failure concentration"
            )

    return UsageLearnProposal(
        week_id=week,
        authority="advisory",
        incomplete=False,
        task_weights=proposals,
        suggested_new_tasks=suggested,
        notes=notes,
    )


__all__ = [
    "TaskWeightProposal",
    "UsageLearnProposal",
    "propose_next_week_weights",
]
