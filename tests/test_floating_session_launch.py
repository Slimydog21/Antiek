"""Consumer double-run launch for floating deep-research session public entry."""

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
    complete_session_research,
    merge_sessions,
    open_from_highlight,
    project_session_html,
    set_view_mode,
)
from substrate.floating_session.store import InMemorySessionStore  # noqa: E402


def _once() -> dict[str, object]:
    eng = InMemoryEngagementStore()
    sess = InMemorySessionStore()
    sel = HighlightSelection(
        asset_id="launch-asset",
        selection_text="Transformer attention is content-addressable memory.",
        region_id="r-launch-1",
    )
    s = open_from_highlight(
        sel,
        engagement_store=eng,
        session_store=sess,
        model_id="launch-model",
        view_mode="floating",
    )
    full = set_view_mode(s.session_id, "full", session_store=sess)
    assert full.view_mode == "full"
    floating = set_view_mode(s.session_id, "floating", session_store=sess)
    assert floating.view_mode == "floating"
    complete_session_research(
        s.session_id,
        session_store=sess,
        engagement_store=eng,
        output_text="QKV maps queries to keys and values.",
        insights=["Attention is content-addressable"],
        questions=["How does this scale past training length?"],
    )
    merge = merge_sessions(
        "launch-asset",
        [s.session_id],
        session_store=sess,
        engagement_store=eng,
        mode="draft_combined",
        parent_title="Launch proof",
    )
    html = project_session_html(
        s.session_id,
        session_store=sess,
        engagement_store=eng,
        merge_result=merge,
    )
    assert s.session_id.startswith("fsess_")
    assert merge["document_id"].startswith("draft_")
    assert len(html) > 40
    assert not html.lstrip().lower().startswith("%pdf")
    return {
        "session_id": s.session_id,
        "spawn_id": s.spawn_id,
        "document_id": merge["document_id"],
        "html_len": len(html),
    }


def test_floating_session_consumer_double_run_stable():
    a = _once()
    b = _once()
    assert a["session_id"] == b["session_id"]
    assert a["spawn_id"] == b["spawn_id"]
    assert a["document_id"] == b["document_id"]
    assert a["html_len"] == b["html_len"]
