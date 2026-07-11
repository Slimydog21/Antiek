"""Midnight Oil unattended recap compose (pure).

live_execution_authorized and store_mutated always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

GoalStatus = Literal["pending", "in_progress", "done", "blocked", "skipped"]
VALID_STATUS = frozenset(
    ("pending", "in_progress", "done", "blocked", "skipped")
)


class MidnightOilUnattendedRecapComposeError(ValueError):
    """Fail-closed validation for MO unattended recap."""


@dataclass(frozen=True)
class MidnightOilUnattendedRecapCompose:
    run_id: str
    operator_id: str
    goal_count: int
    goals_done: int
    goals_blocked: int
    goals_pending: int
    within_ceiling: bool | None
    recap_ready: bool
    artifact_count: int
    live_execution_authorized: bool
    store_mutated: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "operator_id": self.operator_id,
            "goal_count": self.goal_count,
            "goals_done": self.goals_done,
            "goals_blocked": self.goals_blocked,
            "goals_pending": self.goals_pending,
            "within_ceiling": self.within_ceiling,
            "recap_ready": self.recap_ready,
            "artifact_count": self.artifact_count,
            "live_execution_authorized": False,
            "store_mutated": False,
            "notes": list(self.notes),
            "authority": "midnight_oil_unattended_recap_compose_advisory",
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MidnightOilUnattendedRecapComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def _require_nonneg_finite(value: object, *, field: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise MidnightOilUnattendedRecapComposeError(
            f"{field} must be a non-negative finite number"
        )
    f = float(value)
    if f != f or f < 0:
        raise MidnightOilUnattendedRecapComposeError(
            f"{field} must be a non-negative finite number"
        )
    return f


def compose_midnight_oil_unattended_recap(
    *,
    run_id: object,
    operator_id: object,
    work_minutes_planned: object,
    work_minutes_actual: object,
    goals: object,
    price_ceiling_usd: object,
    spend_usd: object,
    operator_ack: object,
    artifact_ids: object | None = None,
) -> MidnightOilUnattendedRecapCompose:
    """Compose MO unattended recap. Never re-launches workers."""
    if not isinstance(operator_ack, bool):
        raise MidnightOilUnattendedRecapComposeError(
            "operator_ack must be an explicit boolean"
        )
    rid = _require_nonempty(run_id, field="run_id")
    oid = _require_nonempty(operator_id, field="operator_id")
    planned = _require_nonneg_finite(
        work_minutes_planned, field="work_minutes_planned"
    )
    if planned <= 0:
        raise MidnightOilUnattendedRecapComposeError(
            "work_minutes_planned must be > 0"
        )
    if work_minutes_actual is not None:
        _require_nonneg_finite(
            work_minutes_actual, field="work_minutes_actual"
        )

    if not isinstance(goals, list) or len(goals) == 0:
        raise MidnightOilUnattendedRecapComposeError(
            "goals must be a non-empty array"
        )

    notes: list[str] = [
        "live_execution_authorized=false — recap never re-launches MO workers",
        "store_mutated=false — recap is advisory snapshot only",
        "goal statuses and spend are caller-supplied only (no invent)",
    ]

    goals_done = 0
    goals_blocked = 0
    goals_pending = 0
    seen: set[str] = set()
    for i, g in enumerate(goals):
        if not isinstance(g, dict):
            raise MidnightOilUnattendedRecapComposeError(
                f"goals[{i}] must be an object"
            )
        gid = _require_nonempty(g.get("goal_id"), field=f"goals[{i}].goal_id")
        if gid in seen:
            raise MidnightOilUnattendedRecapComposeError(
                f"duplicate goal_id: {gid}"
            )
        seen.add(gid)
        _require_nonempty(g.get("title"), field=f"goals[{i}].title")
        st = g.get("status")
        if st not in VALID_STATUS:
            raise MidnightOilUnattendedRecapComposeError(
                f"goals[{i}].status must be pending|in_progress|done|blocked|skipped"
            )
        if g.get("notes") is not None:
            _require_nonempty(g.get("notes"), field=f"goals[{i}].notes")
        if st == "done":
            goals_done += 1
        elif st == "blocked":
            goals_blocked += 1
        elif st in ("pending", "in_progress"):
            goals_pending += 1

    goal_count = len(goals)
    notes.append(
        f"goals={goal_count} · done={goals_done} · blocked={goals_blocked} · "
        f"pendingish={goals_pending}"
    )
    notes.append(f"work_minutes_planned={planned}")
    if work_minutes_actual is None:
        notes.append("work_minutes_actual=null (unknown honesty)")
    else:
        notes.append(f"work_minutes_actual={work_minutes_actual}")

    within_ceiling: bool | None = None
    if price_ceiling_usd is not None and spend_usd is not None:
        ceiling = _require_nonneg_finite(
            price_ceiling_usd, field="price_ceiling_usd"
        )
        spend = _require_nonneg_finite(spend_usd, field="spend_usd")
        within_ceiling = spend <= ceiling
        notes.append(
            f"within_ceiling=true · spend={spend} ≤ ceiling={ceiling}"
            if within_ceiling
            else f"within_ceiling=false · spend={spend} > ceiling={ceiling}"
        )
    else:
        notes.append(
            "within_ceiling=null — spend and/or ceiling unknown (no invent $0)"
        )

    artifact_count = 0
    if artifact_ids is not None:
        if not isinstance(artifact_ids, list):
            raise MidnightOilUnattendedRecapComposeError(
                "artifact_ids must be an array when set"
            )
        aseen: set[str] = set()
        for i, aid in enumerate(artifact_ids):
            a = _require_nonempty(aid, field=f"artifact_ids[{i}]")
            if a in aseen:
                raise MidnightOilUnattendedRecapComposeError(
                    f"duplicate artifact_id: {a}"
                )
            aseen.add(a)
        artifact_count = len(aseen)
        notes.append(f"artifact_count={artifact_count}")

    has_progress = goals_done >= 1 or artifact_count >= 1
    recap_ready = operator_ack and has_progress
    if not operator_ack:
        notes.append("recap_ready=false — operator_ack required")
    elif not has_progress:
        notes.append(
            "recap_ready=false — no done goals or artifacts (no invent progress)"
        )
    else:
        notes.append(
            "recap_ready=true — operator may review unattended outcomes"
        )

    notes.extend(
        ("live_execution_authorized=false", "store_mutated=false")
    )

    return MidnightOilUnattendedRecapCompose(
        run_id=rid,
        operator_id=oid,
        goal_count=goal_count,
        goals_done=goals_done,
        goals_blocked=goals_blocked,
        goals_pending=goals_pending,
        within_ceiling=within_ceiling,
        recap_ready=recap_ready,
        artifact_count=artifact_count,
        live_execution_authorized=False,
        store_mutated=False,
        notes=tuple(notes),
        authority="midnight_oil_unattended_recap_compose_advisory",
    )


__all__ = [
    "MidnightOilUnattendedRecapCompose",
    "MidnightOilUnattendedRecapComposeError",
    "compose_midnight_oil_unattended_recap",
]
