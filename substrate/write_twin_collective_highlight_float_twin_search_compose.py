"""Write twin collective analysis over highlight-float twin-search competition (pure).

draft_written / analysis_written / merge_executed always False.
live_dispatched / remote_index_queried / twin_written always False.
production_router_verdict always REJECT.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.highlight_float_twin_search_competition_compose import (
    HighlightFloatTwinSearchCompetitionCompose,
    HighlightFloatTwinSearchCompetitionComposeError,
    compose_highlight_float_twin_search_competition,
)
from substrate.write_mode_twin_collective_analysis_compose import (
    WriteModeTwinCollectiveAnalysisCompose,
    WriteModeTwinCollectiveAnalysisComposeError,
    compose_write_mode_twin_collective_analysis,
)


class WriteTwinCollectiveHighlightFloatTwinSearchComposeError(ValueError):
    """Fail-closed validation for write twin + highlight float twin-search."""


@dataclass(frozen=True)
class WriteTwinCollectiveHighlightFloatTwinSearchCompose:
    session_id: str
    draft_id: str
    parent_asset_id: str
    write: WriteModeTwinCollectiveAnalysisCompose
    highlight_pack: HighlightFloatTwinSearchCompetitionCompose
    pack_ready: bool
    draft_written: bool
    analysis_written: bool
    merge_executed: bool
    store_mutated: bool
    live_dispatched: bool
    live_dispatch_authorized: bool
    remote_fetched: bool
    remote_index_queried: bool
    twin_written: bool
    production_router_verdict: str
    live_router_authorized: bool
    purchase_executed: bool
    hosted: bool
    backlog_mutated: bool
    pack_dispatched: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "draft_id": self.draft_id,
            "parent_asset_id": self.parent_asset_id,
            "write": self.write.to_dict(),
            "highlight_pack": self.highlight_pack.to_dict(),
            "pack_ready": self.pack_ready,
            "draft_written": False,
            "analysis_written": False,
            "merge_executed": False,
            "store_mutated": False,
            "live_dispatched": False,
            "live_dispatch_authorized": False,
            "remote_fetched": False,
            "remote_index_queried": False,
            "twin_written": False,
            "production_router_verdict": "REJECT",
            "live_router_authorized": False,
            "purchase_executed": False,
            "hosted": False,
            "backlog_mutated": False,
            "pack_dispatched": False,
            "notes": list(self.notes),
            "authority": (
                "write_twin_collective_highlight_float_twin_search_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WriteTwinCollectiveHighlightFloatTwinSearchComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_write_twin_collective_highlight_float_twin_search(
    *,
    write: object,
    highlight_pack: object,
    operator_ack: object,
    require_both: object | None = None,
) -> WriteTwinCollectiveHighlightFloatTwinSearchCompose:
    """Write twin collective + highlight float twin-search. Never writes/dispatches."""
    if not isinstance(operator_ack, bool):
        raise WriteTwinCollectiveHighlightFloatTwinSearchComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(write, dict):
        raise WriteTwinCollectiveHighlightFloatTwinSearchComposeError(
            "write must be an object"
        )
    if not isinstance(highlight_pack, dict):
        raise WriteTwinCollectiveHighlightFloatTwinSearchComposeError(
            "highlight_pack must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise WriteTwinCollectiveHighlightFloatTwinSearchComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "draft_written=false · analysis_written=false · merge_executed=false",
        "live_dispatched=false · remote_index_queried=false · twin_written=false",
        "production_router_verdict=REJECT · live_router_authorized=false",
    ]

    try:
        write_pack = compose_write_mode_twin_collective_analysis(
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
        raise WriteTwinCollectiveHighlightFloatTwinSearchComposeError(
            str(e)
        ) from e
    notes.extend(f"[write] {n}" for n in write_pack.notes)

    try:
        hl_pack = compose_highlight_float_twin_search_competition(
            highlight=highlight_pack.get("highlight"),
            twin_search_pack=highlight_pack.get("twin_search_pack"),
            operator_ack=operator_ack,
            seed_search_from_highlight=highlight_pack.get(
                "seed_search_from_highlight"
            ),
            require_both=highlight_pack.get("require_both"),
        )
    except HighlightFloatTwinSearchCompetitionComposeError as e:
        raise WriteTwinCollectiveHighlightFloatTwinSearchComposeError(
            str(e)
        ) from e
    notes.extend(f"[highlight_pack] {n}" for n in hl_pack.notes)

    session = _require_nonempty(write_pack.session_id, field="session_id")
    draft = _require_nonempty(write_pack.draft_id, field="draft_id")
    parent = _require_nonempty(write_pack.parent_asset_id, field="parent_asset_id")

    session_aligned = hl_pack.session_id == session
    parent_aligned = hl_pack.parent_asset_id == parent
    if not session_aligned:
        notes.append(
            "session_id mismatch between write and highlight_pack — pack_ready blocked"
        )
    if not parent_aligned:
        notes.append(
            "parent_asset_id mismatch between write and highlight_pack — pack_ready blocked"
        )

    if require:
        pack_ready = (
            session_aligned
            and parent_aligned
            and write_pack.pack_ready is True
            and hl_pack.pack_ready is True
            and hl_pack.production_router_verdict == "REJECT"
            and write_pack.draft_written is False
            and write_pack.analysis_written is False
            and hl_pack.remote_index_queried is False
            and operator_ack is True
        )
    else:
        pack_ready = (
            session_aligned
            and parent_aligned
            and operator_ack is True
            and hl_pack.production_router_verdict == "REJECT"
            and (write_pack.pack_ready is True or hl_pack.pack_ready is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — write twin collective + highlight float twin-search ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — write, highlight_pack, alignment, or operator_ack gate open"
        )

    if (
        write_pack.draft_written is not False
        or write_pack.analysis_written is not False
        or write_pack.merge_executed is not False
        or write_pack.store_mutated is not False
        or write_pack.live_dispatched is not False
        or hl_pack.live_dispatched is not False
        or hl_pack.remote_index_queried is not False
        or hl_pack.twin_written is not False
        or hl_pack.production_router_verdict != "REJECT"
    ):
        raise WriteTwinCollectiveHighlightFloatTwinSearchComposeError(
            "invariant: honesty flags must remain false"
        )

    notes.extend(
        (
            "draft_written=false",
            "analysis_written=false",
            "merge_executed=false",
            "store_mutated=false",
            "live_dispatched=false",
            "live_dispatch_authorized=false",
            "remote_fetched=false",
            "remote_index_queried=false",
            "twin_written=false",
            "production_router_verdict=REJECT",
            "live_router_authorized=false",
            "purchase_executed=false",
            "hosted=false",
            "backlog_mutated=false",
            "pack_dispatched=false",
        )
    )

    return WriteTwinCollectiveHighlightFloatTwinSearchCompose(
        session_id=session,
        draft_id=draft,
        parent_asset_id=parent,
        write=write_pack,
        highlight_pack=hl_pack,
        pack_ready=pack_ready,
        draft_written=False,
        analysis_written=False,
        merge_executed=False,
        store_mutated=False,
        live_dispatched=False,
        live_dispatch_authorized=False,
        remote_fetched=False,
        remote_index_queried=False,
        twin_written=False,
        production_router_verdict="REJECT",
        live_router_authorized=False,
        purchase_executed=False,
        hosted=False,
        backlog_mutated=False,
        pack_dispatched=False,
        notes=tuple(notes),
        authority=(
            "write_twin_collective_highlight_float_twin_search_compose_advisory"
        ),
    )


def format_write_twin_collective_highlight_float_twin_search_summary(
    c: WriteTwinCollectiveHighlightFloatTwinSearchCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"write_ready={c.write.pack_ready} · "
        f"highlight_ready={c.highlight_pack.pack_ready} · "
        f"verdict={c.production_router_verdict} · "
        f"draft_written=false · analysis_written=false · remote_index_queried=false"
    )


__all__ = [
    "WriteTwinCollectiveHighlightFloatTwinSearchCompose",
    "WriteTwinCollectiveHighlightFloatTwinSearchComposeError",
    "compose_write_twin_collective_highlight_float_twin_search",
    "format_write_twin_collective_highlight_float_twin_search_summary",
]
