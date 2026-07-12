"""Floating multi-select over model decision + twin search free settings (pure).

live_dispatched / pack_dispatched / merge_executed always False.
live_router_authorized / secrets_stored / live_meter_read always False.
remote_index_queried / suite_rewritten / pdf_primary always False.
production_router_verdict always REJECT.
would_exceed on nested decision blocks pack_ready under require_both.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.floating_multi_select_collective_cohesive_compose import (
    FloatingMultiSelectCollectiveCohesiveCompose,
    FloatingMultiSelectCollectiveCohesiveComposeError,
    compose_floating_multi_select_collective_cohesive,
)
from substrate.model_decision_twin_search_html_native_marketplace_free_settings_compose import (
    ModelDecisionTwinSearchHtmlNativeMarketplaceFreeSettingsCompose,
    ModelDecisionTwinSearchHtmlNativeMarketplaceFreeSettingsComposeError,
    compose_model_decision_twin_search_html_native_marketplace_free_settings,
)


class FloatingMultiselectModelDecisionTwinSearchFreeSettingsComposeError(ValueError):
    """Fail-closed validation for multi-select + model decision free settings pack."""


@dataclass(frozen=True)
class FloatingMultiselectModelDecisionTwinSearchFreeSettingsCompose:
    session_id: str
    parent_asset_id: str
    week_id: str
    asset_id: str
    title: str
    account_id: str
    multiselect: FloatingMultiSelectCollectiveCohesiveCompose
    decision_pack: ModelDecisionTwinSearchHtmlNativeMarketplaceFreeSettingsCompose
    session_aligned: bool
    parent_aligned: bool
    pack_ready: bool
    live_dispatched: bool
    pack_dispatched: bool
    merge_executed: bool
    analysis_written: bool
    live_router_authorized: bool
    secrets_stored: bool
    live_meter_read: bool
    remote_index_queried: bool
    backlog_mutated: bool
    store_mutated: bool
    suite_rewritten: bool
    pdf_view_authorized: bool
    pdf_primary: bool
    twin_written: bool
    prompts_injected: bool
    live_dispatch_authorized: bool
    inventory_mutated: bool
    live_execution_authorized: bool
    charge_executed: bool
    draft_written: bool
    record_persisted: bool
    purchase_executed: bool
    hosted: bool
    remote_fetched: bool
    production_router_verdict: str
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "parent_asset_id": self.parent_asset_id,
            "week_id": self.week_id,
            "asset_id": self.asset_id,
            "title": self.title,
            "account_id": self.account_id,
            "multiselect": self.multiselect.to_dict(),
            "decision_pack": self.decision_pack.to_dict(),
            "session_aligned": self.session_aligned,
            "parent_aligned": self.parent_aligned,
            "pack_ready": self.pack_ready,
            "live_dispatched": False,
            "pack_dispatched": False,
            "merge_executed": False,
            "analysis_written": False,
            "live_router_authorized": False,
            "secrets_stored": False,
            "live_meter_read": False,
            "remote_index_queried": False,
            "backlog_mutated": False,
            "store_mutated": False,
            "suite_rewritten": False,
            "pdf_view_authorized": False,
            "pdf_primary": False,
            "twin_written": False,
            "prompts_injected": False,
            "live_dispatch_authorized": False,
            "inventory_mutated": False,
            "live_execution_authorized": False,
            "charge_executed": False,
            "draft_written": False,
            "record_persisted": False,
            "purchase_executed": False,
            "hosted": False,
            "remote_fetched": False,
            "production_router_verdict": "REJECT",
            "notes": list(self.notes),
            "authority": (
                "floating_multiselect_model_decision_twin_search_free_settings_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FloatingMultiselectModelDecisionTwinSearchFreeSettingsComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_floating_multiselect_model_decision_twin_search_free_settings(
    *,
    multiselect: object,
    decision_pack: object,
    operator_ack: object,
    require_both: object | None = None,
) -> FloatingMultiselectModelDecisionTwinSearchFreeSettingsCompose:
    """Multi-select cohesive + model decision free settings. Never dispatches."""
    if not isinstance(operator_ack, bool):
        raise FloatingMultiselectModelDecisionTwinSearchFreeSettingsComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(multiselect, dict):
        raise FloatingMultiselectModelDecisionTwinSearchFreeSettingsComposeError(
            "multiselect must be an object"
        )
    if not isinstance(decision_pack, dict):
        raise FloatingMultiselectModelDecisionTwinSearchFreeSettingsComposeError(
            "decision_pack must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise FloatingMultiselectModelDecisionTwinSearchFreeSettingsComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "live_dispatched=false · pack_dispatched=false · merge_executed=false",
        "live_router_authorized=false · secrets_stored=false · live_meter_read=false",
        "remote_index_queried=false · suite_rewritten=false · pdf_primary=false",
        "production_router_verdict=REJECT",
    ]

    try:
        ms = compose_floating_multi_select_collective_cohesive(
            session_id=multiselect.get("session_id"),
            parent_asset_id=multiselect.get("parent_asset_id"),
            members=multiselect.get("members"),
            selected_instance_ids=multiselect.get("selected_instance_ids"),
            pack_mode=multiselect.get("pack_mode"),
            cohesive_prompt=multiselect.get("cohesive_prompt"),
            operator_ack=operator_ack,
            extra_context=multiselect.get("extra_context"),
            analysis_kind=multiselect.get("analysis_kind"),
            extra_findings=multiselect.get("extra_findings"),
        )
    except FloatingMultiSelectCollectiveCohesiveComposeError as e:
        raise FloatingMultiselectModelDecisionTwinSearchFreeSettingsComposeError(
            str(e)
        ) from e
    notes.extend(f"[multiselect] {n}" for n in ms.notes)

    try:
        dp = compose_model_decision_twin_search_html_native_marketplace_free_settings(
            decision=decision_pack.get("decision"),
            twin_search_pack=decision_pack.get("twin_search_pack"),
            operator_ack=operator_ack,
            require_both=decision_pack.get("require_both"),
            block_on_budget_exceed=decision_pack.get("block_on_budget_exceed"),
        )
    except ModelDecisionTwinSearchHtmlNativeMarketplaceFreeSettingsComposeError as e:
        raise FloatingMultiselectModelDecisionTwinSearchFreeSettingsComposeError(
            str(e)
        ) from e
    notes.extend(f"[decision_pack] {n}" for n in dp.notes)

    session = _require_nonempty(ms.session_id, field="session_id")
    parent = _require_nonempty(ms.parent_asset_id, field="parent_asset_id")
    week = _require_nonempty(dp.week_id, field="week_id")
    asset = _require_nonempty(dp.asset_id, field="asset_id")
    title = _require_nonempty(dp.title, field="title")
    account = _require_nonempty(dp.account_id, field="account_id")

    session_aligned = dp.session_id == session
    parent_aligned = (
        dp.parent_asset_id == parent or dp.asset_id == parent
    )
    if not session_aligned:
        notes.append(
            "session_id mismatch between multiselect and decision_pack — pack_ready blocked"
        )
    if not parent_aligned:
        notes.append(
            "parent_asset_id mismatch between multiselect and decision_pack — pack_ready blocked"
        )

    if require:
        pack_ready = (
            session_aligned
            and parent_aligned
            and ms.pack_ready is True
            and dp.pack_ready is True
            and dp.production_router_verdict == "REJECT"
            and dp.decision.would_exceed is not True
            and dp.live_router_authorized is False
            and dp.secrets_stored is False
            and dp.live_meter_read is False
            and dp.remote_index_queried is False
            and dp.pdf_primary is False
            and ms.live_dispatched is False
            and ms.pack_dispatched is False
            and ms.merge_executed is False
            and operator_ack is True
        )
    else:
        pack_ready = (
            session_aligned
            and parent_aligned
            and operator_ack is True
            and dp.production_router_verdict == "REJECT"
            and dp.pdf_primary is False
            and (ms.pack_ready is True or dp.pack_ready is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — floating multi-select + model decision twin search "
            "free settings ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — multiselect, decision_pack, alignment, budget, "
            "or operator_ack gate open"
        )

    if (
        ms.live_dispatched is not False
        or ms.pack_dispatched is not False
        or ms.merge_executed is not False
        or dp.live_router_authorized is not False
        or dp.secrets_stored is not False
        or dp.live_meter_read is not False
        or dp.remote_index_queried is not False
        or dp.pdf_primary is not False
        or dp.production_router_verdict != "REJECT"
    ):
        raise FloatingMultiselectModelDecisionTwinSearchFreeSettingsComposeError(
            "invariant: honesty flags must remain false / REJECT"
        )

    notes.extend(
        (
            "live_dispatched=false",
            "pack_dispatched=false",
            "merge_executed=false",
            "analysis_written=false",
            "live_router_authorized=false",
            "secrets_stored=false",
            "live_meter_read=false",
            "remote_index_queried=false",
            "backlog_mutated=false",
            "store_mutated=false",
            "suite_rewritten=false",
            "pdf_view_authorized=false",
            "pdf_primary=false",
            "twin_written=false",
            "prompts_injected=false",
            "live_dispatch_authorized=false",
            "inventory_mutated=false",
            "live_execution_authorized=false",
            "charge_executed=false",
            "draft_written=false",
            "record_persisted=false",
            "purchase_executed=false",
            "hosted=false",
            "remote_fetched=false",
            "production_router_verdict=REJECT",
        )
    )

    return FloatingMultiselectModelDecisionTwinSearchFreeSettingsCompose(
        session_id=session,
        parent_asset_id=parent,
        week_id=week,
        asset_id=asset,
        title=title,
        account_id=account,
        multiselect=ms,
        decision_pack=dp,
        session_aligned=session_aligned,
        parent_aligned=parent_aligned,
        pack_ready=pack_ready,
        live_dispatched=False,
        pack_dispatched=False,
        merge_executed=False,
        analysis_written=False,
        live_router_authorized=False,
        secrets_stored=False,
        live_meter_read=False,
        remote_index_queried=False,
        backlog_mutated=False,
        store_mutated=False,
        suite_rewritten=False,
        pdf_view_authorized=False,
        pdf_primary=False,
        twin_written=False,
        prompts_injected=False,
        live_dispatch_authorized=False,
        inventory_mutated=False,
        live_execution_authorized=False,
        charge_executed=False,
        draft_written=False,
        record_persisted=False,
        purchase_executed=False,
        hosted=False,
        remote_fetched=False,
        production_router_verdict="REJECT",
        notes=tuple(notes),
        authority=(
            "floating_multiselect_model_decision_twin_search_free_settings_compose_advisory"
        ),
    )


def format_floating_multiselect_model_decision_twin_search_free_settings_summary(
    c: FloatingMultiselectModelDecisionTwinSearchFreeSettingsCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"multiselect_ready={c.multiselect.pack_ready} · "
        f"decision_ready={c.decision_pack.pack_ready} · "
        f"session_aligned={c.session_aligned} · "
        f"parent_aligned={c.parent_aligned} · "
        f"verdict={c.production_router_verdict} · "
        "live_dispatched=false · pack_dispatched=false · live_router_authorized=false"
    )


__all__ = [
    "FloatingMultiselectModelDecisionTwinSearchFreeSettingsCompose",
    "FloatingMultiselectModelDecisionTwinSearchFreeSettingsComposeError",
    "compose_floating_multiselect_model_decision_twin_search_free_settings",
    "format_floating_multiselect_model_decision_twin_search_free_settings_summary",
]
