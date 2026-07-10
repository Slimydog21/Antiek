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
    ViewMode,
    complete_session_research,
    get_session,
    list_sessions_for_asset,
    merge_sessions,
    open_from_highlight,
    set_view_mode,
)
from .store import SessionStore
from .view import project_session_html

__all__ = [
    "FloatingSession",
    "SessionStore",
    "ViewMode",
    "complete_session_research",
    "get_session",
    "list_sessions_for_asset",
    "merge_sessions",
    "open_from_highlight",
    "project_session_html",
    "set_view_mode",
]
