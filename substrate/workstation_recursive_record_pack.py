"""Workstation recursive record pack (pure, advisory).

Packs caller-supplied insights/questions/highlights for prompt context.
record_persisted and prompts_injected are always False.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Literal

RecordKind = Literal[
    "insight", "question", "highlight", "finding", "open_thread"
]

VALID_KINDS = frozenset(
    {"insight", "question", "highlight", "finding", "open_thread"}
)


class WorkstationRecursiveRecordPackError(ValueError):
    """Fail-closed validation for workstation record pack."""


@dataclass(frozen=True)
class WorkstationRecursiveRecordPack:
    session_id: str
    item_count: int
    by_kind: dict[str, int]
    prompt_context_lines: tuple[str, ...]
    pack_ready: bool
    record_persisted: bool
    prompts_injected: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "item_count": self.item_count,
            "by_kind": dict(self.by_kind),
            "prompt_context_lines": list(self.prompt_context_lines),
            "pack_ready": self.pack_ready,
            "record_persisted": False,
            "prompts_injected": False,
            "notes": list(self.notes),
            "authority": "workstation_recursive_record_pack_advisory",
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorkstationRecursiveRecordPackError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_workstation_recursive_record_pack(
    *,
    session_id: object,
    items: object,
    max_context_lines: object | None = None,
) -> WorkstationRecursiveRecordPack:
    """Pack workstation records. Never persists or injects prompts."""
    sid = _require_nonempty(session_id, field="session_id")
    if not isinstance(items, list):
        raise WorkstationRecursiveRecordPackError("items must be an array")

    max_lines: int | None = None
    if max_context_lines is not None:
        if (
            isinstance(max_context_lines, bool)
            or not isinstance(max_context_lines, int)
            or max_context_lines <= 0
        ):
            raise WorkstationRecursiveRecordPackError(
                "max_context_lines must be a positive integer when set"
            )
        max_lines = max_context_lines

    notes: list[str] = [
        "record_persisted=false — pack intent only",
        "prompts_injected=false — does not mutate live prompts",
        "record texts are caller-supplied only (no invent)",
    ]
    by_kind: dict[str, int] = {
        "insight": 0,
        "question": 0,
        "highlight": 0,
        "finding": 0,
        "open_thread": 0,
    }
    seen: set[str] = set()
    scored: list[tuple[float, int, str]] = []

    for i, it in enumerate(items):
        if not isinstance(it, dict):
            raise WorkstationRecursiveRecordPackError(
                f"items[{i}] must be an object"
            )
        rid = _require_nonempty(it.get("record_id"), field=f"items[{i}].record_id")
        if rid in seen:
            raise WorkstationRecursiveRecordPackError(
                f"duplicate record_id: {rid}"
            )
        seen.add(rid)
        kind = it.get("kind")
        if kind not in VALID_KINDS:
            raise WorkstationRecursiveRecordPackError(
                f"items[{i}].kind must be insight|question|highlight|finding|open_thread"
            )
        by_kind[kind] += 1  # type: ignore[index]
        text = _require_nonempty(it.get("text"), field=f"items[{i}].text")

        weight = 0.5
        w = it.get("weight")
        if w is not None:
            if isinstance(w, bool) or not isinstance(w, (int, float)):
                raise WorkstationRecursiveRecordPackError(
                    f"items[{i}].weight must be finite in [0, 1] when set"
                )
            wf = float(w)
            if not math.isfinite(wf) or wf < 0 or wf > 1:
                raise WorkstationRecursiveRecordPackError(
                    f"items[{i}].weight must be finite in [0, 1] when set"
                )
            weight = wf

        asset_part = ""
        if it.get("asset_id") is not None:
            aid = _require_nonempty(
                it.get("asset_id"), field=f"items[{i}].asset_id"
            )
            asset_part = f" @{aid}"

        line = f"[{kind}]{asset_part} {text}"
        scored.append((weight, i, line))

    scored.sort(key=lambda t: (-t[0], t[1]))
    lines = [t[2] for t in scored]
    if max_lines is not None and len(lines) > max_lines:
        notes.append(
            f"max_context_lines={max_lines} — truncated from {len(lines)}"
        )
        lines = lines[:max_lines]

    item_count = len(items)
    pack_ready = item_count >= 1
    if not pack_ready:
        notes.append("pack_ready=false — empty items (no invent records)")
    else:
        notes.append(
            f"pack_ready=true · items={item_count} · context_lines={len(lines)}"
        )
    notes.append("record_persisted=false")
    notes.append("prompts_injected=false")

    return WorkstationRecursiveRecordPack(
        session_id=sid,
        item_count=item_count,
        by_kind=by_kind,
        prompt_context_lines=tuple(lines),
        pack_ready=pack_ready,
        record_persisted=False,
        prompts_injected=False,
        notes=tuple(notes),
        authority="workstation_recursive_record_pack_advisory",
    )


__all__ = [
    "WorkstationRecursiveRecordPack",
    "WorkstationRecursiveRecordPackError",
    "compose_workstation_recursive_record_pack",
]
