"""Collective multiselect over floating DR workstation MO weekly src write pack (pure).

live_dispatched / pack_dispatched / merge_executed / analysis_written always False.
record_persisted / prompts_injected always False.
production_router_verdict always REJECT.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.floating_dr_workstation_record_model_decision_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose import (
    FloatingDrWorkstationRecordModelDecisionMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWritePackCompose,
    FloatingDrWorkstationRecordModelDecisionMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWritePackComposeError,
    compose_floating_dr_workstation_record_model_decision_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack,
)
from substrate.floating_multi_select_collective_cohesive_compose import (
    FloatingMultiSelectCollectiveCohesiveCompose,
    FloatingMultiSelectCollectiveCohesiveComposeError,
    compose_floating_multi_select_collective_cohesive,
)


class CollectiveMultiselectFloatingDrWorkstationMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWritePackComposeError(ValueError):
    """Fail-closed validation for collective multiselect + floating DR pack."""


@dataclass(frozen=True)
class CollectiveMultiselectFloatingDrWorkstationMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWritePackCompose:
    week_id: str
    session_id: str
    parent_asset_id: str
    asset_id: str
    title: str
    account_id: str
    multiselect: FloatingMultiSelectCollectiveCohesiveCompose
    floating_pack: FloatingDrWorkstationRecordModelDecisionMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWritePackCompose
    session_aligned: bool
    parent_aligned: bool
    pack_ready: bool
    live_dispatched: bool
    pack_dispatched: bool
    merge_executed: bool
    analysis_written: bool
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
    draft_written: bool
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
            "multiselect": self.multiselect.to_dict(),
            "floating_pack": self.floating_pack.to_dict(),
            "session_aligned": self.session_aligned,
            "parent_aligned": self.parent_aligned,
            "pack_ready": self.pack_ready,
            "live_dispatched": False,
            "pack_dispatched": False,
            "merge_executed": False,
            "analysis_written": False,
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
            "draft_written": False,
            "production_router_verdict": "REJECT",
            "notes": list(self.notes),
            "authority": (
                "collective_multiselect_floating_dr_workstation_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CollectiveMultiselectFloatingDrWorkstationMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWritePackComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_collective_multiselect_floating_dr_workstation_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack(
    *,
    multiselect: object,
    floating_pack: object,
    operator_ack: object,
    require_both: object | None = None,
) -> CollectiveMultiselectFloatingDrWorkstationMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWritePackCompose:
    """Collective multiselect + floating DR workstation record. Never dispatches."""
    if not isinstance(operator_ack, bool):
        raise CollectiveMultiselectFloatingDrWorkstationMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWritePackComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(multiselect, dict):
        raise CollectiveMultiselectFloatingDrWorkstationMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWritePackComposeError(
            "multiselect must be an object"
        )
    if not isinstance(floating_pack, dict):
        raise CollectiveMultiselectFloatingDrWorkstationMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWritePackComposeError(
            "floating_pack must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise CollectiveMultiselectFloatingDrWorkstationMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWritePackComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "live_dispatched=false · pack_dispatched=false · merge_executed=false",
        "analysis_written=false · record_persisted=false · prompts_injected=false",
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
        raise CollectiveMultiselectFloatingDrWorkstationMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWritePackComposeError(
            str(e)
        ) from e
    notes.extend(f"[multiselect] {n}" for n in ms.notes)

    try:
        fp = compose_floating_dr_workstation_record_model_decision_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack(
            highlight_launch=floating_pack.get("highlight_launch"),
            record_pack=floating_pack.get("record_pack"),
            operator_ack=operator_ack,
            require_both=floating_pack.get("require_both"),
        )
    except FloatingDrWorkstationRecordModelDecisionMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWritePackComposeError as e:
        raise CollectiveMultiselectFloatingDrWorkstationMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWritePackComposeError(
            str(e)
        ) from e
    notes.extend(f"[floating_pack] {n}" for n in fp.notes)

    week = _require_nonempty(fp.week_id, field="week_id")
    session = _require_nonempty(fp.session_id, field="session_id")
    parent = _require_nonempty(fp.parent_asset_id, field="parent_asset_id")
    asset = _require_nonempty(fp.asset_id, field="asset_id")
    title = _require_nonempty(fp.title, field="title")
    account = _require_nonempty(fp.account_id, field="account_id")

    session_aligned = ms.session_id == session
    parent_aligned = ms.parent_asset_id == parent or ms.parent_asset_id == asset
    if not session_aligned:
        notes.append(
            f"session_aligned=false — multiselect.session_id={ms.session_id} "
            f"floating_pack.session_id={session}"
        )
    else:
        notes.append("session_aligned=true")
    if not parent_aligned:
        notes.append(
            f"parent_aligned=false — multiselect.parent={ms.parent_asset_id} "
            f"floating_pack.parent={parent} asset={asset}"
        )
    else:
        notes.append("parent_aligned=true")

    if require:
        pack_ready = (
            session_aligned is True
            and parent_aligned is True
            and ms.pack_ready is True
            and fp.pack_ready is True
            and ms.live_dispatched is False
            and ms.pack_dispatched is False
            and ms.merge_executed is False
            and ms.analysis_written is False
            and fp.live_dispatched is False
            and fp.merge_executed is False
            and fp.record_persisted is False
            and fp.prompts_injected is False
            and fp.live_router_authorized is False
            and fp.secrets_stored is False
            and fp.remote_index_queried is False
            and fp.twin_written is False
            and fp.purchase_executed is False
            and fp.hosted is False
            and fp.pdf_primary is False
            and fp.live_execution_authorized is False
            and fp.charge_executed is False
            and fp.production_router_verdict == "REJECT"
            and operator_ack is True
        )
    else:
        pack_ready = (
            session_aligned is True
            and parent_aligned is True
            and operator_ack is True
            and ms.live_dispatched is False
            and ms.pack_dispatched is False
            and fp.live_dispatched is False
            and fp.record_persisted is False
            and fp.production_router_verdict == "REJECT"
            and fp.live_router_authorized is False
            and (ms.pack_ready is True or fp.pack_ready is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — collective multiselect + floating DR workstation "
            "record ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — multiselect, floating_pack, alignment, or "
            "operator_ack gate open"
        )

    if (
        ms.live_dispatched is not False
        or ms.pack_dispatched is not False
        or ms.merge_executed is not False
        or ms.analysis_written is not False
        or fp.live_dispatched is not False
        or fp.merge_executed is not False
        or fp.record_persisted is not False
        or fp.prompts_injected is not False
        or fp.live_router_authorized is not False
        or fp.secrets_stored is not False
        or fp.remote_index_queried is not False
        or fp.twin_written is not False
        or fp.purchase_executed is not False
        or fp.hosted is not False
        or fp.pdf_primary is not False
        or fp.live_execution_authorized is not False
        or fp.charge_executed is not False
        or fp.production_router_verdict != "REJECT"
    ):
        raise CollectiveMultiselectFloatingDrWorkstationMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWritePackComposeError(
            "invariant: honesty flags must remain false / REJECT"
        )

    notes.extend(
        (
            "live_dispatched=false",
            "pack_dispatched=false",
            "merge_executed=false",
            "analysis_written=false",
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
            "draft_written=false",
            "production_router_verdict=REJECT",
        )
    )

    return CollectiveMultiselectFloatingDrWorkstationMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWritePackCompose(
        week_id=week,
        session_id=session,
        parent_asset_id=parent,
        asset_id=asset,
        title=title,
        account_id=account,
        multiselect=ms,
        floating_pack=fp,
        session_aligned=session_aligned,
        parent_aligned=parent_aligned,
        pack_ready=pack_ready,
        live_dispatched=False,
        pack_dispatched=False,
        merge_executed=False,
        analysis_written=False,
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
        draft_written=False,
        production_router_verdict="REJECT",
        notes=tuple(notes),
        authority=(
            "collective_multiselect_floating_dr_workstation_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_advisory"
        ),
    )


def format_collective_multiselect_floating_dr_workstation_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_summary(
    c: CollectiveMultiselectFloatingDrWorkstationMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWritePackCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"multiselect_ready={c.multiselect.pack_ready} · "
        f"mode={c.multiselect.pack_mode} · "
        f"floating_ready={c.floating_pack.pack_ready} · "
        f"session_aligned={c.session_aligned} · "
        f"parent_aligned={c.parent_aligned} · "
        f"verdict={c.production_router_verdict} · "
        "live_dispatched=false · pack_dispatched=false · analysis_written=false"
    )


__all__ = [
    "CollectiveMultiselectFloatingDrWorkstationMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWritePackCompose",
    "CollectiveMultiselectFloatingDrWorkstationMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWritePackComposeError",
    "compose_collective_multiselect_floating_dr_workstation_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack",
    "format_collective_multiselect_floating_dr_workstation_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_summary",
]
