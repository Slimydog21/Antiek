"""Midnight Oil swarm brief (pure, fail-closed).

Operator vision: set work window + goals + price ceiling approval for an
unattended multi-agent deep research swarm.

live_execution_authorized is always False.
price_ceiling is advisory; never charges.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class MidnightOilSwarmBriefError(ValueError):
    """Fail-closed validation for MO swarm brief."""


@dataclass(frozen=True)
class SwarmGoal:
    goal_id: str
    statement: str
    priority: float


@dataclass(frozen=True)
class SwarmLane:
    lane_id: str
    goal_id: str
    statement: str
    time_share: float


@dataclass(frozen=True)
class MidnightOilSwarmBrief:
    operator_id: str
    work_minutes: float
    goals: tuple[SwarmGoal, ...]
    lanes: tuple[SwarmLane, ...]
    price_ceiling_usd: float | None
    recommended_ceiling_usd: float | None
    operator_approved: bool
    dispatch_ready: bool
    live_execution_authorized: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "operator_id": self.operator_id,
            "work_minutes": self.work_minutes,
            "goals": [
                {
                    "goal_id": g.goal_id,
                    "statement": g.statement,
                    "priority": g.priority,
                }
                for g in self.goals
            ],
            "lanes": [
                {
                    "lane_id": ln.lane_id,
                    "goal_id": ln.goal_id,
                    "statement": ln.statement,
                    "time_share": ln.time_share,
                }
                for ln in self.lanes
            ],
            "price_ceiling_usd": self.price_ceiling_usd,
            "recommended_ceiling_usd": self.recommended_ceiling_usd,
            "operator_approved": self.operator_approved,
            "dispatch_ready": self.dispatch_ready,
            "live_execution_authorized": False,
            "notes": list(self.notes),
            "authority": "midnight_oil_swarm_brief_advisory",
        }


def _require_bool(value: object, *, field: str) -> bool:
    if not isinstance(value, bool):
        raise MidnightOilSwarmBriefError(f"{field} must be an explicit boolean")
    return value


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MidnightOilSwarmBriefError(f"{field} must be a non-empty string")
    return value.strip()


def _require_money(value: object, *, field: str) -> float | None:
    if value is None:
        return None
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise MidnightOilSwarmBriefError(f"{field} must be finite number or null")
    f = float(value)
    if f != f or f == float("inf") or f == float("-inf"):  # NaN/inf
        raise MidnightOilSwarmBriefError(f"{field} must be finite number or null")
    if f < 0:
        raise MidnightOilSwarmBriefError(f"{field} must be >= 0")
    return f


def build_midnight_oil_swarm_brief(
    *,
    operator_id: object,
    work_minutes: object,
    goals: object,
    price_ceiling_usd: object,
    operator_approved: object,
    recommended_ceiling_usd: object | None = None,
) -> MidnightOilSwarmBrief:
    """Build unattended swarm brief. Never authorizes live execution."""
    approved = _require_bool(operator_approved, field="operator_approved")
    op = _require_nonempty(operator_id, field="operator_id")
    if not isinstance(work_minutes, (int, float)) or isinstance(work_minutes, bool):
        raise MidnightOilSwarmBriefError("work_minutes must be a positive finite number")
    minutes = float(work_minutes)
    if minutes != minutes or minutes <= 0 or minutes == float("inf"):
        raise MidnightOilSwarmBriefError("work_minutes must be a positive finite number")
    if not isinstance(goals, list) or len(goals) == 0:
        raise MidnightOilSwarmBriefError("goals must be a non-empty array")

    parsed: list[SwarmGoal] = []
    priority_sum = 0.0
    for i, g in enumerate(goals):
        if not isinstance(g, dict):
            raise MidnightOilSwarmBriefError(f"goals[{i}] must be an object")
        gid = _require_nonempty(g.get("goal_id"), field=f"goals[{i}].goal_id")
        stmt = _require_nonempty(g.get("statement"), field=f"goals[{i}].statement")
        pr = g.get("priority")
        if not isinstance(pr, (int, float)) or isinstance(pr, bool):
            raise MidnightOilSwarmBriefError(
                f"goals[{i}].priority must be a positive finite number"
            )
        pf = float(pr)
        if pf != pf or pf <= 0 or pf == float("inf"):
            raise MidnightOilSwarmBriefError(
                f"goals[{i}].priority must be a positive finite number"
            )
        parsed.append(SwarmGoal(goal_id=gid, statement=stmt, priority=pf))
        priority_sum += pf
    if priority_sum != priority_sum or priority_sum <= 0 or priority_sum == float("inf"):
        raise MidnightOilSwarmBriefError("priority sum overflowed or non-positive")

    ceiling = _require_money(price_ceiling_usd, field="price_ceiling_usd")
    recommended = _require_money(
        recommended_ceiling_usd, field="recommended_ceiling_usd"
    )

    lanes = tuple(
        SwarmLane(
            lane_id=f"lane_{i}_{g.goal_id}",
            goal_id=g.goal_id,
            statement=g.statement,
            time_share=g.priority / priority_sum,
        )
        for i, g in enumerate(parsed)
    )

    notes: list[str] = []
    dispatch_ready = False
    if not approved:
        notes.append("operator_approved=false — dispatch_ready=false")
    elif ceiling is None:
        notes.append("price_ceiling_usd unknown — dispatch_ready=false (no invent 0)")
    elif ceiling == 0:
        notes.append(
            "price_ceiling_usd=0 — dispatch_ready=true for zero-spend dry plan only"
        )
        dispatch_ready = True
    else:
        dispatch_ready = True
        notes.append("operator approved with positive ceiling — dispatch_ready=true")

    if recommended is not None and ceiling is not None and ceiling > recommended:
        notes.append(
            f"operator ceiling ${ceiling} exceeds recommended ${recommended} (advisory only)"
        )

    notes.append("live_execution_authorized=false")
    notes.append("pure swarm brief — no worker dispatch, no spend")

    return MidnightOilSwarmBrief(
        operator_id=op,
        work_minutes=minutes,
        goals=tuple(parsed),
        lanes=lanes,
        price_ceiling_usd=ceiling,
        recommended_ceiling_usd=recommended,
        operator_approved=approved,
        dispatch_ready=dispatch_ready,
        live_execution_authorized=False,
        notes=tuple(notes),
        authority="midnight_oil_swarm_brief_advisory",
    )


__all__ = [
    "MidnightOilSwarmBrief",
    "MidnightOilSwarmBriefError",
    "SwarmGoal",
    "SwarmLane",
    "build_midnight_oil_swarm_brief",
]
