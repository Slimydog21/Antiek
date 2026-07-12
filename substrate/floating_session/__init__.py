"""Highlight → floating deep-research session (UI-descriptor substrate).

Bridges the engagement spine for reading/research workstation chrome:

* open a session from a highlight (reserves spine spawn)
* view mode ``floating`` ⇄ ``full`` without destroying the session
* merge completed sessions into parent or draft-combined via spine merge
* multi-session collective merge of completed spawn ids

Does **not** reimplement spawn/merge/project — those live in
``substrate.engagement_spine``. Browser multi-window chrome is non-gating.
"""

from __future__ import annotations

from .context_bridge import (
    attach_session_source_references,
    open_from_highlight_with_references,
    session_context_html,
    session_research_context,
    sessions_collective_html,
    sessions_collective_research,
)
from .flywheel import SessionFlywheelResult, complete_session_with_context_flywheel
from .product_path import (
    HighlightDeepResearchResult,
    open_deep_research_from_highlight,
)
from .session import (
    FloatingSession,
    ViewMode,
    compare_and_set_view_mode,
    complete_session_research,
    get_session,
    list_sessions_for_asset,
    merge_sessions,
    open_from_highlight,
    set_view_mode,
)
from .store import SessionStore
from .view import project_session_html
from .window_compose import (
    DEEP_RESEARCH_WINDOW_KIND,
    InMemoryWindowStore,
    WindowOpenDescriptor,
    WindowStore,
    list_session_window_descriptors,
    map_session_mode_to_window_mode,
    open_session_as_window,
    open_sessions_as_windows,
    session_to_window_descriptor,
    sync_session_window_mode,
    window_id_for_session,
)

__all__ = [
    "DEEP_RESEARCH_WINDOW_KIND",
    "FloatingSession",
    "HighlightDeepResearchResult",
    "InMemoryWindowStore",
    "SessionStore",
    "ViewMode",
    "WindowOpenDescriptor",
    "WindowStore",
    "SessionFlywheelResult",
    "attach_session_source_references",
    "complete_session_research",
    "compare_and_set_view_mode",
    "complete_session_with_context_flywheel",
    "get_session",
    "list_session_window_descriptors",
    "list_sessions_for_asset",
    "map_session_mode_to_window_mode",
    "merge_sessions",
    "open_deep_research_from_highlight",
    "open_from_highlight",
    "open_from_highlight_with_references",
    "open_session_as_window",
    "open_sessions_as_windows",
    "project_session_html",
    "session_context_html",
    "session_research_context",
    "session_to_window_descriptor",
    "sessions_collective_html",
    "sessions_collective_research",
    "set_view_mode",
    "sync_session_window_mode",
    "window_id_for_session",
]
