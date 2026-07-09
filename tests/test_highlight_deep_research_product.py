"""Real-path tests: highlight → session + deep-research window product path."""

from __future__ import annotations

import os
import sys

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from substrate.engagement_spine import (  # noqa: E402
    HighlightSelection,
    InMemoryEngagementStore,
)
from substrate.floating_session import (  # noqa: E402
    DEEP_RESEARCH_WINDOW_KIND,
    InMemoryWindowStore,
    open_deep_research_from_highlight,
    window_id_for_session,
)
from substrate.floating_session.store import InMemorySessionStore  # noqa: E402


@pytest.fixture
def eng():
    return InMemoryEngagementStore()


@pytest.fixture
def sessions():
    return InMemorySessionStore()


@pytest.fixture
def windows():
    return InMemoryWindowStore()


def test_highlight_opens_session_and_window(eng, sessions, windows):
    sel = HighlightSelection(
        asset_id="book-1",
        selection_text="Attention is content-addressable memory.",
        region_id="r-p12",
    )
    result = open_deep_research_from_highlight(
        sel,
        engagement_store=eng,
        session_store=sessions,
        window_store=windows,
        model_id="glm-5.2",
        view_mode="floating",
    )
    assert result.session.session_id.startswith("fsess_")
    assert result.session.spawn_id.startswith("spn_")
    assert result.session.parent_asset_id == "book-1"
    assert result.session.status == "reserved"
    assert result.window.kind == DEEP_RESEARCH_WINDOW_KIND
    assert result.window.payload["session_id"] == result.session.session_id
    assert result.window.payload["spawn_id"] == result.session.spawn_id
    assert result.window.payload["parent_asset_id"] == "book-1"
    assert result.window.payload["selection_text"].startswith("Attention")
    assert result.window.payload["view_format"] == "html"
    assert result.window.window_id == window_id_for_session(result.session.session_id)
    assert windows.get(result.window.window_id) is not None
    d = result.to_dict()
    assert d["view_format"] == "html"
    assert d["window"]["kind"] == DEEP_RESEARCH_WINDOW_KIND


def test_reinvoke_same_region_stable(eng, sessions, windows):
    sel = HighlightSelection(
        asset_id="book-1",
        selection_text="same passage",
        region_id="region-stable",
    )
    a = open_deep_research_from_highlight(
        sel,
        engagement_store=eng,
        session_store=sessions,
        window_store=windows,
    )
    b = open_deep_research_from_highlight(
        sel,
        engagement_store=eng,
        session_store=sessions,
        window_store=windows,
    )
    assert a.session.session_id == b.session.session_id
    assert a.session.spawn_id == b.session.spawn_id
    assert a.window.window_id == b.window.window_id
    # No unbounded window fan-out
    assert len(windows.list_for_parent("book-1")) == 1


def test_rejects_empty_selection(eng, sessions, windows):
    with pytest.raises(ValueError, match="selection_text"):
        open_deep_research_from_highlight(
            HighlightSelection(asset_id="a", selection_text="  "),
            engagement_store=eng,
            session_store=sessions,
            window_store=windows,
        )


def test_html_first_payload_not_pdf(eng, sessions, windows):
    result = open_deep_research_from_highlight(
        HighlightSelection(
            asset_id="doc-h",
            selection_text="HTML-first reading asset passage.",
            region_id="r-html",
        ),
        engagement_store=eng,
        session_store=sessions,
        window_store=windows,
    )
    assert result.window.payload["view_format"] == "html"
    assert result.to_dict()["view_format"] == "html"
    # No PDF surface in product payload
    assert "pdf" not in str(result.window.payload.get("view_format", "")).lower()
