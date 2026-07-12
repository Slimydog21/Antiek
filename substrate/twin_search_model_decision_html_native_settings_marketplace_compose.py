"""Twin intelligent search over model decision HTML-native settings marketplace (pure).

remote_index_queried always False.
live_router_authorized / secrets_stored / live_meter_read always False.
pdf_primary / purchase_executed / hosted / twin_written always False.
production_router_verdict always REJECT.
require_both (default) needs ≥1 search hit AND model_decision_pack.pack_ready.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.model_decision_html_native_settings_marketplace_free_competition_dr_nd_compose import (
    ModelDecisionHtmlNativeSettingsMarketplaceFreeCompetitionDrNdCompose,
    ModelDecisionHtmlNativeSettingsMarketplaceFreeCompetitionDrNdComposeError,
    compose_model_decision_html_native_settings_marketplace_free_competition_dr_nd,
)
from substrate.recursive_twin_intelligent_search import (
    TwinIntelligentSearchError,
    TwinSearchResult,
    search_twin_substrate,
)


class TwinSearchModelDecisionHtmlNativeSettingsMarketplaceComposeError(ValueError):
    """Fail-closed validation for twin search + model decision HTML-native pack."""


@dataclass(frozen=True)
class TwinSearchModelDecisionHtmlNativeSettingsMarketplaceCompose:
    session_id: str
    parent_asset_id: str
    asset_id: str
    title: str
    account_id: str
    week_id: str
    search: TwinSearchResult
    model_decision_pack: ModelDecisionHtmlNativeSettingsMarketplaceFreeCompetitionDrNdCompose
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
    live_meter_read: bool
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
            "search": self.search.to_dict(),
            "model_decision_pack": self.model_decision_pack.to_dict(),
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
            "live_meter_read": False,
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
                "twin_search_model_decision_html_native_settings_marketplace_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TwinSearchModelDecisionHtmlNativeSettingsMarketplaceComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_twin_search_model_decision_html_native_settings_marketplace(
    *,
    search_query: object,
    twin_records: object,
    model_decision_pack: object,
    operator_ack: object,
    search_limit: object | None = None,
    require_both: object | None = None,
) -> TwinSearchModelDecisionHtmlNativeSettingsMarketplaceCompose:
    """Twin search + model decision HTML-native settings marketplace. Never remote-indexes."""
    if not isinstance(operator_ack, bool):
        raise TwinSearchModelDecisionHtmlNativeSettingsMarketplaceComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(model_decision_pack, dict):
        raise TwinSearchModelDecisionHtmlNativeSettingsMarketplaceComposeError(
            "model_decision_pack must be an object"
        )
    if not isinstance(twin_records, list):
        raise TwinSearchModelDecisionHtmlNativeSettingsMarketplaceComposeError(
            "twin_records must be an array"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise TwinSearchModelDecisionHtmlNativeSettingsMarketplaceComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "remote_index_queried=false — pure substrate scan only",
        "live_router_authorized=false · secrets_stored=false · live_meter_read=false",
        "pdf_primary=false · twin_written=false · purchase_executed=false",
        "production_router_verdict=REJECT",
    ]

    try:
        search = search_twin_substrate(
            query=search_query,
            records=twin_records,
            limit=20 if search_limit is None else search_limit,
        )
    except TwinIntelligentSearchError as e:
        raise TwinSearchModelDecisionHtmlNativeSettingsMarketplaceComposeError(
            str(e)
        ) from e
    notes.extend(f"[search] {n}" for n in search.notes)

    try:
        mdp = compose_model_decision_html_native_settings_marketplace_free_competition_dr_nd(
            decision=model_decision_pack.get("decision"),
            html_native_pack=model_decision_pack.get("html_native_pack"),
            operator_ack=operator_ack,
            require_both=model_decision_pack.get("require_both"),
            block_on_budget_exceed=model_decision_pack.get(
                "block_on_budget_exceed"
            ),
        )
    except ModelDecisionHtmlNativeSettingsMarketplaceFreeCompetitionDrNdComposeError as e:
        raise TwinSearchModelDecisionHtmlNativeSettingsMarketplaceComposeError(
            str(e)
        ) from e
    notes.extend(f"[model_decision_pack] {n}" for n in mdp.notes)

    session = _require_nonempty(mdp.session_id, field="session_id")
    parent = _require_nonempty(mdp.parent_asset_id, field="parent_asset_id")
    asset = _require_nonempty(mdp.asset_id, field="asset_id")
    title = _require_nonempty(mdp.title, field="title")
    account = _require_nonempty(mdp.account_id, field="account_id")
    week = _require_nonempty(mdp.week_id, field="week_id")
    hit_count = len(search.hits)

    if require:
        pack_ready = (
            hit_count >= 1
            and mdp.pack_ready is True
            and search.remote_index_queried is False
            and mdp.live_router_authorized is False
            and mdp.secrets_stored is False
            and mdp.live_meter_read is False
            and mdp.pdf_view_authorized is False
            and mdp.pdf_primary is False
            and mdp.twin_written is False
            and mdp.purchase_executed is False
            and mdp.hosted is False
            and mdp.inventory_mutated is False
            and mdp.remote_index_queried is False
            and mdp.suite_rewritten is False
            and mdp.charge_executed is False
            and mdp.production_router_verdict == "REJECT"
            and operator_ack is True
        )
    else:
        pack_ready = (
            operator_ack is True
            and search.remote_index_queried is False
            and mdp.live_router_authorized is False
            and mdp.pdf_primary is False
            and mdp.twin_written is False
            and mdp.purchase_executed is False
            and mdp.production_router_verdict == "REJECT"
            and (hit_count >= 1 or mdp.pack_ready is True)
        )

    if hit_count < 1 and require:
        notes.append(
            "zero search hits — pack_ready blocked under require_both (≥1 hit gate)"
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — twin search + model decision HTML-native settings "
            "marketplace ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — search hits, model_decision_pack, or operator_ack "
            "gate open"
        )

    if (
        search.remote_index_queried is not False
        or mdp.live_router_authorized is not False
        or mdp.secrets_stored is not False
        or mdp.live_meter_read is not False
        or mdp.pdf_view_authorized is not False
        or mdp.pdf_primary is not False
        or mdp.twin_written is not False
        or mdp.purchase_executed is not False
        or mdp.hosted is not False
        or mdp.inventory_mutated is not False
        or mdp.remote_index_queried is not False
        or mdp.suite_rewritten is not False
        or mdp.charge_executed is not False
        or mdp.production_router_verdict != "REJECT"
    ):
        raise TwinSearchModelDecisionHtmlNativeSettingsMarketplaceComposeError(
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
            "live_meter_read=false",
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

    return TwinSearchModelDecisionHtmlNativeSettingsMarketplaceCompose(
        session_id=session,
        parent_asset_id=parent,
        asset_id=asset,
        title=title,
        account_id=account,
        week_id=week,
        search=search,
        model_decision_pack=mdp,
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
        live_meter_read=False,
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
            "twin_search_model_decision_html_native_settings_marketplace_compose_advisory"
        ),
    )


def format_twin_search_model_decision_html_native_settings_marketplace_summary(
    c: TwinSearchModelDecisionHtmlNativeSettingsMarketplaceCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"hits={c.hit_count} · "
        f"decision_ready={c.model_decision_pack.decision.decision_ready} · "
        f"week={c.week_id} · "
        f"verdict={c.production_router_verdict} · "
        "remote_index_queried=false · pdf_primary=false · twin_written=false"
    )


__all__ = [
    "TwinSearchModelDecisionHtmlNativeSettingsMarketplaceCompose",
    "TwinSearchModelDecisionHtmlNativeSettingsMarketplaceComposeError",
    "compose_twin_search_model_decision_html_native_settings_marketplace",
    "format_twin_search_model_decision_html_native_settings_marketplace_summary",
]
