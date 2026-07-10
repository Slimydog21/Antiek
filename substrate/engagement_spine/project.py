"""HTML-first projection for engagement-spine documents.

Uses the shipped ``services.html_projection.render`` path. PDF is never
emitted as the view surface — HTML is the human-viewable form.
"""

from __future__ import annotations

from typing import Any

from services.html_projection import render
from services.html_projection.context import Provenance, RenderContext


def project_to_html(
    doc_model: dict[str, Any],
    *,
    document_id: str = "engagement-asset",
    creator: str = "engagement_spine",
) -> str:
    """Project a TipTap-shaped doc-model to self-contained HTML.

    Returns a non-empty HTML document string. Raises if render produces
    empty output (should never happen for valid doc-models with content).
    """
    if not isinstance(doc_model, dict):
        raise TypeError("doc_model must be a dict")
    content = doc_model.get("content")
    if not content:
        raise ValueError("doc_model.content is required and must be non-empty")

    # Normalize bare "heading" nodes if the renderer contract expects
    # paragraph/prose primarily — keep headings as paragraph fallbacks when
    # the contract does not list heading, so projection never crashes.
    normalized = _normalize_for_renderer(doc_model)

    ctx = RenderContext(
        provenance=Provenance(
            document_id=document_id,
            creator_user_id=creator,
            content_class="engagement",
            schema_version="1",
            rendered_at="1970-01-01T00:00:00Z",  # fixed; not wall-clock
        ),
    )
    html = render(normalized, ctx)
    if not html or not html.strip():
        raise RuntimeError("HTML projection produced empty output")
    if (
        "<html" not in html.lower()
        and "<!doctype" not in html.lower()
        and len(html.strip()) < 8
    ):
        raise RuntimeError("HTML projection too short to be a view surface")
    return html


def _normalize_for_renderer(doc_model: dict[str, Any]) -> dict[str, Any]:
    """Map spine-local block types onto known html_projection block types.

    The engagement spine uses simple paragraph/heading nodes; the
    projection contract prefers ``paragraph`` / ``prose`` / ``antiek_prose``.
    Unknown types still render via the visible unsupported-block fallback.
    """
    out = dict(doc_model)
    content = []
    for node in doc_model.get("content") or []:
        if not isinstance(node, dict):
            continue
        n = dict(node)
        t = n.get("type")
        if t == "heading":
            # Render headings as prose with a level attr when heading unsupported
            level = (n.get("attrs") or {}).get("level", 2)
            text_parts = n.get("content") or []
            text = ""
            for part in text_parts:
                if isinstance(part, dict) and part.get("type") == "text":
                    text += str(part.get("text") or "")
            n = {
                "type": "paragraph",
                "attrs": dict(n.get("attrs") or {}),
                "content": [
                    {
                        "type": "text",
                        "text": text if text else f"(h{level})",
                        "marks": [{"type": "bold"}],
                    }
                ],
            }
            n["attrs"]["heading_level"] = level
        content.append(n)
    out["content"] = content
    return out
