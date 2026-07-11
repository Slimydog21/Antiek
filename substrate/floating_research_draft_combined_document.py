"""Floating research provisional combined draft document (pure).

Parent excerpt + floating findings → provisional draft sections.
draft_written and merge_executed always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class FloatingResearchDraftCombinedDocumentError(ValueError):
    """Fail-closed validation for provisional combined draft."""


@dataclass(frozen=True)
class ProvisionalCombinedDraft:
    parent_asset_id: str
    instance_ids: tuple[str, ...]
    sections: tuple[str, ...]
    section_count: int
    draft_ready: bool
    operator_ack: bool
    draft_written: bool
    merge_executed: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "parent_asset_id": self.parent_asset_id,
            "instance_ids": list(self.instance_ids),
            "sections": list(self.sections),
            "section_count": self.section_count,
            "draft_ready": self.draft_ready,
            "operator_ack": self.operator_ack,
            "draft_written": False,
            "merge_executed": False,
            "notes": list(self.notes),
            "authority": "floating_research_draft_combined_document_advisory",
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FloatingResearchDraftCombinedDocumentError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_floating_research_draft_combined_document(
    *,
    parent_asset_id: object,
    sources: object,
    operator_ack: object,
    parent_excerpt: object | None = None,
) -> ProvisionalCombinedDraft:
    """Build provisional combined draft. Never writes assets."""
    if not isinstance(operator_ack, bool):
        raise FloatingResearchDraftCombinedDocumentError(
            "operator_ack must be an explicit boolean"
        )
    parent = _require_nonempty(parent_asset_id, field="parent_asset_id")
    if not isinstance(sources, list) or len(sources) == 0:
        raise FloatingResearchDraftCombinedDocumentError(
            "sources must be a non-empty array"
        )

    notes: list[str] = [
        "draft_written=false — provisional combined document not persisted",
        "merge_executed=false — parent asset not mutated",
        "section content is caller-supplied only (no invent)",
    ]
    sections: list[str] = []
    if parent_excerpt is not None:
        if not isinstance(parent_excerpt, str) or not parent_excerpt.strip():
            raise FloatingResearchDraftCombinedDocumentError(
                "parent_excerpt must be non-empty string when set"
            )
        sections.append(
            f'<section data-role="parent" data-asset="{parent}">'
            f"{parent_excerpt.strip()}</section>"
        )
    else:
        notes.append("parent_excerpt absent — draft scaffold without parent body")

    instance_ids: list[str] = []
    seen: set[str] = set()
    for i, s in enumerate(sources):
        if not isinstance(s, dict):
            raise FloatingResearchDraftCombinedDocumentError(
                f"sources[{i}] must be an object"
            )
        iid = _require_nonempty(
            s.get("instance_id"), field=f"sources[{i}].instance_id"
        )
        p = _require_nonempty(
            s.get("parent_asset_id"), field=f"sources[{i}].parent_asset_id"
        )
        if p != parent:
            raise FloatingResearchDraftCombinedDocumentError(
                "all sources must share parent_asset_id"
            )
        status = s.get("status")
        if status not in ("proposed", "open", "completed"):
            raise FloatingResearchDraftCombinedDocumentError(
                f"sources[{i}] status must be proposed|open|completed (not closed)"
            )
        if iid in seen:
            raise FloatingResearchDraftCombinedDocumentError(
                f"duplicate instance_id: {iid}"
            )
        seen.add(iid)
        instance_ids.append(iid)

        highlight = s.get("highlight")
        if highlight is not None:
            if not isinstance(highlight, str) or not highlight.strip():
                raise FloatingResearchDraftCombinedDocumentError(
                    f"sources[{i}].highlight must be non-empty string when set"
                )
            sections.append(
                f'<section data-role="highlight" data-instance="{iid}">'
                f"{highlight.strip()}</section>"
            )
        findings = s.get("findings")
        if findings is not None:
            if not isinstance(findings, list):
                raise FloatingResearchDraftCombinedDocumentError(
                    f"sources[{i}].findings must be string[] when set"
                )
            for j, f in enumerate(findings):
                if not isinstance(f, str) or not f.strip():
                    raise FloatingResearchDraftCombinedDocumentError(
                        f"sources[{i}].findings[{j}] must be non-empty string"
                    )
                sections.append(
                    f'<section data-role="finding" data-instance="{iid}">'
                    f"{f.strip()}</section>"
                )

    has_research = any(
        'data-role="highlight"' in sec or 'data-role="finding"' in sec
        for sec in sections
    )
    draft_ready = has_research
    if not draft_ready:
        notes.append(
            "draft_ready=false — no highlight/finding content (no invent sections)"
        )
    else:
        notes.append(
            f"draft_ready=true · sections={len(sections)} · "
            f"instances={len(instance_ids)}"
        )
    if not operator_ack:
        notes.append(
            "operator_ack=false — preview-only; still draft_written=false"
        )
    else:
        notes.append(
            "operator_ack=true — ack for draft preview only; still draft_written=false"
        )
    notes.append("draft_written=false")
    notes.append("merge_executed=false")

    return ProvisionalCombinedDraft(
        parent_asset_id=parent,
        instance_ids=tuple(instance_ids),
        sections=tuple(sections),
        section_count=len(sections),
        draft_ready=draft_ready,
        operator_ack=operator_ack,
        draft_written=False,
        merge_executed=False,
        notes=tuple(notes),
        authority="floating_research_draft_combined_document_advisory",
    )


__all__ = [
    "FloatingResearchDraftCombinedDocumentError",
    "ProvisionalCombinedDraft",
    "compose_floating_research_draft_combined_document",
]
