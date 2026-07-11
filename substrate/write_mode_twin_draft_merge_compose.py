"""Write-mode twin draft merge compose (pure).

draft_written, merge_executed, store_mutated always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class WriteModeTwinDraftMergeComposeError(ValueError):
    """Fail-closed validation for write-mode twin draft merge."""


@dataclass(frozen=True)
class WriteModeTwinDraftMergeCompose:
    draft_id: str
    parent_asset_ids: tuple[str, ...]
    sections: tuple[str, ...]
    section_count: int
    insight_count: int
    question_count: int
    draft_ready: bool
    draft_written: bool
    merge_executed: bool
    store_mutated: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "draft_id": self.draft_id,
            "parent_asset_ids": list(self.parent_asset_ids),
            "sections": list(self.sections),
            "section_count": self.section_count,
            "insight_count": self.insight_count,
            "question_count": self.question_count,
            "draft_ready": self.draft_ready,
            "draft_written": False,
            "merge_executed": False,
            "store_mutated": False,
            "notes": list(self.notes),
            "authority": "write_mode_twin_draft_merge_compose_advisory",
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WriteModeTwinDraftMergeComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_write_mode_twin_draft_merge(
    *,
    draft_id: object,
    slices: object,
    operator_ack: object,
    base_draft_html: object | None = None,
) -> WriteModeTwinDraftMergeCompose:
    """Build provisional write draft from twin slices. Never writes assets."""
    if not isinstance(operator_ack, bool):
        raise WriteModeTwinDraftMergeComposeError(
            "operator_ack must be an explicit boolean"
        )
    did = _require_nonempty(draft_id, field="draft_id")
    if not isinstance(slices, list) or len(slices) == 0:
        raise WriteModeTwinDraftMergeComposeError(
            "slices must be a non-empty array"
        )

    notes: list[str] = [
        "draft_written=false — provisional write draft not persisted",
        "merge_executed=false — published write not mutated",
        "store_mutated=false",
        "twin content is caller-supplied only (no invent)",
    ]

    sections: list[str] = []
    if base_draft_html is not None:
        if not isinstance(base_draft_html, str) or not base_draft_html.strip():
            raise WriteModeTwinDraftMergeComposeError(
                "base_draft_html must be non-empty string when set"
            )
        sections.append(
            f'<section data-role="base-draft" data-draft="{did}">'
            f"{base_draft_html.strip()}</section>"
        )
    else:
        notes.append("base_draft_html absent — twin-only draft scaffold")

    parent_asset_ids: list[str] = []
    seen: set[str] = set()
    insight_count = 0
    question_count = 0

    for i, sl in enumerate(slices):
        if not isinstance(sl, dict):
            raise WriteModeTwinDraftMergeComposeError(
                f"slices[{i}] must be an object"
            )
        parent = _require_nonempty(
            sl.get("parent_asset_id"), field=f"slices[{i}].parent_asset_id"
        )
        if parent in seen:
            raise WriteModeTwinDraftMergeComposeError(
                f"duplicate parent_asset_id: {parent}"
            )
        seen.add(parent)
        parent_asset_ids.append(parent)
        insights = sl.get("insights")
        questions = sl.get("questions")
        if not isinstance(insights, list):
            raise WriteModeTwinDraftMergeComposeError(
                f"slices[{i}].insights must be an array"
            )
        if not isinstance(questions, list):
            raise WriteModeTwinDraftMergeComposeError(
                f"slices[{i}].questions must be an array"
            )
        for j, v in enumerate(insights):
            ins = _require_nonempty(v, field=f"slices[{i}].insights[{j}]")
            sections.append(
                f'<section data-role="twin-insight" data-parent="{parent}">'
                f"{ins}</section>"
            )
            insight_count += 1
        for j, v in enumerate(questions):
            q = _require_nonempty(v, field=f"slices[{i}].questions[{j}]")
            sections.append(
                f'<section data-role="twin-question" data-parent="{parent}">'
                f"{q}</section>"
            )
            question_count += 1

    has_twin = insight_count + question_count >= 1
    draft_ready = operator_ack and has_twin
    notes.append(
        f"parents={len(parent_asset_ids)} · insights={insight_count} · "
        f"questions={question_count}"
    )
    if not operator_ack:
        notes.append("draft_ready=false — operator_ack required")
    elif not has_twin:
        notes.append(
            "draft_ready=false — no twin insights/questions (no invent)"
        )
    else:
        notes.append(
            f"draft_ready=true · sections={len(sections)} (provisional only)"
        )
    notes.extend(
        ("draft_written=false", "merge_executed=false", "store_mutated=false")
    )

    return WriteModeTwinDraftMergeCompose(
        draft_id=did,
        parent_asset_ids=tuple(parent_asset_ids),
        sections=tuple(sections),
        section_count=len(sections),
        insight_count=insight_count,
        question_count=question_count,
        draft_ready=draft_ready,
        draft_written=False,
        merge_executed=False,
        store_mutated=False,
        notes=tuple(notes),
        authority="write_mode_twin_draft_merge_compose_advisory",
    )


__all__ = [
    "WriteModeTwinDraftMergeCompose",
    "WriteModeTwinDraftMergeComposeError",
    "compose_write_mode_twin_draft_merge",
]
