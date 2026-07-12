"""Antiek-bench weekly learn + ND multi-select workstation MO pack (pure).

backlog_mutated / store_mutated always False.
production_router_verdict always REJECT; live_router_authorized always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.antiek_bench_weekly_usage_learn_compose import (
    AntiekBenchWeeklyUsageLearnCompose,
    AntiekBenchWeeklyUsageLearnComposeError,
    compose_antiek_bench_weekly_usage_learn,
)
from substrate.nd_shadow_floating_multiselect_workstation_mo_compose import (
    NdShadowFloatingMultiselectWorkstationMoCompose,
    NdShadowFloatingMultiselectWorkstationMoComposeError,
    compose_nd_shadow_floating_multiselect_workstation_mo,
)


class AntiekBenchWeeklyNdMultiselectMoComposeError(ValueError):
    """Fail-closed validation for weekly learn + ND multi-select pack."""


@dataclass(frozen=True)
class AntiekBenchWeeklyNdMultiselectMoCompose:
    week_id: str
    session_id: str
    parent_asset_id: str
    weekly_learn: AntiekBenchWeeklyUsageLearnCompose
    nd_research: NdShadowFloatingMultiselectWorkstationMoCompose
    pack_ready: bool
    backlog_mutated: bool
    store_mutated: bool
    production_router_verdict: str
    live_router_authorized: bool
    live_dispatched: bool
    pack_dispatched: bool
    purchase_executed: bool
    twin_written: bool
    live_execution_authorized: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "week_id": self.week_id,
            "session_id": self.session_id,
            "parent_asset_id": self.parent_asset_id,
            "weekly_learn": self.weekly_learn.to_dict(),
            "nd_research": self.nd_research.to_dict(),
            "pack_ready": self.pack_ready,
            "backlog_mutated": False,
            "store_mutated": False,
            "production_router_verdict": "REJECT",
            "live_router_authorized": False,
            "live_dispatched": False,
            "pack_dispatched": False,
            "purchase_executed": False,
            "twin_written": False,
            "live_execution_authorized": False,
            "notes": list(self.notes),
            "authority": (
                "antiek_bench_weekly_nd_multiselect_mo_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AntiekBenchWeeklyNdMultiselectMoComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_antiek_bench_weekly_nd_multiselect_mo(
    *,
    weekly_learn: object,
    nd_research: object,
    operator_ack: object,
    require_both: object | None = None,
) -> AntiekBenchWeeklyNdMultiselectMoCompose:
    """Weekly bench learn + ND multi-select research. Never mutates bench/router."""
    if not isinstance(operator_ack, bool):
        raise AntiekBenchWeeklyNdMultiselectMoComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(weekly_learn, dict):
        raise AntiekBenchWeeklyNdMultiselectMoComposeError(
            "weekly_learn must be an object"
        )
    if not isinstance(nd_research, dict):
        raise AntiekBenchWeeklyNdMultiselectMoComposeError(
            "nd_research must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise AntiekBenchWeeklyNdMultiselectMoComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "backlog_mutated=false · store_mutated=false — bench rewrite proposals only",
        "production_router_verdict=REJECT · live_router_authorized=false",
        "live_dispatched=false · pack_dispatched=false · purchase_executed=false",
        "twin_written=false · live_execution_authorized=false",
    ]

    try:
        learn = compose_antiek_bench_weekly_usage_learn(
            week_id=weekly_learn.get("week_id"),
            events=weekly_learn.get("events"),
            operator_ack=operator_ack,
            min_events_per_task=weekly_learn.get("min_events_per_task"),
        )
    except AntiekBenchWeeklyUsageLearnComposeError as e:
        raise AntiekBenchWeeklyNdMultiselectMoComposeError(str(e)) from e
    notes.extend(f"[weekly_learn] {n}" for n in learn.notes)

    try:
        nd_pack = compose_nd_shadow_floating_multiselect_workstation_mo(
            nd_shadow=nd_research.get("nd_shadow"),
            research_pack=nd_research.get("research_pack"),
            operator_ack=operator_ack,
            require_both=nd_research.get("require_both"),
        )
    except NdShadowFloatingMultiselectWorkstationMoComposeError as e:
        raise AntiekBenchWeeklyNdMultiselectMoComposeError(str(e)) from e
    notes.extend(f"[nd_research] {n}" for n in nd_pack.notes)

    week = _require_nonempty(learn.week_id, field="week_id")
    session = _require_nonempty(nd_pack.session_id, field="session_id")
    parent = _require_nonempty(
        nd_pack.parent_asset_id, field="parent_asset_id"
    )

    if require:
        pack_ready = (
            learn.learn_ready is True
            and nd_pack.pack_ready is True
            and nd_pack.production_router_verdict == "REJECT"
            and operator_ack is True
        )
    else:
        pack_ready = (
            operator_ack is True
            and nd_pack.production_router_verdict == "REJECT"
            and (learn.learn_ready is True or nd_pack.pack_ready is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — weekly bench learn + ND multi-select research ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — weekly_learn, nd_research, or operator_ack gate open"
        )

    if (
        learn.backlog_mutated is not False
        or learn.store_mutated is not False
        or nd_pack.production_router_verdict != "REJECT"
        or nd_pack.live_router_authorized is not False
        or nd_pack.live_dispatched is not False
        or nd_pack.purchase_executed is not False
        or nd_pack.live_execution_authorized is not False
    ):
        raise AntiekBenchWeeklyNdMultiselectMoComposeError(
            "invariant: honesty flags must remain false"
        )

    notes.extend(
        (
            "backlog_mutated=false",
            "store_mutated=false",
            "production_router_verdict=REJECT",
            "live_router_authorized=false",
            "live_dispatched=false",
            "pack_dispatched=false",
            "purchase_executed=false",
            "twin_written=false",
            "live_execution_authorized=false",
        )
    )

    return AntiekBenchWeeklyNdMultiselectMoCompose(
        week_id=week,
        session_id=session,
        parent_asset_id=parent,
        weekly_learn=learn,
        nd_research=nd_pack,
        pack_ready=pack_ready,
        backlog_mutated=False,
        store_mutated=False,
        production_router_verdict="REJECT",
        live_router_authorized=False,
        live_dispatched=False,
        pack_dispatched=False,
        purchase_executed=False,
        twin_written=False,
        live_execution_authorized=False,
        notes=tuple(notes),
        authority="antiek_bench_weekly_nd_multiselect_mo_compose_advisory",
    )


def format_antiek_bench_weekly_nd_multiselect_mo_summary(
    c: AntiekBenchWeeklyNdMultiselectMoCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"learn_ready={c.weekly_learn.learn_ready} · "
        f"proposals={c.weekly_learn.proposal_count} · "
        f"nd_research_ready={c.nd_research.pack_ready} · "
        f"verdict={c.production_router_verdict} · "
        f"backlog_mutated=false · store_mutated=false · "
        f"live_router_authorized=false · live_execution_authorized=false"
    )


__all__ = [
    "AntiekBenchWeeklyNdMultiselectMoCompose",
    "AntiekBenchWeeklyNdMultiselectMoComposeError",
    "compose_antiek_bench_weekly_nd_multiselect_mo",
    "format_antiek_bench_weekly_nd_multiselect_mo_summary",
]
