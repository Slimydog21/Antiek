"""ND shadow REJECT + Antiek-bench weekly marketplace free source (pure).

production_router_verdict always REJECT; live_router_authorized always False.
backlog_mutated / store_mutated / purchase_executed / hosted always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.antiek_bench_weekly_marketplace_free_source_compose import (
    AntiekBenchWeeklyMarketplaceFreeSourceCompose,
    AntiekBenchWeeklyMarketplaceFreeSourceComposeError,
    compose_antiek_bench_weekly_marketplace_free_source,
)
from substrate.notdiamond_shadow_advisory_compose import (
    NotDiamondShadowAdvisoryCompose,
    NotDiamondShadowAdvisoryComposeError,
    compose_notdiamond_shadow_advisory,
)


class NdShadowAntiekBenchWeeklyMarketplaceComposeError(ValueError):
    """Fail-closed validation for ND shadow + weekly marketplace pack."""


@dataclass(frozen=True)
class NdShadowAntiekBenchWeeklyMarketplaceCompose:
    week_id: str
    session_id: str
    parent_asset_id: str
    nd_shadow: NotDiamondShadowAdvisoryCompose
    weekly_market: AntiekBenchWeeklyMarketplaceFreeSourceCompose
    pack_ready: bool
    production_router_verdict: str
    live_router_authorized: bool
    backlog_mutated: bool
    store_mutated: bool
    purchase_executed: bool
    hosted: bool
    remote_fetched: bool
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
    live_dispatch_authorized: bool
    secrets_stored: bool
    inventory_mutated: bool
    live_dispatched: bool
    pack_dispatched: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "week_id": self.week_id,
            "session_id": self.session_id,
            "parent_asset_id": self.parent_asset_id,
            "nd_shadow": self.nd_shadow.to_dict(),
            "weekly_market": self.weekly_market.to_dict(),
            "pack_ready": self.pack_ready,
            "production_router_verdict": "REJECT",
            "live_router_authorized": False,
            "backlog_mutated": False,
            "store_mutated": False,
            "purchase_executed": False,
            "hosted": False,
            "remote_fetched": False,
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
            "live_dispatch_authorized": False,
            "secrets_stored": False,
            "inventory_mutated": False,
            "live_dispatched": False,
            "pack_dispatched": False,
            "notes": list(self.notes),
            "authority": (
                "nd_shadow_antiek_bench_weekly_marketplace_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise NdShadowAntiekBenchWeeklyMarketplaceComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_nd_shadow_antiek_bench_weekly_marketplace(
    *,
    nd_shadow: object,
    weekly_market: object,
    operator_ack: object,
    require_both: object | None = None,
) -> NdShadowAntiekBenchWeeklyMarketplaceCompose:
    """ND shadow REJECT over weekly marketplace free source. Never live-routes."""
    if not isinstance(operator_ack, bool):
        raise NdShadowAntiekBenchWeeklyMarketplaceComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(nd_shadow, dict):
        raise NdShadowAntiekBenchWeeklyMarketplaceComposeError(
            "nd_shadow must be an object"
        )
    if not isinstance(weekly_market, dict):
        raise NdShadowAntiekBenchWeeklyMarketplaceComposeError(
            "weekly_market must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise NdShadowAntiekBenchWeeklyMarketplaceComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "production_router_verdict=REJECT · live_router_authorized=false",
        "backlog_mutated=false · store_mutated=false",
        "purchase_executed=false · hosted=false · remote_fetched=false",
    ]

    try:
        nd = compose_notdiamond_shadow_advisory(
            selected_model_id=nd_shadow.get("selected_model_id"),
            nd_recommended_model_id=nd_shadow.get("nd_recommended_model_id"),
            kill_switch_on=nd_shadow.get("kill_switch_on"),
            confidence=nd_shadow.get("confidence"),
            task=nd_shadow.get("task"),
            inventory_model_ids=nd_shadow.get("inventory_model_ids"),
        )
    except NotDiamondShadowAdvisoryComposeError as e:
        raise NdShadowAntiekBenchWeeklyMarketplaceComposeError(str(e)) from e
    notes.extend(f"[nd_shadow] {n}" for n in nd.notes)

    try:
        wm = compose_antiek_bench_weekly_marketplace_free_source(
            weekly_learn=weekly_market.get("weekly_learn"),
            market_research=weekly_market.get("market_research"),
            operator_ack=operator_ack,
            require_both=weekly_market.get("require_both"),
        )
    except AntiekBenchWeeklyMarketplaceFreeSourceComposeError as e:
        raise NdShadowAntiekBenchWeeklyMarketplaceComposeError(
            str(e)
        ) from e
    notes.extend(f"[weekly_market] {n}" for n in wm.notes)

    week = _require_nonempty(wm.week_id, field="week_id")
    session = _require_nonempty(wm.session_id, field="session_id")
    parent = _require_nonempty(wm.parent_asset_id, field="parent_asset_id")

    if require:
        pack_ready = (
            nd.production_router_verdict == "REJECT"
            and nd.live_router_authorized is False
            and wm.pack_ready is True
            and wm.production_router_verdict == "REJECT"
            and wm.backlog_mutated is False
            and wm.store_mutated is False
            and operator_ack is True
        )
    else:
        pack_ready = (
            operator_ack is True
            and nd.production_router_verdict == "REJECT"
            and nd.live_router_authorized is False
            and wm.production_router_verdict == "REJECT"
            and (nd.shadow_visible is True or wm.pack_ready is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — ND shadow REJECT + weekly marketplace free source ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — nd_shadow, weekly_market, or operator_ack gate open"
        )

    if (
        nd.production_router_verdict != "REJECT"
        or nd.live_router_authorized is not False
        or wm.production_router_verdict != "REJECT"
        or wm.live_router_authorized is not False
        or wm.backlog_mutated is not False
        or wm.store_mutated is not False
        or wm.purchase_executed is not False
        or wm.hosted is not False
    ):
        raise NdShadowAntiekBenchWeeklyMarketplaceComposeError(
            "invariant: honesty flags must remain false"
        )

    notes.extend(
        (
            "production_router_verdict=REJECT",
            "live_router_authorized=false",
            "backlog_mutated=false",
            "store_mutated=false",
            "purchase_executed=false",
            "hosted=false",
            "remote_fetched=false",
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
            "live_dispatch_authorized=false",
            "secrets_stored=false",
            "inventory_mutated=false",
            "live_dispatched=false",
            "pack_dispatched=false",
        )
    )

    return NdShadowAntiekBenchWeeklyMarketplaceCompose(
        week_id=week,
        session_id=session,
        parent_asset_id=parent,
        nd_shadow=nd,
        weekly_market=wm,
        pack_ready=pack_ready,
        production_router_verdict="REJECT",
        live_router_authorized=False,
        backlog_mutated=False,
        store_mutated=False,
        purchase_executed=False,
        hosted=False,
        remote_fetched=False,
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
        live_dispatch_authorized=False,
        secrets_stored=False,
        inventory_mutated=False,
        live_dispatched=False,
        pack_dispatched=False,
        notes=tuple(notes),
        authority="nd_shadow_antiek_bench_weekly_marketplace_compose_advisory",
    )


def format_nd_shadow_antiek_bench_weekly_marketplace_summary(
    c: NdShadowAntiekBenchWeeklyMarketplaceCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"shadow_visible={c.nd_shadow.shadow_visible} · "
        f"weekly_market_ready={c.weekly_market.pack_ready} · "
        f"proposals={c.weekly_market.weekly_learn.proposal_count} · "
        f"verdict={c.production_router_verdict} · "
        f"live_router_authorized=false · backlog_mutated=false · purchase_executed=false"
    )


__all__ = [
    "NdShadowAntiekBenchWeeklyMarketplaceCompose",
    "NdShadowAntiekBenchWeeklyMarketplaceComposeError",
    "compose_nd_shadow_antiek_bench_weekly_marketplace",
    "format_nd_shadow_antiek_bench_weekly_marketplace_summary",
]
