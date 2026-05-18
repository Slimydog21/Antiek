"""Tests for /ops/provider-ratio (H3 observability).

Validates the dispatch-ratio aggregation + alerting trigger
semantics. Used by the bridge-health alerting cron to detect silent
Hermes-primary failures that the OpenRouter fallback is hiding.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timezone, timedelta

import pytest
from fastapi.testclient import TestClient

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)


@pytest.fixture
def temp_substrate(monkeypatch):
    tmp = tempfile.mkdtemp(prefix="antiek-h3-")
    events_dir = os.path.join(tmp, "events")
    os.makedirs(events_dir, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", os.path.join(tmp, "g.duckdb"))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events_dir)
    yield {"events_dir": events_dir, "tmpdir": tmp}


def _client(_):
    from interfaces.research.api.app import create_app
    app = create_app(
        register_wrestling=False, register_providers=False, cors_origins=[],
    )
    return TestClient(app)


def _write_dispatch_event(
    events_dir: str, inv_id: str, *,
    provider: str, finish: str = "stop",
    minutes_ago: int = 1,
) -> None:
    """Append one dispatch.call event to <inv_id>.jsonl in events_dir."""
    ts = (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).isoformat()
    ev = {
        "event_id": f"evt-{provider}-{finish}-{minutes_ago}",
        "investigation_id": inv_id,
        "action_type": "dispatch.call",
        "created_at": ts,
        "payload": {
            "action_type": "dispatch.call",
            "provider": provider,
            "model": "any",
            "tier": "flash",
            "target_role": "decomposer",
            "input_tokens": 100,
            "output_tokens": 50,
            "cost_usd": 0.0,
            "latency_ms": 200,
            "verification_required": False,
            "fallback_chain_index": 0,
            "prompt_hash": "sha256:test",
            "finish_reason": finish,
            "context_pack_event_id": None,
        },
    }
    path = os.path.join(events_dir, f"{inv_id}.jsonl")
    with open(path, "a") as fp:
        fp.write(json.dumps(ev) + "\n")


# ─────────────────────────────────────────────────────────────────────
# 1. Empty / no events
# ─────────────────────────────────────────────────────────────────────


def test_empty_returns_zero(temp_substrate):
    client = _client(temp_substrate)
    resp = client.get("/ops/provider-ratio?window_minutes=15")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_dispatches"] == 0
    assert body["by_provider"] == []
    assert body["alert_recommended"] is False


# ─────────────────────────────────────────────────────────────────────
# 2. Aggregation
# ─────────────────────────────────────────────────────────────────────


def test_aggregates_dispatches_by_provider(temp_substrate):
    ed = temp_substrate["events_dir"]
    for _ in range(5):
        _write_dispatch_event(ed, "inv-a", provider="hermes")
    for _ in range(2):
        _write_dispatch_event(ed, "inv-b", provider="openrouter")
    client = _client(temp_substrate)
    body = client.get("/ops/provider-ratio?window_minutes=15").json()
    assert body["total_dispatches"] == 7
    providers = {b["provider"]: b for b in body["by_provider"]}
    assert providers["hermes"]["success_count"] == 5
    assert providers["openrouter"]["success_count"] == 2
    assert body["hermes_success_fraction"] == pytest.approx(5 / 7)
    assert body["openrouter_fraction"] == pytest.approx(2 / 7)


def test_window_excludes_old_dispatches(temp_substrate):
    ed = temp_substrate["events_dir"]
    _write_dispatch_event(ed, "inv-recent", provider="hermes", minutes_ago=2)
    _write_dispatch_event(ed, "inv-old", provider="hermes", minutes_ago=60)
    client = _client(temp_substrate)
    body = client.get("/ops/provider-ratio?window_minutes=15").json()
    assert body["total_dispatches"] == 1
    body = client.get("/ops/provider-ratio?window_minutes=120").json()
    assert body["total_dispatches"] == 2


def test_error_dispatches_counted_separately(temp_substrate):
    ed = temp_substrate["events_dir"]
    _write_dispatch_event(ed, "inv-x", provider="hermes", finish="stop")
    _write_dispatch_event(ed, "inv-x", provider="hermes", finish="error")
    body = _client(temp_substrate).get("/ops/provider-ratio").json()
    h = next(b for b in body["by_provider"] if b["provider"] == "hermes")
    assert h["success_count"] == 1
    assert h["error_count"] == 1
    assert h["total"] == 2


# ─────────────────────────────────────────────────────────────────────
# 3. Alerting trigger
# ─────────────────────────────────────────────────────────────────────


def test_alert_fires_when_openrouter_exceeds_threshold(temp_substrate):
    """Default threshold = 10%. With 1 hermes + 4 openrouter = 80%
    fallback usage, alert must fire."""
    ed = temp_substrate["events_dir"]
    _write_dispatch_event(ed, "inv-y", provider="hermes")
    for _ in range(4):
        _write_dispatch_event(ed, "inv-y", provider="openrouter")
    body = _client(temp_substrate).get("/ops/provider-ratio").json()
    assert body["alert_recommended"] is True
    assert "openrouter" in body["alert_reason"]


def test_alert_silent_under_threshold(temp_substrate):
    """9 hermes + 1 openrouter = 10% — exactly AT the default
    threshold (alert is strict-greater-than, so this should NOT fire)."""
    ed = temp_substrate["events_dir"]
    for _ in range(9):
        _write_dispatch_event(ed, "inv-z", provider="hermes")
    _write_dispatch_event(ed, "inv-z", provider="openrouter")
    body = _client(temp_substrate).get("/ops/provider-ratio").json()
    assert body["alert_recommended"] is False


def test_custom_threshold_lower_than_default(temp_substrate):
    """Operator can tune the threshold via query param. Setting 0.05
    catches the 10% case that the default-0.10 missed."""
    ed = temp_substrate["events_dir"]
    for _ in range(9):
        _write_dispatch_event(ed, "inv-z", provider="hermes")
    _write_dispatch_event(ed, "inv-z", provider="openrouter")
    body = _client(temp_substrate).get(
        "/ops/provider-ratio?openrouter_alert_threshold=0.05"
    ).json()
    assert body["alert_recommended"] is True


def test_no_dispatches_does_not_trigger_alert(temp_substrate):
    """Zero dispatches in window → no alert (operator inactive,
    distinct from substrate broken). The bridge-health probe handles
    the substrate-broken case via /health.authenticated."""
    body = _client(temp_substrate).get("/ops/provider-ratio").json()
    assert body["alert_recommended"] is False
    assert body["total_dispatches"] == 0
