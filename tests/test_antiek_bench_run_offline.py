"""Antiek-bench offline dogfood product path (residual bo)."""

from __future__ import annotations

import os
import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from interfaces.research.api.settings_budget import (  # noqa: E402
    register_settings_budget_routes,
)
from substrate.antiek_bench import (  # noqa: E402
    COMPETITIVE_DOGFOOD_VERSION,
    DEFAULT_OFFLINE_MODELS,
    InMemoryBenchStore,
    build_leaderboard,
    run_offline_dogfood_product,
)
from substrate.antiek_bench.settings_surface import (  # noqa: E402
    settings_suite_proposal_payload,
)
from substrate.antiek_bench.suite import SuiteRegistry  # noqa: E402
from substrate.antiek_bench.usage_bridge import list_usage_events  # noqa: E402


def test_run_offline_dogfood_product_records_and_ranks():
    store = InMemoryBenchStore()
    out = run_offline_dogfood_product(
        week_id="2026-W28",
        store=store,
        include_html=True,
    )
    assert out["offline"] is True
    assert out["auto_promoted"] is False
    assert out["view_format"] == "html"
    assert out["suite_version"] == COMPETITIVE_DOGFOOD_VERSION
    assert out["run_count"] == len(DEFAULT_OFFLINE_MODELS)
    assert len(out["runs"]) == len(DEFAULT_OFFLINE_MODELS)
    assert out["recommended_model_id"] == "stub-strong"
    assert out["html"]
    assert "application/pdf" not in out["html"].lower()
    # Residual (ds): dogfood scores → usage events for recursive suite rewrite.
    assert out["usage_events_recorded"] > 0
    events = list_usage_events(store=store)
    assert len(events) == out["usage_events_recorded"]
    assert all(e.get("source") == "antiek_bench.offline_dogfood" for e in events)

    snap = build_leaderboard("2026-W28", store=store)
    assert snap.run_count == len(DEFAULT_OFFLINE_MODELS)
    assert snap.models[0].model_id == "stub-strong"
    # Strong stub should beat weak
    assert snap.models[0].mean_score >= snap.models[-1].mean_score

    # Suite proposal can form from dogfood usage; never auto-promoted.
    prop = settings_suite_proposal_payload(
        store=store, registry=SuiteRegistry(), include_html=True
    )
    assert prop["auto_promoted"] is False
    assert prop["view_format"] == "html"
    assert prop["has_proposal"] is True
    assert prop["status"] == "proposed"


def test_run_offline_rejects_empty_week():
    store = InMemoryBenchStore()
    try:
        run_offline_dogfood_product(week_id="  ", store=store)
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "week_id" in str(exc).lower()


def test_api_run_offline_and_leaderboard():
    store = InMemoryBenchStore()
    app = FastAPI()
    register_settings_budget_routes(app)
    app.state.antiek_bench_store = store
    client = TestClient(app)

    r = client.post(
        "/settings/antiek-bench/run-offline",
        json={"week_id": "2026-W28", "include_html": True},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["offline"] is True
    assert body["run_count"] == 3
    assert body["recommended_model_id"] == "stub-strong"
    assert body["view_format"] == "html"
    assert body["html"]

    lb = client.get(
        "/settings/antiek-bench/leaderboard",
        params={"week_id": "2026-W28", "include_html": "true"},
    )
    assert lb.status_code == 200
    lbody = lb.json()
    assert lbody["run_count"] == 3
    assert lbody["recommended_model_id"] == "stub-strong"
    assert lbody["models"][0]["model_id"] == "stub-strong"

    # Custom cohort
    r2 = client.post(
        "/settings/antiek-bench/run-offline",
        json={
            "week_id": "2026-W29",
            "include_html": False,
            "models": [
                {"model_id": "a-high", "quality": 0.99},
                {"model_id": "b-low", "quality": 0.1},
            ],
        },
    )
    assert r2.status_code == 200
    b2 = r2.json()
    assert b2["run_count"] == 2
    assert b2["recommended_model_id"] == "a-high"
    assert set(b2["models_run"]) == {"a-high", "b-low"}
