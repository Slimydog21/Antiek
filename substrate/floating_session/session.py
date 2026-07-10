"""Floating deep-research session lifecycle over engagement_spine."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Literal

from substrate.engagement_spine import (
    HighlightSelection,
    complete_spawn,
    get_spawn,
    merge_spawn_outputs,
    spawn_from_highlight,
)
from substrate.engagement_spine.store import EngagementStore

from .store import SessionStore

ViewMode = Literal["floating", "full"]


@dataclass(frozen=True)
class FloatingSession:
    session_id: str
    parent_asset_id: str
    spawn_id: str
    investigation_id: str
    view_mode: ViewMode
    selection_text: str
    region_id: str | None = None
    model_id: str | None = None
    goal: str = ""
    status: str = "reserved"  # mirrors spawn status when known


def _session_id(parent_asset_id: str, spawn_id: str) -> str:
    digest = hashlib.sha256(f"fsess:v1:{parent_asset_id}:{spawn_id}".encode()).hexdigest()[
        :16
    ]
    return f"fsess_{digest}"


def _to_row(session: FloatingSession) -> dict[str, Any]:
    return {
        "session_id": session.session_id,
        "parent_asset_id": session.parent_asset_id,
        "spawn_id": session.spawn_id,
        "investigation_id": session.investigation_id,
        "view_mode": session.view_mode,
        "selection_text": session.selection_text,
        "region_id": session.region_id,
        "model_id": session.model_id,
        "goal": session.goal,
        "status": session.status,
    }


def _from_row(row: dict[str, Any]) -> FloatingSession:
    raw_view_mode = row.get("view_mode") or "floating"
    if raw_view_mode == "floating":
        view_mode: ViewMode = "floating"
    elif raw_view_mode == "full":
        view_mode = "full"
    else:
        raise ValueError(f"invalid view_mode: {raw_view_mode!r}")
    return FloatingSession(
        session_id=row["session_id"],
        parent_asset_id=row["parent_asset_id"],
        spawn_id=row["spawn_id"],
        investigation_id=row["investigation_id"],
        view_mode=view_mode,
        selection_text=row.get("selection_text") or "",
        region_id=row.get("region_id"),
        model_id=row.get("model_id"),
        goal=row.get("goal") or "",
        status=row.get("status") or "reserved",
    )


def open_from_highlight(
    selection: HighlightSelection,
    *,
    engagement_store: EngagementStore,
    session_store: SessionStore,
    model_id: str | None = None,
    view_mode: ViewMode = "floating",
    force_new: bool = False,
) -> FloatingSession:
    """Open a deep-research session from a highlight.

    Reserves (or reuses) an engagement_spine spawn, then stores a session
    chrome descriptor with floating|full view mode.
    """
    if view_mode not in ("floating", "full"):
        raise ValueError(f"invalid view_mode: {view_mode!r}")

    spawn = spawn_from_highlight(
        selection,
        store=engagement_store,
        model_id=model_id,
        force_new=force_new,
    )
    sid = _session_id(spawn.parent_asset_id, spawn.spawn_id)

    # Idempotent session for same spawn
    existing = session_store.get_session(sid)
    if existing is not None and not force_new:
        return _from_row(existing)

    session = FloatingSession(
        session_id=sid,
        parent_asset_id=spawn.parent_asset_id,
        spawn_id=spawn.spawn_id,
        investigation_id=spawn.investigation_id,
        view_mode=view_mode,
        selection_text=spawn.selection_text,
        region_id=spawn.region_id,
        model_id=spawn.model_id,
        goal=spawn.goal,
        status=spawn.status,
    )
    session_store.put_session(_to_row(session))
    return session


def set_view_mode(
    session_id: str,
    mode: ViewMode,
    *,
    session_store: SessionStore,
) -> FloatingSession:
    """Flip floating ⇄ full without destroying the session or spawn."""
    if mode not in ("floating", "full"):
        raise ValueError(f"invalid view_mode: {mode!r}")
    row = session_store.get_session(session_id)
    if row is None:
        raise KeyError(f"unknown session_id: {session_id}")
    row = dict(row)
    row["view_mode"] = mode
    session_store.put_session(row)
    return _from_row(row)


def get_session(
    session_id: str,
    *,
    session_store: SessionStore,
    engagement_store: EngagementStore | None = None,
) -> FloatingSession | None:
    row = session_store.get_session(session_id)
    if row is None:
        return None
    session = _from_row(row)
    if engagement_store is not None:
        spawn = get_spawn(session.spawn_id, store=engagement_store)
        if spawn is not None and spawn.status != session.status:
            row = dict(row)
            row["status"] = spawn.status
            session_store.put_session(row)
            session = _from_row(row)
    return session


def list_sessions_for_asset(
    parent_asset_id: str,
    *,
    session_store: SessionStore,
) -> list[FloatingSession]:
    return [_from_row(r) for r in session_store.list_sessions(parent_asset_id)]


def complete_session_research(
    session_id: str,
    *,
    session_store: SessionStore,
    engagement_store: EngagementStore,
    output_text: str,
    insights: list[str] | tuple[str, ...] = (),
    questions: list[str] | tuple[str, ...] = (),
) -> FloatingSession:
    """Mark the underlying spawn complete (does not auto-merge)."""
    row = session_store.get_session(session_id)
    if row is None:
        raise KeyError(f"unknown session_id: {session_id}")
    complete_spawn(
        row["spawn_id"],
        store=engagement_store,
        output_text=output_text,
        insights=list(insights),
        questions=list(questions),
        status="complete",
    )
    row = dict(row)
    row["status"] = "complete"
    session_store.put_session(row)
    return _from_row(row)


def merge_sessions(
    parent_asset_id: str,
    session_ids: list[str] | tuple[str, ...],
    *,
    session_store: SessionStore,
    engagement_store: EngagementStore,
    mode: Literal["into_parent", "draft_combined"] = "draft_combined",
    parent_title: str | None = None,
    parent_body: str | None = None,
) -> dict[str, Any]:
    """Merge one or more completed sessions via spine ``merge_spawn_outputs``.

    Supports multi-session collective merge: pass ≥2 session ids.
    """
    if not session_ids:
        raise ValueError("at least one session_id is required")
    spawn_ids: list[str] = []
    for sid in session_ids:
        row = session_store.get_session(sid)
        if row is None:
            raise KeyError(f"unknown session_id: {sid}")
        if row.get("parent_asset_id") != parent_asset_id:
            raise ValueError(
                f"session {sid} parent is {row.get('parent_asset_id')}, "
                f"not {parent_asset_id}"
            )
        spawn_ids.append(str(row["spawn_id"]))

    result = merge_spawn_outputs(
        parent_asset_id,
        spawn_ids,
        store=engagement_store,
        mode=mode,
        parent_title=parent_title,
        parent_body=parent_body,
    )
    return {
        "mode": result.mode,
        "parent_asset_id": result.parent_asset_id,
        "document_id": result.document_id,
        "source_spawn_ids": list(result.source_spawn_ids),
        "source_session_ids": list(session_ids),
        "doc_model": result.doc_model,
        "sections_merged": result.sections_merged,
    }
