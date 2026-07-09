"""Product path: highlight → deep-research session + workspace window.

Composes existing floating-session open + window_compose open helpers.
Does not reimplement spawn, merge, MAX_WINDOWS, or z-order.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.engagement_spine import HighlightSelection
from substrate.engagement_spine.store import EngagementStore

from .session import FloatingSession, SessionStore, ViewMode, open_from_highlight
from .window_compose import (
    WindowOpenDescriptor,
    WindowStore,
    open_session_as_window,
    session_to_window_descriptor,
)


@dataclass(frozen=True)
class HighlightDeepResearchResult:
    """Outcome of the product path for one highlight."""

    session: FloatingSession
    window: WindowOpenDescriptor

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session.session_id,
            "spawn_id": self.session.spawn_id,
            "investigation_id": self.session.investigation_id,
            "parent_asset_id": self.session.parent_asset_id,
            "selection_text": self.session.selection_text,
            "status": self.session.status,
            "view_mode": self.session.view_mode,
            "model_id": self.session.model_id,
            "region_id": self.session.region_id,
            "window": self.window.to_dict(),
            "view_format": "html",
        }


def open_deep_research_from_highlight(
    selection: HighlightSelection,
    *,
    engagement_store: EngagementStore,
    session_store: SessionStore,
    window_store: WindowStore,
    model_id: str | None = None,
    view_mode: ViewMode = "floating",
    force_new: bool = False,
    window_title: str | None = None,
) -> HighlightDeepResearchResult:
    """Product entry: reserve/reuse session from highlight, then open window.

    Re-invoking with the same region (and force_new=False) returns the same
    session and focuses the same stable window id (no unbounded duplicates).
    """
    if not selection.selection_text or not selection.selection_text.strip():
        raise ValueError("selection_text is required")
    if not selection.asset_id or not selection.asset_id.strip():
        raise ValueError("asset_id is required")

    session = open_from_highlight(
        selection,
        engagement_store=engagement_store,
        session_store=session_store,
        model_id=model_id,
        view_mode=view_mode,
        force_new=force_new,
    )
    # Ensure descriptor mode matches session before open
    desc_preview = session_to_window_descriptor(session, title=window_title)
    if desc_preview.payload.get("view_format") != "html":
        raise RuntimeError("product path requires view_format=html")

    window = open_session_as_window(
        session,
        window_store=window_store,
        title=window_title,
    )
    return HighlightDeepResearchResult(session=session, window=window)
