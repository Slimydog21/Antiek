"""HTML view for floating-session merge output."""

from __future__ import annotations

from typing import Any

from substrate.engagement_spine import project_to_html
from substrate.engagement_spine.store import EngagementStore

from .session import FloatingSession, get_session
from .store import SessionStore


def project_session_html(
    session_id: str,
    *,
    session_store: SessionStore,
    engagement_store: EngagementStore,
    merge_result: dict[str, Any] | None = None,
) -> str:
    """Project a session (or its merge doc_model) to HTML.

    Prefer ``merge_result['doc_model']`` when provided; otherwise build a
    minimal session descriptor doc from the session + spawn status.
    """
    session = get_session(
        session_id,
        session_store=session_store,
        engagement_store=engagement_store,
    )
    if session is None:
        raise KeyError(f"unknown session_id: {session_id}")

    if merge_result and isinstance(merge_result.get("doc_model"), dict):
        doc_model = merge_result["doc_model"]
        document_id = str(merge_result.get("document_id") or session.session_id)
    else:
        doc_model = _session_doc_model(session)
        document_id = session.session_id

    html = project_to_html(
        doc_model,
        document_id=document_id,
        creator="floating_session",
    )
    if not html or not html.strip():
        raise RuntimeError("empty session HTML")
    if html.lstrip().lower().startswith("%pdf"):
        raise RuntimeError("PDF is not a valid session view surface")
    # Identity must surface for content-property tests.
    has_session_id = session.session_id in html or session.spawn_id in html
    has_parent_or_sel = (
        session.parent_asset_id in html or session.selection_text[:40] in html
    )
    if not has_session_id and not has_parent_or_sel:
        raise RuntimeError("session identity missing from HTML")
    return html


def _session_doc_model(session: FloatingSession) -> dict[str, Any]:
    lines = [
        f"Session {session.session_id}",
        f"Parent asset: {session.parent_asset_id}",
        f"Spawn: {session.spawn_id}",
        f"Investigation: {session.investigation_id}",
        f"View mode: {session.view_mode}",
        f"Status: {session.status}",
        f"Selection: {session.selection_text}",
    ]
    if session.model_id:
        lines.append(f"Model: {session.model_id}")
    if session.goal:
        lines.append(f"Goal: {session.goal}")
    content: list[dict[str, Any]] = [
        {
            "type": "heading",
            "attrs": {"level": 1},
            "content": [{"type": "text", "text": "Deep-research floating session"}],
        }
    ]
    for line in lines:
        content.append(
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": line}],
            }
        )
    return {"type": "doc", "content": content}
