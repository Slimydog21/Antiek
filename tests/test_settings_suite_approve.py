"""Settings explicit suite approve/promote product path (residual am)."""

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
    settings_approve_suite_proposal_payload,
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


def _seed_failed(store):
    record_usage_event(
        UsageEvent(
            task_class="distill",
            outcome="failed",
            prompt_hint="Approve residual failed distill case",
        ),
        store=store,
    )


def test_approve_promotes_active_suite(store, registry):
    _seed_failed(store)
    before = active_suite(registry=registry).suite_version
    prop = settings_suite_proposal_payload(store=store, registry=registry)
    assert prop["status"] == "proposed"
    pid = prop["proposal_id"]
    assert pid

    result = settings_approve_suite_proposal_payload(
        pid, store=store, registry=registry, approve=True, include_html=True
    )
    assert result["ok"] is True
    assert result["approved"] is True
    assert result["promoted"] is True
    assert result["status"] == "approved"
    assert result["active_suite_before"] == before
    assert result["active_suite_version"] != before
    assert result["active_suite_version"] == prop["proposed_suite_version"]
    assert active_suite(registry=registry).suite_version == result["active_suite_version"]
    assert result["view_format"] == "html"
    assert result["html"]
    assert "application/pdf" not in result["html"].lower()


def test_reject_leaves_active_unchanged(store, registry):
    _seed_failed(store)
    before = active_suite(registry=registry).suite_version
    prop = settings_suite_proposal_payload(store=store, registry=registry)
    pid = prop["proposal_id"]
    result = settings_approve_suite_proposal_payload(
        pid, store=store, registry=registry, approve=False
    )
    assert result["ok"] is True
    assert result["approved"] is False
    assert result["promoted"] is False
    assert result["status"] == "rejected"
    assert result["active_suite_version"] == before
    assert active_suite(registry=registry).suite_version == before


def test_unknown_proposal_honest(store, registry):
    result = settings_approve_suite_proposal_payload(
        "prop_does_not_exist", store=store, registry=registry, approve=True
    )
    assert result["ok"] is False
    assert result["promoted"] is False
    assert result["notes"]


def test_api_approve_gate_double_run_and_get_never_promotes(store, registry):
    _seed_failed(store)
    app = FastAPI()
    register_settings_budget_routes(app)
    app.state.antiek_bench_store = store
    app.state.antiek_bench_registry = registry
    client = TestClient(app)

    before = active_suite(registry=registry).suite_version
    g1 = client.get("/settings/antiek-bench/suite-proposal?include_html=true")
    assert g1.status_code == 200
    body = g1.json()
    assert body["status"] == "proposed"
    assert body["auto_promoted"] is False
    assert active_suite(registry=registry).suite_version == before
    pid = body["proposal_id"]

    # Double GET still proposed, not promoted
    g2 = client.get("/settings/antiek-bench/suite-proposal")
    assert g2.json()["status"] == "proposed"
    assert active_suite(registry=registry).suite_version == before

    r = client.post(
        "/settings/antiek-bench/suite-proposal/approve",
        json={"proposal_id": pid, "approve": True, "include_html": True},
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["ok"] is True
    assert out["promoted"] is True
    assert out["status"] == "approved"
    assert out["active_suite_version"] != before
    assert active_suite(registry=registry).suite_version == out["active_suite_version"]

    # Second approve of same id: still ok / already approved path via store status
    r2 = client.post(
        "/settings/antiek-bench/suite-proposal/approve",
        json={"proposal_id": pid, "approve": True},
    )
    assert r2.status_code == 200
    # Active remains the promoted version
    assert active_suite(registry=registry).suite_version == out["active_suite_version"]
