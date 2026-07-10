"""API tests for engagement spine routes (process-local store MVP)."""

from __future__ import annotations

import os
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from interfaces.research.api import engagement_routes as eng_mod  # noqa: E402
from interfaces.research.api.engagement_routes import (  # noqa: E402
    register_engagement_routes,
    reset_engagement_stores,
)
from substrate.engagement_spine import record_twin_insight  # noqa: E402


@pytest.fixture
def client():
    reset_engagement_stores()
    app = FastAPI()
    register_engagement_routes(app)
    return TestClient(app)


def test_spawn_attach_context_collective(client):
    r = client.post(
        "/engagement/spawn-from-highlight",
        json={
            "asset_id": "paper-1",
            "selection_text": "Attention is all you need.",
            "region_id": "r1",
            "references": ["https://arxiv.org/abs/1706.03762"],
            "model_id": "glm-test",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["spawn_id"].startswith("spn_")
    assert body["view_format"] == "html"
    assert len(body["source_references"]) == 1
    spawn_id = body["spawn_id"]

    r2 = client.post(
        "/engagement/attach-refs",
        json={
            "spawn_id": spawn_id,
            "references": ["https://research.substack.com/p/attention"],
        },
    )
    assert r2.status_code == 200
    assert len(r2.json()["source_references"]) == 2
    # Residual (ko): attach-refs surfaces reserved spawn research_tier.
    assert r2.json().get("research_tier") in ("fast", "deep", "wrestle")

    # Seed a twin into the process store for promote path
    record_twin_insight(
        "paper-1",
        "Self-attention is content-addressed routing.",
        store=eng_mod._eng(),
    )

    r3 = client.post(
        "/engagement/research-context",
        json={"asset_id": "paper-1", "spawn_id": spawn_id},
    )
    assert r3.status_code == 200
    ctx = r3.json()
    assert ctx["view_format"] == "html"
    assert ctx["twin_count"] >= 1
    assert ctx["ref_count"] == 2
    assert "prompt_block" in ctx
    assert "Self-attention" in ctx["prompt_block"]

    # Second spawn for collective
    r4 = client.post(
        "/engagement/spawn-from-highlight",
        json={
            "asset_id": "paper-2",
            "selection_text": "Residual learning.",
            "region_id": "r2",
            "references": ["https://arxiv.org/abs/1512.03385"],
        },
    )
    spawn2 = r4.json()["spawn_id"]
    r5 = client.post(
        "/engagement/collective",
        json={"spawn_ids": [spawn_id, spawn2], "include_twin_promote": True},
    )
    assert r5.status_code == 200
    col = r5.json()
    assert col["collective_id"].startswith("col_")
    assert col["spawn_count"] == 2
    assert "prompt_block" in col
    # Residual (oi): multi-spawn collective feeds Antiek-bench recursive rewrite.
    assert "usage_event" in col
    assert col["usage_event"]["source"] == "collective_merge"
    assert col["usage_event"]["outcome"] == "worked"
    assert col["usage_event"]["task_class"] in (
        "synthesize",
        "distill",
        "wrestle",
        "book_qa",
    )


def test_session_open_and_flywheel(client):
    r = client.post(
        "/engagement/sessions/open",
        json={
            "asset_id": "book-x",
            "selection_text": "A passage worth deep research.",
            "region_id": "bx1",
            "references": ["2402.03300"],
            "view_mode": "floating",
            "research_tier": "wrestle",
        },
    )
    assert r.status_code == 200
    open_body = r.json()
    session_id = open_body["session_id"]
    assert session_id.startswith("fsess_")
    # Residual (ji): open echoes research_tier when provided.
    assert open_body.get("research_tier") == "wrestle"
    # Residual (nw): session open feeds Antiek-bench (floating_deep_research).
    assert "usage_event" in open_body
    assert open_body["usage_event"]["outcome"] == "worked"
    assert open_body["usage_event"]["task_class"] == "wrestle"
    assert open_body["usage_event"]["source"] == "floating_deep_research"

    r2 = client.post(
        "/engagement/sessions/complete-flywheel",
        json={
            "session_id": session_id,
            "output_text": "Analysis complete.",
            "insights": ["Finding from deep research session."],
            "questions": ["What remains open?"],
        },
    )
    assert r2.status_code == 200, r2.text
    body = r2.json()
    assert body["status"] == "complete"
    assert body["view_format"] == "html"
    assert body["context"]["twin_count"] >= 1
    assert "prompt_block" in body
    assert "usage_event" in body
    assert body["usage_event"]["outcome"] == "worked"
    # Residual (jt): wrestle session → wrestle bench task_class (not distill).
    assert body.get("research_tier") == "wrestle"
    assert body["usage_event"].get("task_class") == "wrestle"


def test_session_open_twin_chase_usage_source(client):
    """Residual (nw): Twin chase goal_hint → usage source=twin_chase."""
    r = client.post(
        "/engagement/sessions/open",
        json={
            "asset_id": "paper-y",
            "selection_text": "[question] What follows?\n\n[insight] Claim X",
            "goal_hint": "Twin chase on paper-y: 2 note(s) (questions=1, insights=1) · note_ids=q1,i1",
            "view_mode": "floating",
            "research_tier": "deep",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body.get("research_tier") == "deep"
    assert body["usage_event"]["source"] == "twin_chase"
    assert body["usage_event"]["task_class"] == "synthesize"
    assert body["usage_event"]["outcome"] == "worked"
    assert "Twin chase" in (body["usage_event"].get("prompt_hint") or "")


def test_session_open_highlight_dr_launch_usage_source(client):
    """Residual (asu/asv): highlighted passage/synthesis goal_hint → highlight_dr_launch."""
    r = client.post(
        "/engagement/sessions/open",
        json={
            "asset_id": "doc-read",
            "selection_text": "Attention is content-addressable memory.",
            "goal_hint": "Deep-research the highlighted passage from reading",
            "view_mode": "floating",
            "research_tier": "deep",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["usage_event"]["source"] == "highlight_dr_launch"
    assert body["usage_event"]["task_class"] == "synthesize"
    assert body["usage_event"]["outcome"] == "worked"
    assert "highlighted passage" in (body["usage_event"].get("prompt_hint") or "").lower()

    # Residual (asv): ResearchWorkstation HighlightToolbar synthesis path.
    r2 = client.post(
        "/engagement/sessions/open",
        json={
            "asset_id": "synth-1",
            "selection_text": "Synthesis claim under test.",
            "goal_hint": "Deep-research the highlighted synthesis passage",
            "view_mode": "full",
            "research_tier": "wrestle",
        },
    )
    assert r2.status_code == 200
    body2 = r2.json()
    assert body2["usage_event"]["source"] == "highlight_dr_launch"
    assert body2["usage_event"]["task_class"] == "wrestle"


def test_attach_unknown_spawn_404(client):
    r = client.post(
        "/engagement/attach-refs",
        json={"spawn_id": "spn_missing", "references": ["1706.03762"]},
    )
    assert r.status_code == 404


def test_spawn_rejects_empty_selection(client):
    r = client.post(
        "/engagement/spawn-from-highlight",
        json={"asset_id": "a", "selection_text": "  "},
    )
    assert r.status_code == 400


def test_durable_file_store_survives_reset_rebuild(tmp_path, monkeypatch):
    """ANTIEK_ENGAGEMENT_DIR → FileEngagementStore; data survives store rebuild."""
    monkeypatch.setenv("ANTIEK_ENGAGEMENT_DIR", str(tmp_path / "eng-data"))
    reset_engagement_stores()
    app = FastAPI()
    register_engagement_routes(app)
    c = TestClient(app)
    r = c.post(
        "/engagement/spawn-from-highlight",
        json={
            "asset_id": "durable-asset",
            "selection_text": "durable passage",
            "region_id": "d1",
            "references": ["1706.03762"],
        },
    )
    assert r.status_code == 200
    spawn_id = r.json()["spawn_id"]

    # Rebuild stores from same dir (simulates process restart)
    reset_engagement_stores()
    app2 = FastAPI()
    register_engagement_routes(app2)
    c2 = TestClient(app2)
    r2 = c2.post(
        "/engagement/attach-refs",
        json={"spawn_id": spawn_id, "references": ["https://x.substack.com/p/y"]},
    )
    assert r2.status_code == 200, r2.text
    kinds = {ref["kind"] for ref in r2.json()["source_references"]}
    assert "arxiv" in kinds
    assert "substack" in kinds
