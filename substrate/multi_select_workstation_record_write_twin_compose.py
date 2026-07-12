"""Floating multi-select over workstation record→prompt + write twin highlight (pure).

live_dispatched / pack_dispatched / merge_executed always False.
prompts_injected / record_persisted / remote_index_queried always False.
production_router_verdict always REJECT.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.floating_multi_select_collective_cohesive_compose import (
    FloatingMultiSelectCollectiveCohesiveCompose,
    FloatingMultiSelectCollectiveCohesiveComposeError,
    compose_floating_multi_select_collective_cohesive,
)
from substrate.workstation_record_write_twin_highlight_compose import (
    WorkstationRecordWriteTwinHighlightCompose,
    WorkstationRecordWriteTwinHighlightComposeError,
    compose_workstation_record_write_twin_highlight,
)


class MultiSelectWorkstationRecordWriteTwinComposeError(ValueError):
    """Fail-closed validation for multi-select + record write twin pack."""


@dataclass(frozen=True)
class MultiSelectWorkstationRecordWriteTwinCompose:
    session_id: str
    parent_asset_id: str
    multiselect: FloatingMultiSelectCollectiveCohesiveCompose
    record_write: WorkstationRecordWriteTwinHighlightCompose
    pack_ready: bool
    live_dispatched: bool
    pack_dispatched: bool
    merge_executed: bool
    analysis_written: bool
    prompts_injected: bool
    record_persisted: bool
    live_router_authorized: bool
    remote_index_queried: bool
    twin_written: bool
    draft_written: bool
    production_router_verdict: str
    purchase_executed: bool
    hosted: bool
    store_mutated: bool
    backlog_mutated: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "parent_asset_id": self.parent_asset_id,
            "multiselect": self.multiselect.to_dict(),
            "record_write": self.record_write.to_dict(),
            "pack_ready": self.pack_ready,
            "live_dispatched": False,
            "pack_dispatched": False,
            "merge_executed": False,
            "analysis_written": False,
            "prompts_injected": False,
            "record_persisted": False,
            "live_router_authorized": False,
            "remote_index_queried": False,
            "twin_written": False,
            "draft_written": False,
            "production_router_verdict": "REJECT",
            "purchase_executed": False,
            "hosted": False,
            "store_mutated": False,
            "backlog_mutated": False,
            "notes": list(self.notes),
            "authority": "multi_select_workstation_record_write_twin_compose_advisory",
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MultiSelectWorkstationRecordWriteTwinComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_multi_select_workstation_record_write_twin(
    *,
    multiselect: object,
    record_write: object,
    operator_ack: object,
    require_both: object | None = None,
) -> MultiSelectWorkstationRecordWriteTwinCompose:
    """Multi-select cohesive + record write twin. Never dispatches/injects."""
    if not isinstance(operator_ack, bool):
        raise MultiSelectWorkstationRecordWriteTwinComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(multiselect, dict):
        raise MultiSelectWorkstationRecordWriteTwinComposeError(
            "multiselect must be an object"
        )
    if not isinstance(record_write, dict):
        raise MultiSelectWorkstationRecordWriteTwinComposeError(
            "record_write must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise MultiSelectWorkstationRecordWriteTwinComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "live_dispatched=false · pack_dispatched=false · merge_executed=false",
        "prompts_injected=false · record_persisted=false · remote_index_queried=false",
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
        raise MultiSelectWorkstationRecordWriteTwinComposeError(str(e)) from e
    notes.extend(f"[multiselect] {n}" for n in ms.notes)

    try:
        rw = compose_workstation_record_write_twin_highlight(
            record_prompt=record_write.get("record_prompt"),
            write_pack=record_write.get("write_pack"),
            operator_ack=operator_ack,
            require_both=record_write.get("require_both"),
        )
    except WorkstationRecordWriteTwinHighlightComposeError as e:
        raise MultiSelectWorkstationRecordWriteTwinComposeError(str(e)) from e
    notes.extend(f"[record_write] {n}" for n in rw.notes)

    session = _require_nonempty(ms.session_id, field="session_id")
    parent = _require_nonempty(ms.parent_asset_id, field="parent_asset_id")

    session_aligned = rw.session_id == session
    parent_aligned = rw.parent_asset_id == parent
    if not session_aligned:
        notes.append(
            "session_id mismatch between multiselect and record_write — pack_ready blocked"
        )
    if not parent_aligned:
        notes.append(
            "parent_asset_id mismatch between multiselect and record_write — pack_ready blocked"
        )

    if require:
        pack_ready = (
            session_aligned
            and parent_aligned
            and ms.pack_ready is True
            and rw.pack_ready is True
            and rw.production_router_verdict == "REJECT"
            and ms.live_dispatched is False
            and ms.pack_dispatched is False
            and rw.prompts_injected is False
            and rw.remote_index_queried is False
            and operator_ack is True
        )
    else:
        pack_ready = (
            session_aligned
            and parent_aligned
            and operator_ack is True
            and rw.production_router_verdict == "REJECT"
            and (ms.pack_ready is True or rw.pack_ready is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — multi-select cohesive + workstation record write twin ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — multiselect, record_write, alignment, or operator_ack gate open"
        )

    if (
        ms.live_dispatched is not False
        or ms.pack_dispatched is not False
        or ms.merge_executed is not False
        or rw.prompts_injected is not False
        or rw.record_persisted is not False
        or rw.remote_index_queried is not False
        or rw.production_router_verdict != "REJECT"
    ):
        raise MultiSelectWorkstationRecordWriteTwinComposeError(
            "invariant: honesty flags must remain false"
        )

    notes.extend(
        (
            "live_dispatched=false",
            "pack_dispatched=false",
            "merge_executed=false",
            "analysis_written=false",
            "prompts_injected=false",
            "record_persisted=false",
            "live_router_authorized=false",
            "remote_index_queried=false",
            "twin_written=false",
            "draft_written=false",
            "production_router_verdict=REJECT",
            "purchase_executed=false",
            "hosted=false",
            "store_mutated=false",
            "backlog_mutated=false",
        )
    )

    return MultiSelectWorkstationRecordWriteTwinCompose(
        session_id=session,
        parent_asset_id=parent,
        multiselect=ms,
        record_write=rw,
        pack_ready=pack_ready,
        live_dispatched=False,
        pack_dispatched=False,
        merge_executed=False,
        analysis_written=False,
        prompts_injected=False,
        record_persisted=False,
        live_router_authorized=False,
        remote_index_queried=False,
        twin_written=False,
        draft_written=False,
        production_router_verdict="REJECT",
        purchase_executed=False,
        hosted=False,
        store_mutated=False,
        backlog_mutated=False,
        notes=tuple(notes),
        authority="multi_select_workstation_record_write_twin_compose_advisory",
    )


def format_multi_select_workstation_record_write_twin_summary(
    c: MultiSelectWorkstationRecordWriteTwinCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"multiselect_ready={c.multiselect.pack_ready} · "
        f"record_write_ready={c.record_write.pack_ready} · "
        f"verdict={c.production_router_verdict} · "
        f"live_dispatched=false · pack_dispatched=false · prompts_injected=false"
    )


__all__ = [
    "MultiSelectWorkstationRecordWriteTwinCompose",
    "MultiSelectWorkstationRecordWriteTwinComposeError",
    "compose_multi_select_workstation_record_write_twin",
    "format_multi_select_workstation_record_write_twin_summary",
]
