"""Twin-side notes: insights and questions for every information asset.

The recursive note-taker vision: every asset has a twin substrate of
insights and questions that can be merged, referenced, and searched.
This module is the pure write/read path; graph promotion is optional
via ``insight_question.promote_*`` when the operator wants depth-graph
nodes.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Literal

from .store import EngagementStore

TwinKind = Literal["insight", "question"]


@dataclass(frozen=True)
class TwinNote:
    note_id: str
    asset_id: str
    kind: TwinKind
    text: str
    source_spawn_id: str | None = None
    investigation_id: str | None = None


def _note_id(asset_id: str, kind: TwinKind, text: str) -> str:
    canon = " ".join(text.strip().lower().split())
    digest = hashlib.sha256(f"{asset_id}:{kind}:{canon}".encode("utf-8")).hexdigest()[:16]
    return f"twin_{digest}"


def record_twin_insight(
    asset_id: str,
    text: str,
    *,
    store: EngagementStore,
    source_spawn_id: str | None = None,
    investigation_id: str | None = None,
) -> TwinNote:
    return _record(
        asset_id,
        text,
        kind="insight",
        store=store,
        source_spawn_id=source_spawn_id,
        investigation_id=investigation_id,
    )


def record_twin_question(
    asset_id: str,
    text: str,
    *,
    store: EngagementStore,
    source_spawn_id: str | None = None,
    investigation_id: str | None = None,
) -> TwinNote:
    return _record(
        asset_id,
        text,
        kind="question",
        store=store,
        source_spawn_id=source_spawn_id,
        investigation_id=investigation_id,
    )


def _record(
    asset_id: str,
    text: str,
    *,
    kind: TwinKind,
    store: EngagementStore,
    source_spawn_id: str | None,
    investigation_id: str | None,
) -> TwinNote:
    if not asset_id or not asset_id.strip():
        raise ValueError("asset_id is required")
    cleaned = text.strip()
    if not cleaned:
        raise ValueError("text is required")
    note = TwinNote(
        note_id=_note_id(asset_id.strip(), kind, cleaned),
        asset_id=asset_id.strip(),
        kind=kind,
        text=cleaned,
        source_spawn_id=source_spawn_id,
        investigation_id=investigation_id,
    )
    store.put_twin(_to_row(note))
    return note


def list_twin_notes(asset_id: str, *, store: EngagementStore) -> list[TwinNote]:
    return [_from_row(r) for r in store.list_twins(asset_id)]


def _to_row(note: TwinNote) -> dict[str, Any]:
    return {
        "note_id": note.note_id,
        "asset_id": note.asset_id,
        "kind": note.kind,
        "text": note.text,
        "source_spawn_id": note.source_spawn_id,
        "investigation_id": note.investigation_id,
    }


def _from_row(row: dict[str, Any]) -> TwinNote:
    return TwinNote(
        note_id=row["note_id"],
        asset_id=row["asset_id"],
        kind=row["kind"],  # type: ignore[arg-type]
        text=row["text"],
        source_spawn_id=row.get("source_spawn_id"),
        investigation_id=row.get("investigation_id"),
    )
