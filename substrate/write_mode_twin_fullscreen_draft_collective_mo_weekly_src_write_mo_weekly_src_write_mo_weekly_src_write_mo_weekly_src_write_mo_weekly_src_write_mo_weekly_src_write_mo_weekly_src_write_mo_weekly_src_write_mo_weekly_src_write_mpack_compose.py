"""Write twin collective over fullscreen draft collective MO weekly src write (pure).

draft_written / analysis_written / merge_executed always False.
live_dispatched / live_execution_authorized always False.
production_router_verdict always REJECT.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.fullscreen_open_draft_before_merge_collective_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mpack_compose import (
    FullscreenOpenDraftBeforeMergeCollectiveMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMpackCompose,
    FullscreenOpenDraftBeforeMergeCollectiveMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMpackComposeError,
    compose_fullscreen_open_draft_before_merge_collective_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mpack,
)
from substrate.write_mode_twin_collective_analysis_compose import (
    WriteModeTwinCollectiveAnalysisCompose,
    WriteModeTwinCollectiveAnalysisComposeError,
    compose_write_mode_twin_collective_analysis,
)


class WriteModeTwinFullscreenDraftCollectiveMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMpackComposeError(
    ValueError
):
    """Fail-closed validation for write twin collective + fullscreen draft-before-merge pack."""


@dataclass(frozen=True)
class WriteModeTwinFullscreenDraftCollectiveMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMpackCompose:
    session_id: str
    parent_asset_id: str
    week_id: str
    asset_id: str
    title: str
    account_id: str
    write: WriteModeTwinCollectiveAnalysisCompose
    fullscreen_pack: FullscreenOpenDraftBeforeMergeCollectiveMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMpackCompose
    session_aligned: bool
    parent_aligned: bool
    pack_ready: bool
    draft_written: bool
    analysis_written: bool
    merge_executed: bool
    live_dispatched: bool
    pack_dispatched: bool
    live_execution_authorized: bool
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
    charge_executed: bool
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
            "write": self.write.to_dict(),
            "fullscreen_pack": self.fullscreen_pack.to_dict(),
            "session_aligned": self.session_aligned,
            "parent_aligned": self.parent_aligned,
            "pack_ready": self.pack_ready,
            "draft_written": False,
            "analysis_written": False,
            "merge_executed": False,
            "live_dispatched": False,
            "pack_dispatched": False,
            "live_execution_authorized": False,
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
            "charge_executed": False,
            "record_persisted": False,
            "purchase_executed": False,
            "hosted": False,
            "remote_fetched": False,
            "production_router_verdict": "REJECT",
            "notes": list(self.notes),
            "authority": (
                "write_mode_twin_fullscreen_draft_collective_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mpack_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WriteModeTwinFullscreenDraftCollectiveMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMpackComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_write_mode_twin_fullscreen_draft_collective_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mpack(
    *,
    write: object,
    fullscreen_pack: object,
    operator_ack: object,
    require_both: object | None = None,
) -> WriteModeTwinFullscreenDraftCollectiveMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMpackCompose:
    """Write twin collective on fullscreen collective multiselect. Never writes."""
    if not isinstance(operator_ack, bool):
        raise WriteModeTwinFullscreenDraftCollectiveMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMpackComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(write, dict):
        raise WriteModeTwinFullscreenDraftCollectiveMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMpackComposeError(
            "write must be an object"
        )
    if not isinstance(fullscreen_pack, dict):
        raise WriteModeTwinFullscreenDraftCollectiveMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMpackComposeError(
            "fullscreen_pack must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise WriteModeTwinFullscreenDraftCollectiveMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMpackComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "draft_written=false · analysis_written=false · merge_executed=false",
        "live_dispatched=false · live_execution_authorized=false",
        "production_router_verdict=REJECT",
    ]

    try:
        w = compose_write_mode_twin_collective_analysis(
            session_id=write.get("session_id"),
            draft_id=write.get("draft_id"),
            parent_asset_id=write.get("parent_asset_id"),
            twin_slices=write.get("twin_slices"),
            chase_slots=write.get("chase_slots"),
            analysis_kind=write.get("analysis_kind"),
            operator_ack=operator_ack,
            base_draft_html=write.get("base_draft_html"),
            extra_findings=write.get("extra_findings"),
            require_both=write.get("require_both"),
        )
    except WriteModeTwinCollectiveAnalysisComposeError as e:
        raise WriteModeTwinFullscreenDraftCollectiveMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMpackComposeError(
            str(e)
        ) from e
    notes.extend(f"[write] {n}" for n in w.notes)

    try:
        fp = compose_fullscreen_open_draft_before_merge_collective_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mpack(
            fullscreen=fullscreen_pack.get("fullscreen"),
            draft_pack=fullscreen_pack.get("draft_pack"),
            operator_ack=operator_ack,
            require_both=fullscreen_pack.get("require_both"),
        )
    except FullscreenOpenDraftBeforeMergeCollectiveMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMpackComposeError as e:
        raise WriteModeTwinFullscreenDraftCollectiveMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMpackComposeError(
            str(e)
        ) from e
    notes.extend(f"[fullscreen_pack] {n}" for n in fp.notes)

    session = _require_nonempty(w.session_id, field="session_id")
    parent = _require_nonempty(w.parent_asset_id, field="parent_asset_id")
    week = _require_nonempty(fp.week_id, field="week_id")
    asset = _require_nonempty(fp.asset_id, field="asset_id")
    title = _require_nonempty(fp.title, field="title")
    account = _require_nonempty(fp.account_id, field="account_id")

    session_aligned = fp.session_id == session
    parent_aligned = fp.parent_asset_id == parent or fp.asset_id == parent
    if not session_aligned:
        notes.append(
            "session_id mismatch between write and fullscreen_pack — "
            "pack_ready blocked"
        )
    else:
        notes.append("session_aligned=true")
    if not parent_aligned:
        notes.append(
            "parent_asset_id mismatch between write and fullscreen_pack — "
            "pack_ready blocked"
        )
    else:
        notes.append("parent_aligned=true")

    if require:
        pack_ready = (
            session_aligned is True
            and parent_aligned is True
            and w.pack_ready is True
            and fp.pack_ready is True
            and w.draft_written is False
            and w.analysis_written is False
            and w.merge_executed is False
            and w.live_dispatched is False
            and fp.live_dispatched is False
            and fp.live_execution_authorized is False
            and fp.draft_written is False
            and fp.merge_executed is False
            and fp.analysis_written is False
            and fp.twin_written is False
            and fp.charge_executed is False
            and fp.live_router_authorized is False
            and fp.secrets_stored is False
            and fp.remote_index_queried is False
            and fp.pdf_primary is False
            and fp.production_router_verdict == "REJECT"
            and operator_ack is True
        )
    else:
        pack_ready = (
            session_aligned is True
            and parent_aligned is True
            and operator_ack is True
            and fp.production_router_verdict == "REJECT"
            and fp.pdf_primary is False
            and w.live_dispatched is False
            and (w.pack_ready is True or fp.pack_ready is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — write twin collective + fullscreen collective "
            "multiselect ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — write, fullscreen_pack, alignment, or "
            "operator_ack gate open"
        )

    if (
        w.draft_written is not False
        or w.analysis_written is not False
        or w.merge_executed is not False
        or w.live_dispatched is not False
        or fp.live_dispatched is not False
        or fp.live_execution_authorized is not False
        or fp.draft_written is not False
        or fp.merge_executed is not False
        or fp.analysis_written is not False
        or fp.twin_written is not False
        or fp.charge_executed is not False
        or fp.live_router_authorized is not False
        or fp.secrets_stored is not False
        or fp.remote_index_queried is not False
        or fp.pdf_primary is not False
        or fp.production_router_verdict != "REJECT"
    ):
        raise WriteModeTwinFullscreenDraftCollectiveMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMpackComposeError(
            "invariant: honesty flags must remain false / REJECT"
        )

    notes.extend(
        (
            "draft_written=false",
            "analysis_written=false",
            "merge_executed=false",
            "live_dispatched=false",
            "pack_dispatched=false",
            "live_execution_authorized=false",
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
            "charge_executed=false",
            "record_persisted=false",
            "purchase_executed=false",
            "hosted=false",
            "remote_fetched=false",
            "production_router_verdict=REJECT",
        )
    )

    return WriteModeTwinFullscreenDraftCollectiveMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMpackCompose(
        session_id=session,
        parent_asset_id=parent,
        week_id=week,
        asset_id=asset,
        title=title,
        account_id=account,
        write=w,
        fullscreen_pack=fp,
        session_aligned=session_aligned,
        parent_aligned=parent_aligned,
        pack_ready=pack_ready,
        draft_written=False,
        analysis_written=False,
        merge_executed=False,
        live_dispatched=False,
        pack_dispatched=False,
        live_execution_authorized=False,
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
        charge_executed=False,
        record_persisted=False,
        purchase_executed=False,
        hosted=False,
        remote_fetched=False,
        production_router_verdict="REJECT",
        notes=tuple(notes),
        authority=(
            "write_mode_twin_fullscreen_draft_collective_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mpack_compose_advisory"
        ),
    )


def format_write_mode_twin_fullscreen_draft_collective_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mpack_summary(
    c: WriteModeTwinFullscreenDraftCollectiveMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMpackCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"write_ready={c.write.pack_ready} · "
        f"fullscreen_ready={c.fullscreen_pack.pack_ready} · "
        f"session_aligned={c.session_aligned} · "
        f"parent_aligned={c.parent_aligned} · "
        f"verdict={c.production_router_verdict} · "
        "draft_written=false · analysis_written=false · live_dispatched=false"
    )


__all__ = [
    "WriteModeTwinFullscreenDraftCollectiveMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMpackCompose",
    "WriteModeTwinFullscreenDraftCollectiveMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMpackComposeError",
    "compose_write_mode_twin_fullscreen_draft_collective_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mpack",
    "format_write_mode_twin_fullscreen_draft_collective_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mpack_summary",
]
