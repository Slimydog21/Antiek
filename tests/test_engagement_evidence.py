"""Evidence pack product surface (residual as)."""

from __future__ import annotations

import os
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from interfaces.research.api.engagement_routes import (  # noqa: E402
    register_engagement_routes,
    reset_engagement_stores,
)
from interfaces.research.api import engagement_routes as eng_mod  # noqa: E402
from substrate.engagement_spine import (  # noqa: E402
    HighlightSelection,
    attach_source_references,
    build_citation_chain_hops,
    citation_chain_complete,
    evidence_pack_payload,
    record_twin_insight,
    record_twin_question,
    spawn_from_highlight,
)
from substrate.engagement_spine.evidence import (  # noqa: E402
    CITATION_HOP_PIPELINE_STAGES,
    citation_hop_pipeline_progress,
)


@pytest.fixture
def client():
    reset_engagement_stores()
    app = FastAPI()
    register_engagement_routes(app)
    return TestClient(app)


def test_build_citation_chain_hops_ordered_stages():
    """Residual (air): multi-hop stages with stable anchors · no invented edges."""
    hops = build_citation_chain_hops(
        ["Claim A", "  ", "Claim B"],
        ["Q1?"],
        [
            {
                "kind": "arxiv",
                "raw": "1706.03762",
                "canonical_url": "https://arxiv.org/abs/1706.03762",
            }
        ],
    )
    assert [h["hop"] for h in hops] == ["insights", "questions", "sources"]
    assert hops[0]["count"] == 2  # blank insight skipped
    assert hops[0]["items"][0]["anchor"] == "evidence-insight-0"
    assert hops[0]["items"][1]["text"] == "Claim B"
    assert hops[0]["items"][1]["anchor"] == "evidence-insight-2"
    assert hops[1]["items"][0]["anchor"] == "evidence-question-0"
    assert hops[2]["items"][0]["anchor"] == "evidence-source-0"
    assert "arxiv" in hops[2]["items"][0]["text"].lower()
    assert citation_chain_complete(2, 1) is True
    assert citation_chain_complete(0, 1) is False
    assert citation_chain_complete(1, 0) is False
    # Empty stages omitted — never invent hop edges.
    assert build_citation_chain_hops([], [], []) == []
    only_q = build_citation_chain_hops([], ["open?"], [])
    assert [h["hop"] for h in only_q] == ["questions"]


def test_citation_hop_pipeline_progress_never_invents():
    """Residual (apz): hop pipeline completeness mirrors frontend pure helper."""
    assert list(CITATION_HOP_PIPELINE_STAGES) == [
        "insights",
        "questions",
        "sources",
    ]
    mid = citation_hop_pipeline_progress(
        insight_count=2, question_count=0, ref_count=1
    )
    assert mid["present"] == ["insights", "sources"]
    assert mid["missing"] == ["questions"]
    assert mid["present_count"] == 2
    assert mid["total"] == 3
    assert abs(mid["coverage_ratio"] - (2 / 3)) < 1e-9
    assert mid["chain_complete"] is True

    empty = citation_hop_pipeline_progress()
    assert empty["present"] == []
    assert empty["missing"] == ["insights", "questions", "sources"]
    assert empty["chain_complete"] is False


def test_evidence_pack_with_twins_and_refs():
    store = eng_mod._eng()
    spawn = spawn_from_highlight(
        HighlightSelection(asset_id="paper-e", selection_text="attention"),
        store=store,
    )
    attach_source_references(
        spawn.spawn_id,
        ["https://arxiv.org/abs/1706.03762"],
        store=store,
    )
    record_twin_insight("paper-e", "Attention is content-addressable.", store=store)
    record_twin_question("paper-e", "How does multi-head help?", store=store)
    pack = evidence_pack_payload(
        "paper-e", store=store, spawn_id=spawn.spawn_id, include_html=True
    )
    assert pack["view_format"] == "html"
    assert pack["insight_count"] == 1
    assert pack["question_count"] == 1
    assert pack["ref_count"] == 1
    assert pack["html"]
    assert "application/pdf" not in pack["html"].lower()
    assert "content-addressable" in pack["html"]
    assert "1706.03762" in pack["html"] or "arxiv" in pack["html"].lower()
    # Residual (kc): default research_tier deep when spawn reserved without tier.
    assert pack["research_tier"] == "deep"
    # Residual (air): multi-hop citation chain payload + HTML hop projection.
    assert pack["chain_complete"] is True
    chain = pack["citation_chain"]
    assert isinstance(chain, list) and len(chain) == 3
    # Residual (apz): hop pipeline completeness summary on pack payload.
    hop_pipe = pack["citation_hop_pipeline"]
    assert hop_pipe["present"] == ["insights", "questions", "sources"]
    assert hop_pipe["missing"] == []
    assert hop_pipe["present_count"] == 3
    assert hop_pipe["coverage_ratio"] == 1.0
    assert hop_pipe["chain_complete"] is True
    assert [h["hop"] for h in chain] == ["insights", "questions", "sources"]
    assert chain[0]["items"][0]["anchor"] == "evidence-insight-0"
    assert chain[2]["items"][0]["anchor"] == "evidence-source-0"
    html = pack["html"] or ""
    assert "Citation chain hops:" in html
    assert "chain_complete=true" in html
    assert "evidence-insight-0" in html
    assert "evidence-source-0" in html


def test_evidence_pack_surfaces_spawn_research_tier_wrestle():
    """Residual (kc): evidence pack carries reserved spawn research_tier."""
    store = eng_mod._eng()
    spawn = spawn_from_highlight(
        HighlightSelection(
            asset_id="paper-w",
            selection_text="wrestle evidence",
            region_id="ev-w",
        ),
        store=store,
        research_tier="wrestle",
    )
    record_twin_insight("paper-w", "Wrestle insight", store=store)
    pack = evidence_pack_payload(
        "paper-w", store=store, spawn_id=spawn.spawn_id, include_html=True
    )
    assert pack["research_tier"] == "wrestle"
    assert pack["spawn_id"] == spawn.spawn_id
    # Residual (ki): HTML projection includes tier for agent-readable audit.
    assert "tier=wrestle" in (pack.get("html") or "")
    assert "application/pdf" not in (pack.get("html") or "").lower()


def test_api_evidence_pack_double_run(client):
    store = eng_mod._eng()
    spawn = spawn_from_highlight(
        HighlightSelection(asset_id="asset-e", selection_text="x"),
        store=store,
    )
    record_twin_insight("asset-e", "Insight A", store=store)
    r1 = client.post(
        "/engagement/evidence-pack",
        json={
            "asset_id": "asset-e",
            "spawn_id": spawn.spawn_id,
            "include_html": True,
        },
    )
    r2 = client.post(
        "/engagement/evidence-pack",
        json={
            "asset_id": "asset-e",
            "spawn_id": spawn.spawn_id,
            "include_html": True,
        },
    )
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["insight_count"] == r2.json()["insight_count"] == 1
    assert r1.json()["view_format"] == "html"
    assert r1.json()["html"]
    # Residual (air): API surfaces citation_chain + chain_complete (incomplete without refs).
    assert r1.json().get("chain_complete") is False
    assert isinstance(r1.json().get("citation_chain"), list)
    assert r1.json()["citation_chain"][0]["hop"] == "insights"
