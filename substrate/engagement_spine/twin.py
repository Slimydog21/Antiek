"""Twin-side notes: insights and questions for every information asset.

The recursive note-taker vision: every asset has a twin substrate of
insights and questions that can be merged, referenced, and searched.
This module is the pure write/read path. Depth-graph promotion and
search/context assembly live in ``twin_promote`` (composes
``insight_question.promote_*`` without coupling the store to DuckDB).
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
    digest = hashlib.sha256(f"{asset_id}:{kind}:{canon}".encode()).hexdigest()[:16]
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


def twins_product_payload(
    asset_id: str,
    *,
    store: EngagementStore,
    include_html: bool = False,
) -> dict[str, Any]:
    """Product entry: list twin notes for an asset (HTML-capable)."""
    if not asset_id or not str(asset_id).strip():
        raise ValueError("asset_id is required")
    notes = list_twin_notes(asset_id, store=store)
    insights = [n for n in notes if n.kind == "insight"]
    questions = [n for n in notes if n.kind == "question"]
    payload: dict[str, Any] = {
        "asset_id": asset_id.strip(),
        "note_count": len(notes),
        "insight_count": len(insights),
        "question_count": len(questions),
        "notes": [_to_row(n) for n in notes],
        "view_format": "html",
        "product_panel": "twin_notes",
        "source": "engagement_spine.twin",
        "notes_meta": [],
    }
    # Avoid key collision with note list: use `messages` for operator notes.
    payload["messages"] = (
        ["No twin notes yet — record insights/questions as the recursive note-taker."]
        if not notes
        else ["Twin substrate is the recursive note-taker for this asset."]
    )
    if include_html:
        payload["html"] = project_twins_html(payload)
    return payload


def record_twin_product(
    asset_id: str,
    *,
    store: EngagementStore,
    kind: TwinKind,
    text: str,
    source_spawn_id: str | None = None,
    investigation_id: str | None = None,
    include_html: bool = False,
) -> dict[str, Any]:
    """Product entry: record one twin note then return full twin payload."""
    if kind == "insight":
        record_twin_insight(
            asset_id,
            text,
            store=store,
            source_spawn_id=source_spawn_id,
            investigation_id=investigation_id,
        )
    elif kind == "question":
        record_twin_question(
            asset_id,
            text,
            store=store,
            source_spawn_id=source_spawn_id,
            investigation_id=investigation_id,
        )
    else:
        raise ValueError(f"invalid twin kind: {kind!r}")
    return twins_product_payload(asset_id, store=store, include_html=include_html)


def project_twins_html(payload: dict[str, Any]) -> str:
    """HTML-first twin document view (never PDF)."""
    from .project import project_to_html

    asset_id = str(payload.get("asset_id") or "")
    blocks: list[dict[str, Any]] = [
        {
            "type": "heading",
            "attrs": {"level": 1},
            "content": [{"type": "text", "text": "Twin notes"}],
        },
        {
            "type": "paragraph",
            "content": [
                {
                    "type": "text",
                    "text": (
                        f"Asset {asset_id} · insights={payload.get('insight_count')} · "
                        f"questions={payload.get('question_count')} · view: HTML"
                    ),
                }
            ],
        },
    ]
    for row in payload.get("notes") or []:
        if not isinstance(row, dict):
            continue
        label = "Insight" if row.get("kind") == "insight" else "Question"
        blocks.append(
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": f"{label}: {row.get('text') or ''}"}
                ],
            }
        )
    if len(blocks) == 2:
        blocks.append(
            {
                "type": "paragraph",
                "content": [
                    {
                        "type": "text",
                        "text": "(empty twin substrate — LLM note-taker has not written yet)",
                    }
                ],
            }
        )
    html = project_to_html(
        {"type": "doc", "content": blocks},
        document_id=f"twin-{asset_id}",
        creator="engagement_spine.twin",
    )
    if html.lstrip().lower().startswith("%pdf"):
        raise RuntimeError("PDF is not a valid twin view surface")
    return html


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
    kind = row["kind"]
    if kind not in ("insight", "question"):
        raise ValueError(f"invalid twin kind: {kind!r}")
    return TwinNote(
        note_id=row["note_id"],
        asset_id=row["asset_id"],
        kind=kind,
        text=row["text"],
        source_spawn_id=row.get("source_spawn_id"),
        investigation_id=row.get("investigation_id"),
    )
