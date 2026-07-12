"""Floating deep-research session lifecycle over engagement_spine."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from substrate.dispatch.research_tier import (
    DEFAULT_RESEARCH_TIER,
    normalize_research_tier,
)
from substrate.engagement_spine import (
    HighlightSelection,
    complete_spawn,
    get_spawn,
    merge_spawn_outputs,
    record_twin_insight,
    record_twin_question,
    spawn_from_highlight,
)
from substrate.engagement_spine.merge import MergeResult
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
    # Residual (ji): closed research tier mirrored from spawn reservation.
    research_tier: str = DEFAULT_RESEARCH_TIER
    owner_id: str = "__operator__"


def _session_id(parent_asset_id: str, spawn_id: str, owner_id: str = "__operator__") -> str:
    owner_scope = "" if owner_id == "__operator__" else f":owner:{owner_id}"
    digest = hashlib.sha256(
        f"fsess:v1{owner_scope}:{parent_asset_id}:{spawn_id}".encode()
    ).hexdigest()[:16]
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
        "research_tier": normalize_research_tier(session.research_tier),
        "owner_id": session.owner_id,
    }


def _from_row(row: dict[str, Any]) -> FloatingSession:
    return FloatingSession(
        session_id=row["session_id"],
        parent_asset_id=row["parent_asset_id"],
        spawn_id=row["spawn_id"],
        investigation_id=row["investigation_id"],
        view_mode=row.get("view_mode") or "floating",
        selection_text=row.get("selection_text") or "",
        region_id=row.get("region_id"),
        model_id=row.get("model_id"),
        goal=row.get("goal") or "",
        status=row.get("status") or "reserved",
        research_tier=normalize_research_tier(row.get("research_tier")),
        owner_id=str(row.get("owner_id") or "__operator__"),
    )


def open_from_highlight(
    selection: HighlightSelection,
    *,
    engagement_store: EngagementStore,
    session_store: SessionStore,
    model_id: str | None = None,
    view_mode: ViewMode = "floating",
    force_new: bool = False,
    research_tier: str | None = None,
    owner_id: str = "__operator__",
) -> FloatingSession:
    """Open a deep-research session from a highlight.

    Reserves (or reuses) an engagement_spine spawn, then stores a session
    chrome descriptor with floating|full view mode.

    Residual (ji): optional ``research_tier`` recorded on spawn + session.
    """
    if view_mode not in ("floating", "full"):
        raise ValueError(f"invalid view_mode: {view_mode!r}")

    spawn = spawn_from_highlight(
        selection,
        store=engagement_store,
        model_id=model_id,
        force_new=force_new,
        research_tier=research_tier,
        owner_id=owner_id,
    )
    sid = _session_id(spawn.parent_asset_id, spawn.spawn_id, spawn.owner_id)

    # Idempotent session for same spawn
    existing = session_store.get_session(sid)
    if existing is not None and not force_new:
        # The durable row and its owner index are a recoverable two-step write.
        # Replaying open repairs an index lost after row replace/before index replace.
        session_store.put_session(existing)
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
        research_tier=spawn.research_tier,
        owner_id=spawn.owner_id,
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


def compare_and_set_view_mode(
    session_id: str,
    mode: ViewMode,
    *,
    expected_mode: ViewMode | None,
    session_store: SessionStore,
) -> tuple[FloatingSession, bool]:
    """Atomically update view mode within the configured store boundary."""
    if mode not in ("floating", "full") or expected_mode not in (
        None,
        "floating",
        "full",
    ):
        raise ValueError("invalid view mode authority")
    row, applied = session_store.compare_and_set_view(session_id, expected_mode, mode)
    return _from_row(row), applied


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
            row = session_store.update_status(session_id, spawn.status)
            session = _from_row(row)
    return session


def list_sessions_for_asset(
    parent_asset_id: str,
    *,
    session_store: SessionStore,
    owner_id: str | None = None,
) -> list[FloatingSession]:
    rows = session_store.list_sessions(
        parent_asset_id, owner_id or "__operator__"
    )
    if owner_id is None:
        return [_from_row(row) for row in rows]
    return [
        _from_row(row)
        for row in rows
        if row.get("owner_id") == owner_id
    ]


def complete_session_research(
    session_id: str,
    *,
    session_store: SessionStore,
    engagement_store: EngagementStore,
    output_text: str,
    insights: list[str] | tuple[str, ...] = (),
    questions: list[str] | tuple[str, ...] = (),
    record_twins: bool = True,
) -> FloatingSession:
    """Mark the underlying spawn complete (does not auto-merge).

    When ``record_twins`` is True (default), each insight/question is also
    written to the parent asset's twin substrate so the recursive note-taker
    path can promote them into the depth graph later.
    """
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
    if record_twins:
        asset = row["parent_asset_id"]
        spawn_id = row["spawn_id"]
        inv = row.get("investigation_id")
        for text in insights:
            cleaned = (text or "").strip()
            if not cleaned:
                continue
            record_twin_insight(
                asset,
                cleaned,
                store=engagement_store,
                source_spawn_id=spawn_id,
                investigation_id=inv,
                owner_id=str(row.get("owner_id") or "__operator__"),
            )
        for text in questions:
            cleaned = (text or "").strip()
            if not cleaned:
                continue
            record_twin_question(
                asset,
                cleaned,
                store=engagement_store,
                source_spawn_id=spawn_id,
                investigation_id=inv,
                owner_id=str(row.get("owner_id") or "__operator__"),
            )
    return _from_row(session_store.update_status(session_id, "complete"))


def merge_sessions(
    parent_asset_id: str,
    session_ids: list[str] | tuple[str, ...],
    *,
    session_store: SessionStore,
    engagement_store: EngagementStore,
    mode: Literal["into_parent", "draft_combined"] = "draft_combined",
    parent_title: str | None = None,
    parent_body: str | None = None,
    expected_parent_sha256: str | None = None,
    owner_id: str = "__operator__",
    before_write: Callable[[dict[str, Any]], None] | None = None,
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
        if str(row.get("owner_id") or "") != owner_id:
            raise ValueError(f"session {sid} does not belong to merge owner")
        if row.get("parent_asset_id") != parent_asset_id:
            raise ValueError(
                f"session {sid} parent is {row.get('parent_asset_id')}, not {parent_asset_id}"
            )
        spawn_ids.append(str(row["spawn_id"]))

    def _prepared(result: MergeResult) -> None:
        if before_write is None:
            return
        before_write(
            {
                "mode": result.mode,
                "parent_asset_id": result.parent_asset_id,
                "document_id": result.document_id,
                "source_spawn_ids": list(result.source_spawn_ids),
                "source_session_ids": list(session_ids),
                "doc_model": result.doc_model,
                "sections_merged": result.sections_merged,
                "document_sha256": result.document_sha256,
            }
        )

    result = merge_spawn_outputs(
        parent_asset_id,
        spawn_ids,
        store=engagement_store,
        mode=mode,
        parent_title=parent_title,
        parent_body=parent_body,
        expected_parent_sha256=expected_parent_sha256,
        owner_id=owner_id,
        before_write=_prepared if before_write is not None else None,
    )
    return {
        "mode": result.mode,
        "parent_asset_id": result.parent_asset_id,
        "document_id": result.document_id,
        "source_spawn_ids": list(result.source_spawn_ids),
        "source_session_ids": list(session_ids),
        "doc_model": result.doc_model,
        "sections_merged": result.sections_merged,
        "document_sha256": result.document_sha256,
    }
