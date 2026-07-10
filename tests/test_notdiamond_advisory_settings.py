"""Settings NotDiamond advisory display — offline residual (ak)."""

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
from substrate.notdiamond_advisory import (  # noqa: E402
    ANTIEK_NOTDIAMOND_ENV,
    kill_switch_enabled,
    notdiamond_advisory_payload,
    project_notdiamond_advisory_html,
)


def test_payload_advisory_go_authority_reject(monkeypatch):
    monkeypatch.delenv(ANTIEK_NOTDIAMOND_ENV, raising=False)
    p = notdiamond_advisory_payload(include_html=True)
    assert p["advisory_allowed"] is True
    assert p["advisory_verdict"] == "GO"
    assert p["authority_allowed"] is False
    assert p["authority_rejected"] is True
    assert p["authority_verdict"] == "REJECT"
    assert p["notdiamond_is_dispatch_authority"] is False
    assert p["dispatch_owner"] != "notdiamond"
    assert "notdiamond" not in str(p["dispatch_owner"]).lower() or "primary" in str(
        p["dispatch_owner"]
    ).lower()
    assert p["kill_switch_enabled"] is False
    assert p["default_off"] is True
    assert p["view_format"] == "html"
    assert p["html"]
    assert "application/pdf" not in p["html"].lower()
    assert "REJECT" in p["html"] or "rejected" in p["html"].lower()
    assert "not the dispatch authority" in p["html"].lower() or "Authority" in p["html"]


def test_kill_switch_default_off_and_enable(monkeypatch):
    monkeypatch.delenv(ANTIEK_NOTDIAMOND_ENV, raising=False)
    assert kill_switch_enabled() is False
    monkeypatch.setenv(ANTIEK_NOTDIAMOND_ENV, "0")
    assert kill_switch_enabled() is False
    monkeypatch.setenv(ANTIEK_NOTDIAMOND_ENV, "1")
    assert kill_switch_enabled() is True
    p = notdiamond_advisory_payload()
    assert p["kill_switch_enabled"] is True
    # Enabling kill-switch never grants authority
    assert p["authority_rejected"] is True
    assert p["notdiamond_is_dispatch_authority"] is False


def test_html_projection_standalone():
    html = project_notdiamond_advisory_html()
    assert html.strip()
    assert "NotDiamond" in html or "notdiamond" in html.lower() or "Advisory" in html


def test_settings_api_double_run_stable(monkeypatch):
    monkeypatch.delenv(ANTIEK_NOTDIAMOND_ENV, raising=False)
    app = FastAPI()
    register_settings_budget_routes(app)
    client = TestClient(app)
    r1 = client.get("/settings/notdiamond/advisory?include_html=true")
    r2 = client.get("/settings/notdiamond/advisory?include_html=true")
    assert r1.status_code == 200
    assert r2.status_code == 200
    b1, b2 = r1.json(), r2.json()
    assert b1["authority_rejected"] is True
    assert b1["advisory_allowed"] is True
    assert b1["notdiamond_is_dispatch_authority"] is False
    assert b1["view_format"] == "html"
    assert b1["html"]
    assert b1["authority_rejected"] == b2["authority_rejected"]
    assert b1["advisory_verdict"] == b2["advisory_verdict"]
    assert b1["kill_switch_enabled"] == b2["kill_switch_enabled"]
