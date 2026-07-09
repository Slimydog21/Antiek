"""Consumer double-run launch for session↔window composition."""

from __future__ import annotations

import os
import sys

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
    open_from_highlight,
    open_session_as_window,
    open_sessions_as_windows,
    session_to_window_descriptor,
    sync_session_window_mode,
    window_id_for_session,
)
from substrate.floating_session.store import InMemorySessionStore  # noqa: E402


def _once() -> dict[str, object]:
    eng = InMemoryEngagementStore()
    sess = InMemorySessionStore()
    wins = InMemoryWindowStore()
    s1 = open_from_highlight(
        HighlightSelection(
            asset_id="launch-asset",
            selection_text="Transformer attention is content-addressable memory.",
            region_id="r-launch-1",
        ),
        engagement_store=eng,
        session_store=sess,
        model_id="launch-model",
        view_mode="floating",
    )
    s2 = open_from_highlight(
        HighlightSelection(
            asset_id="launch-asset",
            selection_text="Second passage for multi-session windows.",
            region_id="r-launch-2",
        ),
        engagement_store=eng,
        session_store=sess,
        view_mode="floating",
    )
    d1 = session_to_window_descriptor(s1)
    assert d1.kind == DEEP_RESEARCH_WINDOW_KIND
    assert d1.payload["session_id"] == s1.session_id
    opened = open_sessions_as_windows(
        "launch-asset",
        session_store=sess,
        window_store=wins,
        session_ids=[s1.session_id, s2.session_id],
    )
    assert len(opened) == 2
    assert opened[0].window_id != opened[1].window_id
    sync_session_window_mode(
        s1.session_id, "full", session_store=sess, window_store=wins
    )
    w = wins.get(window_id_for_session(s1.session_id))
    assert w is not None and w["mode"] == "full"
    # reopen same session stable
    again = open_session_as_window(s1, window_store=wins)
    assert again.window_id == window_id_for_session(s1.session_id)
    return {
        "session_1": s1.session_id,
        "session_2": s2.session_id,
        "window_1": window_id_for_session(s1.session_id),
        "window_2": window_id_for_session(s2.session_id),
        "kind": d1.kind,
        "payload_parent": d1.payload["parent_asset_id"],
        "mode_after_sync": w["mode"],
    }


def test_session_window_compose_consumer_double_run_stable():
    a = _once()
    b = _once()
    assert a == b
    assert a["window_1"] != a["window_2"]
    assert a["kind"] == DEEP_RESEARCH_WINDOW_KIND
    assert a["payload_parent"] == "launch-asset"
    assert a["mode_after_sync"] == "full"
