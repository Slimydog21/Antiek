"""Bridge floating sessions → twin/source-ref research context + collective.

Product residual: session chrome can attach knowledge-dense refs and
assemble (or collectively merge) research context packs without leaving
the floating deep-research substrate.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from typing import Any

from substrate.dispatch.research_tier import normalize_research_tier
from substrate.engagement_spine import (
    HighlightSelection,
    SourceReference,
    assemble_research_context,
    attach_source_references,
    collective_research_html,
    merge_spawns_collective,
    research_context_html,
    spawn_from_highlight_with_references,
)
from substrate.engagement_spine.collective import CollectiveResearchUnit
from substrate.engagement_spine.research_context import ResearchContextPack
from substrate.engagement_spine.store import EngagementStore

from .session import FloatingSession, ViewMode, _from_row, _session_id, _to_row
from .store import SessionStore


def open_from_highlight_with_references(
    selection: HighlightSelection,
    *,
    engagement_store: EngagementStore,
    session_store: SessionStore,
    references: Sequence[str | SourceReference] = (),
    model_id: str | None = None,
    view_mode: ViewMode = "floating",
    force_new: bool = False,
    research_tier: str | None = None,
    owner_id: str = "__operator__",
    source_collective_id: str | None = None,
    source_collective_preview_sha256: str | None = None,
) -> FloatingSession:
    """Open floating session from highlight and attach source references.

    Residual (ji): optional ``research_tier`` on spawn + session reservation.
    """
    if view_mode not in ("floating", "full"):
        raise ValueError(f"invalid view_mode: {view_mode!r}")

    spawn = spawn_from_highlight_with_references(
        selection,
        store=engagement_store,
        references=references,
        model_id=model_id,
        force_new=force_new,
        research_tier=research_tier,
        owner_id=owner_id,
    )
    sid = _session_id(spawn.parent_asset_id, spawn.spawn_id, spawn.owner_id)
    existing = session_store.get_session(sid)
    if existing is not None and not force_new:
        # Idempotent replay also reconciles a durable owner index interrupted
        # after the canonical row replace.
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
        research_tier=normalize_research_tier(
            getattr(spawn, "research_tier", None),
        ),
        owner_id=spawn.owner_id,
        source_collective_id=source_collective_id,
        source_collective_preview_sha256=source_collective_preview_sha256,
    )
    session_store.put_session(_to_row(session))
    return session


def attach_session_source_references(
    session_id: str,
    references: Sequence[str | SourceReference],
    *,
    session_store: SessionStore,
    engagement_store: EngagementStore,
) -> FloatingSession:
    """Attach arxiv/substack/url refs to the session's underlying spawn."""
    row = session_store.get_session(session_id)
    if row is None:
        raise KeyError(f"unknown session_id: {session_id}")
    owner_id = str(row.get("owner_id") or "")
    if not owner_id:
        raise ValueError("session ownership requires reconciliation")
    attach_source_references(
        row["spawn_id"],
        references,
        store=engagement_store,
        owner_id=owner_id,
    )
    return _from_row(row)


def session_research_context(
    session_id: str,
    *,
    session_store: SessionStore,
    engagement_store: EngagementStore,
    query: str | None = None,
    promote_insight_fn: Any = None,
    promote_question_fn: Any = None,
    include_twin_promote: bool = True,
) -> ResearchContextPack:
    """Assemble twin + source-ref research context for one floating session."""
    row = session_store.get_session(session_id)
    if row is None:
        raise KeyError(f"unknown session_id: {session_id}")
    return assemble_research_context(
        row["parent_asset_id"],
        store=engagement_store,
        spawn_id=row["spawn_id"],
        query=query,
        investigation_id=row.get("investigation_id"),
        promote_insight_fn=promote_insight_fn,
        promote_question_fn=promote_question_fn,
        include_twin_promote=include_twin_promote,
        owner_id=str(row.get("owner_id") or "__operator__"),
    )


def sessions_collective_research(
    session_ids: Sequence[str],
    *,
    session_store: SessionStore,
    engagement_store: EngagementStore,
    query: str | None = None,
    promote_insight_fn: Any = None,
    promote_question_fn: Any = None,
    include_twin_promote: bool = True,
) -> CollectiveResearchUnit:
    """Merge multiple floating sessions into one collective research unit."""
    if not session_ids:
        raise ValueError("at least one session_id is required")
    spawn_ids: list[str] = []
    owner_ids: set[str] = set()
    for sid in session_ids:
        row = session_store.get_session(sid)
        if row is None:
            raise KeyError(f"unknown session_id: {sid}")
        owner_ids.add(str(row.get("owner_id") or ""))
        spawn_ids.append(row["spawn_id"])
    if len(owner_ids) != 1 or "" in owner_ids:
        raise ValueError("collective sessions require one explicit owner")
    unit = merge_spawns_collective(
        spawn_ids,
        store=engagement_store,
        query=query,
        promote_insight_fn=promote_insight_fn,
        promote_question_fn=promote_question_fn,
        include_twin_promote=include_twin_promote,
        owner_id=next(iter(owner_ids)),
    )
    session_by_spawn = dict(zip(spawn_ids, session_ids, strict=True))
    return replace(
        unit,
        research_outputs=tuple(
            {**row, "session_id": session_by_spawn.get(str(row.get("spawn_id")))}
            for row in unit.research_outputs
        ),
    )


def session_context_html(
    session_id: str,
    *,
    session_store: SessionStore,
    engagement_store: EngagementStore,
    **kwargs: Any,
) -> str:
    pack = session_research_context(
        session_id,
        session_store=session_store,
        engagement_store=engagement_store,
        **kwargs,
    )
    return research_context_html(pack)


def sessions_collective_html(
    session_ids: Sequence[str],
    *,
    session_store: SessionStore,
    engagement_store: EngagementStore,
    **kwargs: Any,
) -> str:
    unit = sessions_collective_research(
        session_ids,
        session_store=session_store,
        engagement_store=engagement_store,
        **kwargs,
    )
    return collective_research_html(unit)
