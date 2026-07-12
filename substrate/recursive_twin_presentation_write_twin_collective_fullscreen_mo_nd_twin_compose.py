"""Recursive twin presentation over write twin collective fullscreen MO ND twin (pure).

twin_written / prompts_injected / merge_executed always False.
draft_written / analysis_written / live_dispatched always False.
live_execution_authorized / live_router_authorized always False.
production_router_verdict always REJECT.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from substrate.recursive_twin_note_taker_compose import (
    RecursiveTwinNoteTakerCompose,
    RecursiveTwinNoteTakerComposeError,
    compose_recursive_twin_note_taker,
)
from substrate.recursive_twin_presentation_competition_dr_compose import (
    TwinPresentationSurface,
)
from substrate.write_mode_twin_collective_fullscreen_mo_unattended_nd_twin_compose import (
    WriteModeTwinCollectiveFullscreenMoUnattendedNdTwinCompose,
    WriteModeTwinCollectiveFullscreenMoUnattendedNdTwinComposeError,
    compose_write_mode_twin_collective_fullscreen_mo_unattended_nd_twin,
)

TwinPresentationViewMode = Literal[
    "side_panel", "overlay", "fullscreen_twin", "inline"
]

_VIEW_MODES: frozenset[str] = frozenset(
    ("side_panel", "overlay", "fullscreen_twin", "inline")
)


class RecursiveTwinPresentationWriteTwinCollectiveFullscreenMoNdTwinComposeError(
    ValueError
):
    """Fail-closed validation for twin presentation + write collective MO pack."""


@dataclass(frozen=True)
class RecursiveTwinPresentationWriteTwinCollectiveFullscreenMoNdTwinCompose:
    session_id: str
    parent_asset_id: str
    week_id: str
    asset_id: str
    title: str
    account_id: str
    twin: RecursiveTwinNoteTakerCompose
    presentation: TwinPresentationSurface
    write_pack: WriteModeTwinCollectiveFullscreenMoUnattendedNdTwinCompose
    session_aligned: bool
    parent_aligned: bool
    pack_ready: bool
    twin_written: bool
    prompts_injected: bool
    merge_executed: bool
    live_dispatch_authorized: bool
    draft_written: bool
    analysis_written: bool
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
            "twin": self.twin.to_dict(),
            "presentation": self.presentation.to_dict(),
            "write_pack": self.write_pack.to_dict(),
            "session_aligned": self.session_aligned,
            "parent_aligned": self.parent_aligned,
            "pack_ready": self.pack_ready,
            "twin_written": False,
            "prompts_injected": False,
            "merge_executed": False,
            "live_dispatch_authorized": False,
            "draft_written": False,
            "analysis_written": False,
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
            "inventory_mutated": False,
            "charge_executed": False,
            "record_persisted": False,
            "purchase_executed": False,
            "hosted": False,
            "remote_fetched": False,
            "production_router_verdict": "REJECT",
            "notes": list(self.notes),
            "authority": (
                "recursive_twin_presentation_write_twin_collective_fullscreen_mo_nd_twin_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RecursiveTwinPresentationWriteTwinCollectiveFullscreenMoNdTwinComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def _require_string_list(value: object, *, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise RecursiveTwinPresentationWriteTwinCollectiveFullscreenMoNdTwinComposeError(
            f"{field} must be an array when set"
        )
    return [
        _require_nonempty(item, field=f"{field}[{i}]")
        for i, item in enumerate(value)
    ]


def compose_recursive_twin_presentation_write_twin_collective_fullscreen_mo_nd_twin(
    *,
    twin: object,
    presentation: object,
    write_pack: object,
    operator_ack: object,
    require_both: object | None = None,
) -> RecursiveTwinPresentationWriteTwinCollectiveFullscreenMoNdTwinCompose:
    """Twin presentation + write twin collective fullscreen MO ND twin. Never writes/merges."""
    if not isinstance(operator_ack, bool):
        raise RecursiveTwinPresentationWriteTwinCollectiveFullscreenMoNdTwinComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(twin, dict):
        raise RecursiveTwinPresentationWriteTwinCollectiveFullscreenMoNdTwinComposeError(
            "twin must be an object"
        )
    if not isinstance(presentation, dict):
        raise RecursiveTwinPresentationWriteTwinCollectiveFullscreenMoNdTwinComposeError(
            "presentation must be an object"
        )
    if not isinstance(write_pack, dict):
        raise RecursiveTwinPresentationWriteTwinCollectiveFullscreenMoNdTwinComposeError(
            "write_pack must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise RecursiveTwinPresentationWriteTwinCollectiveFullscreenMoNdTwinComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "twin_written=false · prompts_injected=false · merge_executed=false",
        "draft_written=false · analysis_written=false · live_dispatched=false",
        "live_execution_authorized=false · live_router_authorized=false",
        "production_router_verdict=REJECT",
    ]

    try:
        twin_c = compose_recursive_twin_note_taker(
            parent_asset_id=twin.get("parent_asset_id"),
            source_excerpt=twin.get("source_excerpt"),
            operator_ack=operator_ack,
            existing_twin_asset_id=twin.get("existing_twin_asset_id"),
            focus_questions=twin.get("focus_questions"),
        )
    except RecursiveTwinNoteTakerComposeError as e:
        raise RecursiveTwinPresentationWriteTwinCollectiveFullscreenMoNdTwinComposeError(
            str(e)
        ) from e
    notes.extend(f"[twin] {n}" for n in twin_c.notes)

    view_mode = presentation.get("view_mode")
    if view_mode not in _VIEW_MODES:
        raise RecursiveTwinPresentationWriteTwinCollectiveFullscreenMoNdTwinComposeError(
            "presentation.view_mode must be side_panel|overlay|fullscreen_twin|inline"
        )
    open_requested = presentation.get("open_requested")
    if not isinstance(open_requested, bool):
        raise RecursiveTwinPresentationWriteTwinCollectiveFullscreenMoNdTwinComposeError(
            "presentation.open_requested must be an explicit boolean"
        )
    merge_to_parent_preview = presentation.get("merge_to_parent_preview")
    if merge_to_parent_preview is None:
        merge_to_parent_preview = False
    if not isinstance(merge_to_parent_preview, bool):
        raise RecursiveTwinPresentationWriteTwinCollectiveFullscreenMoNdTwinComposeError(
            "presentation.merge_to_parent_preview must be boolean when set"
        )

    presented_insights = _require_string_list(
        presentation.get("presented_insights"),
        field="presentation.presented_insights",
    )
    presented_questions = _require_string_list(
        presentation.get("presented_questions"),
        field="presentation.presented_questions",
    )

    presentation_sections: list[str] = list(twin_c.twin_scaffold_sections)
    presentation_sections.append(
        f'<section data-role="presentation-chrome" data-view-mode="{view_mode}" '
        f'data-open="{open_requested}" data-merge-preview="{merge_to_parent_preview}"></section>'
    )
    for insight in presented_insights:
        presentation_sections.append(
            f'<section data-role="presented-insight" data-parent="{twin_c.parent_asset_id}">'
            f"{insight}</section>"
        )
    for question in presented_questions:
        presentation_sections.append(
            f'<section data-role="presented-question" data-parent="{twin_c.parent_asset_id}">'
            f"{question}</section>"
        )

    presentation_ready = (
        operator_ack is True
        and twin_c.twin_propose_ready is True
        and open_requested is True
        and twin_c.twin_written is False
        and twin_c.prompts_injected is False
    )
    if presentation_ready:
        notes.append(
            f"presentation_ready=true · view_mode={view_mode} · "
            f"insights={len(presented_insights)} · questions={len(presented_questions)}"
        )
    else:
        notes.append(
            "presentation_ready=false — operator_ack, twin_propose_ready, or open_requested gate open"
        )
    if merge_to_parent_preview:
        notes.append(
            "merge_to_parent_preview=true — draft preview only; merge_executed=false"
        )

    try:
        wp = compose_write_mode_twin_collective_fullscreen_mo_unattended_nd_twin(
            write=write_pack.get("write"),
            fullscreen_pack=write_pack.get("fullscreen_pack"),
            operator_ack=operator_ack,
            require_both=write_pack.get("require_both"),
        )
    except WriteModeTwinCollectiveFullscreenMoUnattendedNdTwinComposeError as e:
        raise RecursiveTwinPresentationWriteTwinCollectiveFullscreenMoNdTwinComposeError(
            str(e)
        ) from e
    notes.extend(f"[write_pack] {n}" for n in wp.notes)

    parent = _require_nonempty(twin_c.parent_asset_id, field="parent_asset_id")
    session = _require_nonempty(wp.session_id, field="session_id")
    week = _require_nonempty(wp.week_id, field="week_id")
    asset = _require_nonempty(wp.asset_id, field="asset_id")
    title = _require_nonempty(wp.title, field="title")
    account = _require_nonempty(wp.account_id, field="account_id")

    session_aligned = wp.session_id == session
    parent_aligned = wp.parent_asset_id == parent or wp.asset_id == parent
    if not parent_aligned:
        notes.append(
            "parent_asset_id mismatch between twin and write_pack — pack_ready blocked"
        )

    if require:
        pack_ready = (
            session_aligned
            and parent_aligned
            and presentation_ready is True
            and twin_c.twin_propose_ready is True
            and wp.pack_ready is True
            and twin_c.twin_written is False
            and twin_c.prompts_injected is False
            and twin_c.live_dispatch_authorized is False
            and wp.draft_written is False
            and wp.analysis_written is False
            and wp.merge_executed is False
            and wp.live_dispatched is False
            and wp.live_execution_authorized is False
            and wp.live_router_authorized is False
            and wp.secrets_stored is False
            and wp.remote_index_queried is False
            and wp.pdf_primary is False
            and wp.production_router_verdict == "REJECT"
            and operator_ack is True
        )
    else:
        pack_ready = (
            session_aligned
            and parent_aligned
            and operator_ack is True
            and twin_c.twin_written is False
            and wp.production_router_verdict == "REJECT"
            and wp.pdf_primary is False
            and (presentation_ready is True or wp.pack_ready is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — twin presentation + write twin collective fullscreen MO ND twin "
            "ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — twin, presentation, write_pack, alignment, or operator_ack gate open"
        )

    if (
        twin_c.twin_written is not False
        or twin_c.prompts_injected is not False
        or twin_c.live_dispatch_authorized is not False
        or wp.draft_written is not False
        or wp.analysis_written is not False
        or wp.merge_executed is not False
        or wp.live_dispatched is not False
        or wp.live_execution_authorized is not False
        or wp.live_router_authorized is not False
        or wp.secrets_stored is not False
        or wp.remote_index_queried is not False
        or wp.pdf_primary is not False
        or wp.production_router_verdict != "REJECT"
    ):
        raise RecursiveTwinPresentationWriteTwinCollectiveFullscreenMoNdTwinComposeError(
            "invariant: honesty flags must remain false / REJECT"
        )

    notes.extend(
        (
            "twin_written=false",
            "prompts_injected=false",
            "merge_executed=false",
            "live_dispatch_authorized=false",
            "draft_written=false",
            "analysis_written=false",
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
            "inventory_mutated=false",
            "charge_executed=false",
            "record_persisted=false",
            "purchase_executed=false",
            "hosted=false",
            "remote_fetched=false",
            "production_router_verdict=REJECT",
        )
    )

    surface = TwinPresentationSurface(
        view_mode=str(view_mode),
        open_requested=open_requested,
        merge_to_parent_preview=merge_to_parent_preview,
        presented_insight_count=len(presented_insights),
        presented_question_count=len(presented_questions),
        presentation_sections=tuple(presentation_sections),
        presentation_ready=presentation_ready,
    )

    return RecursiveTwinPresentationWriteTwinCollectiveFullscreenMoNdTwinCompose(
        session_id=session,
        parent_asset_id=parent,
        week_id=week,
        asset_id=asset,
        title=title,
        account_id=account,
        twin=twin_c,
        presentation=surface,
        write_pack=wp,
        session_aligned=session_aligned,
        parent_aligned=parent_aligned,
        pack_ready=pack_ready,
        twin_written=False,
        prompts_injected=False,
        merge_executed=False,
        live_dispatch_authorized=False,
        draft_written=False,
        analysis_written=False,
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
        inventory_mutated=False,
        charge_executed=False,
        record_persisted=False,
        purchase_executed=False,
        hosted=False,
        remote_fetched=False,
        production_router_verdict="REJECT",
        notes=tuple(notes),
        authority=(
            "recursive_twin_presentation_write_twin_collective_fullscreen_mo_nd_twin_compose_advisory"
        ),
    )


def format_recursive_twin_presentation_write_twin_collective_fullscreen_mo_nd_twin_summary(
    c: RecursiveTwinPresentationWriteTwinCollectiveFullscreenMoNdTwinCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"presentation_ready={c.presentation.presentation_ready} · "
        f"write_ready={c.write_pack.pack_ready} · "
        f"view_mode={c.presentation.view_mode} · "
        f"parent_aligned={c.parent_aligned} · "
        f"verdict={c.production_router_verdict} · "
        "twin_written=false · merge_executed=false · draft_written=false"
    )


__all__ = [
    "RecursiveTwinPresentationWriteTwinCollectiveFullscreenMoNdTwinCompose",
    "RecursiveTwinPresentationWriteTwinCollectiveFullscreenMoNdTwinComposeError",
    "compose_recursive_twin_presentation_write_twin_collective_fullscreen_mo_nd_twin",
    "format_recursive_twin_presentation_write_twin_collective_fullscreen_mo_nd_twin_summary",
]
