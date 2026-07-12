"""Twin intelligent search over HTML-native recursive twin marketplace free (pure).

remote_index_queried always False.
pdf_view_authorized / pdf_primary always False.
twin_written / purchase_executed / hosted always False.
secrets_stored / inventory_mutated / live_router_authorized always False.
production_router_verdict always REJECT.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.html_native_recursive_twin_marketplace_free_compose import (
    HtmlNativeRecursiveTwinMarketplaceFreeCompose,
    HtmlNativeRecursiveTwinMarketplaceFreeComposeError,
    compose_html_native_recursive_twin_marketplace_free,
)
from substrate.recursive_twin_intelligent_search import (
    TwinIntelligentSearchError,
    TwinSearchResult,
    search_twin_substrate,
)


class TwinSearchHtmlNativeRecursiveTwinMarketplaceComposeError(ValueError):
    """Fail-closed validation for twin search + HTML-native marketplace pack."""


@dataclass(frozen=True)
class TwinSearchHtmlNativeRecursiveTwinMarketplaceCompose:
    session_id: str
    parent_asset_id: str
    asset_id: str
    title: str
    account_id: str
    week_id: str
    focus_task: str
    search: TwinSearchResult
    html_pack: HtmlNativeRecursiveTwinMarketplaceFreeCompose
    hit_count: int
    pack_ready: bool
    remote_index_queried: bool
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
            "focus_task": self.focus_task,
            "search": self.search.to_dict(),
            "html_pack": self.html_pack.to_dict(),
            "hit_count": self.hit_count,
            "pack_ready": self.pack_ready,
            "remote_index_queried": False,
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
            "live_dispatched": False,
            "pack_dispatched": False,
            "merge_executed": False,
            "draft_written": False,
            "record_persisted": False,
            "analysis_written": False,
            "production_router_verdict": "REJECT",
            "notes": list(self.notes),
            "authority": (
                "twin_search_html_native_recursive_twin_marketplace_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TwinSearchHtmlNativeRecursiveTwinMarketplaceComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_twin_search_html_native_recursive_twin_marketplace(
    *,
    search_query: object,
    twin_records: object,
    html_pack: object,
    operator_ack: object,
    search_limit: object | None = None,
    require_both: object | None = None,
) -> TwinSearchHtmlNativeRecursiveTwinMarketplaceCompose:
    """Twin search + HTML-native recursive twin marketplace. Never remote-indexes."""
    if not isinstance(operator_ack, bool):
        raise TwinSearchHtmlNativeRecursiveTwinMarketplaceComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(html_pack, dict):
        raise TwinSearchHtmlNativeRecursiveTwinMarketplaceComposeError(
            "html_pack must be an object"
        )
    if not isinstance(twin_records, list):
        raise TwinSearchHtmlNativeRecursiveTwinMarketplaceComposeError(
            "twin_records must be an array"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise TwinSearchHtmlNativeRecursiveTwinMarketplaceComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "remote_index_queried=false — pure substrate scan only",
        "pdf_view_authorized=false · pdf_primary=false · store_mutated=false",
        "twin_written=false · purchase_executed=false · hosted=false",
        "production_router_verdict=REJECT",
    ]

    try:
        search = search_twin_substrate(
            query=search_query,
            records=twin_records,
            limit=20 if search_limit is None else search_limit,
        )
    except TwinIntelligentSearchError as e:
        raise TwinSearchHtmlNativeRecursiveTwinMarketplaceComposeError(
            str(e)
        ) from e
    notes.extend(f"[search] {n}" for n in search.notes)

    try:
        hp = compose_html_native_recursive_twin_marketplace_free(
            html_view=html_pack.get("html_view"),
            twin_pack=html_pack.get("twin_pack"),
            operator_ack=operator_ack,
            require_both=html_pack.get("require_both"),
        )
    except HtmlNativeRecursiveTwinMarketplaceFreeComposeError as e:
        raise TwinSearchHtmlNativeRecursiveTwinMarketplaceComposeError(
            str(e)
        ) from e
    notes.extend(f"[html_pack] {n}" for n in hp.notes)

    session = _require_nonempty(hp.session_id, field="session_id")
    parent = _require_nonempty(hp.parent_asset_id, field="parent_asset_id")
    asset = _require_nonempty(hp.asset_id, field="asset_id")
    title = _require_nonempty(hp.title, field="title")
    account = _require_nonempty(hp.account_id, field="account_id")
    week = _require_nonempty(hp.week_id, field="week_id")
    focus = _require_nonempty(hp.focus_task, field="focus_task")
    hit_count = len(search.hits)

    if require:
        pack_ready = (
            hit_count >= 1
            and hp.pack_ready is True
            and search.remote_index_queried is False
            and hp.pdf_view_authorized is False
            and hp.pdf_primary is False
            and hp.store_mutated is False
            and hp.twin_written is False
            and hp.prompts_injected is False
            and hp.live_dispatch_authorized is False
            and hp.purchase_executed is False
            and hp.hosted is False
            and hp.remote_fetched is False
            and hp.inventory_mutated is False
            and hp.secrets_stored is False
            and hp.live_router_authorized is False
            and hp.suite_rewritten is False
            and hp.production_router_verdict == "REJECT"
            and operator_ack is True
        )
    else:
        pack_ready = (
            operator_ack is True
            and search.remote_index_queried is False
            and hp.pdf_view_authorized is False
            and hp.pdf_primary is False
            and hp.twin_written is False
            and hp.purchase_executed is False
            and hp.hosted is False
            and hp.production_router_verdict == "REJECT"
            and (hit_count >= 1 or hp.pack_ready is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — twin search + HTML-native recursive twin marketplace "
            "free ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — search hits, html_pack, or operator_ack gate open"
        )

    if (
        search.remote_index_queried is not False
        or hp.pdf_view_authorized is not False
        or hp.pdf_primary is not False
        or hp.store_mutated is not False
        or hp.twin_written is not False
        or hp.prompts_injected is not False
        or hp.live_dispatch_authorized is not False
        or hp.purchase_executed is not False
        or hp.hosted is not False
        or hp.remote_fetched is not False
        or hp.inventory_mutated is not False
        or hp.secrets_stored is not False
        or hp.live_router_authorized is not False
        or hp.suite_rewritten is not False
        or hp.production_router_verdict != "REJECT"
    ):
        raise TwinSearchHtmlNativeRecursiveTwinMarketplaceComposeError(
            "invariant: honesty flags must remain false / REJECT"
        )

    notes.extend(
        (
            "remote_index_queried=false",
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
            "live_dispatched=false",
            "pack_dispatched=false",
            "merge_executed=false",
            "draft_written=false",
            "record_persisted=false",
            "analysis_written=false",
            "production_router_verdict=REJECT",
        )
    )

    return TwinSearchHtmlNativeRecursiveTwinMarketplaceCompose(
        session_id=session,
        parent_asset_id=parent,
        asset_id=asset,
        title=title,
        account_id=account,
        week_id=week,
        focus_task=focus,
        search=search,
        html_pack=hp,
        hit_count=hit_count,
        pack_ready=pack_ready,
        remote_index_queried=False,
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
        live_dispatched=False,
        pack_dispatched=False,
        merge_executed=False,
        draft_written=False,
        record_persisted=False,
        analysis_written=False,
        production_router_verdict="REJECT",
        notes=tuple(notes),
        authority=(
            "twin_search_html_native_recursive_twin_marketplace_compose_advisory"
        ),
    )


def format_twin_search_html_native_recursive_twin_marketplace_summary(
    c: TwinSearchHtmlNativeRecursiveTwinMarketplaceCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"hits={c.hit_count} · "
        f"html_ready={c.html_pack.pack_ready} · "
        f"week={c.week_id} · task={c.focus_task} · "
        f"verdict={c.production_router_verdict} · "
        "remote_index_queried=false · pdf_view_authorized=false · "
        "twin_written=false · purchase_executed=false"
    )


__all__ = [
    "TwinSearchHtmlNativeRecursiveTwinMarketplaceCompose",
    "TwinSearchHtmlNativeRecursiveTwinMarketplaceComposeError",
    "compose_twin_search_html_native_recursive_twin_marketplace",
    "format_twin_search_html_native_recursive_twin_marketplace_summary",
]
