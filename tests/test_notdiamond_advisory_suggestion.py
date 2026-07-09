"""NotDiamond advisory suggestion + install posture (residual br)."""

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
from substrate.antiek_bench import InMemoryBenchStore, run_offline_dogfood_product  # noqa: E402
from substrate.notdiamond_advisory import (  # noqa: E402
    notdiamond_advisory_payload,
    resolve_advisory_suggestion,
)


def test_offline_fallback_suggestion():
    s = resolve_advisory_suggestion()
    assert s["suggested_model_id"] == "stub-strong"
    assert s["notdiamond_is_dispatch_authority"] is False
    assert s["installable"] is True


def test_leaderboard_preferred_when_store_has_runs():
    store = InMemoryBenchStore()
    run_offline_dogfood_product(week_id="2026-W28", store=store, include_html=False)
    s = resolve_advisory_suggestion(store=store, week_id="2026-W28")
    assert s["suggested_model_id"] == "stub-strong"
    assert "leaderboard" in s["suggestion_source"]
    assert s["notdiamond_is_dispatch_authority"] is False


def test_payload_never_authority_and_html():
    p = notdiamond_advisory_payload(include_html=True)
    assert p["authority_rejected"] is True
    assert p["notdiamond_is_dispatch_authority"] is False
    assert p["dispatch_owner"] != "notdiamond"
    assert p["suggested_model_id"]
    assert p["view_format"] == "html"
    assert p["html"]
    assert "application/pdf" not in p["html"].lower()
    assert "stub-strong" in p["html"] or "Suggested model" in p["html"]


def test_api_advisory_includes_suggestion():
    store = InMemoryBenchStore()
    run_offline_dogfood_product(week_id="2026-W28", store=store, include_html=False)
    app = FastAPI()
    register_settings_budget_routes(app)
    app.state.antiek_bench_store = store
    client = TestClient(app)
    r = client.get(
        "/settings/notdiamond/advisory",
        params={"include_html": "true", "week_id": "2026-W28"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["authority_rejected"] is True
    assert body["notdiamond_is_dispatch_authority"] is False
    assert body["suggested_model_id"] == "stub-strong"
    assert body["installable"] is True
    assert body["view_format"] == "html"
