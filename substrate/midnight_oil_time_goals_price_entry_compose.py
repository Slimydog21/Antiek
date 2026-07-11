"""Midnight Oil time + goals + price ceiling entry compose (pure).

live_execution_authorized always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.midnight_oil_launch_package_compose import (
    MidnightOilPriceCeilingRecommend,
    recommend_midnight_oil_price_ceiling,
)


class MidnightOilTimeGoalsPriceEntryComposeError(ValueError):
    """Fail-closed validation for MO entry compose."""


@dataclass(frozen=True)
class MidnightOilTimeGoalsPriceEntryCompose:
    operator_id: str
    work_minutes: float
    goal_count: int
    goal_ids: tuple[str, ...]
    recommend: MidnightOilPriceCeilingRecommend
    approved_ceiling_usd: float | None
    entry_ready: bool
    live_execution_authorized: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        rec = self.recommend
        rec_dict = {
            "recommended_ceiling_usd": rec.recommended_ceiling_usd,
            "work_hours": rec.work_hours,
            "notes": list(rec.notes),
            "authority": rec.authority,
        }
        return {
            "operator_id": self.operator_id,
            "work_minutes": self.work_minutes,
            "goal_count": self.goal_count,
            "goal_ids": list(self.goal_ids),
            "recommend": rec_dict,
            "approved_ceiling_usd": self.approved_ceiling_usd,
            "entry_ready": self.entry_ready,
            "live_execution_authorized": False,
            "notes": list(self.notes),
            "authority": "midnight_oil_time_goals_price_entry_compose_advisory",
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MidnightOilTimeGoalsPriceEntryComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def _require_positive_finite(value: object, *, field: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise MidnightOilTimeGoalsPriceEntryComposeError(
            f"{field} must be a positive finite number"
        )
    f = float(value)
    if f != f or f <= 0:
        raise MidnightOilTimeGoalsPriceEntryComposeError(
            f"{field} must be a positive finite number"
        )
    return f


def compose_midnight_oil_time_goals_price_entry(
    *,
    operator_id: object,
    work_minutes: object,
    goals: object,
    operator_ack: object,
    usd_per_hour: object | None = None,
    approved_ceiling_usd: object | None = None,
) -> MidnightOilTimeGoalsPriceEntryCompose:
    """Compose MO entry. Never authorizes unattended execution."""
    if not isinstance(operator_ack, bool):
        raise MidnightOilTimeGoalsPriceEntryComposeError(
            "operator_ack must be an explicit boolean"
        )
    oid = _require_nonempty(operator_id, field="operator_id")
    minutes = _require_positive_finite(work_minutes, field="work_minutes")
    if not isinstance(goals, list) or len(goals) == 0:
        raise MidnightOilTimeGoalsPriceEntryComposeError(
            "goals must be a non-empty array"
        )

    notes: list[str] = [
        "live_execution_authorized=false — entry form never launches MO workers",
        "recommended ceiling is advisory; operator approval is separate",
    ]

    goal_ids: list[str] = []
    seen: set[str] = set()
    for i, g in enumerate(goals):
        if not isinstance(g, dict):
            raise MidnightOilTimeGoalsPriceEntryComposeError(
                f"goals[{i}] must be an object"
            )
        gid = _require_nonempty(g.get("goal_id"), field=f"goals[{i}].goal_id")
        _require_nonempty(g.get("title"), field=f"goals[{i}].title")
        if gid in seen:
            raise MidnightOilTimeGoalsPriceEntryComposeError(
                f"duplicate goal_id: {gid}"
            )
        seen.add(gid)
        goal_ids.append(gid)
    goal_count = len(goal_ids)
    notes.append(f"goal_count={goal_count} · work_minutes={minutes}")

    recommend = recommend_midnight_oil_price_ceiling(
        work_minutes=minutes,
        goal_count=goal_count,
        usd_per_hour=usd_per_hour,
    )
    notes.extend(recommend.notes)

    approved: float | None = None
    if approved_ceiling_usd is not None:
        if not isinstance(approved_ceiling_usd, (int, float)) or isinstance(
            approved_ceiling_usd, bool
        ):
            raise MidnightOilTimeGoalsPriceEntryComposeError(
                "approved_ceiling_usd must be non-negative finite when set"
            )
        approved = float(approved_ceiling_usd)
        if approved != approved or approved < 0:
            raise MidnightOilTimeGoalsPriceEntryComposeError(
                "approved_ceiling_usd must be non-negative finite when set"
            )
        notes.append(f"approved_ceiling_usd={approved}")
    else:
        notes.append("approved_ceiling_usd=null — operator has not approved yet")

    entry_ready = False
    if not operator_ack:
        notes.append("entry_ready=false — operator_ack required")
    elif recommend.recommended_ceiling_usd is not None:
        if approved is None:
            notes.append(
                "entry_ready=false — recommended ceiling present; approve a ceiling first"
            )
        else:
            entry_ready = True
            notes.append(
                "entry_ready=true — time+goals+approved ceiling "
                "(still live_execution_authorized=false)"
            )
    else:
        if approved is None:
            notes.append(
                "entry_ready=false — recommendation unknown and no approved ceiling"
            )
        else:
            entry_ready = True
            notes.append(
                "entry_ready=true — approved ceiling without recommended $ (honest null rec)"
            )

    notes.append("live_execution_authorized=false")

    return MidnightOilTimeGoalsPriceEntryCompose(
        operator_id=oid,
        work_minutes=minutes,
        goal_count=goal_count,
        goal_ids=tuple(goal_ids),
        recommend=recommend,
        approved_ceiling_usd=approved,
        entry_ready=entry_ready,
        live_execution_authorized=False,
        notes=tuple(notes),
        authority="midnight_oil_time_goals_price_entry_compose_advisory",
    )


__all__ = [
    "MidnightOilTimeGoalsPriceEntryCompose",
    "MidnightOilTimeGoalsPriceEntryComposeError",
    "compose_midnight_oil_time_goals_price_entry",
]
