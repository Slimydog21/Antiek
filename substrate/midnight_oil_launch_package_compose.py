"""Midnight Oil full launch package compose (pure, advisory).

Recommends price ceiling + builds swarm brief + evaluates readiness.
live_execution_authorized is always False.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from substrate.midnight_oil_swarm_brief import (
    MidnightOilSwarmBrief,
    MidnightOilSwarmBriefError,
    build_midnight_oil_swarm_brief,
)
from substrate.midnight_oil_swarm_readiness import (
    MidnightOilSwarmReadinessDecision,
    MidnightOilSwarmReadinessError,
    evaluate_midnight_oil_swarm_readiness,
)


class MidnightOilLaunchPackageComposeError(ValueError):
    """Fail-closed validation for MO launch package compose."""


@dataclass(frozen=True)
class MidnightOilPriceCeilingRecommend:
    recommended_ceiling_usd: float | None
    work_hours: float | None
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "recommended_ceiling_usd": self.recommended_ceiling_usd,
            "work_hours": self.work_hours,
            "notes": list(self.notes),
            "authority": "midnight_oil_price_ceiling_recommend_advisory",
        }


@dataclass(frozen=True)
class MidnightOilLaunchPackage:
    operator_id: str
    recommend: MidnightOilPriceCeilingRecommend
    brief: MidnightOilSwarmBrief
    readiness: MidnightOilSwarmReadinessDecision
    package_ready: bool
    live_execution_authorized: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "operator_id": self.operator_id,
            "recommend": self.recommend.to_dict(),
            "brief": self.brief.to_dict(),
            "readiness": self.readiness.to_dict(),
            "package_ready": self.package_ready,
            "live_execution_authorized": False,
            "notes": list(self.notes),
            "authority": "midnight_oil_launch_package_compose_advisory",
        }


def _require_positive_finite(value: object, *, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MidnightOilLaunchPackageComposeError(
            f"{field} must be a positive finite number"
        )
    f = float(value)
    if not math.isfinite(f) or f <= 0:
        raise MidnightOilLaunchPackageComposeError(
            f"{field} must be a positive finite number"
        )
    return f


def _require_nonneg_int(value: object, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise MidnightOilLaunchPackageComposeError(
            f"{field} must be a non-negative integer"
        )
    return value


def _finite_money(value: object, *, field: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MidnightOilLaunchPackageComposeError(
            f"{field} must be finite number or null"
        )
    f = float(value)
    if not math.isfinite(f):
        raise MidnightOilLaunchPackageComposeError(
            f"{field} must be finite number or null"
        )
    if f < 0:
        raise MidnightOilLaunchPackageComposeError(f"{field} must be >= 0")
    return f


def recommend_midnight_oil_price_ceiling(
    *,
    work_minutes: object,
    goal_count: object,
    usd_per_hour: object | None = None,
    goal_intensity: object | None = None,
) -> MidnightOilPriceCeilingRecommend:
    """Recommend price ceiling. Never invents $0 when rate unknown."""
    minutes = _require_positive_finite(work_minutes, field="work_minutes")
    count = _require_nonneg_int(goal_count, field="goal_count")
    if count < 1:
        raise MidnightOilLaunchPackageComposeError(
            "goal_count must be >= 1 for a recommendation"
        )

    notes: list[str] = ["recommended ceiling is advisory only — never charges"]
    work_hours = minutes / 60.0
    if not math.isfinite(work_hours):
        raise MidnightOilLaunchPackageComposeError(
            "work_hours overflowed to non-finite"
        )

    rate = _finite_money(usd_per_hour, field="usd_per_hour")
    intensity = 1.0
    if goal_intensity is not None:
        intensity = _require_positive_finite(
            goal_intensity, field="goal_intensity"
        )

    if rate is None:
        notes.append(
            "usd_per_hour unknown — recommended_ceiling_usd=null (no invent 0)"
        )
        return MidnightOilPriceCeilingRecommend(
            recommended_ceiling_usd=None,
            work_hours=work_hours,
            notes=tuple(notes),
            authority="midnight_oil_price_ceiling_recommend_advisory",
        )

    fanout = math.sqrt(count)
    if not math.isfinite(fanout) or fanout <= 0:
        raise MidnightOilLaunchPackageComposeError("goal fanout overflowed")
    recommended = rate * work_hours * intensity * fanout
    if not math.isfinite(recommended):
        raise MidnightOilLaunchPackageComposeError(
            "recommended_ceiling_usd overflowed to non-finite"
        )
    recommended_ceiling_usd = round(recommended * 100) / 100
    notes.append(
        f"recommended=${recommended_ceiling_usd} from rate=${rate}/h · "
        f"hours={work_hours} · goals={count} · intensity={intensity}"
    )
    return MidnightOilPriceCeilingRecommend(
        recommended_ceiling_usd=recommended_ceiling_usd,
        work_hours=work_hours,
        notes=tuple(notes),
        authority="midnight_oil_price_ceiling_recommend_advisory",
    )


def compose_midnight_oil_launch_package(
    *,
    operator_id: object,
    work_minutes: object,
    goals: object,
    price_ceiling_usd: object,
    operator_approved: object,
    unattended_ack: object,
    spend_consent: object,
    recommended_ceiling_usd: object | None = None,
    usd_per_hour: object | None = None,
) -> MidnightOilLaunchPackage:
    """Compose full MO launch package. Never authorizes live execution."""
    if not isinstance(operator_approved, bool):
        raise MidnightOilLaunchPackageComposeError(
            "operator_approved must be an explicit boolean"
        )
    if not isinstance(unattended_ack, bool):
        raise MidnightOilLaunchPackageComposeError(
            "unattended_ack must be an explicit boolean"
        )
    if not isinstance(spend_consent, bool):
        raise MidnightOilLaunchPackageComposeError(
            "spend_consent must be an explicit boolean"
        )
    if not isinstance(goals, list) or len(goals) == 0:
        raise MidnightOilLaunchPackageComposeError(
            "goals must be a non-empty array"
        )

    notes: list[str] = [
        "live_execution_authorized=false — launch package advisory only",
    ]

    if recommended_ceiling_usd is not None:
        forced = _finite_money(
            recommended_ceiling_usd, field="recommended_ceiling_usd"
        )
        recommend = MidnightOilPriceCeilingRecommend(
            recommended_ceiling_usd=forced,
            work_hours=None,
            notes=(
                "recommended_ceiling_usd caller-supplied override (not recomputed)",
            ),
            authority="midnight_oil_price_ceiling_recommend_advisory",
        )
    else:
        recommend = recommend_midnight_oil_price_ceiling(
            work_minutes=work_minutes,
            goal_count=len(goals),
            usd_per_hour=usd_per_hour,
        )

    try:
        brief = build_midnight_oil_swarm_brief(
            operator_id=operator_id,
            work_minutes=work_minutes,
            goals=goals,
            price_ceiling_usd=price_ceiling_usd,
            operator_approved=operator_approved,
            recommended_ceiling_usd=recommend.recommended_ceiling_usd,
        )
        readiness = evaluate_midnight_oil_swarm_readiness(
            operator_id=operator_id,
            work_minutes=work_minutes,
            goal_count=len(goals),
            price_ceiling_usd=price_ceiling_usd,
            brief_dispatch_ready=brief.dispatch_ready,
            unattended_ack=unattended_ack,
            spend_consent=spend_consent,
            recommended_ceiling_usd=recommend.recommended_ceiling_usd,
        )
    except (MidnightOilSwarmBriefError, MidnightOilSwarmReadinessError) as e:
        raise MidnightOilLaunchPackageComposeError(str(e)) from e

    package_ready = (
        brief.dispatch_ready is True and readiness.unattended_ready is True
    )
    if package_ready:
        notes.append(
            "package_ready=true — brief dispatch_ready + unattended_ready "
            "(still no live exec)"
        )
    else:
        notes.append(
            f"package_ready=false (dispatch_ready={brief.dispatch_ready}, "
            f"unattended_ready={readiness.unattended_ready})"
        )
    notes.append("live_execution_authorized=false")

    return MidnightOilLaunchPackage(
        operator_id=brief.operator_id,
        recommend=recommend,
        brief=brief,
        readiness=readiness,
        package_ready=package_ready,
        live_execution_authorized=False,
        notes=tuple(notes),
        authority="midnight_oil_launch_package_compose_advisory",
    )


__all__ = [
    "MidnightOilLaunchPackage",
    "MidnightOilLaunchPackageComposeError",
    "MidnightOilPriceCeilingRecommend",
    "compose_midnight_oil_launch_package",
    "recommend_midnight_oil_price_ceiling",
]
