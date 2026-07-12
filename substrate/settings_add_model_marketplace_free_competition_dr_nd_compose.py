"""Settings add-model inventory over marketplace free competition DR ND pack (pure).

secrets_stored / inventory_mutated always False.
purchase_executed / hosted always False.
live_router_authorized always False.
production_router_verdict always REJECT.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.marketplace_free_competition_dr_nd_shadow_source_attach_compose import (
    MarketplaceFreeCompetitionDrNdShadowSourceAttachCompose,
    MarketplaceFreeCompetitionDrNdShadowSourceAttachComposeError,
    compose_marketplace_free_competition_dr_nd_shadow_source_attach,
)
from substrate.settings_add_model_inventory_compose import (
    SettingsAddModelInventoryCompose,
    SettingsAddModelInventoryComposeError,
    compose_settings_add_model_inventory,
)


class SettingsAddModelMarketplaceFreeCompetitionDrNdComposeError(ValueError):
    """Fail-closed validation for settings add-model + marketplace free competition pack."""


@dataclass(frozen=True)
class SettingsAddModelMarketplaceFreeCompetitionDrNdCompose:
    title: str
    account_id: str
    session_id: str
    parent_asset_id: str
    week_id: str
    asset_id: str
    settings: SettingsAddModelInventoryCompose
    market_pack: MarketplaceFreeCompetitionDrNdShadowSourceAttachCompose
    pack_ready: bool
    secrets_stored: bool
    inventory_mutated: bool
    purchase_executed: bool
    hosted: bool
    pdf_view_authorized: bool
    pdf_primary: bool
    live_dispatch_authorized: bool
    remote_fetched: bool
    backlog_mutated: bool
    store_mutated: bool
    suite_rewritten: bool
    twin_written: bool
    prompts_injected: bool
    merge_executed: bool
    draft_written: bool
    analysis_written: bool
    live_dispatched: bool
    pack_dispatched: bool
    live_execution_authorized: bool
    live_router_authorized: bool
    live_meter_read: bool
    remote_index_queried: bool
    charge_executed: bool
    record_persisted: bool
    production_router_verdict: str
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "account_id": self.account_id,
            "session_id": self.session_id,
            "parent_asset_id": self.parent_asset_id,
            "week_id": self.week_id,
            "asset_id": self.asset_id,
            "settings": self.settings.to_dict(),
            "market_pack": self.market_pack.to_dict(),
            "pack_ready": self.pack_ready,
            "secrets_stored": False,
            "inventory_mutated": False,
            "purchase_executed": False,
            "hosted": False,
            "pdf_view_authorized": False,
            "pdf_primary": False,
            "live_dispatch_authorized": False,
            "remote_fetched": False,
            "backlog_mutated": False,
            "store_mutated": False,
            "suite_rewritten": False,
            "twin_written": False,
            "prompts_injected": False,
            "merge_executed": False,
            "draft_written": False,
            "analysis_written": False,
            "live_dispatched": False,
            "pack_dispatched": False,
            "live_execution_authorized": False,
            "live_router_authorized": False,
            "live_meter_read": False,
            "remote_index_queried": False,
            "charge_executed": False,
            "record_persisted": False,
            "production_router_verdict": "REJECT",
            "notes": list(self.notes),
            "authority": (
                "settings_add_model_marketplace_free_competition_dr_nd_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SettingsAddModelMarketplaceFreeCompetitionDrNdComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_settings_add_model_marketplace_free_competition_dr_nd(
    *,
    settings: object,
    market_pack: object,
    operator_ack: object,
    require_both: object | None = None,
) -> SettingsAddModelMarketplaceFreeCompetitionDrNdCompose:
    """Settings add-model + marketplace free competition DR ND pack. Never mutates inventory."""
    if not isinstance(operator_ack, bool):
        raise SettingsAddModelMarketplaceFreeCompetitionDrNdComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(settings, dict):
        raise SettingsAddModelMarketplaceFreeCompetitionDrNdComposeError(
            "settings must be an object"
        )
    if not isinstance(market_pack, dict):
        raise SettingsAddModelMarketplaceFreeCompetitionDrNdComposeError(
            "market_pack must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise SettingsAddModelMarketplaceFreeCompetitionDrNdComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "secrets_stored=false · inventory_mutated=false",
        "purchase_executed=false · hosted=false · pdf_primary=false",
        "live_router_authorized=false · production_router_verdict=REJECT",
    ]

    try:
        st = compose_settings_add_model_inventory(
            models=settings.get("models"),
            pending_add_model_ids=settings.get("pending_add_model_ids"),
            action=settings.get("action"),
            daily_cap_usd=settings.get("daily_cap_usd"),
            spent_usd=settings.get("spent_usd"),
            operator_ack=operator_ack,
            selected_model_id=settings.get("selected_model_id"),
            projected_cost_usd_high=settings.get("projected_cost_usd_high"),
            projected_cost_usd_low=settings.get("projected_cost_usd_low"),
        )
    except SettingsAddModelInventoryComposeError as e:
        raise SettingsAddModelMarketplaceFreeCompetitionDrNdComposeError(
            str(e)
        ) from e
    notes.extend(f"[settings] {n}" for n in st.notes)

    try:
        mp = compose_marketplace_free_competition_dr_nd_shadow_source_attach(
            market=market_pack.get("market"),
            competition_pack=market_pack.get("competition_pack"),
            operator_ack=operator_ack,
            require_both=market_pack.get("require_both"),
        )
    except MarketplaceFreeCompetitionDrNdShadowSourceAttachComposeError as e:
        raise SettingsAddModelMarketplaceFreeCompetitionDrNdComposeError(
            str(e)
        ) from e
    notes.extend(f"[market_pack] {n}" for n in mp.notes)

    title = _require_nonempty(mp.title, field="title")
    account = _require_nonempty(mp.account_id, field="account_id")
    session = _require_nonempty(mp.session_id, field="session_id")
    parent = _require_nonempty(mp.parent_asset_id, field="parent_asset_id")
    week = _require_nonempty(mp.week_id, field="week_id")
    asset = _require_nonempty(mp.asset_id, field="asset_id")

    if require:
        pack_ready = (
            st.pack_ready is True
            and mp.pack_ready is True
            and st.secrets_stored is False
            and st.inventory_mutated is False
            and st.live_router_authorized is False
            and mp.purchase_executed is False
            and mp.hosted is False
            and mp.pdf_primary is False
            and mp.live_dispatch_authorized is False
            and mp.remote_fetched is False
            and mp.backlog_mutated is False
            and mp.live_router_authorized is False
            and mp.twin_written is False
            and mp.merge_executed is False
            and mp.draft_written is False
            and mp.secrets_stored is False
            and mp.remote_index_queried is False
            and mp.production_router_verdict == "REJECT"
            and mp.competition_pack.nd_pack.nd_shadow.production_router_verdict
            == "REJECT"
            and operator_ack is True
        )
    else:
        pack_ready = (
            operator_ack is True
            and st.secrets_stored is False
            and st.inventory_mutated is False
            and mp.purchase_executed is False
            and mp.hosted is False
            and mp.production_router_verdict == "REJECT"
            and (st.pack_ready is True or mp.pack_ready is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — settings add-model + marketplace free competition DR ND "
            "ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — settings, market_pack, or operator_ack gate open"
        )

    if (
        st.secrets_stored is not False
        or st.inventory_mutated is not False
        or st.live_router_authorized is not False
        or mp.purchase_executed is not False
        or mp.hosted is not False
        or mp.pdf_primary is not False
        or mp.live_dispatch_authorized is not False
        or mp.remote_fetched is not False
        or mp.backlog_mutated is not False
        or mp.live_router_authorized is not False
        or mp.twin_written is not False
        or mp.merge_executed is not False
        or mp.draft_written is not False
        or mp.secrets_stored is not False
        or mp.remote_index_queried is not False
        or mp.production_router_verdict != "REJECT"
        or mp.competition_pack.nd_pack.nd_shadow.production_router_verdict
        != "REJECT"
    ):
        raise SettingsAddModelMarketplaceFreeCompetitionDrNdComposeError(
            "invariant: honesty flags must remain false / REJECT"
        )

    notes.extend(
        (
            "secrets_stored=false",
            "inventory_mutated=false",
            "purchase_executed=false",
            "hosted=false",
            "pdf_view_authorized=false",
            "pdf_primary=false",
            "live_dispatch_authorized=false",
            "remote_fetched=false",
            "backlog_mutated=false",
            "store_mutated=false",
            "suite_rewritten=false",
            "twin_written=false",
            "prompts_injected=false",
            "merge_executed=false",
            "draft_written=false",
            "analysis_written=false",
            "live_dispatched=false",
            "pack_dispatched=false",
            "live_execution_authorized=false",
            "live_router_authorized=false",
            "live_meter_read=false",
            "remote_index_queried=false",
            "charge_executed=false",
            "record_persisted=false",
            "production_router_verdict=REJECT",
        )
    )

    return SettingsAddModelMarketplaceFreeCompetitionDrNdCompose(
        title=title,
        account_id=account,
        session_id=session,
        parent_asset_id=parent,
        week_id=week,
        asset_id=asset,
        settings=st,
        market_pack=mp,
        pack_ready=pack_ready,
        secrets_stored=False,
        inventory_mutated=False,
        purchase_executed=False,
        hosted=False,
        pdf_view_authorized=False,
        pdf_primary=False,
        live_dispatch_authorized=False,
        remote_fetched=False,
        backlog_mutated=False,
        store_mutated=False,
        suite_rewritten=False,
        twin_written=False,
        prompts_injected=False,
        merge_executed=False,
        draft_written=False,
        analysis_written=False,
        live_dispatched=False,
        pack_dispatched=False,
        live_execution_authorized=False,
        live_router_authorized=False,
        live_meter_read=False,
        remote_index_queried=False,
        charge_executed=False,
        record_persisted=False,
        production_router_verdict="REJECT",
        notes=tuple(notes),
        authority=(
            "settings_add_model_marketplace_free_competition_dr_nd_compose_advisory"
        ),
    )


def format_settings_add_model_marketplace_free_competition_dr_nd_summary(
    c: SettingsAddModelMarketplaceFreeCompetitionDrNdCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"settings_ready={c.settings.pack_ready} · "
        f"market_ready={c.market_pack.pack_ready} · "
        f"proposed_new={c.settings.proposed_new_count} · "
        f"verdict={c.production_router_verdict} · "
        "secrets_stored=false · inventory_mutated=false · purchase_executed=false"
    )


__all__ = [
    "SettingsAddModelMarketplaceFreeCompetitionDrNdCompose",
    "SettingsAddModelMarketplaceFreeCompetitionDrNdComposeError",
    "compose_settings_add_model_marketplace_free_competition_dr_nd",
    "format_settings_add_model_marketplace_free_competition_dr_nd_summary",
]
