"""Workstation record→prompt over write twin + highlight float twin-search (pure).

record_persisted / prompts_injected / live_router_authorized always False.
draft_written / analysis_written / remote_index_queried always False.
production_router_verdict always REJECT.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.workstation_record_prompt_model_decision_compose import (
    WorkstationRecordPromptModelDecisionCompose,
    WorkstationRecordPromptModelDecisionComposeError,
    compose_workstation_record_prompt_model_decision,
)
from substrate.write_twin_collective_highlight_float_twin_search_compose import (
    WriteTwinCollectiveHighlightFloatTwinSearchCompose,
    WriteTwinCollectiveHighlightFloatTwinSearchComposeError,
    compose_write_twin_collective_highlight_float_twin_search,
)


class WorkstationRecordWriteTwinHighlightComposeError(ValueError):
    """Fail-closed validation for record→prompt + write twin highlight pack."""


@dataclass(frozen=True)
class WorkstationRecordWriteTwinHighlightCompose:
    session_id: str
    parent_asset_id: str
    record_prompt: WorkstationRecordPromptModelDecisionCompose
    write_pack: WriteTwinCollectiveHighlightFloatTwinSearchCompose
    pack_ready: bool
    record_persisted: bool
    prompts_injected: bool
    live_router_authorized: bool
    secrets_stored: bool
    live_meter_read: bool
    draft_written: bool
    analysis_written: bool
    merge_executed: bool
    remote_index_queried: bool
    twin_written: bool
    live_dispatched: bool
    production_router_verdict: str
    purchase_executed: bool
    hosted: bool
    store_mutated: bool
    backlog_mutated: bool
    pack_dispatched: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "parent_asset_id": self.parent_asset_id,
            "record_prompt": self.record_prompt.to_dict(),
            "write_pack": self.write_pack.to_dict(),
            "pack_ready": self.pack_ready,
            "record_persisted": False,
            "prompts_injected": False,
            "live_router_authorized": False,
            "secrets_stored": False,
            "live_meter_read": False,
            "draft_written": False,
            "analysis_written": False,
            "merge_executed": False,
            "remote_index_queried": False,
            "twin_written": False,
            "live_dispatched": False,
            "production_router_verdict": "REJECT",
            "purchase_executed": False,
            "hosted": False,
            "store_mutated": False,
            "backlog_mutated": False,
            "pack_dispatched": False,
            "notes": list(self.notes),
            "authority": "workstation_record_write_twin_highlight_compose_advisory",
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorkstationRecordWriteTwinHighlightComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_workstation_record_write_twin_highlight(
    *,
    record_prompt: object,
    write_pack: object,
    operator_ack: object,
    require_both: object | None = None,
) -> WorkstationRecordWriteTwinHighlightCompose:
    """Record→prompt + write twin highlight. Never injects or persists."""
    if not isinstance(operator_ack, bool):
        raise WorkstationRecordWriteTwinHighlightComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(record_prompt, dict):
        raise WorkstationRecordWriteTwinHighlightComposeError(
            "record_prompt must be an object"
        )
    if not isinstance(write_pack, dict):
        raise WorkstationRecordWriteTwinHighlightComposeError(
            "write_pack must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise WorkstationRecordWriteTwinHighlightComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "record_persisted=false · prompts_injected=false · live_router_authorized=false",
        "draft_written=false · analysis_written=false · remote_index_queried=false",
        "production_router_verdict=REJECT",
    ]

    try:
        rec = compose_workstation_record_prompt_model_decision(
            session_id=record_prompt.get("session_id"),
            parent_asset_id=record_prompt.get("parent_asset_id"),
            records=record_prompt.get("records"),
            user_prompt=record_prompt.get("user_prompt"),
            selected_model_id=record_prompt.get("selected_model_id"),
            models=record_prompt.get("models"),
            daily_cap_usd=record_prompt.get("daily_cap_usd"),
            spent_usd=record_prompt.get("spent_usd"),
            operator_ack=operator_ack,
            placement=record_prompt.get("placement"),
            max_context_lines=record_prompt.get("max_context_lines"),
            projected_cost_usd_high=record_prompt.get("projected_cost_usd_high"),
            projected_cost_usd_low=record_prompt.get("projected_cost_usd_low"),
            bench_bests=record_prompt.get("bench_bests"),
            focus_task=record_prompt.get("focus_task"),
            nd_shadow=record_prompt.get("nd_shadow"),
        )
    except WorkstationRecordPromptModelDecisionComposeError as e:
        raise WorkstationRecordWriteTwinHighlightComposeError(str(e)) from e
    notes.extend(f"[record_prompt] {n}" for n in rec.notes)

    try:
        wp = compose_write_twin_collective_highlight_float_twin_search(
            write=write_pack.get("write"),
            highlight_pack=write_pack.get("highlight_pack"),
            operator_ack=operator_ack,
            require_both=write_pack.get("require_both"),
        )
    except WriteTwinCollectiveHighlightFloatTwinSearchComposeError as e:
        raise WorkstationRecordWriteTwinHighlightComposeError(str(e)) from e
    notes.extend(f"[write_pack] {n}" for n in wp.notes)

    session = _require_nonempty(rec.session_id, field="session_id")
    parent = _require_nonempty(rec.parent_asset_id, field="parent_asset_id")

    session_aligned = wp.session_id == session
    parent_aligned = wp.parent_asset_id == parent
    if not session_aligned:
        notes.append(
            "session_id mismatch between record_prompt and write_pack — pack_ready blocked"
        )
    if not parent_aligned:
        notes.append(
            "parent_asset_id mismatch between record_prompt and write_pack — pack_ready blocked"
        )

    if require:
        pack_ready = (
            session_aligned
            and parent_aligned
            and rec.pack_ready is True
            and wp.pack_ready is True
            and wp.production_router_verdict == "REJECT"
            and rec.prompts_injected is False
            and rec.record_persisted is False
            and wp.remote_index_queried is False
            and operator_ack is True
        )
    else:
        pack_ready = (
            session_aligned
            and parent_aligned
            and operator_ack is True
            and wp.production_router_verdict == "REJECT"
            and (rec.pack_ready is True or wp.pack_ready is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — workstation record→prompt + write twin highlight pack ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — record_prompt, write_pack, alignment, or operator_ack gate open"
        )

    if (
        rec.record_persisted is not False
        or rec.prompts_injected is not False
        or rec.live_router_authorized is not False
        or wp.draft_written is not False
        or wp.analysis_written is not False
        or wp.remote_index_queried is not False
        or wp.production_router_verdict != "REJECT"
    ):
        raise WorkstationRecordWriteTwinHighlightComposeError(
            "invariant: honesty flags must remain false"
        )

    notes.extend(
        (
            "record_persisted=false",
            "prompts_injected=false",
            "live_router_authorized=false",
            "secrets_stored=false",
            "live_meter_read=false",
            "draft_written=false",
            "analysis_written=false",
            "merge_executed=false",
            "remote_index_queried=false",
            "twin_written=false",
            "live_dispatched=false",
            "production_router_verdict=REJECT",
            "purchase_executed=false",
            "hosted=false",
            "store_mutated=false",
            "backlog_mutated=false",
            "pack_dispatched=false",
        )
    )

    return WorkstationRecordWriteTwinHighlightCompose(
        session_id=session,
        parent_asset_id=parent,
        record_prompt=rec,
        write_pack=wp,
        pack_ready=pack_ready,
        record_persisted=False,
        prompts_injected=False,
        live_router_authorized=False,
        secrets_stored=False,
        live_meter_read=False,
        draft_written=False,
        analysis_written=False,
        merge_executed=False,
        remote_index_queried=False,
        twin_written=False,
        live_dispatched=False,
        production_router_verdict="REJECT",
        purchase_executed=False,
        hosted=False,
        store_mutated=False,
        backlog_mutated=False,
        pack_dispatched=False,
        notes=tuple(notes),
        authority="workstation_record_write_twin_highlight_compose_advisory",
    )


def format_workstation_record_write_twin_highlight_summary(
    c: WorkstationRecordWriteTwinHighlightCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"record_ready={c.record_prompt.pack_ready} · "
        f"write_ready={c.write_pack.pack_ready} · "
        f"usage={c.record_prompt.usage_percent} · "
        f"verdict={c.production_router_verdict} · "
        f"prompts_injected=false · record_persisted=false · remote_index_queried=false"
    )


__all__ = [
    "WorkstationRecordWriteTwinHighlightCompose",
    "WorkstationRecordWriteTwinHighlightComposeError",
    "compose_workstation_record_write_twin_highlight",
    "format_workstation_record_write_twin_highlight_summary",
]
