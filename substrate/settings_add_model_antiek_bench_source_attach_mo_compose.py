"""Settings add-model inventory over Antiek-bench source-attach MO pack (pure).

secrets_stored / inventory_mutated always False.
live_router_authorized always False.
suite_rewritten / backlog_mutated / store_mutated always False.
remote_fetched / live_execution_authorized always False.
production_router_verdict always REJECT.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from substrate.antiek_bench_source_attach_settings_mo_compose import (
    AntiekBenchSourceAttachSettingsMoCompose,
    AntiekBenchSourceAttachSettingsMoComposeError,
    compose_antiek_bench_source_attach_settings_mo,
)
from substrate.settings_add_model_inventory_compose import (
    SettingsAddModelInventoryCompose,
    SettingsAddModelInventoryComposeError,
    compose_settings_add_model_inventory,
)

InventoryVsBench = Literal["agree", "disagree", "bench_none", "no_selection"]


class SettingsAddModelAntiekBenchSourceAttachMoComposeError(ValueError):
    """Fail-closed validation for settings add-model + Antiek-bench source MO."""


@dataclass(frozen=True)
class SettingsAddModelAntiekBenchSourceAttachMoCompose:
    week_id: str
    focus_task: str
    session_id: str
    parent_asset_id: str
    title: str
    account_id: str
    asset_id: str
    settings: SettingsAddModelInventoryCompose
    bench_pack: AntiekBenchSourceAttachSettingsMoCompose
    inventory_vs_bench: InventoryVsBench
    pack_ready: bool
    secrets_stored: bool
    inventory_mutated: bool
    live_router_authorized: bool
    live_meter_read: bool
    backlog_mutated: bool
    store_mutated: bool
    suite_rewritten: bool
    live_execution_authorized: bool
    charge_executed: bool
    remote_fetched: bool
    pdf_view_authorized: bool
    pdf_primary: bool
    remote_index_queried: bool
    twin_written: bool
    prompts_injected: bool
    live_dispatch_authorized: bool
    live_dispatched: bool
    pack_dispatched: bool
    merge_executed: bool
    draft_written: bool
    record_persisted: bool
    analysis_written: bool
    purchase_executed: bool
    hosted: bool
    production_router_verdict: str
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "week_id": self.week_id,
            "focus_task": self.focus_task,
            "session_id": self.session_id,
            "parent_asset_id": self.parent_asset_id,
            "title": self.title,
            "account_id": self.account_id,
            "asset_id": self.asset_id,
            "settings": self.settings.to_dict(),
            "bench_pack": self.bench_pack.to_dict(),
            "inventory_vs_bench": self.inventory_vs_bench,
            "pack_ready": self.pack_ready,
            "secrets_stored": False,
            "inventory_mutated": False,
            "live_router_authorized": False,
            "live_meter_read": False,
            "backlog_mutated": False,
            "store_mutated": False,
            "suite_rewritten": False,
            "live_execution_authorized": False,
            "charge_executed": False,
            "remote_fetched": False,
            "pdf_view_authorized": False,
            "pdf_primary": False,
            "remote_index_queried": False,
            "twin_written": False,
            "prompts_injected": False,
            "live_dispatch_authorized": False,
            "live_dispatched": False,
            "pack_dispatched": False,
            "merge_executed": False,
            "draft_written": False,
            "record_persisted": False,
            "analysis_written": False,
            "purchase_executed": False,
            "hosted": False,
            "production_router_verdict": "REJECT",
            "notes": list(self.notes),
            "authority": (
                "settings_add_model_antiek_bench_source_attach_mo_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SettingsAddModelAntiekBenchSourceAttachMoComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_settings_add_model_antiek_bench_source_attach_mo(
    *,
    settings: object,
    bench_pack: object,
    operator_ack: object,
    require_both: object | None = None,
) -> SettingsAddModelAntiekBenchSourceAttachMoCompose:
    """Settings add-model on Antiek-bench source-attach MO. Never mutates/routes."""
    if not isinstance(operator_ack, bool):
        raise SettingsAddModelAntiekBenchSourceAttachMoComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(settings, dict):
        raise SettingsAddModelAntiekBenchSourceAttachMoComposeError(
            "settings must be an object"
        )
    if not isinstance(bench_pack, dict):
        raise SettingsAddModelAntiekBenchSourceAttachMoComposeError(
            "bench_pack must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise SettingsAddModelAntiekBenchSourceAttachMoComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "secrets_stored=false — model ids only; never raw API keys",
        "inventory_mutated=false — propose_add is intent only",
        "live_router_authorized=false — operator selects model",
        "suite_rewritten=false · backlog_mutated=false · store_mutated=false",
        "remote_fetched=false · live_execution_authorized=false",
        "production_router_verdict=REJECT",
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
        raise SettingsAddModelAntiekBenchSourceAttachMoComposeError(
            str(e)
        ) from e
    notes.extend(f"[settings] {n}" for n in st.notes)

    try:
        bp = compose_antiek_bench_source_attach_settings_mo(
            bench=bench_pack.get("bench"),
            source_pack=bench_pack.get("source_pack"),
            operator_ack=operator_ack,
            require_both=bench_pack.get("require_both"),
        )
    except AntiekBenchSourceAttachSettingsMoComposeError as e:
        raise SettingsAddModelAntiekBenchSourceAttachMoComposeError(
            str(e)
        ) from e
    notes.extend(f"[bench_pack] {n}" for n in bp.notes)

    week = _require_nonempty(bp.week_id, field="week_id")
    focus = _require_nonempty(bp.focus_task, field="focus_task")
    session = _require_nonempty(bp.session_id, field="session_id")
    parent = _require_nonempty(bp.parent_asset_id, field="parent_asset_id")
    title = _require_nonempty(bp.title, field="title")
    account = _require_nonempty(bp.account_id, field="account_id")
    asset = _require_nonempty(bp.asset_id, field="asset_id")

    selected: str | None = None
    if st.decision_tree is not None:
        selected = st.decision_tree.driver.decision.selected_model_id
    elif settings.get("selected_model_id") is not None:
        raw = settings.get("selected_model_id")
        if isinstance(raw, str) and raw.strip():
            selected = raw.strip()

    rec = None
    if bp.bench.recommendation is not None:
        rec = bp.bench.recommendation.recommended_model_id

    inventory_vs_bench: InventoryVsBench
    if rec is None:
        inventory_vs_bench = "bench_none"
        notes.append(
            "inventory_vs_bench=bench_none — insufficient usage for task rec"
        )
    elif selected is None or not str(selected).strip():
        inventory_vs_bench = "no_selection"
        notes.append(
            "inventory_vs_bench=no_selection — no operator model selected"
        )
    elif str(selected).strip() == rec:
        inventory_vs_bench = "agree"
        notes.append(
            "inventory_vs_bench=agree — selection matches bench rec (still advisory)"
        )
    else:
        inventory_vs_bench = "disagree"
        notes.append(
            f"inventory_vs_bench=disagree — selected={str(selected).strip()} "
            f"rec={rec} (operator wins)"
        )

    if require:
        pack_ready = (
            st.pack_ready is True
            and bp.pack_ready is True
            and st.secrets_stored is False
            and st.inventory_mutated is False
            and st.live_router_authorized is False
            and bp.live_router_authorized is False
            and bp.suite_rewritten is False
            and bp.backlog_mutated is False
            and bp.store_mutated is False
            and bp.remote_fetched is False
            and bp.pdf_primary is False
            and bp.live_execution_authorized is False
            and bp.purchase_executed is False
            and bp.production_router_verdict == "REJECT"
            and operator_ack is True
        )
    else:
        pack_ready = (
            operator_ack is True
            and st.secrets_stored is False
            and st.inventory_mutated is False
            and bp.live_router_authorized is False
            and bp.remote_fetched is False
            and bp.production_router_verdict == "REJECT"
            and (st.pack_ready is True or bp.pack_ready is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — settings add-model + Antiek-bench source attach "
            "MO ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — settings, bench_pack, or operator_ack gate open"
        )

    if (
        st.secrets_stored is not False
        or st.inventory_mutated is not False
        or st.live_router_authorized is not False
        or bp.live_router_authorized is not False
        or bp.suite_rewritten is not False
        or bp.backlog_mutated is not False
        or bp.store_mutated is not False
        or bp.remote_fetched is not False
        or bp.pdf_primary is not False
        or bp.live_execution_authorized is not False
        or bp.purchase_executed is not False
        or bp.production_router_verdict != "REJECT"
    ):
        raise SettingsAddModelAntiekBenchSourceAttachMoComposeError(
            "invariant: honesty flags must remain false / REJECT"
        )

    notes.extend(
        (
            "secrets_stored=false",
            "inventory_mutated=false",
            "live_router_authorized=false",
            "live_meter_read=false",
            "backlog_mutated=false",
            "store_mutated=false",
            "suite_rewritten=false",
            "live_execution_authorized=false",
            "charge_executed=false",
            "remote_fetched=false",
            "pdf_view_authorized=false",
            "pdf_primary=false",
            "remote_index_queried=false",
            "twin_written=false",
            "prompts_injected=false",
            "live_dispatch_authorized=false",
            "live_dispatched=false",
            "pack_dispatched=false",
            "merge_executed=false",
            "draft_written=false",
            "record_persisted=false",
            "analysis_written=false",
            "purchase_executed=false",
            "hosted=false",
            "production_router_verdict=REJECT",
        )
    )

    return SettingsAddModelAntiekBenchSourceAttachMoCompose(
        week_id=week,
        focus_task=focus,
        session_id=session,
        parent_asset_id=parent,
        title=title,
        account_id=account,
        asset_id=asset,
        settings=st,
        bench_pack=bp,
        inventory_vs_bench=inventory_vs_bench,
        pack_ready=pack_ready,
        secrets_stored=False,
        inventory_mutated=False,
        live_router_authorized=False,
        live_meter_read=False,
        backlog_mutated=False,
        store_mutated=False,
        suite_rewritten=False,
        live_execution_authorized=False,
        charge_executed=False,
        remote_fetched=False,
        pdf_view_authorized=False,
        pdf_primary=False,
        remote_index_queried=False,
        twin_written=False,
        prompts_injected=False,
        live_dispatch_authorized=False,
        live_dispatched=False,
        pack_dispatched=False,
        merge_executed=False,
        draft_written=False,
        record_persisted=False,
        analysis_written=False,
        purchase_executed=False,
        hosted=False,
        production_router_verdict="REJECT",
        notes=tuple(notes),
        authority=(
            "settings_add_model_antiek_bench_source_attach_mo_compose_advisory"
        ),
    )


def format_settings_add_model_antiek_bench_source_attach_mo_summary(
    c: SettingsAddModelAntiekBenchSourceAttachMoCompose,
) -> str:
    rec = (
        c.bench_pack.bench.recommendation.recommended_model_id
        if c.bench_pack.bench.recommendation is not None
        else "null"
    )
    return (
        f"pack_ready={c.pack_ready} · "
        f"action={c.settings.action} · "
        f"proposed_new={c.settings.proposed_new_count} · "
        f"bench_ready={c.bench_pack.pack_ready} · "
        f"rec={rec} · "
        f"vs={c.inventory_vs_bench} · "
        f"week={c.week_id} · task={c.focus_task} · "
        f"verdict={c.production_router_verdict} · "
        "secrets_stored=false · inventory_mutated=false · "
        "live_router_authorized=false · suite_rewritten=false"
    )


__all__ = [
    "SettingsAddModelAntiekBenchSourceAttachMoCompose",
    "SettingsAddModelAntiekBenchSourceAttachMoComposeError",
    "compose_settings_add_model_antiek_bench_source_attach_mo",
    "format_settings_add_model_antiek_bench_source_attach_mo_summary",
]
