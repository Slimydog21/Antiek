"""Consumer double-run: highlight → session + window product path."""

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
    open_deep_research_from_highlight,
    window_id_for_session,
)
from substrate.floating_session.store import InMemorySessionStore  # noqa: E402


def _once() -> dict[str, object]:
    eng = InMemoryEngagementStore()
    sess = InMemorySessionStore()
    wins = InMemoryWindowStore()
    sel = HighlightSelection(
        asset_id="launch-asset",
        selection_text="Transformer attention is content-addressable memory.",
        region_id="r-launch-1",
    )
    r1 = open_deep_research_from_highlight(
        sel,
        engagement_store=eng,
        session_store=sess,
        window_store=wins,
        model_id="launch-model",
    )
    r2 = open_deep_research_from_highlight(
        sel,
        engagement_store=eng,
        session_store=sess,
        window_store=wins,
        model_id="launch-model",
    )
    assert r1.session.session_id == r2.session.session_id
    assert r1.window.window_id == r2.window.window_id
    assert r1.window.kind == DEEP_RESEARCH_WINDOW_KIND
    assert r1.window.payload["view_format"] == "html"
    assert "content-addressable" in r1.window.payload["selection_text"]
    return {
        "session_id": r1.session.session_id,
        "spawn_id": r1.session.spawn_id,
        "window_id": r1.window.window_id,
        "kind": r1.window.kind,
        "parent": r1.window.payload["parent_asset_id"],
        "stable_window": window_id_for_session(r1.session.session_id),
    }


def test_highlight_product_path_double_run_stable():
    a = _once()
    b = _once()
    assert a == b
    assert a["window_id"] == a["stable_window"]
    assert a["kind"] == DEEP_RESEARCH_WINDOW_KIND
    assert a["parent"] == "launch-asset"
