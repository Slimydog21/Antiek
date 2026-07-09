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

from .session import (
    FloatingSession,
    SessionStore,
    ViewMode,
    complete_session_research,
    get_session,
    list_sessions_for_asset,
    merge_sessions,
    open_from_highlight,
    set_view_mode,
)
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
    "InMemoryWindowStore",
    "SessionStore",
    "ViewMode",
    "WindowOpenDescriptor",
    "WindowStore",
    "complete_session_research",
    "get_session",
    "list_session_window_descriptors",
    "list_sessions_for_asset",
    "map_session_mode_to_window_mode",
    "merge_sessions",
    "open_from_highlight",
    "open_session_as_window",
    "open_sessions_as_windows",
    "project_session_html",
    "session_to_window_descriptor",
    "set_view_mode",
    "sync_session_window_mode",
    "window_id_for_session",
]
