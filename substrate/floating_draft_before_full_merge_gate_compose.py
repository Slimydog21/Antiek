"""Floating draft-before-full-merge gate (pure).

Provisional combined draft first; optional promote to full-merge intent with
separate full_merge_ack. draft_written, merge_executed, live_dispatched always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from substrate.floating_instance_tray_compose import (
    FloatingInstanceTrayCompose,
    FloatingInstanceTrayComposeError,
    compose_floating_instance_tray,
)
from substrate.floating_research_draft_combined_document import (
    FloatingResearchDraftCombinedDocumentError,
    ProvisionalCombinedDraft,
    compose_floating_research_draft_combined_document,
)

MergeStage = Literal["draft_only", "promote_full_merge"]
VALID_STAGES = frozenset(("draft_only", "promote_full_merge"))


class FloatingDraftBeforeFullMergeGateComposeError(ValueError):
    """Fail-closed validation for draft-before-full-merge gate."""


@dataclass(frozen=True)
class FloatingDraftBeforeFullMergeGateCompose:
    session_id: str
    parent_asset_id: str
    stage: MergeStage
    draft: ProvisionalCombinedDraft
    tray: FloatingInstanceTrayCompose | None
    gate_ready: bool
    full_merge_intent_ready: bool
    draft_written: bool
    merge_executed: bool
    live_dispatched: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "parent_asset_id": self.parent_asset_id,
            "stage": self.stage,
            "draft": self.draft.to_dict(),
            "tray": self.tray.to_dict() if self.tray else None,
            "gate_ready": self.gate_ready,
            "full_merge_intent_ready": self.full_merge_intent_ready,
            "draft_written": False,
            "merge_executed": False,
            "live_dispatched": False,
            "notes": list(self.notes),
            "authority": (
                "floating_draft_before_full_merge_gate_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FloatingDraftBeforeFullMergeGateComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_floating_draft_before_full_merge_gate(
    *,
    session_id: object,
    parent_asset_id: object,
    sources: object,
    stage: object,
    operator_ack: object,
    parent_excerpt: object | None = None,
    full_merge_ack: object | None = None,
) -> FloatingDraftBeforeFullMergeGateCompose:
    """Draft first, then optional full-merge intent. Never writes or merges."""
    if not isinstance(operator_ack, bool):
        raise FloatingDraftBeforeFullMergeGateComposeError(
            "operator_ack must be an explicit boolean"
        )
    if stage not in VALID_STAGES:
        raise FloatingDraftBeforeFullMergeGateComposeError(
            "stage must be draft_only or promote_full_merge"
        )
    stage_s: MergeStage = stage  # type: ignore[assignment]
    session = _require_nonempty(session_id, field="session_id")
    parent = _require_nonempty(parent_asset_id, field="parent_asset_id")
    if not isinstance(sources, list) or len(sources) == 0:
        raise FloatingDraftBeforeFullMergeGateComposeError(
            "sources must be a non-empty array"
        )

    notes: list[str] = [
        "draft_written=false — provisional combined document never persisted here",
        "merge_executed=false — parent asset never mutated here",
        "live_dispatched=false",
        "full merge requires separate full_merge_ack after draft_ready",
    ]

    try:
        draft = compose_floating_research_draft_combined_document(
            parent_asset_id=parent,
            sources=sources,
            operator_ack=operator_ack,
            parent_excerpt=parent_excerpt,
        )
    except FloatingResearchDraftCombinedDocumentError as e:
        raise FloatingDraftBeforeFullMergeGateComposeError(str(e)) from e
    notes.extend(f"[draft] {n}" for n in draft.notes)

    members: list[dict[str, Any]] = []
    for s in sources:
        if not isinstance(s, dict):
            raise FloatingDraftBeforeFullMergeGateComposeError(
                "sources entries must be objects"
            )
        members.append(
            {
                "instance_id": s.get("instance_id"),
                "parent_asset_id": s.get("parent_asset_id"),
                "status": s.get("status"),
            }
        )

    tray: FloatingInstanceTrayCompose | None = None
    full_merge_intent_ready = False
    gate_ready = False

    if stage_s == "draft_only":
        if len(sources) == 1:
            try:
                tray = compose_floating_instance_tray(
                    parent_asset_id=parent,
                    members=members,
                    selected_instance_ids=[members[0]["instance_id"]],
                    action="draft_merge_one",
                    operator_ack=operator_ack,
                )
            except FloatingInstanceTrayComposeError as e:
                raise FloatingDraftBeforeFullMergeGateComposeError(
                    str(e)
                ) from e
            notes.extend(f"[tray] {n}" for n in tray.notes)
            gate_ready = (
                draft.draft_ready is True
                and operator_ack is True
                and tray.tray_ready is True
            )
        else:
            notes.append(
                "multi-source draft — tray single-merge skipped; draft compose only"
            )
            gate_ready = draft.draft_ready is True and operator_ack is True
        if gate_ready:
            notes.append(
                "gate_ready=true — draft-before-merge preview ready; "
                "still draft_written=false"
            )
        else:
            notes.append(
                "gate_ready=false — draft not ready or operator_ack missing"
            )
    else:
        if not isinstance(full_merge_ack, bool):
            raise FloatingDraftBeforeFullMergeGateComposeError(
                "full_merge_ack must be an explicit boolean when "
                "stage=promote_full_merge"
            )
        if not draft.draft_ready:
            notes.append(
                "full_merge_intent blocked — draft_ready required before promote"
            )
        if not operator_ack:
            notes.append("full_merge_intent blocked — operator_ack required")
        if not full_merge_ack:
            notes.append(
                "full_merge_intent blocked — full_merge_ack required "
                "(separate from draft ack)"
            )

        all_completed = all(
            isinstance(s, dict) and s.get("status") == "completed"
            for s in sources
        )
        if not all_completed:
            notes.append(
                "full_merge_intent blocked — all sources must be completed "
                "for full merge"
            )

        if len(sources) == 1 and all_completed:
            try:
                tray = compose_floating_instance_tray(
                    parent_asset_id=parent,
                    members=members,
                    selected_instance_ids=[members[0]["instance_id"]],
                    action="full_merge_one",
                    operator_ack=full_merge_ack and operator_ack,
                )
            except FloatingInstanceTrayComposeError as e:
                raise FloatingDraftBeforeFullMergeGateComposeError(
                    str(e)
                ) from e
            notes.extend(f"[tray] {n}" for n in tray.notes)
            full_merge_intent_ready = (
                draft.draft_ready is True
                and operator_ack is True
                and full_merge_ack is True
                and tray.tray_ready is True
            )
        elif len(sources) > 1:
            notes.append(
                "multi-source full merge uses collective analysis path — "
                "tray full_merge_one skipped"
            )
            full_merge_intent_ready = (
                draft.draft_ready is True
                and operator_ack is True
                and full_merge_ack is True
                and all_completed is True
            )
        else:
            full_merge_intent_ready = False

        gate_ready = full_merge_intent_ready
        if full_merge_intent_ready:
            notes.append(
                "full_merge_intent_ready=true — intent only; merge_executed=false"
            )
            notes.append(
                "gate_ready=true — promote path ready; still merge_executed=false"
            )
        else:
            notes.append("full_merge_intent_ready=false")
            notes.append("gate_ready=false — promote gates open")

    notes.extend(
        (
            "draft_written=false",
            "merge_executed=false",
            "live_dispatched=false",
        )
    )

    return FloatingDraftBeforeFullMergeGateCompose(
        session_id=session,
        parent_asset_id=parent,
        stage=stage_s,
        draft=draft,
        tray=tray,
        gate_ready=gate_ready,
        full_merge_intent_ready=full_merge_intent_ready,
        draft_written=False,
        merge_executed=False,
        live_dispatched=False,
        notes=tuple(notes),
        authority="floating_draft_before_full_merge_gate_compose_advisory",
    )


def format_floating_draft_before_full_merge_gate_summary(
    c: FloatingDraftBeforeFullMergeGateCompose,
) -> str:
    return (
        f"gate_ready={c.gate_ready} · stage={c.stage} · "
        f"draft_ready={c.draft.draft_ready} · "
        f"full_merge_intent_ready={c.full_merge_intent_ready} · "
        f"draft_written=false · merge_executed=false · live_dispatched=false"
    )


__all__ = [
    "FloatingDraftBeforeFullMergeGateCompose",
    "FloatingDraftBeforeFullMergeGateComposeError",
    "compose_floating_draft_before_full_merge_gate",
    "format_floating_draft_before_full_merge_gate_summary",
]
