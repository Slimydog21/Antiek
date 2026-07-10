"""Merge completed subagent deep-research outputs into parent or draft.

Two modes:

* ``into_parent`` — fold spawn outputs + twin notes into the parent asset's
  document model (in-place update of the store's parent document).
* ``draft_combined`` — create a new draft document id that combines the
  parent body with spawn outputs; parent is left untouched until an
  explicit later commit.

Both produce a TipTap-shaped doc-model suitable for HTML projection.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Literal

from .spawn import ResearchSpawn, _from_row
from .store import EngagementStore
from .twin import TwinNote
from .twin import _from_row as twin_from_row

MergeMode = Literal["into_parent", "draft_combined"]


@dataclass(frozen=True)
class MergeResult:
    mode: MergeMode
    parent_asset_id: str
    document_id: str
    source_spawn_ids: tuple[str, ...]
    doc_model: dict[str, Any]
    sections_merged: int


def merge_spawn_outputs(
    parent_asset_id: str,
    spawn_ids: list[str] | tuple[str, ...],
    *,
    store: EngagementStore,
    mode: MergeMode = "into_parent",
    parent_title: str | None = None,
    parent_body: str | None = None,
) -> MergeResult:
    """Merge one or more completed spawns into parent or a draft document.

    Raises ``ValueError`` if any spawn is missing or not complete.
    Raises ``KeyError`` if a spawn_id is unknown.
    """
    if not parent_asset_id.strip():
        raise ValueError("parent_asset_id is required")
    if not spawn_ids:
        raise ValueError("at least one spawn_id is required")
    if mode not in ("into_parent", "draft_combined"):
        raise ValueError(f"invalid merge mode: {mode}")

    spawns: list[ResearchSpawn] = []
    for sid in spawn_ids:
        row = store.get_spawn(sid)
        if row is None:
            raise KeyError(f"unknown spawn_id: {sid}")
        spawn = _from_row(row)
        if spawn.parent_asset_id != parent_asset_id:
            raise ValueError(
                f"spawn {sid} belongs to {spawn.parent_asset_id}, not {parent_asset_id}"
            )
        if spawn.status != "complete":
            raise ValueError(
                f"spawn {sid} status is {spawn.status!r}; only complete spawns merge"
            )
        spawns.append(spawn)

    twins = [twin_from_row(r) for r in store.list_twins(parent_asset_id)]
    existing = store.get_document(parent_asset_id) or {}
    title = parent_title or existing.get("title") or f"Asset {parent_asset_id}"
    body = parent_body if parent_body is not None else existing.get("body_text") or ""

    doc_model = _build_doc_model(
        title=title,
        body=body,
        spawns=spawns,
        twins=twins,
        parent_asset_id=parent_asset_id,
        mode=mode,
    )

    if mode == "into_parent":
        document_id = parent_asset_id
    else:
        digest = hashlib.sha256(
            f"draft:{parent_asset_id}:{','.join(sorted(spawn_ids))}".encode()
        ).hexdigest()[:12]
        document_id = f"draft_{parent_asset_id}_{digest}"

    store.put_document(
        document_id,
        {
            "document_id": document_id,
            "parent_asset_id": parent_asset_id,
            "title": title,
            "body_text": body,
            "mode": mode,
            "source_spawn_ids": list(spawn_ids),
            "doc_model": doc_model,
        },
    )

    sections = 1 + len(spawns) + (1 if twins else 0)
    return MergeResult(
        mode=mode,
        parent_asset_id=parent_asset_id,
        document_id=document_id,
        source_spawn_ids=tuple(spawn_ids),
        doc_model=doc_model,
        sections_merged=sections,
    )


def merge_product_payload(
    parent_asset_id: str,
    spawn_ids: list[str] | tuple[str, ...],
    *,
    store: EngagementStore,
    mode: MergeMode = "draft_combined",
    parent_title: str | None = None,
    parent_body: str | None = None,
    include_html: bool = False,
) -> dict[str, Any]:
    """Product entry: merge spawns into parent or draft-combined (HTML-first).

    ``draft_combined`` leaves the parent document untouched until a later
    into_parent merge. Never invents PDF as the view surface.
    """
    result = merge_spawn_outputs(
        parent_asset_id,
        spawn_ids,
        store=store,
        mode=mode,
        parent_title=parent_title,
        parent_body=parent_body,
    )
    parent_doc = store.get_document(parent_asset_id) or {}
    draft_leaves_parent = mode == "draft_combined"
    payload: dict[str, Any] = {
        "mode": result.mode,
        "parent_asset_id": result.parent_asset_id,
        "document_id": result.document_id,
        "source_spawn_ids": list(result.source_spawn_ids),
        "sections_merged": result.sections_merged,
        "draft_leaves_parent": draft_leaves_parent,
        "parent_document_id": parent_asset_id if draft_leaves_parent else result.document_id,
        "view_format": "html",
        "product_panel": "engagement_merge",
        "source": "engagement_spine.merge_spawn_outputs",
        "notes": [
            (
                "Draft-combined document; parent asset unchanged until into_parent merge."
                if draft_leaves_parent
                else "Merged into parent asset document in-place."
            )
        ],
    }
    # Honesty: draft mode must not rewrite parent document_id content mode
    if draft_leaves_parent and parent_doc.get("mode") == "into_parent":
        payload["notes"].append("Parent already had into_parent content; draft is separate.")
    if include_html:
        payload["html"] = project_merge_html(result)
    return payload


def project_merge_html(result: MergeResult | dict[str, Any]) -> str:
    """HTML-first projection of a merge result (never PDF)."""
    from .project import project_to_html

    mode: str
    if isinstance(result, MergeResult):
        doc_model = result.doc_model
        document_id = result.document_id
        mode = result.mode
        parent = result.parent_asset_id
    else:
        doc_model = result.get("doc_model") or {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "Empty merge"}],
                }
            ],
        }
        document_id = str(result.get("document_id") or "merge")
        mode = str(result.get("mode") or "")
        parent = str(result.get("parent_asset_id") or "")

    # Ensure tip-tap style wrapper if bare content list was stored
    if "type" not in doc_model and "content" in doc_model:
        wrapped = {
            "type": "doc",
            "content": doc_model.get("content") or [],
        }
        # prepend mode banner
        banner = {
            "type": "paragraph",
            "content": [
                {
                    "type": "text",
                    "text": f"Merge mode: {mode} · parent: {parent} · document: {document_id} · view: HTML",
                }
            ],
        }
        wrapped["content"] = [banner] + list(wrapped["content"])
        doc_model = wrapped
    elif doc_model.get("type") == "doc":
        banner = {
            "type": "paragraph",
            "content": [
                {
                    "type": "text",
                    "text": f"Merge mode: {mode} · parent: {parent} · document: {document_id} · view: HTML",
                }
            ],
        }
        content = list(doc_model.get("content") or [])
        doc_model = {**doc_model, "content": [banner] + content}

    html = project_to_html(
        doc_model,
        document_id=document_id,
        creator="engagement_spine.merge",
    )
    if html.lstrip().lower().startswith("%pdf"):
        raise RuntimeError("PDF is not a valid merge view surface")
    return html


def _para(text: str, block_id: str) -> dict[str, Any]:
    return {
        "type": "paragraph",
        "attrs": {"block_id": block_id},
        "content": [{"type": "text", "text": text}],
    }


def _heading(text: str, level: int, block_id: str) -> dict[str, Any]:
    return {
        "type": "heading",
        "attrs": {"level": level, "block_id": block_id},
        "content": [{"type": "text", "text": text}],
    }


def _build_doc_model(
    *,
    title: str,
    body: str,
    spawns: list[ResearchSpawn],
    twins: list[TwinNote],
    parent_asset_id: str,
    mode: MergeMode,
) -> dict[str, Any]:
    content: list[dict[str, Any]] = []
    if body.strip():
        content.append(_heading("Source", 2, "h-source"))
        content.append(_para(body.strip(), "p-source"))

    for i, spawn in enumerate(spawns):
        content.append(
            _heading(f"Deep research: {spawn.goal[:80]}", 2, f"h-spawn-{i}")
        )
        content.append(
            _para(f"Selection: {spawn.selection_text}", f"p-sel-{i}")
        )
        if spawn.output_text:
            content.append(_para(spawn.output_text, f"p-out-{i}"))
        for j, insight in enumerate(spawn.output_insights):
            content.append(_para(f"Insight: {insight}", f"p-ins-{i}-{j}"))
        for j, question in enumerate(spawn.output_questions):
            content.append(_para(f"Question: {question}", f"p-q-{i}-{j}"))

    if twins:
        content.append(_heading("Twin notes", 2, "h-twin"))
        for j, note in enumerate(twins):
            label = "Insight" if note.kind == "insight" else "Question"
            content.append(_para(f"{label}: {note.text}", f"p-twin-{j}"))

    if not content:
        content.append(_para("(empty merged document)", "p-empty"))

    return {
        "title": title if mode == "into_parent" else f"[Draft] {title}",
        "content": content,
        "edges": [],
        "meta": {
            "parent_asset_id": parent_asset_id,
            "merge_mode": mode,
            "spawn_ids": [s.spawn_id for s in spawns],
        },
    }
