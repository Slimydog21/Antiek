"""Marketplace free-before-buy over competition DR + settings add-model pack (pure).

purchase_executed / hosted / pdf_view_authorized always False.
live_dispatch_authorized / remote_fetched / backlog_mutated always False.
secrets_stored / inventory_mutated / live_router_authorized always False.
production_router_verdict always REJECT.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.settings_add_model_nd_shadow_twin_presentation_compose import (
    SettingsAddModelNdShadowTwinPresentationCompose,
    SettingsAddModelNdShadowTwinPresentationComposeError,
    compose_settings_add_model_nd_shadow_twin_presentation,
)
from substrate.marketplace_free_before_buy_html_port_compose import (
    MarketplaceFreeBeforeBuyHtmlPortCompose,
    MarketplaceFreeBeforeBuyHtmlPortComposeError,
    compose_marketplace_free_before_buy_html_port,
)


class MarketplaceFreeSettingsAddModelNdShadowTwinComposeError(ValueError):
    """Fail-closed validation for marketplace free + competition DR pack."""


@dataclass(frozen=True)
class MarketplaceFreeSettingsAddModelNdShadowTwinCompose:
    title: str
    account_id: str
    session_id: str
    week_id: str
    parent_asset_id: str
    asset_id: str
    market: MarketplaceFreeBeforeBuyHtmlPortCompose
    settings_pack: SettingsAddModelNdShadowTwinPresentationCompose
    pack_ready: bool
    purchase_executed: bool
    hosted: bool
    pdf_view_authorized: bool
    pdf_primary: bool
    live_dispatch_authorized: bool
    remote_fetched: bool
    backlog_mutated: bool
    secrets_stored: bool
    inventory_mutated: bool
    live_router_authorized: bool
    suite_rewritten: bool
    store_mutated: bool
    live_execution_authorized: bool
    charge_executed: bool
    remote_index_queried: bool
    twin_written: bool
    prompts_injected: bool
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
            "title": self.title,
            "account_id": self.account_id,
            "session_id": self.session_id,
            "week_id": self.week_id,
            "parent_asset_id": self.parent_asset_id,
            "asset_id": self.asset_id,
            "market": self.market.to_dict(),
            "settings_pack": self.settings_pack.to_dict(),
            "pack_ready": self.pack_ready,
            "purchase_executed": False,
            "hosted": False,
            "pdf_view_authorized": False,
            "pdf_primary": False,
            "live_dispatch_authorized": False,
            "remote_fetched": False,
            "backlog_mutated": False,
            "secrets_stored": False,
            "inventory_mutated": False,
            "live_router_authorized": False,
            "suite_rewritten": False,
            "store_mutated": False,
            "live_execution_authorized": False,
            "charge_executed": False,
            "remote_index_queried": False,
            "twin_written": False,
            "prompts_injected": False,
            "live_dispatched": False,
            "pack_dispatched": False,
            "merge_executed": False,
            "draft_written": False,
            "record_persisted": False,
            "analysis_written": False,
            "production_router_verdict": "REJECT",
            "notes": list(self.notes),
            "authority": (
                "marketplace_free_settings_add_model_nd_shadow_twin_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MarketplaceFreeSettingsAddModelNdShadowTwinComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_marketplace_free_settings_add_model_nd_shadow_twin(
    *,
    market: object,
    settings_pack: object,
    operator_ack: object,
    require_both: object | None = None,
) -> MarketplaceFreeSettingsAddModelNdShadowTwinCompose:
    """Free-before-buy on settings add-model ND shadow pack. Never purchases/hosts."""
    if not isinstance(operator_ack, bool):
        raise MarketplaceFreeSettingsAddModelNdShadowTwinComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(market, dict):
        raise MarketplaceFreeSettingsAddModelNdShadowTwinComposeError(
            "market must be an object"
        )
    if not isinstance(settings_pack, dict):
        raise MarketplaceFreeSettingsAddModelNdShadowTwinComposeError(
            "settings_pack must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise MarketplaceFreeSettingsAddModelNdShadowTwinComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "purchase_executed=false · hosted=false",
        "pdf_view_authorized=false · pdf_primary=false",
        "live_dispatch_authorized=false · remote_fetched=false · backlog_mutated=false",
        "secrets_stored=false · inventory_mutated=false · live_router_authorized=false",
        "production_router_verdict=REJECT",
    ]

    try:
        m = compose_marketplace_free_before_buy_html_port(
            title=market.get("title"),
            account_id=market.get("account_id"),
            free_copy_available=market.get("free_copy_available"),
            purchase_ack=market.get("purchase_ack"),
            port_requested=market.get("port_requested"),
            free_html_projection_sha=market.get("free_html_projection_sha"),
            purchase_html_projection_sha=market.get(
                "purchase_html_projection_sha"
            ),
        )
    except MarketplaceFreeBeforeBuyHtmlPortComposeError as e:
        raise MarketplaceFreeSettingsAddModelNdShadowTwinComposeError(
            str(e)
        ) from e
    notes.extend(f"[market] {n}" for n in m.notes)

    try:
        cp = compose_settings_add_model_nd_shadow_twin_presentation(
            settings=settings_pack.get("settings"),
            nd_pack=settings_pack.get("nd_pack"),
            operator_ack=operator_ack,
            require_both=settings_pack.get("require_both"),
        )
    except SettingsAddModelNdShadowTwinPresentationComposeError as e:
        raise MarketplaceFreeSettingsAddModelNdShadowTwinComposeError(
            str(e)
        ) from e
    notes.extend(f"[settings_pack] {n}" for n in cp.notes)

    title = _require_nonempty(m.title, field="title")
    account = _require_nonempty(m.account_id, field="account_id")
    session = _require_nonempty(cp.session_id, field="session_id")
    week = _require_nonempty(cp.week_id, field="week_id")
    parent = _require_nonempty(cp.parent_asset_id, field="parent_asset_id")
    asset = _require_nonempty(cp.nd_pack.asset_id, field="asset_id")

    if require:
        pack_ready = (
            m.port_ready is True
            and cp.pack_ready is True
            and m.purchase_executed is False
            and m.hosted is False
            and m.pdf_view_authorized is False
            and cp.nd_pack.live_dispatch_authorized is False
            and cp.nd_pack.remote_fetched is False
            and cp.backlog_mutated is False
            and cp.inventory_mutated is False
            and cp.secrets_stored is False
            and cp.live_router_authorized is False
            and cp.nd_pack.suite_rewritten is False
            and cp.live_execution_authorized is False
            and cp.purchase_executed is False
            and cp.nd_pack.charge_executed is False
            and cp.production_router_verdict == "REJECT"
            and operator_ack is True
        )
    else:
        pack_ready = (
            operator_ack is True
            and m.purchase_executed is False
            and m.hosted is False
            and cp.nd_pack.live_dispatch_authorized is False
            and cp.nd_pack.remote_fetched is False
            and cp.production_router_verdict == "REJECT"
            and (m.port_ready is True or cp.pack_ready is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — marketplace free + settings add-model ND shadow bench "
            "MO ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — market, settings_pack, or operator_ack gate open"
        )

    if (
        m.purchase_executed is not False
        or m.hosted is not False
        or m.pdf_view_authorized is not False
        or cp.nd_pack.live_dispatch_authorized is not False
        or cp.nd_pack.remote_fetched is not False
        or cp.backlog_mutated is not False
        or cp.inventory_mutated is not False
        or cp.secrets_stored is not False
        or cp.live_router_authorized is not False
        or cp.nd_pack.suite_rewritten is not False
        or cp.live_execution_authorized is not False
        or cp.purchase_executed is not False
        or cp.production_router_verdict != "REJECT"
    ):
        raise MarketplaceFreeSettingsAddModelNdShadowTwinComposeError(
            "invariant: honesty flags must remain false / REJECT"
        )

    notes.extend(
        (
            "purchase_executed=false",
            "hosted=false",
            "pdf_view_authorized=false",
            "pdf_primary=false",
            "live_dispatch_authorized=false",
            "remote_fetched=false",
            "backlog_mutated=false",
            "secrets_stored=false",
            "inventory_mutated=false",
            "live_router_authorized=false",
            "suite_rewritten=false",
            "store_mutated=false",
            "live_execution_authorized=false",
            "charge_executed=false",
            "remote_index_queried=false",
            "twin_written=false",
            "prompts_injected=false",
            "live_dispatched=false",
            "pack_dispatched=false",
            "merge_executed=false",
            "draft_written=false",
            "record_persisted=false",
            "analysis_written=false",
            "production_router_verdict=REJECT",
        )
    )

    return MarketplaceFreeSettingsAddModelNdShadowTwinCompose(
        title=title,
        account_id=account,
        session_id=session,
        week_id=week,
        parent_asset_id=parent,
        asset_id=asset,
        market=m,
        settings_pack=cp,
        pack_ready=pack_ready,
        purchase_executed=False,
        hosted=False,
        pdf_view_authorized=False,
        pdf_primary=False,
        live_dispatch_authorized=False,
        remote_fetched=False,
        backlog_mutated=False,
        secrets_stored=False,
        inventory_mutated=False,
        live_router_authorized=False,
        suite_rewritten=False,
        store_mutated=False,
        live_execution_authorized=False,
        charge_executed=False,
        remote_index_queried=False,
        twin_written=False,
        prompts_injected=False,
        live_dispatched=False,
        pack_dispatched=False,
        merge_executed=False,
        draft_written=False,
        record_persisted=False,
        analysis_written=False,
        production_router_verdict="REJECT",
        notes=tuple(notes),
        authority=(
            "marketplace_free_settings_add_model_nd_shadow_twin_compose_advisory"
        ),
    )


def format_marketplace_free_settings_add_model_nd_shadow_twin_summary(
    c: MarketplaceFreeSettingsAddModelNdShadowTwinCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"port_ready={c.market.port_ready} · path={c.market.path} · "
        f"settings_ready={c.settings_pack.pack_ready} · "
        f"proposed_new={c.settings_pack.settings.proposed_new_count} · "
        f"week={c.week_id} · "
        f"verdict={c.production_router_verdict} · "
        "purchase_executed=false · hosted=false · secrets_stored=false"
    )




__all__ = [
    "MarketplaceFreeSettingsAddModelNdShadowTwinCompose",
    "MarketplaceFreeSettingsAddModelNdShadowTwinComposeError",
    "compose_marketplace_free_settings_add_model_nd_shadow_twin",
    "format_marketplace_free_settings_add_model_nd_shadow_twin_summary",
]
