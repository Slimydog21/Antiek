"""Real-path tests: floating_session → windowsStore-shaped composition."""

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
    complete_session_research,
    list_session_window_descriptors,
    open_from_highlight,
    open_session_as_window,
    open_sessions_as_windows,
    project_session_html,
    session_to_window_descriptor,
    sync_session_window_mode,
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


def _open_session(eng, sessions, *, asset="book-1", region="r1", text="A highlight passage."):
    return open_from_highlight(
        HighlightSelection(asset_id=asset, selection_text=text, region_id=region),
        engagement_store=eng,
        session_store=sessions,
        model_id="glm-5.2",
        view_mode="floating",
    )


def test_session_to_window_descriptor_identity(eng, sessions):
    s = _open_session(eng, sessions)
    desc = session_to_window_descriptor(s)
    assert desc.kind == DEEP_RESEARCH_WINDOW_KIND
    assert desc.mode == "floating"
    assert desc.window_id == window_id_for_session(s.session_id)
    assert desc.payload["session_id"] == s.session_id
    assert desc.payload["spawn_id"] == s.spawn_id
    assert desc.payload["parent_asset_id"] == "book-1"
    assert desc.payload["investigation_id"] == s.investigation_id
    assert desc.payload["model_id"] == "glm-5.2"
    assert desc.payload["view_format"] == "html"
    d = desc.to_dict()
    assert d["id"] == desc.window_id
    assert d["kind"] == DEEP_RESEARCH_WINDOW_KIND


def test_open_session_as_window_and_list(eng, sessions, windows):
    s = _open_session(eng, sessions)
    desc = open_session_as_window(s, window_store=windows)
    assert windows.get(desc.window_id) is not None
    row = windows.get(desc.window_id)
    assert row is not None
    assert row["payload"]["session_id"] == s.session_id
    assert row["mode"] == "floating"
    listed = windows.list_for_parent("book-1")
    assert len(listed) == 1
    # Re-open same session focuses, no duplicate
    again = open_session_as_window(s, window_store=windows)
    assert again.window_id == desc.window_id
    assert len(windows.list_for_parent("book-1")) == 1


def test_sync_mode_floating_full(eng, sessions, windows):
    s = _open_session(eng, sessions)
    open_session_as_window(s, window_store=windows)
    updated = sync_session_window_mode(
        s.session_id, "full", session_store=sessions, window_store=windows
    )
    assert updated.view_mode == "full"
    w = windows.get(window_id_for_session(s.session_id))
    assert w is not None and w["mode"] == "full"
    back = sync_session_window_mode(
        s.session_id, "floating", session_store=sessions, window_store=windows
    )
    assert back.view_mode == "floating"
    w2 = windows.get(window_id_for_session(s.session_id))
    assert w2 is not None and w2["mode"] == "floating"


def test_multi_session_distinct_window_descriptors(eng, sessions, windows):
    s1 = _open_session(eng, sessions, region="r1", text="First highlight")
    s2 = _open_session(eng, sessions, region="r2", text="Second highlight")
    opened = open_sessions_as_windows(
        "book-1",
        session_store=sessions,
        window_store=windows,
        session_ids=[s1.session_id, s2.session_id],
    )
    assert len(opened) == 2
    ids = {o.window_id for o in opened}
    assert len(ids) == 2
    assert window_id_for_session(s1.session_id) in ids
    assert window_id_for_session(s2.session_id) in ids
    listed = windows.list_for_parent("book-1")
    assert len(listed) == 2


def test_list_session_window_descriptors_without_open(eng, sessions):
    _open_session(eng, sessions, region="r1")
    _open_session(eng, sessions, region="r2", text="other")
    descs = list_session_window_descriptors("book-1", session_store=sessions)
    assert len(descs) == 2
    assert all(d.kind == DEEP_RESEARCH_WINDOW_KIND for d in descs)
    assert all(d.payload["parent_asset_id"] == "book-1" for d in descs)


def test_composed_session_html_not_pdf(eng, sessions, windows):
    s = _open_session(eng, sessions)
    desc = open_session_as_window(s, window_store=windows)
    complete_session_research(
        s.session_id,
        session_store=sessions,
        engagement_store=eng,
        output_text="Research body about attention.",
        insights=["Insight A"],
        questions=["Q?"],
    )
    html = project_session_html(
        s.session_id, session_store=sessions, engagement_store=eng
    )
    assert s.session_id in html or s.spawn_id in html or "book-1" in html
    assert not html.lstrip().lower().startswith("%pdf")
    assert desc.payload["view_format"] == "html"
