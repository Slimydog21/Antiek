"""Midnight Oil swarm readiness (pure, advisory).

Unattended handoff gates: goals, time, ceiling, consent, brief, ack.
live_execution_authorized is always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class MidnightOilSwarmReadinessError(ValueError):
    """Fail-closed validation for MO swarm readiness."""


@dataclass(frozen=True)
class MidnightOilSwarmReadinessDecision:
    operator_id: str
    goals_ready: bool
    time_ready: bool
    ceiling_ready: bool
    consent_ready: bool
    brief_ready: bool
    unattended_ready: bool
    live_execution_authorized: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "operator_id": self.operator_id,
            "goals_ready": self.goals_ready,
            "time_ready": self.time_ready,
            "ceiling_ready": self.ceiling_ready,
            "consent_ready": self.consent_ready,
            "brief_ready": self.brief_ready,
            "unattended_ready": self.unattended_ready,
            "live_execution_authorized": False,
            "notes": list(self.notes),
            "authority": "midnight_oil_swarm_readiness_advisory",
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MidnightOilSwarmReadinessError(f"{field} must be a non-empty string")
    return value.strip()


def _finite_money(value: object, *, field: str) -> float | None:
    if value is None:
        return None
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise MidnightOilSwarmReadinessError(f"{field} must be finite number or null")
    v = float(value)
    if v != v or v == float("inf") or v == float("-inf"):
        raise MidnightOilSwarmReadinessError(f"{field} must be finite number or null")
    if v < 0:
        raise MidnightOilSwarmReadinessError(f"{field} must be >= 0")
    return v


def evaluate_midnight_oil_swarm_readiness(
    *,
    operator_id: object,
    work_minutes: object,
    goal_count: object,
    price_ceiling_usd: object,
    brief_dispatch_ready: object,
    unattended_ack: object,
    spend_consent: object,
    recommended_ceiling_usd: object | None = None,
) -> MidnightOilSwarmReadinessDecision:
    """Evaluate unattended MO swarm readiness. Never authorizes live workers."""
    op = _require_nonempty(operator_id, field="operator_id")
    if (
        not isinstance(work_minutes, (int, float))
        or isinstance(work_minutes, bool)
        or float(work_minutes) <= 0
        or float(work_minutes) != float(work_minutes)
        or float(work_minutes) == float("inf")
    ):
        raise MidnightOilSwarmReadinessError(
            "work_minutes must be a positive finite number"
        )
    minutes = float(work_minutes)
    if (
        not isinstance(goal_count, int)
        or isinstance(goal_count, bool)
        or goal_count < 0
    ):
        raise MidnightOilSwarmReadinessError(
            "goal_count must be a non-negative integer"
        )
    for name, val in (
        ("brief_dispatch_ready", brief_dispatch_ready),
        ("unattended_ack", unattended_ack),
        ("spend_consent", spend_consent),
    ):
        if not isinstance(val, bool):
            raise MidnightOilSwarmReadinessError(
                f"{name} must be an explicit boolean"
            )

    ceiling = _finite_money(price_ceiling_usd, field="price_ceiling_usd")
    recommended = _finite_money(
        recommended_ceiling_usd, field="recommended_ceiling_usd"
    )

    notes: list[str] = [
        "live_execution_authorized=false — pure unattended readiness only",
    ]

    goals_ready = goal_count >= 1
    if not goals_ready:
        notes.append("goal_count < 1 — goals_ready=false")
    else:
        notes.append(f"goals_ready=true (count={goal_count})")

    time_ready = minutes > 0
    notes.append(
        f"time_ready=true (minutes={minutes})"
        if time_ready
        else "time_ready=false"
    )

    if ceiling is None:
        ceiling_ready = False
        notes.append(
            "price_ceiling_usd unknown — ceiling_ready=false (no invent 0)"
        )
    else:
        ceiling_ready = True
        notes.append(f"ceiling_ready=true (ceiling={ceiling})")
        if recommended is not None and ceiling > recommended:
            notes.append(
                f"operator ceiling {ceiling} exceeds recommended {recommended} (advisory)"
            )

    if ceiling is None:
        consent_ready = False
        notes.append("consent_ready=false (ceiling unknown)")
    elif ceiling == 0:
        consent_ready = True
        notes.append(
            "price_ceiling_usd=0 — consent_ready=true (zero-spend dry; consent optional)"
        )
    elif spend_consent is True:
        consent_ready = True
        notes.append("spend_consent=true — consent_ready=true")
    else:
        consent_ready = False
        notes.append(
            "price_ceiling_usd>0 without spend_consent — consent_ready=false"
        )

    brief_ready = brief_dispatch_ready is True
    if not brief_ready:
        notes.append("brief_dispatch_ready=false — brief_ready=false")
    else:
        notes.append("brief_dispatch_ready=true — brief_ready=true")

    if unattended_ack is not True:
        notes.append("unattended_ack=false — blocks unattended_ready")

    unattended_ready = (
        goals_ready
        and time_ready
        and ceiling_ready
        and consent_ready
        and brief_ready
        and unattended_ack is True
    )
    notes.append(f"unattended_ready={unattended_ready}")
    notes.append("live_execution_authorized=false")

    return MidnightOilSwarmReadinessDecision(
        operator_id=op,
        goals_ready=goals_ready,
        time_ready=time_ready,
        ceiling_ready=ceiling_ready,
        consent_ready=consent_ready,
        brief_ready=brief_ready,
        unattended_ready=unattended_ready,
        live_execution_authorized=False,
        notes=tuple(notes),
        authority="midnight_oil_swarm_readiness_advisory",
    )


__all__ = [
    "MidnightOilSwarmReadinessDecision",
    "MidnightOilSwarmReadinessError",
    "evaluate_midnight_oil_swarm_readiness",
]
