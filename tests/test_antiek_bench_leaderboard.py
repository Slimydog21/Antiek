"""Real-path tests for settings-facing Antiek-bench leaderboard residual."""

from __future__ import annotations

import os
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from interfaces.research.api.settings_budget import (  # noqa: E402
    register_settings_budget_routes,
)
from substrate.antiek_bench import (  # noqa: E402
    InMemoryBenchStore,
    SuiteRegistry,
    build_leaderboard,
    default_core_suite,
    project_leaderboard_html,
    register_suite,
    run_suite,
    settings_leaderboard_payload,
)
from substrate.antiek_bench.run import keyword_stub_provider  # noqa: E402


@pytest.fixture
def store() -> InMemoryBenchStore:
    return InMemoryBenchStore()


@pytest.fixture
def registry() -> SuiteRegistry:
    reg = SuiteRegistry()
    register_suite(default_core_suite(), registry=reg, make_active=True)
    return reg


def _seed_runs(store: InMemoryBenchStore, registry: SuiteRegistry, week: str) -> None:
    run_suite(
        model_id="strong-model",
        week_id=week,
        store=store,
        registry=registry,
        provider_fn=keyword_stub_provider("strong-model", quality=1.0),
    )
    run_suite(
        model_id="weak-model",
        week_id=week,
        store=store,
        registry=registry,
        provider_fn=keyword_stub_provider("weak-model", quality=0.15),
    )


def test_build_leaderboard_orders_by_mean_and_task_classes(store, registry):
    week = "2026-W28"
    _seed_runs(store, registry, week)
    snap = build_leaderboard(week, store=store)
    assert snap.week_id == week
    assert snap.run_count == 2
    assert len(snap.models) == 2
    assert snap.models[0].model_id == "strong-model"
    assert snap.models[0].mean_score >= snap.models[1].mean_score
    assert snap.models[1].model_id == "weak-model"
    assert "distill" in snap.task_classes
    assert "synthesize" in snap.task_classes
    assert "distill" in snap.models[0].by_task_class
    assert "synthesize" in snap.models[0].by_task_class
    # JSON-serializable
    d = snap.to_dict()
    assert d["week_id"] == week
    assert isinstance(d["models"], list)
    assert d["view_format"] == "html"


def test_leaderboard_stable_for_same_runs(store, registry):
    week = "2026-W28"
    _seed_runs(store, registry, week)
    a = build_leaderboard(week, store=store).to_dict()
    b = build_leaderboard(week, store=store).to_dict()
    assert a == b


def test_leaderboard_empty_week(store):
    snap = build_leaderboard("2026-W01", store=store)
    assert snap.run_count == 0
    assert snap.models == ()


def test_settings_payload_recommends_top_model(store, registry):
    week = "2026-W28"
    _seed_runs(store, registry, week)
    payload = settings_leaderboard_payload(week, store=store, include_html=False)
    assert payload["settings_panel"] == "antiek_bench_weekly"
    assert payload["recommended_model_id"] == "strong-model"
    assert payload["recommended_mean_score"] is not None
    means = [float(r["mean_score"]) for r in store.list_runs()]
    assert payload["recommended_mean_score"] == max(means)


def test_project_leaderboard_html_content(store, registry):
    week = "2026-W28"
    _seed_runs(store, registry, week)
    snap = build_leaderboard(week, store=store)
    html = project_leaderboard_html(snap)
    assert week in html
    assert "strong-model" in html
    assert "weak-model" in html
    assert "distill" in html
    assert "synthesize" in html
    assert "mean_score" in html or "0." in html
    assert not html.lstrip().lower().startswith("%pdf")


def test_settings_api_route_with_injected_store(store, registry):
    week = "2026-W28"
    _seed_runs(store, registry, week)
    app = FastAPI()
    register_settings_budget_routes(app)
    app.state.antiek_bench_store = store
    client = TestClient(app)
    res = client.get("/settings/antiek-bench/leaderboard", params={"week_id": week})
    assert res.status_code == 200
    body = res.json()
    assert body["week_id"] == week
    assert body["run_count"] == 2
    assert body["models"][0]["model_id"] == "strong-model"
    assert "distill" in body["task_classes"]
    assert body["recommended_model_id"] == "strong-model"


def test_settings_api_honest_empty_without_store():
    app = FastAPI()
    register_settings_budget_routes(app)
    client = TestClient(app)
    res = client.get(
        "/settings/antiek-bench/leaderboard", params={"week_id": "2026-W28"}
    )
    assert res.status_code == 200
    body = res.json()
    assert body["run_count"] == 0
    assert body["models"] == []
    assert any("not configured" in n for n in body["notes"])
