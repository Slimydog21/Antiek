"""Four read surfaces that laundered "I could not read this" into a definite
answer (2026-09-22 four-agent audit, findings #5 #6 #7 #8).

Each test pins the honest shape (unknown is None / a named failure) AND a
control (the readable / healthy case still reports the definite answer).
"""

from __future__ import annotations

import ast
import io
import json
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]


# ── #5 /ops/objective-card: an unreadable config is not "placeholder pricing" ──


def test_5_unreadable_dispatch_config_is_unknown_not_placeholder(monkeypatch):
    from interfaces.research.api import ops_objective as mod

    monkeypatch.setattr(mod, "_load_dispatch_config", lambda: None)
    sec = mod._dispatch_section()
    assert sec["config_readable"] is False
    assert sec["pricing_placeholder"] is None
    assert "could not be read" in sec["pricing_note"]
    assert "placeholders" not in sec["pricing_note"].split("NO statement")[0]


def test_5_control_readable_config_reports_the_definite_answer(monkeypatch):
    from interfaces.research.api import ops_objective as mod

    real = {"version": 3, "tiers": {"t1": {"pricing": {"input_per_mtok": 1.5, "output_per_mtok": 3.0}}}}
    monkeypatch.setattr(mod, "_load_dispatch_config", lambda: real)
    sec = mod._dispatch_section()
    assert sec["config_readable"] is True and sec["pricing_placeholder"] is False
    assert "not all-zero placeholders" in sec["pricing_note"]
    zeros = {"version": 3, "tiers": {"t1": {"pricing": {"input_per_mtok": 0.0, "output_per_mtok": 0.0}}}}
    monkeypatch.setattr(mod, "_load_dispatch_config", lambda: zeros)
    sec = mod._dispatch_section()
    assert sec["pricing_placeholder"] is True and "0.0 placeholders" in sec["pricing_note"]


# ── #6 /health: a crashed TurboPuffer probe is not "TurboPuffer is switched off" ──


_FLAGS = (
    "turbopuffer_servable_enabled", "turbopuffer_shadow_enabled", "turbopuffer_api_key_present",
    "turbopuffer_active_pointer", "turbopuffer_hybrid_ready",
)


def _health_with_probe(monkeypatch, tmp_path, probe: dict) -> dict:
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    import importlib

    app_mod = importlib.import_module("interfaces.research.api.app")
    monkeypatch.setattr(app_mod, "_probe_turbopuffer", lambda: probe)
    client = TestClient(app_mod.create_app())
    r = client.get("/health")
    assert r.status_code == 200, r.text
    return r.json()


def test_6_crashed_probe_reports_error_and_unknown_flags(monkeypatch, tmp_path):
    crashed = {
        "servable_enabled": False, "shadow_enabled": False, "api_key_present": False,
        "active_pointer_file": False, "active_pointer_context_ok": None, "hybrid_ready": False,
        "resolved_kind": "brute_force", "indexed_row_count": None, "content_hash": None,
        "duckdb_is_sot": None, "thought_partner_hybrid_wired": None,
        "production_default_mount": False, "error": "RuntimeError: probe exploded",
    }
    body = _health_with_probe(monkeypatch, tmp_path, crashed)
    assert body["turbopuffer_probe_error"] == "RuntimeError: probe exploded"
    for f in _FLAGS:
        assert body[f] is None, f  # unknown, not "switched off"


def test_6_control_healthy_probe_reports_definite_flags(monkeypatch, tmp_path):
    healthy = {
        "servable_enabled": True, "shadow_enabled": False, "api_key_present": True,
        "active_pointer_file": True, "active_pointer_context_ok": True, "hybrid_ready": True,
        "resolved_kind": "hybrid", "indexed_row_count": 42, "content_hash": "abc",
        "duckdb_is_sot": True, "thought_partner_hybrid_wired": True, "production_default_mount": True,
    }
    body = _health_with_probe(monkeypatch, tmp_path, healthy)
    assert body["turbopuffer_probe_error"] is None
    assert body["turbopuffer_servable_enabled"] is True
    assert body["turbopuffer_shadow_enabled"] is False
    assert body["turbopuffer_hybrid_ready"] is True


# ── #7 KeyError reaches its own 409 handler ──


def test_7_keyerror_handler_precedes_the_lookuperror_handler():
    assert issubclass(KeyError, LookupError)  # the reason order matters
    src = (ROOT / "interfaces/research/api/multimedia_research_intent_routes.py").read_text()
    tree = ast.parse(src)
    orders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Try):
            names = []
            for h in node.handlers:
                t = h.type
                if isinstance(t, ast.Tuple):
                    names.append(tuple(ast.unparse(e) for e in t.elts))
                elif t is not None:
                    names.append((ast.unparse(t),))
            if any("KeyError" in n for n in names) and any("LookupError" in n for n in names):
                orders.append(names)
    assert orders, "the try with both handlers must exist"
    for names in orders:
        ki = next(i for i, n in enumerate(names) if "KeyError" in n)
        li = next(i for i, n in enumerate(names) if "LookupError" in n)
        assert ki < li, f"KeyError handler is unreachable behind LookupError: {names}"


# ── #8 a 200 with a non-JSON body stays inside EmailDeliveryFailure ──


class _FakeResponse:
    def __init__(self, payload: bytes):
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _urlopen_returning(monkeypatch, payload: bytes):
    def fake_urlopen(req, timeout=None):
        return _FakeResponse(payload)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)


@pytest.mark.parametrize("provider_name", ["resend", "agentmail"])
def test_8_non_json_200_body_is_a_delivery_failure(monkeypatch, provider_name):
    from substrate.auth.email_provider import (
        AgentMailEmailProvider,
        EmailDeliveryFailure,
        OutboundEmail,
        ResendEmailProvider,
    )

    _urlopen_returning(monkeypatch, b"<html><body>502 Bad Gateway (proxy)</body></html>")
    provider = (ResendEmailProvider(api_key="k") if provider_name == "resend"
                else AgentMailEmailProvider(api_key="k", inbox_id="inbox"))
    with pytest.raises(EmailDeliveryFailure, match="non-JSON body"):
        provider.send(OutboundEmail(to="a@b.c", subject="s", text_body="t"))


def test_8_control_json_200_still_delivers(monkeypatch):
    from substrate.auth.email_provider import OutboundEmail, ResendEmailProvider

    _urlopen_returning(monkeypatch, json.dumps({"id": "msg-1"}).encode("utf-8"))
    rec = ResendEmailProvider(api_key="k").send(OutboundEmail(to="a@b.c", subject="s", text_body="t"))
    assert rec is not None


def test_8_control_http_error_still_a_delivery_failure(monkeypatch):
    from substrate.auth.email_provider import (
        EmailDeliveryFailure,
        OutboundEmail,
        ResendEmailProvider,
    )

    def fake_urlopen(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 500, "Error", hdrs={}, fp=io.BytesIO(b"{}"))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(EmailDeliveryFailure, match="HTTP 500"):
        ResendEmailProvider(api_key="k").send(OutboundEmail(to="a@b.c", subject="s", text_body="t"))
