"""Twin intelligent search over HTML-native marketplace free MO pack (pure).

remote_index_queried always False.
twin_written / purchase_executed / hosted always False.
pdf_view_authorized / pdf_primary always False.
production_router_verdict always REJECT.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.html_native_marketplace_free_midnight_oil_settings_compose import (
    HtmlNativeMarketplaceFreeMidnightOilSettingsCompose,
    HtmlNativeMarketplaceFreeMidnightOilSettingsComposeError,
    compose_html_native_marketplace_free_midnight_oil_settings,
)
from substrate.recursive_twin_intelligent_search import (
    TwinIntelligentSearchError,
    TwinSearchResult,
    search_twin_substrate,
)


class TwinSearchHtmlNativeMarketplaceFreeMoComposeError(ValueError):
    """Fail-closed validation for twin search + HTML-native marketplace free MO."""


@dataclass(frozen=True)
class TwinSearchHtmlNativeMarketplaceFreeMoCompose:
    week_id: str
    session_id: str
    parent_asset_id: str
    asset_id: str
    title: str
    account_id: str
    search: TwinSearchResult
    html_pack: HtmlNativeMarketplaceFreeMidnightOilSettingsCompose
    pack_ready: bool
    hit_count: int
    remote_index_queried: bool
    twin_written: bool
    prompts_injected: bool
    purchase_executed: bool
    hosted: bool
    pdf_view_authorized: bool
    pdf_primary: bool
    live_dispatch_authorized: bool
    live_execution_authorized: bool
    charge_executed: bool
    remote_fetched: bool
    backlog_mutated: bool
    store_mutated: bool
    suite_rewritten: bool
    secrets_stored: bool
    inventory_mutated: bool
    live_router_authorized: bool
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
            "week_id": self.week_id,
            "session_id": self.session_id,
            "parent_asset_id": self.parent_asset_id,
            "asset_id": self.asset_id,
            "title": self.title,
            "account_id": self.account_id,
            "search": self.search.to_dict(),
            "html_pack": self.html_pack.to_dict(),
            "pack_ready": self.pack_ready,
            "hit_count": self.hit_count,
            "remote_index_queried": False,
            "twin_written": False,
            "prompts_injected": False,
            "purchase_executed": False,
            "hosted": False,
            "pdf_view_authorized": False,
            "pdf_primary": False,
            "live_dispatch_authorized": False,
            "live_execution_authorized": False,
            "charge_executed": False,
            "remote_fetched": False,
            "backlog_mutated": False,
            "store_mutated": False,
            "suite_rewritten": False,
            "secrets_stored": False,
            "inventory_mutated": False,
            "live_router_authorized": False,
            "live_dispatched": False,
            "pack_dispatched": False,
            "merge_executed": False,
            "draft_written": False,
            "record_persisted": False,
            "analysis_written": False,
            "production_router_verdict": "REJECT",
            "notes": list(self.notes),
            "authority": (
                "twin_search_html_native_marketplace_free_mo_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TwinSearchHtmlNativeMarketplaceFreeMoComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_twin_search_html_native_marketplace_free_mo(
    *,
    search_query: object,
    twin_records: object,
    html_pack: object,
    operator_ack: object,
    search_limit: object | None = None,
    require_both: object | None = None,
) -> TwinSearchHtmlNativeMarketplaceFreeMoCompose:
    """Twin substrate search + HTML-native marketplace free MO. Never remote-indexes."""
    if not isinstance(operator_ack, bool):
        raise TwinSearchHtmlNativeMarketplaceFreeMoComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(html_pack, dict):
        raise TwinSearchHtmlNativeMarketplaceFreeMoComposeError(
            "html_pack must be an object"
        )
    if not isinstance(twin_records, list):
        raise TwinSearchHtmlNativeMarketplaceFreeMoComposeError(
            "twin_records must be an array"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise TwinSearchHtmlNativeMarketplaceFreeMoComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "remote_index_queried=false — pure substrate scan only",
        "twin_written=false · purchase_executed=false · hosted=false",
        "pdf_view_authorized=false · pdf_primary=false",
        "production_router_verdict=REJECT",
    ]

    try:
        search = search_twin_substrate(
            query=search_query,
            records=twin_records,
            limit=20 if search_limit is None else search_limit,
        )
    except TwinIntelligentSearchError as e:
        raise TwinSearchHtmlNativeMarketplaceFreeMoComposeError(str(e)) from e
    notes.extend(f"[search] {n}" for n in search.notes)

    try:
        hp = compose_html_native_marketplace_free_midnight_oil_settings(
            html_view=html_pack.get("html_view"),
            market_pack=html_pack.get("market_pack"),
            operator_ack=operator_ack,
            require_both=html_pack.get("require_both"),
        )
    except HtmlNativeMarketplaceFreeMidnightOilSettingsComposeError as e:
        raise TwinSearchHtmlNativeMarketplaceFreeMoComposeError(str(e)) from e
    notes.extend(f"[html_pack] {n}" for n in hp.notes)

    week = _require_nonempty(hp.week_id, field="week_id")
    session = _require_nonempty(hp.session_id, field="session_id")
    asset = _require_nonempty(hp.asset_id, field="asset_id")
    parent = _require_nonempty(hp.parent_asset_id, field="parent_asset_id")
    title = _require_nonempty(hp.title, field="title")
    account = _require_nonempty(hp.account_id, field="account_id")
    hit_count = len(search.hits)

    if require:
        pack_ready = (
            hit_count >= 1
            and hp.pack_ready is True
            and search.remote_index_queried is False
            and hp.pdf_view_authorized is False
            and hp.pdf_primary is False
            and hp.purchase_executed is False
            and hp.hosted is False
            and hp.twin_written is False
            and hp.live_execution_authorized is False
            and hp.charge_executed is False
            and hp.remote_fetched is False
            and hp.secrets_stored is False
            and hp.live_router_authorized is False
            and hp.production_router_verdict == "REJECT"
            and operator_ack is True
        )
    else:
        pack_ready = (
            operator_ack is True
            and search.remote_index_queried is False
            and hp.production_router_verdict == "REJECT"
            and hp.pdf_primary is False
            and hp.purchase_executed is False
            and (hit_count >= 1 or hp.pack_ready is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — twin search + HTML-native marketplace free MO "
            "ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — search hits, html_pack, or operator_ack gate open"
        )

    if (
        search.remote_index_queried is not False
        or hp.pdf_view_authorized is not False
        or hp.pdf_primary is not False
        or hp.purchase_executed is not False
        or hp.hosted is not False
        or hp.twin_written is not False
        or hp.live_execution_authorized is not False
        or hp.charge_executed is not False
        or hp.remote_fetched is not False
        or hp.secrets_stored is not False
        or hp.live_router_authorized is not False
        or hp.production_router_verdict != "REJECT"
    ):
        raise TwinSearchHtmlNativeMarketplaceFreeMoComposeError(
            "invariant: honesty flags must remain false / REJECT"
        )

    notes.extend(
        (
            "remote_index_queried=false",
            "twin_written=false",
            "prompts_injected=false",
            "purchase_executed=false",
            "hosted=false",
            "pdf_view_authorized=false",
            "pdf_primary=false",
            "live_dispatch_authorized=false",
            "live_execution_authorized=false",
            "charge_executed=false",
            "remote_fetched=false",
            "backlog_mutated=false",
            "store_mutated=false",
            "suite_rewritten=false",
            "secrets_stored=false",
            "inventory_mutated=false",
            "live_router_authorized=false",
            "live_dispatched=false",
            "pack_dispatched=false",
            "merge_executed=false",
            "draft_written=false",
            "record_persisted=false",
            "analysis_written=false",
            "production_router_verdict=REJECT",
        )
    )

    return TwinSearchHtmlNativeMarketplaceFreeMoCompose(
        week_id=week,
        session_id=session,
        parent_asset_id=parent,
        asset_id=asset,
        title=title,
        account_id=account,
        search=search,
        html_pack=hp,
        pack_ready=pack_ready,
        hit_count=hit_count,
        remote_index_queried=False,
        twin_written=False,
        prompts_injected=False,
        purchase_executed=False,
        hosted=False,
        pdf_view_authorized=False,
        pdf_primary=False,
        live_dispatch_authorized=False,
        live_execution_authorized=False,
        charge_executed=False,
        remote_fetched=False,
        backlog_mutated=False,
        store_mutated=False,
        suite_rewritten=False,
        secrets_stored=False,
        inventory_mutated=False,
        live_router_authorized=False,
        live_dispatched=False,
        pack_dispatched=False,
        merge_executed=False,
        draft_written=False,
        record_persisted=False,
        analysis_written=False,
        production_router_verdict="REJECT",
        notes=tuple(notes),
        authority=(
            "twin_search_html_native_marketplace_free_mo_compose_advisory"
        ),
    )


def format_twin_search_html_native_marketplace_free_mo_summary(
    c: TwinSearchHtmlNativeMarketplaceFreeMoCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"hits={c.hit_count} · "
        f"html_ready={c.html_pack.pack_ready} · "
        f"query={c.search.query} · "
        f"verdict={c.production_router_verdict} · "
        "remote_index_queried=false · twin_written=false · purchase_executed=false"
    )


__all__ = [
    "TwinSearchHtmlNativeMarketplaceFreeMoCompose",
    "TwinSearchHtmlNativeMarketplaceFreeMoComposeError",
    "compose_twin_search_html_native_marketplace_free_mo",
    "format_twin_search_html_native_marketplace_free_mo_summary",
]
