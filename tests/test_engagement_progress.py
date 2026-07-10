"""Research progress telemetry product path (residual ar)."""

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
from substrate.engagement_spine import (  # noqa: E402
    HighlightSelection,
    InMemoryEngagementStore,
    progress_payload,
    record_progress,
    seed_default_pipeline,
    spawn_from_highlight,
)
from substrate.engagement_spine.progress import (  # noqa: E402
    COMPETITIVE_DR_PIPELINE_STAGES,
    competitive_stage_pipeline_progress,
)


@pytest.fixture
def client():
    reset_engagement_stores()
    app = FastAPI()
    register_engagement_routes(app)
    return TestClient(app)


def test_record_progress_pipeline():
    store = InMemoryEngagementStore()
    spawn = spawn_from_highlight(
        HighlightSelection(asset_id="a", selection_text="hello progress"),
        store=store,
    )
    events = seed_default_pipeline(spawn.spawn_id, store=store)
    assert len(events) == 4
    assert [e.stage for e in events] == ["plan", "gather", "synthesize", "cite"]
    payload = progress_payload(spawn.spawn_id, store=store, include_html=True)
    assert payload["event_count"] == 4
    assert payload["latest_stage"] == "cite"
    assert payload["is_terminal"] is False
    assert payload["view_format"] == "html"
    assert payload["html"]
    assert "application/pdf" not in payload["html"].lower()
    # Residual (jz): default research_tier deep on progress snapshot.
    assert payload["research_tier"] == "deep"
    # Residual (aqc): multi-stage pipeline completeness on payload + HTML.
    stage_pipe = payload["stage_pipeline"]
    assert stage_pipe["completed"] == ["plan", "gather", "synthesize", "cite"]
    assert stage_pipe["completed_count"] == 4
    assert stage_pipe["total"] == 5
    assert stage_pipe["current"] == "cite"
    assert stage_pipe["is_terminal"] is False
    assert abs(stage_pipe["coverage_ratio"] - 0.8) < 1e-9
    assert "Competitive pipeline" in payload["html"]
    assert "4/5" in payload["html"]
    # Residual (aqf): world-class readiness on progress (hops unknown).
    wc = payload["world_class_readiness"]
    assert wc["multi_stage_ready"] is True
    assert wc["citation_hops_ready"] is None
    assert wc["world_class_bar"] == "multi_stage"
    record_progress(spawn.spawn_id, "complete", "done", store=store)
    payload2 = progress_payload(spawn.spawn_id, store=store)
    assert payload2["latest_stage"] == "complete"
    assert payload2["is_terminal"] is True
    assert payload2["stage_pipeline"]["is_terminal"] is True
    assert "terminal" in payload2["stage_pipeline"]["completed"]


def test_competitive_stage_pipeline_progress_never_invents():
    """Residual (aqc): pure helper never invents unreported stages."""
    assert list(COMPETITIVE_DR_PIPELINE_STAGES) == [
        "plan",
        "gather",
        "synthesize",
        "cite",
        "terminal",
    ]
    empty = competitive_stage_pipeline_progress()
    assert empty["completed"] == []
    assert empty["current"] is None
    mid = competitive_stage_pipeline_progress(
        events=[{"stage": "plan"}, {"stage": "gather"}],
        latest_stage="gather",
    )
    assert mid["completed"] == ["plan", "gather"]
    assert mid["current"] == "gather"


def test_progress_payload_surfaces_spawn_research_tier_wrestle():
    """Residual (jz): progress snapshot carries reserved spawn research_tier."""
    store = InMemoryEngagementStore()
    spawn = spawn_from_highlight(
        HighlightSelection(
            asset_id="w",
            selection_text="wrestle progress",
            region_id="prog-w",
        ),
        store=store,
        research_tier="wrestle",
    )
    assert spawn.research_tier == "wrestle"
    seed_default_pipeline(spawn.spawn_id, store=store)
    payload = progress_payload(spawn.spawn_id, store=store, include_html=True)
    assert payload["research_tier"] == "wrestle"
    assert payload["spawn_id"] == spawn.spawn_id
    # Residual (ki): HTML projection includes tier for agent-readable audit.
    assert "tier=wrestle" in (payload.get("html") or "")
    assert "application/pdf" not in (payload.get("html") or "").lower()


def test_api_progress_double_run(client):
    r = client.post(
        "/engagement/spawn-from-highlight",
        json={"asset_id": "p", "selection_text": "progress api"},
    )
    assert r.status_code == 200
    sid = r.json()["spawn_id"]
    s1 = client.post(
        "/engagement/progress/seed",
        json={"spawn_id": sid, "include_html": True},
    )
    assert s1.status_code == 200, s1.text
    b1 = s1.json()
    assert b1["event_count"] == 4
    assert b1["view_format"] == "html"
    assert b1["html"]
    g1 = client.get(f"/engagement/progress/{sid}?include_html=true")
    g2 = client.get(f"/engagement/progress/{sid}?include_html=true")
    assert g1.status_code == 200 and g2.status_code == 200
    assert g1.json()["event_count"] == g2.json()["event_count"] == 4
    assert g1.json()["latest_stage"] == g2.json()["latest_stage"] == "cite"
    r3 = client.post(
        "/engagement/progress",
        json={"spawn_id": sid, "stage": "complete", "message": "finished"},
    )
    assert r3.status_code == 200
    assert r3.json()["is_terminal"] is True
