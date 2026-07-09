"""Settings Antiek-bench leaderboard product path polish (residual bd)."""

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
    default_core_suite,
    register_suite,
    run_suite,
    settings_leaderboard_payload,
)
from substrate.antiek_bench.run import keyword_stub_provider  # noqa: E402


@pytest.fixture
def store():
    return InMemoryBenchStore()


@pytest.fixture
def registry():
    reg = SuiteRegistry()
    register_suite(default_core_suite(), registry=reg, make_active=True)
    return reg


def test_settings_leaderboard_payload_html(store, registry):
    run_suite(
        model_id="strong",
        week_id="2026-W28",
        store=store,
        registry=registry,
        provider_fn=keyword_stub_provider("strong", quality=1.0),
    )
    payload = settings_leaderboard_payload(
        "2026-W28", store=store, include_html=True
    )
    assert payload["view_format"] == "html"
    assert payload["recommended_model_id"] == "strong"
    assert payload["html"]
    assert "application/pdf" not in payload["html"].lower()


def test_settings_api_leaderboard_with_store_double_run(store, registry):
    run_suite(
        model_id="a",
        week_id="2026-W28",
        store=store,
        registry=registry,
        provider_fn=keyword_stub_provider("a", quality=0.9),
    )
    run_suite(
        model_id="b",
        week_id="2026-W28",
        store=store,
        registry=registry,
        provider_fn=keyword_stub_provider("b", quality=0.2),
    )
    app = FastAPI()
    register_settings_budget_routes(app)
    app.state.antiek_bench_store = store
    client = TestClient(app)

    r1 = client.get(
        "/settings/antiek-bench/leaderboard?week_id=2026-W28&include_html=true"
    )
    r2 = client.get(
        "/settings/antiek-bench/leaderboard?week_id=2026-W28&include_html=true"
    )
    assert r1.status_code == 200, r1.text
    assert r2.status_code == 200
    b1, b2 = r1.json(), r2.json()
    assert b1["view_format"] == "html"
    assert b1["run_count"] == 2
    assert b1["recommended_model_id"] == b2["recommended_model_id"]
    assert b1["models"][0]["model_id"] == b2["models"][0]["model_id"]
    assert b1["html"]


def test_settings_api_leaderboard_honest_empty_without_store():
    app = FastAPI()
    register_settings_budget_routes(app)
    from interfaces.research.api import engagement_routes as eng

    eng._bench_usage_store = None
    client = TestClient(app)
    r = client.get("/settings/antiek-bench/leaderboard?week_id=2026-W28")
    assert r.status_code == 200
    body = r.json()
    assert body["run_count"] == 0
    assert body["view_format"] == "html"
    assert body["notes"]
