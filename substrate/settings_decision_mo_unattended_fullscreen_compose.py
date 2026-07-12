"""Settings decision-tree usage bar over MO unattended fullscreen pack.

live_router_authorized / secrets_stored / live_meter_read always False.
live_execution_authorized / purchase_executed always False.
production_router_verdict always REJECT.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.mo_unattended_fullscreen_draft_collective_compose import (
    MoUnattendedFullscreenDraftCollectiveCompose,
    MoUnattendedFullscreenDraftCollectiveComposeError,
    compose_mo_unattended_fullscreen_draft_collective,
)
from substrate.settings_decision_tree_usage_bar_compose import (
    SettingsDecisionTreeUsageBarCompose,
    SettingsDecisionTreeUsageBarComposeError,
    compose_settings_decision_tree_usage_bar,
)


class SettingsDecisionMoUnattendedFullscreenComposeError(ValueError):
    """Fail-closed validation for settings decision + MO pack."""


@dataclass(frozen=True)
class SettingsDecisionMoUnattendedFullscreenCompose:
    session_id: str
    parent_asset_id: str
    title: str
    account_id: str
    week_id: str
    asset_id: str
    decision: SettingsDecisionTreeUsageBarCompose
    mo_pack: MoUnattendedFullscreenDraftCollectiveCompose
    pack_ready: bool
    live_router_authorized: bool
    secrets_stored: bool
    live_meter_read: bool
    live_execution_authorized: bool
    live_dispatched: bool
    pack_dispatched: bool
    merge_executed: bool
    draft_written: bool
    analysis_written: bool
    purchase_executed: bool
    charge_executed: bool
    hosted: bool
    pdf_view_authorized: bool
    pdf_primary: bool
    twin_written: bool
    prompts_injected: bool
    live_dispatch_authorized: bool
    remote_fetched: bool
    backlog_mutated: bool
    store_mutated: bool
    suite_rewritten: bool
    remote_index_queried: bool
    inventory_mutated: bool
    record_persisted: bool
    production_router_verdict: str
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "parent_asset_id": self.parent_asset_id,
            "title": self.title,
            "account_id": self.account_id,
            "week_id": self.week_id,
            "asset_id": self.asset_id,
            "decision": self.decision.to_dict(),
            "mo_pack": self.mo_pack.to_dict(),
            "pack_ready": self.pack_ready,
            "live_router_authorized": False,
            "secrets_stored": False,
            "live_meter_read": False,
            "live_execution_authorized": False,
            "live_dispatched": False,
            "pack_dispatched": False,
            "merge_executed": False,
            "draft_written": False,
            "analysis_written": False,
            "purchase_executed": False,
            "charge_executed": False,
            "hosted": False,
            "pdf_view_authorized": False,
            "pdf_primary": False,
            "twin_written": False,
            "prompts_injected": False,
            "live_dispatch_authorized": False,
            "remote_fetched": False,
            "backlog_mutated": False,
            "store_mutated": False,
            "suite_rewritten": False,
            "remote_index_queried": False,
            "inventory_mutated": False,
            "record_persisted": False,
            "production_router_verdict": "REJECT",
            "notes": list(self.notes),
            "authority": (
                "settings_decision_mo_unattended_fullscreen_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SettingsDecisionMoUnattendedFullscreenComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_settings_decision_mo_unattended_fullscreen(
    *,
    decision: object,
    mo_pack: object,
    operator_ack: object,
    require_both: object | None = None,
) -> SettingsDecisionMoUnattendedFullscreenCompose:
    """Settings decision + MO unattended fullscreen. Never live-routes."""
    if not isinstance(operator_ack, bool):
        raise SettingsDecisionMoUnattendedFullscreenComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(decision, dict):
        raise SettingsDecisionMoUnattendedFullscreenComposeError(
            "decision must be an object"
        )
    if not isinstance(mo_pack, dict):
        raise SettingsDecisionMoUnattendedFullscreenComposeError(
            "mo_pack must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise SettingsDecisionMoUnattendedFullscreenComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "live_router_authorized=false · secrets_stored=false · live_meter_read=false",
        "live_execution_authorized=false · purchase_executed=false",
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
        raise SettingsDecisionMoUnattendedFullscreenComposeError(
            str(e)
        ) from e
    notes.extend(f"[decision] {n}" for n in dec.notes)

    try:
        mo = compose_mo_unattended_fullscreen_draft_collective(
            mo=mo_pack.get("mo"),
            fullscreen_pack=mo_pack.get("fullscreen_pack"),
            operator_ack=operator_ack,
            require_both=mo_pack.get("require_both"),
        )
    except MoUnattendedFullscreenDraftCollectiveComposeError as e:
        raise SettingsDecisionMoUnattendedFullscreenComposeError(
            str(e)
        ) from e
    notes.extend(f"[mo_pack] {n}" for n in mo.notes)

    session = _require_nonempty(mo.session_id, field="session_id")
    parent = _require_nonempty(mo.parent_asset_id, field="parent_asset_id")
    title = _require_nonempty(mo.title, field="title")
    account = _require_nonempty(mo.account_id, field="account_id")
    week = _require_nonempty(mo.week_id, field="week_id")
    asset = _require_nonempty(mo.asset_id, field="asset_id")

    budget_ok = dec.would_exceed is not True

    if require:
        pack_ready = (
            budget_ok
            and dec.decision_ready is True
            and mo.pack_ready is True
            and dec.live_router_authorized is False
            and dec.secrets_stored is False
            and dec.live_meter_read is False
            and mo.live_execution_authorized is False
            and mo.live_dispatched is False
            and mo.merge_executed is False
            and mo.draft_written is False
            and mo.purchase_executed is False
            and mo.live_router_authorized is False
            and mo.production_router_verdict == "REJECT"
            and operator_ack is True
        )
    else:
        pack_ready = (
            operator_ack is True
            and dec.live_router_authorized is False
            and mo.live_execution_authorized is False
            and mo.purchase_executed is False
            and mo.production_router_verdict == "REJECT"
            and (dec.decision_ready is True or mo.pack_ready is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — settings decision + MO unattended fullscreen "
            "ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — decision, mo_pack, would_exceed, or "
            "operator_ack gate open"
        )

    if (
        dec.live_router_authorized is not False
        or dec.secrets_stored is not False
        or dec.live_meter_read is not False
        or mo.live_execution_authorized is not False
        or mo.live_dispatched is not False
        or mo.merge_executed is not False
        or mo.draft_written is not False
        or mo.purchase_executed is not False
        or mo.live_router_authorized is not False
        or mo.production_router_verdict != "REJECT"
    ):
        raise SettingsDecisionMoUnattendedFullscreenComposeError(
            "invariant: honesty flags must remain false / REJECT"
        )

    notes.extend(
        (
            "live_router_authorized=false",
            "secrets_stored=false",
            "live_meter_read=false",
            "live_execution_authorized=false",
            "live_dispatched=false",
            "pack_dispatched=false",
            "merge_executed=false",
            "draft_written=false",
            "analysis_written=false",
            "purchase_executed=false",
            "charge_executed=false",
            "hosted=false",
            "pdf_view_authorized=false",
            "pdf_primary=false",
            "twin_written=false",
            "prompts_injected=false",
            "live_dispatch_authorized=false",
            "remote_fetched=false",
            "backlog_mutated=false",
            "store_mutated=false",
            "suite_rewritten=false",
            "remote_index_queried=false",
            "inventory_mutated=false",
            "record_persisted=false",
            "production_router_verdict=REJECT",
        )
    )

    return SettingsDecisionMoUnattendedFullscreenCompose(
        session_id=session,
        parent_asset_id=parent,
        title=title,
        account_id=account,
        week_id=week,
        asset_id=asset,
        decision=dec,
        mo_pack=mo,
        pack_ready=pack_ready,
        live_router_authorized=False,
        secrets_stored=False,
        live_meter_read=False,
        live_execution_authorized=False,
        live_dispatched=False,
        pack_dispatched=False,
        merge_executed=False,
        draft_written=False,
        analysis_written=False,
        purchase_executed=False,
        charge_executed=False,
        hosted=False,
        pdf_view_authorized=False,
        pdf_primary=False,
        twin_written=False,
        prompts_injected=False,
        live_dispatch_authorized=False,
        remote_fetched=False,
        backlog_mutated=False,
        store_mutated=False,
        suite_rewritten=False,
        remote_index_queried=False,
        inventory_mutated=False,
        record_persisted=False,
        production_router_verdict="REJECT",
        notes=tuple(notes),
        authority=(
            "settings_decision_mo_unattended_fullscreen_compose_advisory"
        ),
    )


def format_settings_decision_mo_unattended_fullscreen_summary(
    c: SettingsDecisionMoUnattendedFullscreenCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"decision_ready={c.decision.decision_ready} · "
        f"usage_percent={c.decision.usage_percent} · "
        f"would_exceed={c.decision.would_exceed} · "
        f"mo_ready={c.mo_pack.pack_ready} · "
        f"verdict={c.production_router_verdict} · "
        f"live_router_authorized=false · live_execution_authorized=false"
    )


__all__ = [
    "SettingsDecisionMoUnattendedFullscreenCompose",
    "SettingsDecisionMoUnattendedFullscreenComposeError",
    "compose_settings_decision_mo_unattended_fullscreen",
    "format_settings_decision_mo_unattended_fullscreen_summary",
]
