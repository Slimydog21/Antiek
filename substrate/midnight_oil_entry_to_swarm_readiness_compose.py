"""Midnight Oil entry → swarm readiness supercompose (pure).

live_execution_authorized always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.midnight_oil_swarm_readiness import (
    MidnightOilSwarmReadinessDecision,
    MidnightOilSwarmReadinessError,
    evaluate_midnight_oil_swarm_readiness,
)
from substrate.midnight_oil_time_goals_price_entry_compose import (
    MidnightOilTimeGoalsPriceEntryCompose,
    MidnightOilTimeGoalsPriceEntryComposeError,
    compose_midnight_oil_time_goals_price_entry,
)


class MidnightOilEntryToSwarmReadinessComposeError(ValueError):
    """Fail-closed validation for MO entry→readiness pack."""


@dataclass(frozen=True)
class MidnightOilEntryToSwarmReadinessCompose:
    entry: MidnightOilTimeGoalsPriceEntryCompose
    readiness: MidnightOilSwarmReadinessDecision
    package_ready: bool
    live_execution_authorized: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry": self.entry.to_dict(),
            "readiness": self.readiness.to_dict(),
            "package_ready": self.package_ready,
            "live_execution_authorized": False,
            "notes": list(self.notes),
            "authority": "midnight_oil_entry_to_swarm_readiness_compose_advisory",
        }


def compose_midnight_oil_entry_to_swarm_readiness(
    *,
    operator_id: object,
    work_minutes: object,
    goals: object,
    operator_ack: object,
    brief_dispatch_ready: object,
    unattended_ack: object,
    spend_consent: object,
    usd_per_hour: object | None = None,
    approved_ceiling_usd: object | None = None,
) -> MidnightOilEntryToSwarmReadinessCompose:
    """Compose MO entry + swarm readiness. Never launches workers."""
    if not isinstance(operator_ack, bool):
        raise MidnightOilEntryToSwarmReadinessComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(brief_dispatch_ready, bool):
        raise MidnightOilEntryToSwarmReadinessComposeError(
            "brief_dispatch_ready must be an explicit boolean"
        )
    if not isinstance(unattended_ack, bool):
        raise MidnightOilEntryToSwarmReadinessComposeError(
            "unattended_ack must be an explicit boolean"
        )
    if not isinstance(spend_consent, bool):
        raise MidnightOilEntryToSwarmReadinessComposeError(
            "spend_consent must be an explicit boolean"
        )

    notes: list[str] = [
        "live_execution_authorized=false — entry+readiness package never launches workers",
    ]

    try:
        entry = compose_midnight_oil_time_goals_price_entry(
            operator_id=operator_id,
            work_minutes=work_minutes,
            goals=goals,
            operator_ack=operator_ack,
            usd_per_hour=usd_per_hour,
            approved_ceiling_usd=approved_ceiling_usd,
        )
    except MidnightOilTimeGoalsPriceEntryComposeError as e:
        raise MidnightOilEntryToSwarmReadinessComposeError(str(e)) from e
    notes.extend(entry.notes)

    try:
        readiness = evaluate_midnight_oil_swarm_readiness(
            operator_id=entry.operator_id,
            work_minutes=entry.work_minutes,
            goal_count=entry.goal_count,
            price_ceiling_usd=entry.approved_ceiling_usd,
            recommended_ceiling_usd=entry.recommend.recommended_ceiling_usd,
            brief_dispatch_ready=brief_dispatch_ready,
            unattended_ack=unattended_ack,
            spend_consent=spend_consent,
        )
    except MidnightOilSwarmReadinessError as e:
        raise MidnightOilEntryToSwarmReadinessComposeError(str(e)) from e
    notes.extend(readiness.notes)

    package_ready = entry.entry_ready and readiness.unattended_ready
    if not entry.entry_ready:
        notes.append("package_ready=false — entry not ready")
    elif not readiness.unattended_ready:
        notes.append("package_ready=false — swarm readiness not ready")
    else:
        notes.append(
            "package_ready=true — entry+readiness intent only; live_execution_authorized=false"
        )

    if (
        entry.live_execution_authorized is not False
        or readiness.live_execution_authorized is not False
    ):
        raise MidnightOilEntryToSwarmReadinessComposeError(
            "invariant: live_execution_authorized must remain false"
        )

    notes.append("live_execution_authorized=false")

    return MidnightOilEntryToSwarmReadinessCompose(
        entry=entry,
        readiness=readiness,
        package_ready=package_ready,
        live_execution_authorized=False,
        notes=tuple(notes),
        authority="midnight_oil_entry_to_swarm_readiness_compose_advisory",
    )


def format_midnight_oil_entry_to_swarm_readiness_summary(
    c: MidnightOilEntryToSwarmReadinessCompose,
) -> str:
    return (
        f"package_ready={c.package_ready} · entry_ready={c.entry.entry_ready} · "
        f"goals={c.entry.goal_count} · minutes={c.entry.work_minutes} · "
        f"live_execution_authorized=false"
    )


__all__ = [
    "MidnightOilEntryToSwarmReadinessCompose",
    "MidnightOilEntryToSwarmReadinessComposeError",
    "compose_midnight_oil_entry_to_swarm_readiness",
    "format_midnight_oil_entry_to_swarm_readiness_summary",
]
