"""Competitive dogfood fixtures for Antiek-bench (residual av)."""

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
    InMemoryBenchStore,
    SuiteRegistry,
    active_suite,
    competitive_dogfood_suite,
    default_core_suite,
    dogfood_fixture_payload,
    register_competitive_dogfood_suite,
    register_suite,
    run_suite,
)
from substrate.antiek_bench.run import keyword_stub_provider  # noqa: E402


def test_dogfood_suite_covers_task_classes():
    suite = competitive_dogfood_suite()
    assert suite.suite_version == COMPETITIVE_DOGFOOD_VERSION
    classes = set(suite.task_classes())
    assert {"distill", "synthesize", "wrestle", "book_qa"} <= classes
    assert len(suite.items) >= 14
    # Residual (st): write-seed / float HTML / budget foresight postures.
    ids = {i.item_id for i in suite.items}
    assert "dogfood-wrestle-write-seed" in ids
    assert "dogfood-synth-float-evidence" in ids
    assert "dogfood-distill-budget-foresight" in ids
    # Residual (tf): Faraday book_qa electricity STEM.
    assert "dogfood-book-faraday-induction" in ids
    # Residual (tv): multi-spawn collective unit write-seed posture.
    assert "dogfood-wrestle-collective-unit-write-seed" in ids
    # Residual (tz): Boole computing/logic book_qa.
    assert "dogfood-book-boole-laws-of-thought" in ids
    # Residual (ud): Heaviside electricity engineering book_qa.
    assert "dogfood-book-heaviside-em" in ids
    # Residual (us): citation-trust ungrounded hydrate prep.
    assert "dogfood-wrestle-citation-trust-ungrounded" in ids
    # Residual (ve): twin cross-asset merge write-seed posture.
    assert "dogfood-wrestle-twin-cross-asset-merge-write-seed" in ids


def test_register_does_not_auto_activate():
    reg = SuiteRegistry()
    register_suite(default_core_suite(), registry=reg, make_active=True)
    before = active_suite(registry=reg).suite_version
    dog = register_competitive_dogfood_suite(registry=reg, make_active=False)
    assert dog.suite_version == COMPETITIVE_DOGFOOD_VERSION
    assert active_suite(registry=reg).suite_version == before
    assert before != COMPETITIVE_DOGFOOD_VERSION


def test_run_dogfood_offline():
    reg = SuiteRegistry()
    suite = register_competitive_dogfood_suite(registry=reg, make_active=True)
    store = InMemoryBenchStore()
    result = run_suite(
        model_id="stub",
        week_id="2026-W28",
        store=store,
        registry=reg,
        provider_fn=keyword_stub_provider("stub", quality=0.9),
    )
    assert result.mean_score >= 0.0
    assert len(result.scores) == len(suite.items)
    assert result.suite_version == COMPETITIVE_DOGFOOD_VERSION


def test_payload_and_api_html():
    payload = dogfood_fixture_payload(include_html=True)
    assert payload["auto_promoted"] is False
    assert payload["view_format"] == "html"
    assert payload["item_count"] >= 14
    assert payload["html"]
    assert "application/pdf" not in payload["html"].lower()
    # Residual (st/tf/tv/tz/ud/us/ve): v8 fixtures visible in HTML listing.
    assert "dogfood-wrestle-write-seed" in payload["html"]
    assert "twin_seed" in payload["html"]
    assert "dogfood-book-faraday-induction" in payload["html"]
    assert "faraday" in payload["html"].lower()
    assert "dogfood-wrestle-collective-unit-write-seed" in payload["html"]
    assert "collective_unit_prompt" in payload["html"]
    assert "dogfood-book-boole-laws-of-thought" in payload["html"]
    assert "boole" in payload["html"].lower()
    assert "dogfood-book-heaviside-em" in payload["html"]
    assert "heaviside" in payload["html"].lower()
    assert "dogfood-wrestle-citation-trust-ungrounded" in payload["html"]
    assert "ungrounded" in payload["html"].lower()
    assert "dogfood-wrestle-twin-cross-asset-merge-write-seed" in payload["html"]
    assert "twin_cross_asset_merge" in payload["html"]

    app = FastAPI()
    register_settings_budget_routes(app)
    client = TestClient(app)
    r1 = client.get("/settings/antiek-bench/dogfood-fixtures?include_html=true")
    r2 = client.get("/settings/antiek-bench/dogfood-fixtures?include_html=true")
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["suite_version"] == r2.json()["suite_version"]
    assert r1.json()["item_count"] == r2.json()["item_count"]
