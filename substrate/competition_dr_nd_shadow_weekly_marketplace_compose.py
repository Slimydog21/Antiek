"""Competition DR quality + ND shadow weekly marketplace pack (pure).

live_dispatch_authorized / remote_fetched / backlog_mutated always False.
production_router_verdict always REJECT; live_router_authorized always False.
purchase_executed / hosted / store_mutated always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.competition_dr_quality_source_pack_compose import (
    CompetitionDrQualitySourcePackCompose,
    CompetitionDrQualitySourcePackComposeError,
    compose_competition_dr_quality_source_pack,
)
from substrate.nd_shadow_antiek_bench_weekly_marketplace_compose import (
    NdShadowAntiekBenchWeeklyMarketplaceCompose,
    NdShadowAntiekBenchWeeklyMarketplaceComposeError,
    compose_nd_shadow_antiek_bench_weekly_marketplace,
)


class CompetitionDrNdShadowWeeklyMarketplaceComposeError(ValueError):
    """Fail-closed validation for competition DR + ND weekly marketplace pack."""


@dataclass(frozen=True)
class CompetitionDrNdShadowWeeklyMarketplaceCompose:
    session_id: str
    week_id: str
    parent_asset_id: str
    competition: CompetitionDrQualitySourcePackCompose
    nd_weekly: NdShadowAntiekBenchWeeklyMarketplaceCompose
    pack_ready: bool
    live_dispatch_authorized: bool
    remote_fetched: bool
    backlog_mutated: bool
    production_router_verdict: str
    live_router_authorized: bool
    store_mutated: bool
    purchase_executed: bool
    hosted: bool
    prompts_injected: bool
    pdf_view_authorized: bool
    pdf_primary: bool
    twin_written: bool
    charge_executed: bool
    live_execution_authorized: bool
    draft_written: bool
    analysis_written: bool
    merge_executed: bool
    record_persisted: bool
    secrets_stored: bool
    inventory_mutated: bool
    live_dispatched: bool
    pack_dispatched: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "week_id": self.week_id,
            "parent_asset_id": self.parent_asset_id,
            "competition": self.competition.to_dict(),
            "nd_weekly": self.nd_weekly.to_dict(),
            "pack_ready": self.pack_ready,
            "live_dispatch_authorized": False,
            "remote_fetched": False,
            "backlog_mutated": False,
            "production_router_verdict": "REJECT",
            "live_router_authorized": False,
            "store_mutated": False,
            "purchase_executed": False,
            "hosted": False,
            "prompts_injected": False,
            "pdf_view_authorized": False,
            "pdf_primary": False,
            "twin_written": False,
            "charge_executed": False,
            "live_execution_authorized": False,
            "draft_written": False,
            "analysis_written": False,
            "merge_executed": False,
            "record_persisted": False,
            "secrets_stored": False,
            "inventory_mutated": False,
            "live_dispatched": False,
            "pack_dispatched": False,
            "notes": list(self.notes),
            "authority": (
                "competition_dr_nd_shadow_weekly_marketplace_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CompetitionDrNdShadowWeeklyMarketplaceComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_competition_dr_nd_shadow_weekly_marketplace(
    *,
    competition: object,
    nd_weekly: object,
    operator_ack: object,
    require_both: object | None = None,
) -> CompetitionDrNdShadowWeeklyMarketplaceCompose:
    """Competition DR quality + ND weekly marketplace. Never dispatches."""
    if not isinstance(operator_ack, bool):
        raise CompetitionDrNdShadowWeeklyMarketplaceComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(competition, dict):
        raise CompetitionDrNdShadowWeeklyMarketplaceComposeError(
            "competition must be an object"
        )
    if not isinstance(nd_weekly, dict):
        raise CompetitionDrNdShadowWeeklyMarketplaceComposeError(
            "nd_weekly must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise CompetitionDrNdShadowWeeklyMarketplaceComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "live_dispatch_authorized=false · remote_fetched=false · backlog_mutated=false",
        "production_router_verdict=REJECT · live_router_authorized=false",
        "purchase_executed=false · hosted=false · store_mutated=false",
    ]

    try:
        comp = compose_competition_dr_quality_source_pack(
            session_id=competition.get("session_id"),
            competitor_decisions=competition.get("competitor_decisions"),
            requested_families=competition.get("requested_families"),
            citations=competition.get("citations"),
            quality_overall=competition.get("quality_overall"),
            would_exceed=competition.get("would_exceed"),
            operator_ack=operator_ack,
            focus_areas=competition.get("focus_areas"),
            filter_to_selected_families=competition.get(
                "filter_to_selected_families"
            ),
            quality_floor=competition.get("quality_floor"),
            operator_override=competition.get("operator_override"),
            require_no_behind_gaps=competition.get("require_no_behind_gaps"),
        )
    except CompetitionDrQualitySourcePackComposeError as e:
        raise CompetitionDrNdShadowWeeklyMarketplaceComposeError(
            str(e)
        ) from e
    notes.extend(f"[competition] {n}" for n in comp.notes)

    try:
        nw = compose_nd_shadow_antiek_bench_weekly_marketplace(
            nd_shadow=nd_weekly.get("nd_shadow"),
            weekly_market=nd_weekly.get("weekly_market"),
            operator_ack=operator_ack,
            require_both=nd_weekly.get("require_both"),
        )
    except NdShadowAntiekBenchWeeklyMarketplaceComposeError as e:
        raise CompetitionDrNdShadowWeeklyMarketplaceComposeError(
            str(e)
        ) from e
    notes.extend(f"[nd_weekly] {n}" for n in nw.notes)

    session = _require_nonempty(comp.session_id, field="session_id")
    week = _require_nonempty(nw.week_id, field="week_id")
    parent = _require_nonempty(nw.parent_asset_id, field="parent_asset_id")

    aligned = nw.session_id == session
    if not aligned:
        notes.append(
            "session_id mismatch between competition and nd_weekly — pack_ready blocked"
        )

    if require:
        pack_ready = (
            aligned
            and comp.pack_ready is True
            and nw.pack_ready is True
            and nw.production_router_verdict == "REJECT"
            and comp.live_dispatch_authorized is False
            and comp.remote_fetched is False
            and nw.live_router_authorized is False
            and operator_ack is True
        )
    else:
        pack_ready = (
            aligned
            and operator_ack is True
            and nw.production_router_verdict == "REJECT"
            and comp.remote_fetched is False
            and (comp.pack_ready is True or nw.pack_ready is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — competition DR quality + ND shadow weekly marketplace ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — competition, nd_weekly, alignment, or operator_ack gate open"
        )

    if (
        comp.live_dispatch_authorized is not False
        or comp.remote_fetched is not False
        or comp.backlog_mutated is not False
        or nw.production_router_verdict != "REJECT"
        or nw.live_router_authorized is not False
        or nw.backlog_mutated is not False
        or nw.store_mutated is not False
        or nw.purchase_executed is not False
        or nw.hosted is not False
    ):
        raise CompetitionDrNdShadowWeeklyMarketplaceComposeError(
            "invariant: honesty flags must remain false"
        )

    notes.extend(
        (
            "live_dispatch_authorized=false",
            "remote_fetched=false",
            "backlog_mutated=false",
            "production_router_verdict=REJECT",
            "live_router_authorized=false",
            "store_mutated=false",
            "purchase_executed=false",
            "hosted=false",
            "prompts_injected=false",
            "pdf_view_authorized=false",
            "pdf_primary=false",
            "twin_written=false",
            "charge_executed=false",
            "live_execution_authorized=false",
            "draft_written=false",
            "analysis_written=false",
            "merge_executed=false",
            "record_persisted=false",
            "secrets_stored=false",
            "inventory_mutated=false",
            "live_dispatched=false",
            "pack_dispatched=false",
        )
    )

    return CompetitionDrNdShadowWeeklyMarketplaceCompose(
        session_id=session,
        week_id=week,
        parent_asset_id=parent,
        competition=comp,
        nd_weekly=nw,
        pack_ready=pack_ready,
        live_dispatch_authorized=False,
        remote_fetched=False,
        backlog_mutated=False,
        production_router_verdict="REJECT",
        live_router_authorized=False,
        store_mutated=False,
        purchase_executed=False,
        hosted=False,
        prompts_injected=False,
        pdf_view_authorized=False,
        pdf_primary=False,
        twin_written=False,
        charge_executed=False,
        live_execution_authorized=False,
        draft_written=False,
        analysis_written=False,
        merge_executed=False,
        record_persisted=False,
        secrets_stored=False,
        inventory_mutated=False,
        live_dispatched=False,
        pack_dispatched=False,
        notes=tuple(notes),
        authority=(
            "competition_dr_nd_shadow_weekly_marketplace_compose_advisory"
        ),
    )


def format_competition_dr_nd_shadow_weekly_marketplace_summary(
    c: CompetitionDrNdShadowWeeklyMarketplaceCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"competition_ready={c.competition.pack_ready} · "
        f"behind={c.competition.competition.behind_count} · "
        f"nd_weekly_ready={c.nd_weekly.pack_ready} · "
        f"verdict={c.production_router_verdict} · "
        f"live_dispatch_authorized=false · remote_fetched=false · live_router_authorized=false"
    )


__all__ = [
    "CompetitionDrNdShadowWeeklyMarketplaceCompose",
    "CompetitionDrNdShadowWeeklyMarketplaceComposeError",
    "compose_competition_dr_nd_shadow_weekly_marketplace",
    "format_competition_dr_nd_shadow_weekly_marketplace_summary",
]
