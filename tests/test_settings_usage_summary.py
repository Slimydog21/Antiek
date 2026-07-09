"""Settings weekly Antiek-bench usage summary product path (residual ai)."""

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
    record_usage_event,
    settings_usage_summary_payload,
    weekly_usage_summary,
)
from substrate.antiek_bench.usage_bridge import UsageEvent  # noqa: E402


@pytest.fixture
def store():
    return InMemoryBenchStore()


def test_settings_usage_summary_payload_matches_weekly(store):
    record_usage_event(
        UsageEvent(task_class="wrestle", outcome="worked", prompt_hint="a"),
        store=store,
    )
    record_usage_event(
        UsageEvent(task_class="book_qa", outcome="failed", prompt_hint="b"),
        store=store,
    )
    direct = weekly_usage_summary(store=store)
    payload = settings_usage_summary_payload(store=store, include_html=True)
    assert payload["view_format"] == "html"
    assert payload["event_count"] == direct["event_count"] == 2
    assert payload["by_task_class"] == direct["by_task_class"]
    assert "wrestle" in payload["by_task_class"]
    assert payload["by_task_class"]["book_qa"]["failed"] == 1
    assert payload["html"]
    assert "application/pdf" not in payload["html"].lower()
    assert "Events recorded: 2" in payload["html"] or "2" in payload["html"]


def test_settings_usage_summary_empty_store(store):
    payload = settings_usage_summary_payload(store=store, include_html=True)
    assert payload["event_count"] == 0
    assert payload["by_task_class"] == {}
    assert payload["view_format"] == "html"
    assert payload["html"]


def test_settings_api_usage_summary_with_injected_store(store):
    record_usage_event(
        UsageEvent(task_class="distill", outcome="worked"),
        store=store,
    )
    app = FastAPI()
    register_settings_budget_routes(app)
    app.state.antiek_bench_store = store
    client = TestClient(app)

    r1 = client.get("/settings/antiek-bench/usage-summary?include_html=true")
    assert r1.status_code == 200, r1.text
    body1 = r1.json()
    assert body1["event_count"] == 1
    assert body1["view_format"] == "html"
    assert body1["by_task_class"]["distill"]["worked"] == 1
    assert body1["html"]

    # Double-run stable
    r2 = client.get("/settings/antiek-bench/usage-summary?include_html=true")
    assert r2.status_code == 200
    body2 = r2.json()
    assert body2["event_count"] == body1["event_count"]
    assert body2["by_task_class"] == body1["by_task_class"]


def test_settings_api_honest_empty_without_store():
    app = FastAPI()
    register_settings_budget_routes(app)
    # Ensure engagement process store is empty/unset for this process path
    from interfaces.research.api import engagement_routes as eng

    eng._bench_usage_store = None
    client = TestClient(app)
    r = client.get("/settings/antiek-bench/usage-summary")
    assert r.status_code == 200
    body = r.json()
    assert body["event_count"] == 0
    assert body["view_format"] == "html"
    assert body["notes"]
    assert "empty" in body["notes"][0].lower() or "no " in body["notes"][0].lower()
