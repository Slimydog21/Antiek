"""NotDiamond advisory suggestion + install posture (residual br)."""

from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

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


def test_missing_nd_evidence_is_not_measured_and_not_installable():
    s = resolve_advisory_suggestion()
    assert s["suggested_model_id"] is None
    assert s["measurement_status"] == "NOT MEASURED"
    assert s["notdiamond_is_dispatch_authority"] is False
    assert s["installable"] is False


def test_antiek_bench_is_not_relabelled_as_notdiamond_evidence():
    store = InMemoryBenchStore()
    run_offline_dogfood_product(week_id="2026-W28", store=store, include_html=False)
    s = resolve_advisory_suggestion(store=store, week_id="2026-W28")
    assert s["suggested_model_id"] is None
    assert s["suggestion_source"] == "notdiamond_advisory.not_measured"
    assert s["measurement_status"] == "NOT MEASURED"
    assert s["installable"] is False
    assert s["notdiamond_is_dispatch_authority"] is False


def test_payload_never_authority_and_html():
    p = notdiamond_advisory_payload(include_html=True)
    assert p["authority_rejected"] is True
    assert p["notdiamond_is_dispatch_authority"] is False
    assert p["dispatch_owner"] != "notdiamond"
    assert p["suggested_model_id"] is None
    assert p["measurement_status"] == "NOT MEASURED"
    assert p["installable"] is False
    assert p["view_format"] == "html"
    assert p["html"]
    assert "application/pdf" not in p["html"].lower()
    assert "NOT MEASURED" in p["html"]


def test_api_advisory_does_not_fabricate_installable_suggestion():
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
    assert body["suggested_model_id"] is None
    assert body["measurement_status"] == "NOT MEASURED"
    assert body["installable"] is False
    assert body["view_format"] == "html"


def test_settings_advisory_module_has_no_dispatch_or_driver_mutator_imports():
    path = Path("substrate/notdiamond_advisory.py")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    forbidden_modules = {"substrate.dispatch", "substrate.model_registration"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert not any(
                alias.name.startswith(module)
                for alias in node.names
                for module in forbidden_modules
            )
        elif isinstance(node, ast.ImportFrom):
            assert not any((node.module or "").startswith(module) for module in forbidden_modules)


def test_not_measured_payload_is_a_closed_non_installable_shape():
    payload = notdiamond_advisory_payload()
    assert {
        "suggested_model_id": payload["suggested_model_id"],
        "suggested_provider_id": payload["suggested_provider_id"],
        "measurement_status": payload["measurement_status"],
        "installable": payload["installable"],
        "notdiamond_is_dispatch_authority": payload["notdiamond_is_dispatch_authority"],
    } == {
        "suggested_model_id": None,
        "suggested_provider_id": None,
        "measurement_status": "NOT MEASURED",
        "installable": False,
        "notdiamond_is_dispatch_authority": False,
    }
