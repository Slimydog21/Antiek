"""HTML-native view over marketplace free settings ND twin pack (pure).

pdf_view_authorized / pdf_primary always False.
twin_written / purchase_executed / hosted always False.
secrets_stored / inventory_mutated / live_router_authorized always False.
production_router_verdict always REJECT.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.html_native_view_session_authority_compose import (
    HtmlNativeViewSessionAuthorityCompose,
    HtmlNativeViewSessionAuthorityComposeError,
    compose_html_native_view_session_authority,
)
from substrate.marketplace_free_settings_add_model_nd_shadow_twin_compose import (
    MarketplaceFreeSettingsAddModelNdShadowTwinCompose,
    MarketplaceFreeSettingsAddModelNdShadowTwinComposeError,
    compose_marketplace_free_settings_add_model_nd_shadow_twin,
)


class HtmlNativeMarketplaceFreeSettingsNdTwinComposeError(ValueError):
    """Fail-closed validation for HTML-native + marketplace free settings ND twin pack."""


@dataclass(frozen=True)
class HtmlNativeMarketplaceFreeSettingsNdTwinCompose:
    session_id: str
    parent_asset_id: str
    asset_id: str
    title: str
    account_id: str
    week_id: str
    html_view: HtmlNativeViewSessionAuthorityCompose
    market_pack: MarketplaceFreeSettingsAddModelNdShadowTwinCompose
    session_aligned: bool
    parent_aligned: bool
    pack_ready: bool
    pdf_view_authorized: bool
    pdf_primary: bool
    store_mutated: bool
    twin_written: bool
    prompts_injected: bool
    live_dispatch_authorized: bool
    purchase_executed: bool
    hosted: bool
    remote_fetched: bool
    backlog_mutated: bool
    secrets_stored: bool
    inventory_mutated: bool
    live_router_authorized: bool
    suite_rewritten: bool
    live_execution_authorized: bool
    charge_executed: bool
    remote_index_queried: bool
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
            "parent_asset_id": self.parent_asset_id,
            "asset_id": self.asset_id,
            "title": self.title,
            "account_id": self.account_id,
            "week_id": self.week_id,
            "html_view": self.html_view.to_dict(),
            "market_pack": self.market_pack.to_dict(),
            "session_aligned": self.session_aligned,
            "parent_aligned": self.parent_aligned,
            "pack_ready": self.pack_ready,
            "pdf_view_authorized": False,
            "pdf_primary": False,
            "store_mutated": False,
            "twin_written": False,
            "prompts_injected": False,
            "live_dispatch_authorized": False,
            "purchase_executed": False,
            "hosted": False,
            "remote_fetched": False,
            "backlog_mutated": False,
            "secrets_stored": False,
            "inventory_mutated": False,
            "live_router_authorized": False,
            "suite_rewritten": False,
            "live_execution_authorized": False,
            "charge_executed": False,
            "remote_index_queried": False,
            "live_dispatched": False,
            "pack_dispatched": False,
            "merge_executed": False,
            "draft_written": False,
            "record_persisted": False,
            "analysis_written": False,
            "production_router_verdict": "REJECT",
            "notes": list(self.notes),
            "authority": (
                "html_native_marketplace_free_settings_nd_twin_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HtmlNativeMarketplaceFreeSettingsNdTwinComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_html_native_marketplace_free_settings_nd_twin(
    *,
    html_view: object,
    market_pack: object,
    operator_ack: object,
    require_both: object | None = None,
) -> HtmlNativeMarketplaceFreeSettingsNdTwinCompose:
    """HTML-native on marketplace free settings ND twin. Never PDF-primary."""
    if not isinstance(operator_ack, bool):
        raise HtmlNativeMarketplaceFreeSettingsNdTwinComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(html_view, dict):
        raise HtmlNativeMarketplaceFreeSettingsNdTwinComposeError(
            "html_view must be an object"
        )
    if not isinstance(market_pack, dict):
        raise HtmlNativeMarketplaceFreeSettingsNdTwinComposeError(
            "market_pack must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise HtmlNativeMarketplaceFreeSettingsNdTwinComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "pdf_view_authorized=false · pdf_primary=false · store_mutated=false",
        "twin_written=false · purchase_executed=false · hosted=false",
        "production_router_verdict=REJECT",
    ]

    try:
        hv = compose_html_native_view_session_authority(
            session_id=html_view.get("session_id"),
            asset_id=html_view.get("asset_id"),
            html_projection_sha=html_view.get("html_projection_sha"),
            view_requested=html_view.get("view_requested"),
            twin_bound=html_view.get("twin_bound"),
            operator_ack=operator_ack,
            twin_substrate_ready=html_view.get("twin_substrate_ready"),
            claimed_format=html_view.get("claimed_format"),
            reading=html_view.get("reading"),
            research=html_view.get("research"),
        )
    except HtmlNativeViewSessionAuthorityComposeError as e:
        raise HtmlNativeMarketplaceFreeSettingsNdTwinComposeError(
            str(e)
        ) from e
    notes.extend(f"[html_view] {n}" for n in hv.notes)

    try:
        tp = compose_marketplace_free_settings_add_model_nd_shadow_twin(
            market=market_pack.get("market"),
            settings_pack=market_pack.get("settings_pack"),
            operator_ack=operator_ack,
            require_both=market_pack.get("require_both"),
        )
    except MarketplaceFreeSettingsAddModelNdShadowTwinComposeError as e:
        raise HtmlNativeMarketplaceFreeSettingsNdTwinComposeError(
            str(e)
        ) from e
    notes.extend(f"[market_pack] {n}" for n in tp.notes)

    session = _require_nonempty(hv.session_id, field="session_id")
    asset = _require_nonempty(hv.asset_id, field="asset_id")
    parent = _require_nonempty(tp.parent_asset_id, field="parent_asset_id")
    title = _require_nonempty(tp.title, field="title")
    account = _require_nonempty(tp.account_id, field="account_id")
    week = _require_nonempty(tp.week_id, field="week_id")
    
    session_aligned = tp.session_id == session
    parent_aligned = tp.parent_asset_id == asset or tp.asset_id == asset
    if not session_aligned:
        notes.append(
            f"session_aligned=false — html_view.session_id={session} "
            f"market_pack.session_id={tp.session_id}"
        )
    else:
        notes.append("session_aligned=true")
    if not parent_aligned:
        notes.append(
            f"parent_aligned=false — html_view.asset_id={asset} "
            f"market_pack.parent_asset_id={parent}"
        )
    else:
        notes.append("parent_aligned=true")

    if require:
        pack_ready = (
            session_aligned is True
            and parent_aligned is True
            and hv.pack_ready is True
            and tp.pack_ready is True
            and tp.production_router_verdict == "REJECT"
            and hv.pdf_view_authorized is False
            and hv.pdf_primary is False
            and hv.store_mutated is False
            and tp.twin_written is False
            and tp.prompts_injected is False
            and tp.live_dispatch_authorized is False
            and tp.purchase_executed is False
            and tp.hosted is False
            and tp.remote_fetched is False
            and tp.inventory_mutated is False
            and tp.secrets_stored is False
            and tp.live_router_authorized is False
            and tp.suite_rewritten is False
            and tp.charge_executed is False
            and tp.pdf_view_authorized is False
            and tp.pdf_primary is False
            and operator_ack is True
        )
    else:
        pack_ready = (
            session_aligned is True
            and parent_aligned is True
            and operator_ack is True
            and tp.production_router_verdict == "REJECT"
            and hv.pdf_view_authorized is False
            and hv.pdf_primary is False
            and tp.twin_written is False
            and tp.purchase_executed is False
            and tp.hosted is False
            and (hv.pack_ready is True or tp.pack_ready is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — HTML-native view + marketplace free settings ND twin "
            "ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — html_view, market_pack, alignment, or operator_ack "
            "gate open"
        )

    if (
        hv.pdf_view_authorized is not False
        or hv.pdf_primary is not False
        or hv.store_mutated is not False
        or tp.twin_written is not False
        or tp.prompts_injected is not False
        or tp.live_dispatch_authorized is not False
        or tp.purchase_executed is not False
        or tp.hosted is not False
        or tp.remote_fetched is not False
        or tp.inventory_mutated is not False
        or tp.secrets_stored is not False
        or tp.live_router_authorized is not False
        or tp.suite_rewritten is not False
        or tp.production_router_verdict != "REJECT"
    ):
        raise HtmlNativeMarketplaceFreeSettingsNdTwinComposeError(
            "invariant: honesty flags must remain false / REJECT"
        )

    notes.extend(
        (
            "pdf_view_authorized=false",
            "pdf_primary=false",
            "store_mutated=false",
            "twin_written=false",
            "prompts_injected=false",
            "live_dispatch_authorized=false",
            "purchase_executed=false",
            "hosted=false",
            "remote_fetched=false",
            "backlog_mutated=false",
            "secrets_stored=false",
            "inventory_mutated=false",
            "live_router_authorized=false",
            "suite_rewritten=false",
            "live_execution_authorized=false",
            "charge_executed=false",
            "remote_index_queried=false",
            "live_dispatched=false",
            "pack_dispatched=false",
            "merge_executed=false",
            "draft_written=false",
            "record_persisted=false",
            "analysis_written=false",
            "production_router_verdict=REJECT",
        )
    )

    return HtmlNativeMarketplaceFreeSettingsNdTwinCompose(
        session_id=session,
        parent_asset_id=parent,
        asset_id=asset,
        title=title,
        account_id=account,
        week_id=week,
        html_view=hv,
        market_pack=tp,
        session_aligned=session_aligned,
        parent_aligned=parent_aligned,
        pack_ready=pack_ready,
        pdf_view_authorized=False,
        pdf_primary=False,
        store_mutated=False,
        twin_written=False,
        prompts_injected=False,
        live_dispatch_authorized=False,
        purchase_executed=False,
        hosted=False,
        remote_fetched=False,
        backlog_mutated=False,
        secrets_stored=False,
        inventory_mutated=False,
        live_router_authorized=False,
        suite_rewritten=False,
        live_execution_authorized=False,
        charge_executed=False,
        remote_index_queried=False,
        live_dispatched=False,
        pack_dispatched=False,
        merge_executed=False,
        draft_written=False,
        record_persisted=False,
        analysis_written=False,
        production_router_verdict="REJECT",
        notes=tuple(notes),
        authority=(
            "html_native_marketplace_free_settings_nd_twin_compose_advisory"
        ),
    )


def format_html_native_marketplace_free_settings_nd_twin_summary(
    c: HtmlNativeMarketplaceFreeSettingsNdTwinCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"html_ready={c.html_view.pack_ready} · "
        f"market_ready={c.market_pack.pack_ready} · "
        f"session_aligned={c.session_aligned} · parent_aligned={c.parent_aligned} · "
        f"path={c.market_pack.market.path} · week={c.week_id} · "
        f"verdict={c.production_router_verdict} · "
        "pdf_primary=false · purchase_executed=false · hosted=false"
    )




__all__ = [
    "HtmlNativeMarketplaceFreeSettingsNdTwinCompose",
    "HtmlNativeMarketplaceFreeSettingsNdTwinComposeError",
    "compose_html_native_marketplace_free_settings_nd_twin",
    "format_html_native_marketplace_free_settings_nd_twin_summary",
]
