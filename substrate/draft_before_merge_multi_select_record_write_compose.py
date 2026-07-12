"""Draft-before-full-merge over multi-select workstation record write twin (pure).

draft_written / merge_executed always False.
live_dispatched / pack_dispatched / prompts_injected always False.
production_router_verdict always REJECT.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.floating_draft_before_full_merge_gate_compose import (
    FloatingDraftBeforeFullMergeGateCompose,
    FloatingDraftBeforeFullMergeGateComposeError,
    compose_floating_draft_before_full_merge_gate,
)
from substrate.multi_select_workstation_record_write_twin_compose import (
    MultiSelectWorkstationRecordWriteTwinCompose,
    MultiSelectWorkstationRecordWriteTwinComposeError,
    compose_multi_select_workstation_record_write_twin,
)


class DraftBeforeMergeMultiSelectRecordWriteComposeError(ValueError):
    """Fail-closed validation for draft-before-merge + multi-select pack."""


@dataclass(frozen=True)
class DraftBeforeMergeMultiSelectRecordWriteCompose:
    session_id: str
    parent_asset_id: str
    draft_gate: FloatingDraftBeforeFullMergeGateCompose
    multi_pack: MultiSelectWorkstationRecordWriteTwinCompose
    pack_ready: bool
    draft_written: bool
    merge_executed: bool
    live_dispatched: bool
    pack_dispatched: bool
    prompts_injected: bool
    record_persisted: bool
    remote_index_queried: bool
    twin_written: bool
    analysis_written: bool
    production_router_verdict: str
    live_router_authorized: bool
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
            "draft_gate": self.draft_gate.to_dict(),
            "multi_pack": self.multi_pack.to_dict(),
            "pack_ready": self.pack_ready,
            "draft_written": False,
            "merge_executed": False,
            "live_dispatched": False,
            "pack_dispatched": False,
            "prompts_injected": False,
            "record_persisted": False,
            "remote_index_queried": False,
            "twin_written": False,
            "analysis_written": False,
            "production_router_verdict": "REJECT",
            "live_router_authorized": False,
            "purchase_executed": False,
            "hosted": False,
            "store_mutated": False,
            "backlog_mutated": False,
            "notes": list(self.notes),
            "authority": "draft_before_merge_multi_select_record_write_compose_advisory",
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DraftBeforeMergeMultiSelectRecordWriteComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_draft_before_merge_multi_select_record_write(
    *,
    draft_gate: object,
    multi_pack: object,
    operator_ack: object,
    require_both: object | None = None,
) -> DraftBeforeMergeMultiSelectRecordWriteCompose:
    """Draft-before-merge + multi-select record write. Never writes/merges."""
    if not isinstance(operator_ack, bool):
        raise DraftBeforeMergeMultiSelectRecordWriteComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(draft_gate, dict):
        raise DraftBeforeMergeMultiSelectRecordWriteComposeError(
            "draft_gate must be an object"
        )
    if not isinstance(multi_pack, dict):
        raise DraftBeforeMergeMultiSelectRecordWriteComposeError(
            "multi_pack must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise DraftBeforeMergeMultiSelectRecordWriteComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "draft_written=false · merge_executed=false · live_dispatched=false",
        "pack_dispatched=false · prompts_injected=false · remote_index_queried=false",
        "production_router_verdict=REJECT",
    ]

    try:
        dg = compose_floating_draft_before_full_merge_gate(
            session_id=draft_gate.get("session_id"),
            parent_asset_id=draft_gate.get("parent_asset_id"),
            sources=draft_gate.get("sources"),
            stage=draft_gate.get("stage"),
            operator_ack=operator_ack,
            parent_excerpt=draft_gate.get("parent_excerpt"),
            full_merge_ack=draft_gate.get("full_merge_ack"),
        )
    except FloatingDraftBeforeFullMergeGateComposeError as e:
        raise DraftBeforeMergeMultiSelectRecordWriteComposeError(str(e)) from e
    notes.extend(f"[draft_gate] {n}" for n in dg.notes)

    try:
        mp = compose_multi_select_workstation_record_write_twin(
            multiselect=multi_pack.get("multiselect"),
            record_write=multi_pack.get("record_write"),
            operator_ack=operator_ack,
            require_both=multi_pack.get("require_both"),
        )
    except MultiSelectWorkstationRecordWriteTwinComposeError as e:
        raise DraftBeforeMergeMultiSelectRecordWriteComposeError(str(e)) from e
    notes.extend(f"[multi_pack] {n}" for n in mp.notes)

    session = _require_nonempty(dg.session_id, field="session_id")
    parent = _require_nonempty(dg.parent_asset_id, field="parent_asset_id")

    session_aligned = mp.session_id == session
    parent_aligned = mp.parent_asset_id == parent
    if not session_aligned:
        notes.append(
            "session_id mismatch between draft_gate and multi_pack — pack_ready blocked"
        )
    if not parent_aligned:
        notes.append(
            "parent_asset_id mismatch between draft_gate and multi_pack — pack_ready blocked"
        )

    if require:
        pack_ready = (
            session_aligned
            and parent_aligned
            and dg.gate_ready is True
            and mp.pack_ready is True
            and mp.production_router_verdict == "REJECT"
            and dg.draft_written is False
            and dg.merge_executed is False
            and mp.live_dispatched is False
            and mp.prompts_injected is False
            and operator_ack is True
        )
    else:
        pack_ready = (
            session_aligned
            and parent_aligned
            and operator_ack is True
            and mp.production_router_verdict == "REJECT"
            and (dg.gate_ready is True or mp.pack_ready is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — draft-before-merge + multi-select record write pack ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — draft_gate, multi_pack, alignment, or operator_ack gate open"
        )

    if (
        dg.draft_written is not False
        or dg.merge_executed is not False
        or dg.live_dispatched is not False
        or mp.live_dispatched is not False
        or mp.pack_dispatched is not False
        or mp.prompts_injected is not False
        or mp.production_router_verdict != "REJECT"
    ):
        raise DraftBeforeMergeMultiSelectRecordWriteComposeError(
            "invariant: honesty flags must remain false"
        )

    notes.extend(
        (
            "draft_written=false",
            "merge_executed=false",
            "live_dispatched=false",
            "pack_dispatched=false",
            "prompts_injected=false",
            "record_persisted=false",
            "remote_index_queried=false",
            "twin_written=false",
            "analysis_written=false",
            "production_router_verdict=REJECT",
            "live_router_authorized=false",
            "purchase_executed=false",
            "hosted=false",
            "store_mutated=false",
            "backlog_mutated=false",
        )
    )

    return DraftBeforeMergeMultiSelectRecordWriteCompose(
        session_id=session,
        parent_asset_id=parent,
        draft_gate=dg,
        multi_pack=mp,
        pack_ready=pack_ready,
        draft_written=False,
        merge_executed=False,
        live_dispatched=False,
        pack_dispatched=False,
        prompts_injected=False,
        record_persisted=False,
        remote_index_queried=False,
        twin_written=False,
        analysis_written=False,
        production_router_verdict="REJECT",
        live_router_authorized=False,
        purchase_executed=False,
        hosted=False,
        store_mutated=False,
        backlog_mutated=False,
        notes=tuple(notes),
        authority="draft_before_merge_multi_select_record_write_compose_advisory",
    )


def format_draft_before_merge_multi_select_record_write_summary(
    c: DraftBeforeMergeMultiSelectRecordWriteCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"gate_ready={c.draft_gate.gate_ready} · "
        f"multi_ready={c.multi_pack.pack_ready} · "
        f"verdict={c.production_router_verdict} · "
        f"draft_written=false · merge_executed=false · live_dispatched=false"
    )


__all__ = [
    "DraftBeforeMergeMultiSelectRecordWriteCompose",
    "DraftBeforeMergeMultiSelectRecordWriteComposeError",
    "compose_draft_before_merge_multi_select_record_write",
    "format_draft_before_merge_multi_select_record_write_summary",
]
