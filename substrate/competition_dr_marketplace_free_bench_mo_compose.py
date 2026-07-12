"""Competition DR quality over marketplace free + bench recommend MO (pure).

live_dispatch_authorized / remote_fetched / backlog_mutated always False.
purchase_executed / hosted always False.
production_router_verdict always REJECT.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.competition_dr_quality_source_pack_compose import (
    CompetitionDrQualitySourcePackCompose,
    CompetitionDrQualitySourcePackComposeError,
    compose_competition_dr_quality_source_pack,
)
from substrate.marketplace_free_antiek_bench_recommend_mo_compose import (
    MarketplaceFreeAntiekBenchRecommendMoCompose,
    MarketplaceFreeAntiekBenchRecommendMoComposeError,
    compose_marketplace_free_antiek_bench_recommend_mo,
)


class CompetitionDrMarketplaceFreeBenchMoComposeError(ValueError):
    """Fail-closed validation for competition DR + free marketplace bench MO."""


@dataclass(frozen=True)
class CompetitionDrMarketplaceFreeBenchMoCompose:
    session_id: str
    title: str
    account_id: str
    week_id: str
    parent_asset_id: str
    asset_id: str
    competition: CompetitionDrQualitySourcePackCompose
    free_pack: MarketplaceFreeAntiekBenchRecommendMoCompose
    pack_ready: bool
    live_dispatch_authorized: bool
    remote_fetched: bool
    backlog_mutated: bool
    purchase_executed: bool
    hosted: bool
    pdf_view_authorized: bool
    pdf_primary: bool
    live_router_authorized: bool
    secrets_stored: bool
    live_meter_read: bool
    store_mutated: bool
    suite_rewritten: bool
    live_execution_authorized: bool
    charge_executed: bool
    remote_index_queried: bool
    twin_written: bool
    prompts_injected: bool
    inventory_mutated: bool
    live_dispatched: bool
    pack_dispatched: bool
    merge_executed: bool
    draft_written: bool
    record_persisted: bool
    analysis_written: bool
    production_router_verdict: str
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "title": self.title,
            "account_id": self.account_id,
            "week_id": self.week_id,
            "parent_asset_id": self.parent_asset_id,
            "asset_id": self.asset_id,
            "competition": self.competition.to_dict(),
            "free_pack": self.free_pack.to_dict(),
            "pack_ready": self.pack_ready,
            "live_dispatch_authorized": False,
            "remote_fetched": False,
            "backlog_mutated": False,
            "purchase_executed": False,
            "hosted": False,
            "pdf_view_authorized": False,
            "pdf_primary": False,
            "live_router_authorized": False,
            "secrets_stored": False,
            "live_meter_read": False,
            "store_mutated": False,
            "suite_rewritten": False,
            "live_execution_authorized": False,
            "charge_executed": False,
            "remote_index_queried": False,
            "twin_written": False,
            "prompts_injected": False,
            "inventory_mutated": False,
            "live_dispatched": False,
            "pack_dispatched": False,
            "merge_executed": False,
            "draft_written": False,
            "record_persisted": False,
            "analysis_written": False,
            "production_router_verdict": "REJECT",
            "notes": list(self.notes),
            "authority": (
                "competition_dr_marketplace_free_bench_mo_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CompetitionDrMarketplaceFreeBenchMoComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_competition_dr_marketplace_free_bench_mo(
    *,
    competition: object,
    free_pack: object,
    operator_ack: object,
    require_both: object | None = None,
) -> CompetitionDrMarketplaceFreeBenchMoCompose:
    """Competition DR quality + free marketplace bench MO. Never dispatches."""
    if not isinstance(operator_ack, bool):
        raise CompetitionDrMarketplaceFreeBenchMoComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(competition, dict):
        raise CompetitionDrMarketplaceFreeBenchMoComposeError(
            "competition must be an object"
        )
    if not isinstance(free_pack, dict):
        raise CompetitionDrMarketplaceFreeBenchMoComposeError(
            "free_pack must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise CompetitionDrMarketplaceFreeBenchMoComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "live_dispatch_authorized=false · remote_fetched=false · backlog_mutated=false",
        "purchase_executed=false · hosted=false · pdf_primary=false",
        "production_router_verdict=REJECT",
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
        raise CompetitionDrMarketplaceFreeBenchMoComposeError(str(e)) from e
    notes.extend(f"[competition] {n}" for n in comp.notes)

    try:
        fp = compose_marketplace_free_antiek_bench_recommend_mo(
            market=free_pack.get("market"),
            bench_mo=free_pack.get("bench_mo"),
            operator_ack=operator_ack,
            require_both=free_pack.get("require_both"),
        )
    except MarketplaceFreeAntiekBenchRecommendMoComposeError as e:
        raise CompetitionDrMarketplaceFreeBenchMoComposeError(str(e)) from e
    notes.extend(f"[free_pack] {n}" for n in fp.notes)

    session = _require_nonempty(comp.session_id, field="session_id")
    title = _require_nonempty(fp.title, field="title")
    account = _require_nonempty(fp.account_id, field="account_id")
    week = _require_nonempty(fp.week_id, field="week_id")
    parent = _require_nonempty(fp.parent_asset_id, field="parent_asset_id")
    asset = _require_nonempty(fp.asset_id, field="asset_id")

    session_aligned = fp.session_id == session
    if not session_aligned:
        notes.append(
            "session_id mismatch between competition and free_pack — pack_ready blocked"
        )

    if require:
        pack_ready = (
            session_aligned
            and comp.pack_ready is True
            and fp.pack_ready is True
            and comp.live_dispatch_authorized is False
            and comp.remote_fetched is False
            and comp.backlog_mutated is False
            and fp.purchase_executed is False
            and fp.hosted is False
            and fp.pdf_primary is False
            and fp.live_dispatch_authorized is False
            and fp.live_execution_authorized is False
            and fp.charge_executed is False
            and fp.suite_rewritten is False
            and fp.production_router_verdict == "REJECT"
            and operator_ack is True
        )
    else:
        pack_ready = (
            session_aligned
            and operator_ack is True
            and comp.live_dispatch_authorized is False
            and fp.purchase_executed is False
            and fp.hosted is False
            and fp.production_router_verdict == "REJECT"
            and fp.pdf_primary is False
            and (comp.pack_ready is True or fp.pack_ready is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — competition DR quality + free marketplace bench MO "
            "ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — competition, free_pack, alignment, or operator_ack "
            "gate open"
        )

    if (
        comp.live_dispatch_authorized is not False
        or comp.remote_fetched is not False
        or comp.backlog_mutated is not False
        or fp.purchase_executed is not False
        or fp.hosted is not False
        or fp.pdf_primary is not False
        or fp.live_execution_authorized is not False
        or fp.charge_executed is not False
        or fp.suite_rewritten is not False
        or fp.production_router_verdict != "REJECT"
    ):
        raise CompetitionDrMarketplaceFreeBenchMoComposeError(
            "invariant: honesty flags must remain false"
        )

    notes.extend(
        (
            "live_dispatch_authorized=false",
            "remote_fetched=false",
            "backlog_mutated=false",
            "purchase_executed=false",
            "hosted=false",
            "pdf_view_authorized=false",
            "pdf_primary=false",
            "live_router_authorized=false",
            "secrets_stored=false",
            "live_meter_read=false",
            "store_mutated=false",
            "suite_rewritten=false",
            "live_execution_authorized=false",
            "charge_executed=false",
            "remote_index_queried=false",
            "twin_written=false",
            "prompts_injected=false",
            "inventory_mutated=false",
            "live_dispatched=false",
            "pack_dispatched=false",
            "merge_executed=false",
            "draft_written=false",
            "record_persisted=false",
            "analysis_written=false",
            "production_router_verdict=REJECT",
        )
    )

    return CompetitionDrMarketplaceFreeBenchMoCompose(
        session_id=session,
        title=title,
        account_id=account,
        week_id=week,
        parent_asset_id=parent,
        asset_id=asset,
        competition=comp,
        free_pack=fp,
        pack_ready=pack_ready,
        live_dispatch_authorized=False,
        remote_fetched=False,
        backlog_mutated=False,
        purchase_executed=False,
        hosted=False,
        pdf_view_authorized=False,
        pdf_primary=False,
        live_router_authorized=False,
        secrets_stored=False,
        live_meter_read=False,
        store_mutated=False,
        suite_rewritten=False,
        live_execution_authorized=False,
        charge_executed=False,
        remote_index_queried=False,
        twin_written=False,
        prompts_injected=False,
        inventory_mutated=False,
        live_dispatched=False,
        pack_dispatched=False,
        merge_executed=False,
        draft_written=False,
        record_persisted=False,
        analysis_written=False,
        production_router_verdict="REJECT",
        notes=tuple(notes),
        authority=(
            "competition_dr_marketplace_free_bench_mo_compose_advisory"
        ),
    )


def format_competition_dr_marketplace_free_bench_mo_summary(
    c: CompetitionDrMarketplaceFreeBenchMoCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"competition_ready={c.competition.pack_ready} · "
        f"free_ready={c.free_pack.pack_ready} · "
        f"path={c.free_pack.market.path} · "
        f"week={c.week_id} · "
        f"verdict={c.production_router_verdict} · "
        f"live_dispatch_authorized=false · purchase_executed=false · "
        f"remote_fetched=false"
    )


__all__ = [
    "CompetitionDrMarketplaceFreeBenchMoCompose",
    "CompetitionDrMarketplaceFreeBenchMoComposeError",
    "compose_competition_dr_marketplace_free_bench_mo",
    "format_competition_dr_marketplace_free_bench_mo_summary",
]
