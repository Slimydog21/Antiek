"""Midnight Oil unattended full package compose (pure).

live_execution_authorized always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.midnight_oil_entry_to_swarm_readiness_compose import (
    MidnightOilEntryToSwarmReadinessCompose,
    MidnightOilEntryToSwarmReadinessComposeError,
    compose_midnight_oil_entry_to_swarm_readiness,
)
from substrate.midnight_oil_launch_package_compose import (
    MidnightOilLaunchPackage,
    MidnightOilLaunchPackageComposeError,
    compose_midnight_oil_launch_package,
)


class MidnightOilUnattendedPackageComposeError(ValueError):
    """Fail-closed validation for MO unattended package."""


@dataclass(frozen=True)
class MidnightOilUnattendedPackageCompose:
    entry_readiness: MidnightOilEntryToSwarmReadinessCompose
    launch: MidnightOilLaunchPackage
    unattended_package_ready: bool
    live_execution_authorized: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_readiness": self.entry_readiness.to_dict(),
            "launch": self.launch.to_dict(),
            "unattended_package_ready": self.unattended_package_ready,
            "live_execution_authorized": False,
            "notes": list(self.notes),
            "authority": "midnight_oil_unattended_package_compose_advisory",
        }


def compose_midnight_oil_unattended_package(
    *,
    operator_id: object,
    work_minutes: object,
    goals: object,
    operator_ack: object,
    unattended_ack: object,
    spend_consent: object,
    usd_per_hour: object | None = None,
    approved_ceiling_usd: object | None = None,
    brief_dispatch_ready: object | None = None,
) -> MidnightOilUnattendedPackageCompose:
    """Compose entry readiness + launch package. Never launches workers."""
    if not isinstance(operator_ack, bool):
        raise MidnightOilUnattendedPackageComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(unattended_ack, bool):
        raise MidnightOilUnattendedPackageComposeError(
            "unattended_ack must be an explicit boolean"
        )
    if not isinstance(spend_consent, bool):
        raise MidnightOilUnattendedPackageComposeError(
            "spend_consent must be an explicit boolean"
        )
    if not isinstance(goals, list) or len(goals) == 0:
        raise MidnightOilUnattendedPackageComposeError(
            "goals must be a non-empty array"
        )

    notes: list[str] = [
        "live_execution_authorized=false — unattended package never launches workers",
    ]

    brief_ready = (
        operator_ack and unattended_ack
        if brief_dispatch_ready is None
        else brief_dispatch_ready
    )
    if not isinstance(brief_ready, bool):
        raise MidnightOilUnattendedPackageComposeError(
            "brief_dispatch_ready must be boolean when set"
        )

    try:
        entry_readiness = compose_midnight_oil_entry_to_swarm_readiness(
            operator_id=operator_id,
            work_minutes=work_minutes,
            goals=goals,
            operator_ack=operator_ack,
            brief_dispatch_ready=brief_ready,
            unattended_ack=unattended_ack,
            spend_consent=spend_consent,
            usd_per_hour=usd_per_hour,
            approved_ceiling_usd=approved_ceiling_usd,
        )
    except MidnightOilEntryToSwarmReadinessComposeError as e:
        raise MidnightOilUnattendedPackageComposeError(str(e)) from e
    notes.extend(entry_readiness.notes)

    # Map MoGoalEntry title → SwarmGoal statement
    swarm_goals: list[dict[str, Any]] = []
    for i, g in enumerate(goals):
        if not isinstance(g, dict):
            raise MidnightOilUnattendedPackageComposeError(
                f"goals[{i}] must be an object"
            )
        gid = g.get("goal_id")
        title = g.get("title") or g.get("statement")
        swarm_goals.append(
            {
                "goal_id": gid,
                "statement": title,
                "priority": len(goals) - i,
            }
        )

    price = entry_readiness.entry.approved_ceiling_usd
    if price is None:
        price = approved_ceiling_usd

    try:
        launch = compose_midnight_oil_launch_package(
            operator_id=operator_id,
            work_minutes=work_minutes,
            goals=swarm_goals,
            price_ceiling_usd=price,
            recommended_ceiling_usd=entry_readiness.entry.recommend.recommended_ceiling_usd,
            usd_per_hour=usd_per_hour,
            operator_approved=operator_ack,
            unattended_ack=unattended_ack,
            spend_consent=spend_consent,
        )
    except MidnightOilLaunchPackageComposeError as e:
        raise MidnightOilUnattendedPackageComposeError(str(e)) from e
    notes.extend(launch.notes)

    unattended_package_ready = (
        entry_readiness.package_ready
        and launch.package_ready
        and entry_readiness.live_execution_authorized is False
        and launch.live_execution_authorized is False
    )
    if not entry_readiness.package_ready:
        notes.append(
            "unattended_package_ready=false — entry readiness not ready"
        )
    elif not launch.package_ready:
        notes.append(
            "unattended_package_ready=false — launch package not ready"
        )
    else:
        notes.append(
            "unattended_package_ready=true — full unattended intent; "
            "still live_execution_authorized=false"
        )

    if (
        entry_readiness.live_execution_authorized is not False
        or launch.live_execution_authorized is not False
    ):
        raise MidnightOilUnattendedPackageComposeError(
            "invariant: live_execution_authorized must remain false"
        )

    notes.append("live_execution_authorized=false")

    return MidnightOilUnattendedPackageCompose(
        entry_readiness=entry_readiness,
        launch=launch,
        unattended_package_ready=unattended_package_ready,
        live_execution_authorized=False,
        notes=tuple(notes),
        authority="midnight_oil_unattended_package_compose_advisory",
    )


def format_midnight_oil_unattended_package_summary(
    c: MidnightOilUnattendedPackageCompose,
) -> str:
    return (
        f"unattended_package_ready={c.unattended_package_ready} · "
        f"entry_ready={c.entry_readiness.entry.entry_ready} · "
        f"launch_ready={c.launch.package_ready} · "
        f"goals={c.entry_readiness.entry.goal_count} · "
        f"live_execution_authorized=false"
    )


__all__ = [
    "MidnightOilUnattendedPackageCompose",
    "MidnightOilUnattendedPackageComposeError",
    "compose_midnight_oil_unattended_package",
    "format_midnight_oil_unattended_package_summary",
]
