"""Write-mode twin draft + collective analysis pack (pure).

draft_written, analysis_written, merge_executed, store_mutated,
live_dispatched always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.chase_completion_collective_analysis_compose import (
    ChaseCompletionCollectiveAnalysisCompose,
    ChaseCompletionCollectiveAnalysisComposeError,
    compose_chase_completion_collective_analysis,
)
from substrate.write_mode_twin_draft_merge_compose import (
    WriteModeTwinDraftMergeCompose,
    WriteModeTwinDraftMergeComposeError,
    compose_write_mode_twin_draft_merge,
)


class WriteModeTwinCollectiveAnalysisComposeError(ValueError):
    """Fail-closed validation for write-mode twin + collective analysis."""


@dataclass(frozen=True)
class WriteModeTwinCollectiveAnalysisCompose:
    session_id: str
    draft_id: str
    parent_asset_id: str
    twin_draft: WriteModeTwinDraftMergeCompose
    collective_analysis: ChaseCompletionCollectiveAnalysisCompose
    pack_ready: bool
    draft_written: bool
    analysis_written: bool
    merge_executed: bool
    store_mutated: bool
    live_dispatched: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "draft_id": self.draft_id,
            "parent_asset_id": self.parent_asset_id,
            "twin_draft": self.twin_draft.to_dict(),
            "collective_analysis": self.collective_analysis.to_dict(),
            "pack_ready": self.pack_ready,
            "draft_written": False,
            "analysis_written": False,
            "merge_executed": False,
            "store_mutated": False,
            "live_dispatched": False,
            "notes": list(self.notes),
            "authority": (
                "write_mode_twin_collective_analysis_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WriteModeTwinCollectiveAnalysisComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_write_mode_twin_collective_analysis(
    *,
    session_id: object,
    draft_id: object,
    parent_asset_id: object,
    twin_slices: object,
    chase_slots: object,
    analysis_kind: object,
    operator_ack: object,
    base_draft_html: object | None = None,
    extra_findings: object | None = None,
    require_both: object | None = None,
) -> WriteModeTwinCollectiveAnalysisCompose:
    """Twin write draft + collective analysis. Never writes/merges assets."""
    if not isinstance(operator_ack, bool):
        raise WriteModeTwinCollectiveAnalysisComposeError(
            "operator_ack must be an explicit boolean"
        )
    session = _require_nonempty(session_id, field="session_id")
    draft = _require_nonempty(draft_id, field="draft_id")
    parent = _require_nonempty(parent_asset_id, field="parent_asset_id")
    both = True if require_both is None else require_both
    if not isinstance(both, bool):
        raise WriteModeTwinCollectiveAnalysisComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "draft_written=false — provisional write draft not persisted",
        "analysis_written=false — collective analysis intent only",
        "merge_executed=false — published write not mutated",
        "store_mutated=false · live_dispatched=false",
    ]

    try:
        twin_draft = compose_write_mode_twin_draft_merge(
            draft_id=draft,
            slices=twin_slices,
            operator_ack=operator_ack,
            base_draft_html=base_draft_html,
        )
    except WriteModeTwinDraftMergeComposeError as e:
        raise WriteModeTwinCollectiveAnalysisComposeError(str(e)) from e
    notes.extend(f"[twin_draft] {n}" for n in twin_draft.notes)

    if not isinstance(chase_slots, list) or len(chase_slots) < 2:
        raise WriteModeTwinCollectiveAnalysisComposeError(
            "chase_slots must be an array with at least 2 slots"
        )
    for i, s in enumerate(chase_slots):
        if not isinstance(s, dict):
            raise WriteModeTwinCollectiveAnalysisComposeError(
                f"chase_slots[{i}] must be an object"
            )
        p = s.get("parent_asset_id")
        if not isinstance(p, str) or p.strip() != parent:
            raise WriteModeTwinCollectiveAnalysisComposeError(
                "all chase_slots must share input.parent_asset_id"
            )

    try:
        collective_analysis = compose_chase_completion_collective_analysis(
            session_id=session,
            parent_asset_id=parent,
            slots=chase_slots,
            kind=analysis_kind,
            operator_ack=operator_ack,
            extra_findings=extra_findings,
        )
    except ChaseCompletionCollectiveAnalysisComposeError as e:
        raise WriteModeTwinCollectiveAnalysisComposeError(str(e)) from e
    notes.extend(f"[collective] {n}" for n in collective_analysis.notes)

    if both:
        pack_ready = (
            twin_draft.draft_ready is True
            and collective_analysis.analysis_ready is True
            and operator_ack is True
        )
    else:
        pack_ready = operator_ack is True and (
            twin_draft.draft_ready is True
            or collective_analysis.analysis_ready is True
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — twin write draft + collective analysis intent "
            "ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — twin draft, collective analysis, or "
            "operator_ack gate open"
        )

    if (
        twin_draft.draft_written is not False
        or twin_draft.merge_executed is not False
        or twin_draft.store_mutated is not False
        or collective_analysis.analysis_written is not False
        or collective_analysis.live_dispatched is not False
        or collective_analysis.pack_dispatched is not False
    ):
        raise WriteModeTwinCollectiveAnalysisComposeError(
            "invariant: honesty flags must remain false"
        )

    notes.extend(
        (
            "draft_written=false",
            "analysis_written=false",
            "merge_executed=false",
            "store_mutated=false",
            "live_dispatched=false",
        )
    )

    return WriteModeTwinCollectiveAnalysisCompose(
        session_id=session,
        draft_id=draft,
        parent_asset_id=parent,
        twin_draft=twin_draft,
        collective_analysis=collective_analysis,
        pack_ready=pack_ready,
        draft_written=False,
        analysis_written=False,
        merge_executed=False,
        store_mutated=False,
        live_dispatched=False,
        notes=tuple(notes),
        authority="write_mode_twin_collective_analysis_compose_advisory",
    )


def format_write_mode_twin_collective_analysis_summary(
    c: WriteModeTwinCollectiveAnalysisCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · draft_ready={c.twin_draft.draft_ready} · "
        f"analysis_ready={c.collective_analysis.analysis_ready} · "
        f"kind={c.collective_analysis.analysis.kind} · "
        f"draft_written=false · analysis_written=false · merge_executed=false"
    )


__all__ = [
    "WriteModeTwinCollectiveAnalysisCompose",
    "WriteModeTwinCollectiveAnalysisComposeError",
    "compose_write_mode_twin_collective_analysis",
    "format_write_mode_twin_collective_analysis_summary",
]
