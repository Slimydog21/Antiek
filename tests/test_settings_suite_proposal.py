"""Settings Antiek-bench suite-proposal product path (residual al)."""

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
    active_suite,
    default_core_suite,
    record_usage_event,
    register_suite,
    settings_suite_proposal_payload,
)
from substrate.antiek_bench.usage_bridge import UsageEvent  # noqa: E402


@pytest.fixture
def store():
    return InMemoryBenchStore()


@pytest.fixture
def registry():
    reg = SuiteRegistry()
    register_suite(default_core_suite(), registry=reg, make_active=True)
    return reg


def test_settings_suite_proposal_from_usage_events(store, registry):
    before = active_suite(registry=registry).suite_version
    record_usage_event(
        UsageEvent(
            task_class="distill",
            outcome="failed",
            prompt_hint="Distill failed long-context collapse",
        ),
        store=store,
    )
    record_usage_event(
        UsageEvent(task_class="wrestle", outcome="worked", prompt_hint="ok"),
        store=store,
    )
    payload = settings_suite_proposal_payload(
        store=store, registry=registry, include_html=True
    )
    assert payload["has_proposal"] is True
    assert payload["status"] == "proposed"
    assert payload["proposal_id"] and str(payload["proposal_id"]).startswith("prop_")
    assert payload["rationale"]
    assert payload["auto_promoted"] is False
    assert payload["active_suite_unchanged"] is True
    assert payload["active_suite_version"] == before
    assert payload["view_format"] == "html"
    assert payload["event_count"] == 2
    assert payload["html"]
    assert "application/pdf" not in payload["html"].lower()
    assert "proposal" in payload["html"].lower() or "proposed" in payload["html"].lower()
    # Active suite must not change solely by propose
    assert active_suite(registry=registry).suite_version == before


def test_settings_suite_proposal_empty_usage_honest(store, registry):
    before = active_suite(registry=registry).suite_version
    payload = settings_suite_proposal_payload(
        store=store, registry=registry, include_html=True
    )
    assert payload["has_proposal"] is False
    assert payload["proposal_id"] is None
    assert payload["status"] is None
    assert payload["auto_promoted"] is False
    assert payload["event_count"] == 0
    assert payload["notes"]
    assert "no usage" in payload["notes"][0].lower() or "empty" in " ".join(
        payload["notes"]
    ).lower()
    assert payload["view_format"] == "html"
    assert payload["html"]
    assert active_suite(registry=registry).suite_version == before


def test_settings_api_suite_proposal_double_run_stable(store):
    record_usage_event(
        UsageEvent(
            task_class="book_qa",
            outcome="failed",
            prompt_hint="Answer passage question about themes",
        ),
        store=store,
    )
    app = FastAPI()
    register_settings_budget_routes(app)
    app.state.antiek_bench_store = store
    client = TestClient(app)

    r1 = client.get("/settings/antiek-bench/suite-proposal?include_html=true")
    assert r1.status_code == 200, r1.text
    b1 = r1.json()
    assert b1["has_proposal"] is True
    assert b1["status"] == "proposed"
    assert b1["proposal_id"]
    assert b1["auto_promoted"] is False
    assert b1["active_suite_unchanged"] is True
    assert b1["view_format"] == "html"
    assert b1["html"]
    assert b1["rationale"]

    r2 = client.get("/settings/antiek-bench/suite-proposal?include_html=true")
    assert r2.status_code == 200
    b2 = r2.json()
    # Deterministic proposal identity for fixed usage events
    assert b2["proposal_id"] == b1["proposal_id"]
    assert b2["status"] == b1["status"] == "proposed"
    assert b2["proposed_suite_version"] == b1["proposed_suite_version"]
    assert b2["auto_promoted"] is False
    assert b2["active_suite_version"] == b1["active_suite_version"]


def test_settings_api_honest_empty_without_store():
    app = FastAPI()
    register_settings_budget_routes(app)
    from interfaces.research.api import engagement_routes as eng

    eng._bench_usage_store = None
    client = TestClient(app)
    r = client.get("/settings/antiek-bench/suite-proposal")
    assert r.status_code == 200
    body = r.json()
    assert body["has_proposal"] is False
    assert body["auto_promoted"] is False
    assert body["view_format"] == "html"
    assert body["notes"]
    assert "empty" in body["notes"][0].lower() or "no " in body["notes"][0].lower()
