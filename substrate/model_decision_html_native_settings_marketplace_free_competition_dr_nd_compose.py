"""Model decision-tree + usage bar over HTML-native settings marketplace free competition (pure).

live_router_authorized / secrets_stored / live_meter_read always False.
pdf_primary / purchase_executed / hosted / inventory_mutated always False.
production_router_verdict always REJECT.
would_exceed=true blocks pack_ready under block_on_budget_exceed (default).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.html_native_settings_marketplace_free_competition_dr_nd_compose import (
    HtmlNativeSettingsMarketplaceFreeCompetitionDrNdCompose,
    HtmlNativeSettingsMarketplaceFreeCompetitionDrNdComposeError,
    compose_html_native_settings_marketplace_free_competition_dr_nd,
)
from substrate.settings_decision_tree_usage_bar_compose import (
    SettingsDecisionTreeUsageBarCompose,
    SettingsDecisionTreeUsageBarComposeError,
    compose_settings_decision_tree_usage_bar,
)


class ModelDecisionHtmlNativeSettingsMarketplaceFreeCompetitionDrNdComposeError(
    ValueError
):
    """Fail-closed validation for model decision + HTML-native settings pack."""


@dataclass(frozen=True)
class ModelDecisionHtmlNativeSettingsMarketplaceFreeCompetitionDrNdCompose:
    week_id: str
    session_id: str
    parent_asset_id: str
    asset_id: str
    title: str
    account_id: str
    focus_task: str | None
    decision: SettingsDecisionTreeUsageBarCompose
    html_native_pack: HtmlNativeSettingsMarketplaceFreeCompetitionDrNdCompose
    pack_ready: bool
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
    live_dispatched: bool
    pack_dispatched: bool
    merge_executed: bool
    live_execution_authorized: bool
    charge_executed: bool
    draft_written: bool
    record_persisted: bool
    analysis_written: bool
    purchase_executed: bool
    hosted: bool
    remote_fetched: bool
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
            "focus_task": self.focus_task,
            "decision": self.decision.to_dict(),
            "html_native_pack": self.html_native_pack.to_dict(),
            "pack_ready": self.pack_ready,
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
            "live_dispatched": False,
            "pack_dispatched": False,
            "merge_executed": False,
            "live_execution_authorized": False,
            "charge_executed": False,
            "draft_written": False,
            "record_persisted": False,
            "analysis_written": False,
            "purchase_executed": False,
            "hosted": False,
            "remote_fetched": False,
            "production_router_verdict": "REJECT",
            "notes": list(self.notes),
            "authority": (
                "model_decision_html_native_settings_marketplace_free_competition_dr_nd_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ModelDecisionHtmlNativeSettingsMarketplaceFreeCompetitionDrNdComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_model_decision_html_native_settings_marketplace_free_competition_dr_nd(
    *,
    decision: object,
    html_native_pack: object,
    operator_ack: object,
    require_both: object | None = None,
    block_on_budget_exceed: object | None = None,
) -> ModelDecisionHtmlNativeSettingsMarketplaceFreeCompetitionDrNdCompose:
    """Model decision + HTML-native settings marketplace free competition. Never live-routes."""
    if not isinstance(operator_ack, bool):
        raise ModelDecisionHtmlNativeSettingsMarketplaceFreeCompetitionDrNdComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(decision, dict):
        raise ModelDecisionHtmlNativeSettingsMarketplaceFreeCompetitionDrNdComposeError(
            "decision must be an object"
        )
    if not isinstance(html_native_pack, dict):
        raise ModelDecisionHtmlNativeSettingsMarketplaceFreeCompetitionDrNdComposeError(
            "html_native_pack must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise ModelDecisionHtmlNativeSettingsMarketplaceFreeCompetitionDrNdComposeError(
            "require_both must be boolean when set"
        )
    block_budget = (
        True if block_on_budget_exceed is None else block_on_budget_exceed
    )
    if not isinstance(block_budget, bool):
        raise ModelDecisionHtmlNativeSettingsMarketplaceFreeCompetitionDrNdComposeError(
            "block_on_budget_exceed must be boolean when set"
        )

    notes: list[str] = [
        "live_router_authorized=false · secrets_stored=false · live_meter_read=false",
        "pdf_primary=false · purchase_executed=false · inventory_mutated=false",
        "production_router_verdict=REJECT",
    ]

    try:
        dec = compose_settings_decision_tree_usage_bar(
            selected_model_id=decision.get("selected_model_id"),
            models=decision.get("models"),
            daily_cap_usd=decision.get("daily_cap_usd"),
            spent_usd=decision.get("spent_usd"),
            operator_ack=operator_ack,
            projected_cost_usd_high=decision.get("projected_cost_usd_high"),
            projected_cost_usd_low=decision.get("projected_cost_usd_low"),
            bench_bests=decision.get("bench_bests"),
            focus_task=decision.get("focus_task"),
            nd_shadow=decision.get("nd_shadow"),
            pending_add_model_ids=decision.get("pending_add_model_ids"),
        )
    except SettingsDecisionTreeUsageBarComposeError as e:
        raise ModelDecisionHtmlNativeSettingsMarketplaceFreeCompetitionDrNdComposeError(
            str(e)
        ) from e
    notes.extend(f"[decision] {n}" for n in dec.notes)

    try:
        hnp = compose_html_native_settings_marketplace_free_competition_dr_nd(
            html_view=html_native_pack.get("html_view"),
            settings_pack=html_native_pack.get("settings_pack"),
            operator_ack=operator_ack,
            require_both=html_native_pack.get("require_both"),
        )
    except HtmlNativeSettingsMarketplaceFreeCompetitionDrNdComposeError as e:
        raise ModelDecisionHtmlNativeSettingsMarketplaceFreeCompetitionDrNdComposeError(
            str(e)
        ) from e
    notes.extend(f"[html_native_pack] {n}" for n in hnp.notes)

    week = _require_nonempty(hnp.week_id, field="week_id")
    session = _require_nonempty(hnp.session_id, field="session_id")
    asset = _require_nonempty(hnp.asset_id, field="asset_id")
    parent = _require_nonempty(hnp.parent_asset_id, field="parent_asset_id")
    title = _require_nonempty(hnp.title, field="title")
    account = _require_nonempty(hnp.account_id, field="account_id")

    focus_raw = decision.get("focus_task")
    focus_task: str | None = None
    if isinstance(focus_raw, str) and focus_raw.strip():
        focus_task = focus_raw.strip()

    budget_ok = (not block_budget) or (dec.would_exceed is not True)
    if not budget_ok:
        notes.append(
            "would_exceed=true — pack_ready blocked by budget projection gate"
        )

    if require:
        pack_ready = (
            dec.decision_ready is True
            and hnp.pack_ready is True
            and budget_ok
            and dec.live_router_authorized is False
            and dec.secrets_stored is False
            and dec.live_meter_read is False
            and hnp.production_router_verdict == "REJECT"
            and hnp.pdf_primary is False
            and hnp.pdf_view_authorized is False
            and hnp.secrets_stored is False
            and hnp.inventory_mutated is False
            and hnp.purchase_executed is False
            and hnp.hosted is False
            and hnp.live_dispatch_authorized is False
            and hnp.remote_fetched is False
            and hnp.live_router_authorized is False
            and hnp.twin_written is False
            and hnp.merge_executed is False
            and hnp.draft_written is False
            and hnp.remote_index_queried is False
            and hnp.suite_rewritten is False
            and hnp.charge_executed is False
            and operator_ack is True
        )
    else:
        pack_ready = (
            operator_ack is True
            and budget_ok
            and dec.live_router_authorized is False
            and hnp.production_router_verdict == "REJECT"
            and hnp.pdf_primary is False
            and hnp.purchase_executed is False
            and (dec.decision_ready is True or hnp.pack_ready is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — model decision + HTML-native settings marketplace "
            "free competition DR ND ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — decision, html_native_pack, budget, or operator_ack "
            "gate open"
        )

    if (
        dec.live_router_authorized is not False
        or dec.secrets_stored is not False
        or dec.live_meter_read is not False
        or hnp.pdf_primary is not False
        or hnp.pdf_view_authorized is not False
        or hnp.secrets_stored is not False
        or hnp.inventory_mutated is not False
        or hnp.purchase_executed is not False
        or hnp.hosted is not False
        or hnp.live_dispatch_authorized is not False
        or hnp.remote_fetched is not False
        or hnp.live_router_authorized is not False
        or hnp.twin_written is not False
        or hnp.merge_executed is not False
        or hnp.draft_written is not False
        or hnp.remote_index_queried is not False
        or hnp.suite_rewritten is not False
        or hnp.charge_executed is not False
        or hnp.production_router_verdict != "REJECT"
    ):
        raise ModelDecisionHtmlNativeSettingsMarketplaceFreeCompetitionDrNdComposeError(
            "invariant: honesty flags must remain false / REJECT"
        )

    notes.extend(
        (
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
            "live_dispatched=false",
            "pack_dispatched=false",
            "merge_executed=false",
            "live_execution_authorized=false",
            "charge_executed=false",
            "draft_written=false",
            "record_persisted=false",
            "analysis_written=false",
            "purchase_executed=false",
            "hosted=false",
            "remote_fetched=false",
            "production_router_verdict=REJECT",
        )
    )

    return ModelDecisionHtmlNativeSettingsMarketplaceFreeCompetitionDrNdCompose(
        week_id=week,
        session_id=session,
        parent_asset_id=parent,
        asset_id=asset,
        title=title,
        account_id=account,
        focus_task=focus_task,
        decision=dec,
        html_native_pack=hnp,
        pack_ready=pack_ready,
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
        live_dispatched=False,
        pack_dispatched=False,
        merge_executed=False,
        live_execution_authorized=False,
        charge_executed=False,
        draft_written=False,
        record_persisted=False,
        analysis_written=False,
        purchase_executed=False,
        hosted=False,
        remote_fetched=False,
        production_router_verdict="REJECT",
        notes=tuple(notes),
        authority=(
            "model_decision_html_native_settings_marketplace_free_competition_dr_nd_compose_advisory"
        ),
    )


def format_model_decision_html_native_settings_marketplace_free_competition_dr_nd_summary(
    c: ModelDecisionHtmlNativeSettingsMarketplaceFreeCompetitionDrNdCompose,
) -> str:
    budget = (
        "would_exceed=null"
        if c.decision.would_exceed is None
        else f"would_exceed={c.decision.would_exceed}"
    )
    task = c.focus_task if c.focus_task is not None else "null"
    return (
        f"pack_ready={c.pack_ready} · "
        f"decision_ready={c.decision.decision_ready} · "
        f"model={c.decision.driver.decision.selected_model_id} · "
        f"{budget} · "
        f"html_ready={c.html_native_pack.pack_ready} · "
        f"week={c.week_id} · task={task} · "
        f"verdict={c.production_router_verdict} · "
        "live_router_authorized=false · secrets_stored=false · "
        "pdf_primary=false"
    )


__all__ = [
    "ModelDecisionHtmlNativeSettingsMarketplaceFreeCompetitionDrNdCompose",
    "ModelDecisionHtmlNativeSettingsMarketplaceFreeCompetitionDrNdComposeError",
    "compose_model_decision_html_native_settings_marketplace_free_competition_dr_nd",
    "format_model_decision_html_native_settings_marketplace_free_competition_dr_nd_summary",
]
