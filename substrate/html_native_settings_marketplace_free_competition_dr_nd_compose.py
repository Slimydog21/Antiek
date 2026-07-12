"""HTML-native view over settings add-model marketplace free competition DR ND pack (pure).

pdf_view_authorized / pdf_primary always False.
secrets_stored / inventory_mutated / purchase_executed / hosted always False.
live_router_authorized always False.
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
from substrate.settings_add_model_marketplace_free_competition_dr_nd_compose import (
    SettingsAddModelMarketplaceFreeCompetitionDrNdCompose,
    SettingsAddModelMarketplaceFreeCompetitionDrNdComposeError,
    compose_settings_add_model_marketplace_free_competition_dr_nd,
)


class HtmlNativeSettingsMarketplaceFreeCompetitionDrNdComposeError(ValueError):
    """Fail-closed validation for HTML-native + settings marketplace free competition pack."""


@dataclass(frozen=True)
class HtmlNativeSettingsMarketplaceFreeCompetitionDrNdCompose:
    session_id: str
    parent_asset_id: str
    asset_id: str
    title: str
    account_id: str
    week_id: str
    html_view: HtmlNativeViewSessionAuthorityCompose
    settings_pack: SettingsAddModelMarketplaceFreeCompetitionDrNdCompose
    session_aligned: bool
    parent_aligned: bool
    pack_ready: bool
    pdf_view_authorized: bool
    pdf_primary: bool
    store_mutated: bool
    secrets_stored: bool
    inventory_mutated: bool
    purchase_executed: bool
    hosted: bool
    live_dispatch_authorized: bool
    remote_fetched: bool
    backlog_mutated: bool
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
            "session_id": self.session_id,
            "parent_asset_id": self.parent_asset_id,
            "asset_id": self.asset_id,
            "title": self.title,
            "account_id": self.account_id,
            "week_id": self.week_id,
            "html_view": self.html_view.to_dict(),
            "settings_pack": self.settings_pack.to_dict(),
            "session_aligned": self.session_aligned,
            "parent_aligned": self.parent_aligned,
            "pack_ready": self.pack_ready,
            "pdf_view_authorized": False,
            "pdf_primary": False,
            "store_mutated": False,
            "secrets_stored": False,
            "inventory_mutated": False,
            "purchase_executed": False,
            "hosted": False,
            "live_dispatch_authorized": False,
            "remote_fetched": False,
            "backlog_mutated": False,
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
                "html_native_settings_marketplace_free_competition_dr_nd_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HtmlNativeSettingsMarketplaceFreeCompetitionDrNdComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_html_native_settings_marketplace_free_competition_dr_nd(
    *,
    html_view: object,
    settings_pack: object,
    operator_ack: object,
    require_both: object | None = None,
) -> HtmlNativeSettingsMarketplaceFreeCompetitionDrNdCompose:
    """HTML-native on settings marketplace free competition DR ND. Never PDF-primary."""
    if not isinstance(operator_ack, bool):
        raise HtmlNativeSettingsMarketplaceFreeCompetitionDrNdComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(html_view, dict):
        raise HtmlNativeSettingsMarketplaceFreeCompetitionDrNdComposeError(
            "html_view must be an object"
        )
    if not isinstance(settings_pack, dict):
        raise HtmlNativeSettingsMarketplaceFreeCompetitionDrNdComposeError(
            "settings_pack must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise HtmlNativeSettingsMarketplaceFreeCompetitionDrNdComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "pdf_view_authorized=false · pdf_primary=false · store_mutated=false",
        "secrets_stored=false · inventory_mutated=false · purchase_executed=false · hosted=false",
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
        raise HtmlNativeSettingsMarketplaceFreeCompetitionDrNdComposeError(
            str(e)
        ) from e
    notes.extend(f"[html_view] {n}" for n in hv.notes)

    try:
        sp = compose_settings_add_model_marketplace_free_competition_dr_nd(
            settings=settings_pack.get("settings"),
            market_pack=settings_pack.get("market_pack"),
            operator_ack=operator_ack,
            require_both=settings_pack.get("require_both"),
        )
    except SettingsAddModelMarketplaceFreeCompetitionDrNdComposeError as e:
        raise HtmlNativeSettingsMarketplaceFreeCompetitionDrNdComposeError(
            str(e)
        ) from e
    notes.extend(f"[settings_pack] {n}" for n in sp.notes)

    session = _require_nonempty(hv.session_id, field="session_id")
    asset = _require_nonempty(hv.asset_id, field="asset_id")
    parent = _require_nonempty(sp.parent_asset_id, field="parent_asset_id")
    title = _require_nonempty(sp.title, field="title")
    account = _require_nonempty(sp.account_id, field="account_id")
    week = _require_nonempty(sp.week_id, field="week_id")

    session_aligned = sp.session_id == session
    parent_aligned = sp.parent_asset_id == asset or sp.asset_id == asset
    if not session_aligned:
        notes.append(
            f"session_aligned=false — html_view.session_id={session} "
            f"settings_pack.session_id={sp.session_id}"
        )
    else:
        notes.append("session_aligned=true")
    if not parent_aligned:
        notes.append(
            f"parent_aligned=false — html_view.asset_id={asset} "
            f"settings_pack.parent={parent} asset={sp.asset_id}"
        )
    else:
        notes.append("parent_aligned=true")

    if require:
        pack_ready = (
            session_aligned is True
            and parent_aligned is True
            and hv.pack_ready is True
            and sp.pack_ready is True
            and sp.production_router_verdict == "REJECT"
            and hv.pdf_view_authorized is False
            and hv.pdf_primary is False
            and hv.store_mutated is False
            and sp.pdf_view_authorized is False
            and sp.pdf_primary is False
            and sp.purchase_executed is False
            and sp.hosted is False
            and sp.secrets_stored is False
            and sp.inventory_mutated is False
            and sp.live_dispatch_authorized is False
            and sp.remote_fetched is False
            and sp.live_router_authorized is False
            and sp.twin_written is False
            and sp.merge_executed is False
            and sp.draft_written is False
            and sp.remote_index_queried is False
            and sp.suite_rewritten is False
            and sp.charge_executed is False
            and operator_ack is True
        )
    else:
        pack_ready = (
            session_aligned is True
            and parent_aligned is True
            and operator_ack is True
            and sp.production_router_verdict == "REJECT"
            and hv.pdf_view_authorized is False
            and hv.pdf_primary is False
            and sp.purchase_executed is False
            and sp.hosted is False
            and (hv.pack_ready is True or sp.pack_ready is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — HTML-native view + settings marketplace free "
            "competition DR ND ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — html_view, settings_pack, alignment, or "
            "operator_ack gate open"
        )

    if (
        hv.pdf_view_authorized is not False
        or hv.pdf_primary is not False
        or hv.store_mutated is not False
        or sp.pdf_view_authorized is not False
        or sp.pdf_primary is not False
        or sp.purchase_executed is not False
        or sp.hosted is not False
        or sp.secrets_stored is not False
        or sp.inventory_mutated is not False
        or sp.live_dispatch_authorized is not False
        or sp.remote_fetched is not False
        or sp.live_router_authorized is not False
        or sp.twin_written is not False
        or sp.merge_executed is not False
        or sp.draft_written is not False
        or sp.remote_index_queried is not False
        or sp.suite_rewritten is not False
        or sp.charge_executed is not False
        or sp.production_router_verdict != "REJECT"
    ):
        raise HtmlNativeSettingsMarketplaceFreeCompetitionDrNdComposeError(
            "invariant: honesty flags must remain false / REJECT"
        )

    notes.extend(
        (
            "pdf_view_authorized=false",
            "pdf_primary=false",
            "store_mutated=false",
            "secrets_stored=false",
            "inventory_mutated=false",
            "purchase_executed=false",
            "hosted=false",
            "live_dispatch_authorized=false",
            "remote_fetched=false",
            "backlog_mutated=false",
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

    return HtmlNativeSettingsMarketplaceFreeCompetitionDrNdCompose(
        session_id=session,
        parent_asset_id=parent,
        asset_id=asset,
        title=title,
        account_id=account,
        week_id=week,
        html_view=hv,
        settings_pack=sp,
        session_aligned=session_aligned,
        parent_aligned=parent_aligned,
        pack_ready=pack_ready,
        pdf_view_authorized=False,
        pdf_primary=False,
        store_mutated=False,
        secrets_stored=False,
        inventory_mutated=False,
        purchase_executed=False,
        hosted=False,
        live_dispatch_authorized=False,
        remote_fetched=False,
        backlog_mutated=False,
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
            "html_native_settings_marketplace_free_competition_dr_nd_compose_advisory"
        ),
    )


def format_html_native_settings_marketplace_free_competition_dr_nd_summary(
    c: HtmlNativeSettingsMarketplaceFreeCompetitionDrNdCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"html_ready={c.html_view.pack_ready} · "
        f"settings_ready={c.settings_pack.pack_ready} · "
        f"session_aligned={c.session_aligned} · "
        f"parent_aligned={c.parent_aligned} · "
        f"verdict={c.production_router_verdict} · "
        "pdf_primary=false · purchase_executed=false · secrets_stored=false"
    )


__all__ = [
    "HtmlNativeSettingsMarketplaceFreeCompetitionDrNdCompose",
    "HtmlNativeSettingsMarketplaceFreeCompetitionDrNdComposeError",
    "compose_html_native_settings_marketplace_free_competition_dr_nd",
    "format_html_native_settings_marketplace_free_competition_dr_nd_summary",
]
