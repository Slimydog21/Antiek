"""Twin substrate cross-asset merge compose (pure).

merge_executed, twin_written, store_mutated always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class TwinSubstrateCrossAssetMergeComposeError(ValueError):
    """Fail-closed validation for twin cross-asset merge."""


@dataclass(frozen=True)
class TwinSubstrateCrossAssetMergeCompose:
    pack_id: str
    parent_asset_ids: tuple[str, ...]
    parent_count: int
    insight_count: int
    question_count: int
    insights: tuple[str, ...]
    questions: tuple[str, ...]
    merge_ready: bool
    merge_executed: bool
    twin_written: bool
    store_mutated: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "pack_id": self.pack_id,
            "parent_asset_ids": list(self.parent_asset_ids),
            "parent_count": self.parent_count,
            "insight_count": self.insight_count,
            "question_count": self.question_count,
            "insights": list(self.insights),
            "questions": list(self.questions),
            "merge_ready": self.merge_ready,
            "merge_executed": False,
            "twin_written": False,
            "store_mutated": False,
            "notes": list(self.notes),
            "authority": "twin_substrate_cross_asset_merge_compose_advisory",
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TwinSubstrateCrossAssetMergeComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_twin_substrate_cross_asset_merge(
    *,
    pack_id: object,
    slices: object,
    operator_ack: object,
) -> TwinSubstrateCrossAssetMergeCompose:
    """Propose merging twin substrate across ≥2 parents. Never writes/merges."""
    if not isinstance(operator_ack, bool):
        raise TwinSubstrateCrossAssetMergeComposeError(
            "operator_ack must be an explicit boolean"
        )
    pid = _require_nonempty(pack_id, field="pack_id")
    if not isinstance(slices, list) or len(slices) < 2:
        raise TwinSubstrateCrossAssetMergeComposeError(
            "slices must be an array of at least 2 parent twins"
        )

    notes: list[str] = [
        "merge_executed=false — cross-asset twin merge is intent only",
        "twin_written=false — twin documents not created/updated here",
        "store_mutated=false",
        "insights/questions are caller-supplied only (no invent)",
    ]

    parent_asset_ids: list[str] = []
    seen: set[str] = set()
    insights: list[str] = []
    questions: list[str] = []

    for i, sl in enumerate(slices):
        if not isinstance(sl, dict):
            raise TwinSubstrateCrossAssetMergeComposeError(
                f"slices[{i}] must be an object"
            )
        parent = _require_nonempty(
            sl.get("parent_asset_id"), field=f"slices[{i}].parent_asset_id"
        )
        if parent in seen:
            raise TwinSubstrateCrossAssetMergeComposeError(
                f"duplicate parent_asset_id: {parent}"
            )
        seen.add(parent)
        parent_asset_ids.append(parent)
        if sl.get("twin_asset_id") is not None:
            _require_nonempty(
                sl.get("twin_asset_id"), field=f"slices[{i}].twin_asset_id"
            )
        ins = sl.get("insights")
        qs = sl.get("questions")
        if not isinstance(ins, list):
            raise TwinSubstrateCrossAssetMergeComposeError(
                f"slices[{i}].insights must be an array"
            )
        if not isinstance(qs, list):
            raise TwinSubstrateCrossAssetMergeComposeError(
                f"slices[{i}].questions must be an array"
            )
        for j, v in enumerate(ins):
            insights.append(
                _require_nonempty(v, field=f"slices[{i}].insights[{j}]")
            )
        for j, v in enumerate(qs):
            questions.append(
                _require_nonempty(v, field=f"slices[{i}].questions[{j}]")
            )

    parent_count = len(parent_asset_ids)
    insight_count = len(insights)
    question_count = len(questions)
    notes.append(
        f"parents={parent_count} · insights={insight_count} · questions={question_count}"
    )

    has_substrate = insight_count + question_count >= 1
    merge_ready = operator_ack and parent_count >= 2 and has_substrate
    if not operator_ack:
        notes.append("merge_ready=false — operator_ack required")
    elif not has_substrate:
        notes.append(
            "merge_ready=false — no insights/questions (no invent substrate)"
        )
    else:
        notes.append("merge_ready=true — provisional cross-asset twin pack")

    notes.extend(
        ("merge_executed=false", "twin_written=false", "store_mutated=false")
    )

    return TwinSubstrateCrossAssetMergeCompose(
        pack_id=pid,
        parent_asset_ids=tuple(parent_asset_ids),
        parent_count=parent_count,
        insight_count=insight_count,
        question_count=question_count,
        insights=tuple(insights),
        questions=tuple(questions),
        merge_ready=merge_ready,
        merge_executed=False,
        twin_written=False,
        store_mutated=False,
        notes=tuple(notes),
        authority="twin_substrate_cross_asset_merge_compose_advisory",
    )


__all__ = [
    "TwinSubstrateCrossAssetMergeCompose",
    "TwinSubstrateCrossAssetMergeComposeError",
    "compose_twin_substrate_cross_asset_merge",
]
