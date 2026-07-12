"""Floating DR highlight launch over workstation record model decision MO weekly src write pack (pure).

live_dispatched / merge_executed always False.
record_persisted / prompts_injected always False.
production_router_verdict always REJECT.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.highlight_deep_research_launch_compose import (
    HighlightDeepResearchLaunchCompose,
    HighlightDeepResearchLaunchComposeError,
    compose_highlight_deep_research_launch,
)
from substrate.workstation_record_model_decision_twin_search_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_m_pack_compose import (
    WorkstationRecordModelDecisionTwinSearchMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMPackCompose,
    WorkstationRecordModelDecisionTwinSearchMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMPackComposeError,
    compose_workstation_record_model_decision_twin_search_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_m_pack,
)


class FloatingDrWorkstationRecordModelDecisionMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMPackComposeError(ValueError):
    """Fail-closed validation for floating DR + workstation record model decision."""


@dataclass(frozen=True)
class FloatingDrWorkstationRecordModelDecisionMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMPackCompose:
    week_id: str
    session_id: str
    parent_asset_id: str
    asset_id: str
    title: str
    account_id: str
    highlight_launch: HighlightDeepResearchLaunchCompose
    record_pack: WorkstationRecordModelDecisionTwinSearchMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMPackCompose
    parent_aligned: bool
    pack_ready: bool
    live_dispatched: bool
    merge_executed: bool
    record_persisted: bool
    prompts_injected: bool
    live_router_authorized: bool
    secrets_stored: bool
    live_meter_read: bool
    remote_index_queried: bool
    twin_written: bool
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
    inventory_mutated: bool
    pack_dispatched: bool
    draft_written: bool
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
            "highlight_launch": self.highlight_launch.to_dict(),
            "record_pack": self.record_pack.to_dict(),
            "parent_aligned": self.parent_aligned,
            "pack_ready": self.pack_ready,
            "live_dispatched": False,
            "merge_executed": False,
            "record_persisted": False,
            "prompts_injected": False,
            "live_router_authorized": False,
            "secrets_stored": False,
            "live_meter_read": False,
            "remote_index_queried": False,
            "twin_written": False,
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
            "inventory_mutated": False,
            "pack_dispatched": False,
            "draft_written": False,
            "analysis_written": False,
            "production_router_verdict": "REJECT",
            "notes": list(self.notes),
            "authority": (
                "floating_dr_workstation_record_model_decision_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_m_pack_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FloatingDrWorkstationRecordModelDecisionMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMPackComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_floating_dr_workstation_record_model_decision_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_m_pack(
    *,
    highlight_launch: object,
    record_pack: object,
    operator_ack: object,
    require_both: object | None = None,
) -> FloatingDrWorkstationRecordModelDecisionMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMPackCompose:
    """Floating DR launch + workstation record model decision. Never dispatches/merges."""
    if not isinstance(operator_ack, bool):
        raise FloatingDrWorkstationRecordModelDecisionMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMPackComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(highlight_launch, dict):
        raise FloatingDrWorkstationRecordModelDecisionMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMPackComposeError(
            "highlight_launch must be an object"
        )
    if not isinstance(record_pack, dict):
        raise FloatingDrWorkstationRecordModelDecisionMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMPackComposeError(
            "record_pack must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise FloatingDrWorkstationRecordModelDecisionMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMPackComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "live_dispatched=false · merge_executed=false",
        "record_persisted=false · prompts_injected=false",
        "production_router_verdict=REJECT",
    ]

    try:
        hl = compose_highlight_deep_research_launch(
            parent_asset_id=highlight_launch.get("parent_asset_id"),
            highlight=highlight_launch.get("highlight"),
            gated=highlight_launch.get("gated"),
            would_exceed=highlight_launch.get("would_exceed"),
            operator_ack=operator_ack,
            prompt=highlight_launch.get("prompt"),
            preferred_view_mode=highlight_launch.get("preferred_view_mode"),
            operator_override=highlight_launch.get("operator_override"),
            selected_model_id=highlight_launch.get("selected_model_id"),
            source_families=highlight_launch.get("source_families"),
        )
    except HighlightDeepResearchLaunchComposeError as e:
        raise FloatingDrWorkstationRecordModelDecisionMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMPackComposeError(str(e)) from e
    notes.extend(f"[highlight_launch] {n}" for n in hl.notes)

    try:
        rp = compose_workstation_record_model_decision_twin_search_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_m_pack(
            session_id=record_pack.get("session_id"),
            items=record_pack.get("items"),
            decision_pack=record_pack.get("decision_pack"),
            operator_ack=operator_ack,
            max_context_lines=record_pack.get("max_context_lines"),
            require_both=record_pack.get("require_both"),
        )
    except WorkstationRecordModelDecisionTwinSearchMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMPackComposeError as e:
        raise FloatingDrWorkstationRecordModelDecisionMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMPackComposeError(str(e)) from e
    notes.extend(f"[record_pack] {n}" for n in rp.notes)

    week = _require_nonempty(rp.week_id, field="week_id")
    session = _require_nonempty(rp.session_id, field="session_id")
    parent = _require_nonempty(rp.parent_asset_id, field="parent_asset_id")
    asset = _require_nonempty(rp.asset_id, field="asset_id")
    title = _require_nonempty(rp.title, field="title")
    account = _require_nonempty(rp.account_id, field="account_id")

    launch_parent = _require_nonempty(
        hl.instance.parent_asset_id, field="highlight_launch.instance.parent_asset_id"
    )
    parent_aligned = launch_parent == parent or launch_parent == asset
    if not parent_aligned:
        notes.append(
            f"parent_aligned=false — highlight parent={launch_parent} "
            f"record_pack.parent={parent} asset={asset}"
        )
    else:
        notes.append("parent_aligned=true")

    if require:
        pack_ready = (
            parent_aligned is True
            and hl.launch_ready is True
            and rp.pack_ready is True
            and hl.live_dispatched is False
            and hl.merge_executed is False
            and hl.instance.live_dispatched is False
            and hl.instance.merge_executed is False
            and rp.record_persisted is False
            and rp.prompts_injected is False
            and rp.live_router_authorized is False
            and rp.secrets_stored is False
            and rp.remote_index_queried is False
            and rp.twin_written is False
            and rp.purchase_executed is False
            and rp.hosted is False
            and rp.pdf_primary is False
            and rp.live_execution_authorized is False
            and rp.charge_executed is False
            and rp.production_router_verdict == "REJECT"
            and operator_ack is True
        )
    else:
        pack_ready = (
            parent_aligned is True
            and operator_ack is True
            and hl.live_dispatched is False
            and hl.merge_executed is False
            and rp.record_persisted is False
            and rp.prompts_injected is False
            and rp.production_router_verdict == "REJECT"
            and rp.live_router_authorized is False
            and (hl.launch_ready is True or rp.pack_ready is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — floating DR launch + workstation record model "
            "decision ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — highlight_launch, record_pack, alignment, or "
            "operator_ack gate open"
        )

    if (
        hl.live_dispatched is not False
        or hl.merge_executed is not False
        or hl.instance.live_dispatched is not False
        or hl.instance.merge_executed is not False
        or rp.record_persisted is not False
        or rp.prompts_injected is not False
        or rp.live_router_authorized is not False
        or rp.secrets_stored is not False
        or rp.remote_index_queried is not False
        or rp.twin_written is not False
        or rp.purchase_executed is not False
        or rp.hosted is not False
        or rp.pdf_primary is not False
        or rp.live_execution_authorized is not False
        or rp.charge_executed is not False
        or rp.production_router_verdict != "REJECT"
    ):
        raise FloatingDrWorkstationRecordModelDecisionMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMPackComposeError(
            "invariant: honesty flags must remain false / REJECT"
        )

    notes.extend(
        (
            "live_dispatched=false",
            "merge_executed=false",
            "record_persisted=false",
            "prompts_injected=false",
            "live_router_authorized=false",
            "secrets_stored=false",
            "live_meter_read=false",
            "remote_index_queried=false",
            "twin_written=false",
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
            "inventory_mutated=false",
            "pack_dispatched=false",
            "draft_written=false",
            "analysis_written=false",
            "production_router_verdict=REJECT",
        )
    )

    return FloatingDrWorkstationRecordModelDecisionMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMPackCompose(
        week_id=week,
        session_id=session,
        parent_asset_id=parent,
        asset_id=asset,
        title=title,
        account_id=account,
        highlight_launch=hl,
        record_pack=rp,
        parent_aligned=parent_aligned,
        pack_ready=pack_ready,
        live_dispatched=False,
        merge_executed=False,
        record_persisted=False,
        prompts_injected=False,
        live_router_authorized=False,
        secrets_stored=False,
        live_meter_read=False,
        remote_index_queried=False,
        twin_written=False,
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
        inventory_mutated=False,
        pack_dispatched=False,
        draft_written=False,
        analysis_written=False,
        production_router_verdict="REJECT",
        notes=tuple(notes),
        authority=(
            "floating_dr_workstation_record_model_decision_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_m_pack_compose_advisory"
        ),
    )


def format_floating_dr_workstation_record_model_decision_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_m_pack_summary(
    c: FloatingDrWorkstationRecordModelDecisionMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMPackCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"launch_ready={c.highlight_launch.launch_ready} · "
        f"view={c.highlight_launch.preferred_view_mode} · "
        f"records_ready={c.record_pack.pack_ready} · "
        f"parent_aligned={c.parent_aligned} · "
        f"verdict={c.production_router_verdict} · "
        "live_dispatched=false · merge_executed=false · record_persisted=false"
    )


__all__ = [
    "FloatingDrWorkstationRecordModelDecisionMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMPackCompose",
    "FloatingDrWorkstationRecordModelDecisionMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMPackComposeError",
    "compose_floating_dr_workstation_record_model_decision_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_m_pack",
    "format_floating_dr_workstation_record_model_decision_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_m_pack_summary",
]
