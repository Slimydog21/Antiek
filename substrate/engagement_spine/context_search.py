"""Intelligent search over twin notes + source refs (residual bc).

Offline product path for the infinite information platform: substring search
across twin substrate and spawn source references, returning HTML-first hits
for research prompt assembly. Does not invent graph rows or call live search.
"""

from __future__ import annotations

from typing import Any

from .source_refs import list_source_references
from .store import EngagementStore
from .twin import list_twin_notes


def search_engagement_context(
    *,
    store: EngagementStore,
    query: str,
    asset_id: str | None = None,
    spawn_id: str | None = None,
    include_html: bool = True,
    limit: int = 50,
) -> dict[str, Any]:
    """Search twin notes and optional spawn source refs for ``query``.

    Requires non-empty query. When ``asset_id`` is set, only twins for that
    asset are searched. When ``spawn_id`` is set, source refs on that spawn
    are included.
    """
    q = (query or "").strip()
    if not q:
        raise ValueError("query is required")
    q_lower = q.lower()
    lim = max(1, min(int(limit), 200))

    hits: list[dict[str, Any]] = []

    if asset_id and asset_id.strip():
        for note in list_twin_notes(asset_id.strip(), store=store):
            if q_lower in note.text.lower():
                hits.append(
                    {
                        "kind": f"twin_{note.kind}",
                        "id": note.note_id,
                        "asset_id": note.asset_id,
                        "text": note.text,
                        "source": "twin",
                    }
                )
            if len(hits) >= lim:
                break

    if spawn_id and spawn_id.strip() and len(hits) < lim:
        for ref in list_source_references(spawn_id.strip(), store=store):
            hay = f"{ref.raw} {ref.canonical_url or ''} {ref.external_id or ''} {ref.title_hint or ''}".lower()
            if q_lower in hay:
                hits.append(
                    {
                        "kind": f"ref_{ref.kind}",
                        "id": ref.ref_id,
                        "asset_id": asset_id,
                        "text": ref.canonical_url or ref.raw,
                        "source": "source_ref",
                    }
                )
            if len(hits) >= lim:
                break

    payload: dict[str, Any] = {
        "query": q,
        "asset_id": asset_id,
        "spawn_id": spawn_id,
        "hit_count": len(hits),
        "hits": hits[:lim],
        "view_format": "html",
        "product_panel": "engagement_context_search",
        "source": "engagement_spine.context_search",
        "notes": [],
    }
    if not hits:
        payload["notes"] = [
            "No hits — record twin notes or attach source refs, then search again."
        ]
    if include_html:
        payload["html"] = project_context_search_html(payload)
    return payload


def project_context_search_html(payload: dict[str, Any]) -> str:
    from .project import project_to_html

    q = str(payload.get("query") or "")
    blocks: list[dict[str, Any]] = [
        {
            "type": "heading",
            "attrs": {"level": 1},
            "content": [{"type": "text", "text": "Context search"}],
        },
        {
            "type": "paragraph",
            "content": [
                {
                    "type": "text",
                    "text": (
                        f"Query: {q} · hits={payload.get('hit_count')} · view: HTML"
                    ),
                }
            ],
        },
    ]
    hits = payload.get("hits") or []
    if not hits:
        blocks.append(
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": "(no matches)"}],
            }
        )
    for h in hits:
        if not isinstance(h, dict):
            continue
        blocks.append(
            {
                "type": "paragraph",
                "content": [
                    {
                        "type": "text",
                        "text": f"[{h.get('kind')}] {h.get('text')}",
                    }
                ],
            }
        )
    html = project_to_html(
        {"type": "doc", "content": blocks},
        document_id="context-search",
        creator="engagement_spine.context_search",
    )
    if html.lstrip().lower().startswith("%pdf"):
        raise RuntimeError("PDF is not a valid context search view surface")
    return html
