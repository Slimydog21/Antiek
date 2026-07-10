"""Real-path tests for highlight→floating deep-research session residual."""

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
    get_spawn,
)
from substrate.floating_session import (  # noqa: E402
    complete_session_research,
    get_session,
    list_sessions_for_asset,
    merge_sessions,
    open_from_highlight,
    project_session_html,
    set_view_mode,
)
from substrate.floating_session.store import InMemorySessionStore  # noqa: E402


@pytest.fixture
def eng():
    return InMemoryEngagementStore()


@pytest.fixture
def sessions():
    return InMemorySessionStore()


def test_open_from_highlight_reserves_spawn(eng, sessions):
    sel = HighlightSelection(
        asset_id="book-1",
        selection_text="Attention is content-addressable memory.",
        region_id="r-p12",
        page=12,
    )
    s = open_from_highlight(
        sel,
        engagement_store=eng,
        session_store=sessions,
        model_id="glm-5.2",
        view_mode="floating",
    )
    assert s.session_id.startswith("fsess_")
    assert s.spawn_id.startswith("spn_")
    assert s.investigation_id.startswith("inv_")
    assert s.parent_asset_id == "book-1"
    assert s.view_mode == "floating"
    assert s.model_id == "glm-5.2"
    assert s.status == "reserved"
    spawn = get_spawn(s.spawn_id, store=eng)
    assert spawn is not None
    assert spawn.spawn_id == s.spawn_id


def test_open_idempotent_same_region(eng, sessions):
    sel = HighlightSelection(
        asset_id="a1",
        selection_text="same passage",
        region_id="region-x",
    )
    a = open_from_highlight(sel, engagement_store=eng, session_store=sessions)
    b = open_from_highlight(sel, engagement_store=eng, session_store=sessions)
    assert a.session_id == b.session_id
    assert a.spawn_id == b.spawn_id
    listed = list_sessions_for_asset("a1", session_store=sessions)
    assert len(listed) == 1


def test_set_view_mode_floating_full(eng, sessions):
    sel = HighlightSelection(asset_id="a", selection_text="passage", region_id="r1")
    s = open_from_highlight(
        sel, engagement_store=eng, session_store=sessions, view_mode="floating"
    )
    full = set_view_mode(s.session_id, "full", session_store=sessions)
    assert full.view_mode == "full"
    assert full.session_id == s.session_id
    assert full.spawn_id == s.spawn_id
    back = set_view_mode(s.session_id, "floating", session_store=sessions)
    assert back.view_mode == "floating"
    # Spawn intact
    assert get_spawn(s.spawn_id, store=eng) is not None


def test_merge_into_parent_and_draft(eng, sessions):
    sel = HighlightSelection(
        asset_id="doc-m",
        selection_text="Bayes updates priors with evidence.",
        region_id="r-bayes",
    )
    s = open_from_highlight(sel, engagement_store=eng, session_store=sessions)
    complete_session_research(
        s.session_id,
        session_store=sessions,
        engagement_store=eng,
        output_text="Posterior is proportional to likelihood times prior.",
        insights=["Bayesian update is multiplicative in odds form"],
        questions=["How does this scale to hierarchical models?"],
    )
    draft = merge_sessions(
        "doc-m",
        [s.session_id],
        session_store=sessions,
        engagement_store=eng,
        mode="draft_combined",
        parent_title="Bayes notes",
        parent_body="Original body.",
    )
    assert draft["mode"] == "draft_combined"
    assert draft["document_id"].startswith("draft_")
    assert s.spawn_id in draft["source_spawn_ids"]
    assert s.session_id in draft["source_session_ids"]

    parent = merge_sessions(
        "doc-m",
        [s.session_id],
        session_store=sessions,
        engagement_store=eng,
        mode="into_parent",
        parent_title="Bayes notes",
        parent_body="Original body.",
    )
    assert parent["mode"] == "into_parent"
    assert parent["document_id"] == "doc-m"


def test_multi_session_collective_merge(eng, sessions):
    s1 = open_from_highlight(
        HighlightSelection(asset_id="doc-c", selection_text="first highlight", region_id="r1"),
        engagement_store=eng,
        session_store=sessions,
    )
    s2 = open_from_highlight(
        HighlightSelection(asset_id="doc-c", selection_text="second highlight", region_id="r2"),
        engagement_store=eng,
        session_store=sessions,
    )
    for s in (s1, s2):
        complete_session_research(
            s.session_id,
            session_store=sessions,
            engagement_store=eng,
            output_text=f"Research for {s.session_id}",
            insights=[f"Insight {s.spawn_id}"],
            questions=[f"Question {s.spawn_id}?"],
        )
    merged = merge_sessions(
        "doc-c",
        [s1.session_id, s2.session_id],
        session_store=sessions,
        engagement_store=eng,
        mode="draft_combined",
        parent_title="Collective analysis",
    )
    assert len(merged["source_spawn_ids"]) == 2
    assert s1.spawn_id in merged["source_spawn_ids"]
    assert s2.spawn_id in merged["source_spawn_ids"]
    assert merged["sections_merged"] >= 1


def test_project_session_html_not_pdf(eng, sessions):
    s = open_from_highlight(
        HighlightSelection(
            asset_id="doc-h",
            selection_text="HTML-first reading asset passage.",
            region_id="r-html",
        ),
        engagement_store=eng,
        session_store=sessions,
        model_id="composer-2.5",
    )
    html = project_session_html(
        s.session_id, session_store=sessions, engagement_store=eng
    )
    assert s.session_id in html or s.spawn_id in html
    assert "doc-h" in html or "HTML-first" in html
    assert not html.lstrip().lower().startswith("%pdf")

    complete_session_research(
        s.session_id,
        session_store=sessions,
        engagement_store=eng,
        output_text="Merged research prose about HTML vision.",
        insights=["HTML is agent-controllable"],
        questions=["What breaks PDF-first workflows?"],
    )
    merge = merge_sessions(
        "doc-h",
        [s.session_id],
        session_store=sessions,
        engagement_store=eng,
        mode="draft_combined",
        parent_title="HTML vision",
    )
    html2 = project_session_html(
        s.session_id,
        session_store=sessions,
        engagement_store=eng,
        merge_result=merge,
    )
    assert len(html2) > 40
    assert not html2.lstrip().lower().startswith("%pdf")
    assert "HTML" in html2 or "vision" in html2.lower() or s.spawn_id in html2


def test_get_session_refreshes_status(eng, sessions):
    s = open_from_highlight(
        HighlightSelection(asset_id="x", selection_text="t", region_id="r"),
        engagement_store=eng,
        session_store=sessions,
    )
    complete_session_research(
        s.session_id,
        session_store=sessions,
        engagement_store=eng,
        output_text="done",
    )
    again = get_session(
        s.session_id, session_store=sessions, engagement_store=eng
    )
    assert again is not None
    assert again.status == "complete"
