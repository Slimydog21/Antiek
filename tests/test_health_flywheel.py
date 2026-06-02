"""SPR-11 (antiek-flywheel-foundation) — /health flywheel_ready field.

The shipped HealthResponse carries build_sha (SPR-07); SPR-11 adds
``flywheel_ready: bool`` (+ ``knowledge_reuse_count: int``) so the
prod-parity check can red a deployed-but-DEAD flywheel — "it compounds in
dev, not on prod" — not just a stale SHA or empty provider registry.

What this file proves (the M3 acceptance criteria):

  1. The probe is SAFE: a nonexistent/locked graph DB yields
     flywheel_ready=False AND /health still returns 200 (it never raises).
  2. A FRESH graph (schema present, zero knowledge.reused events) yields
     flywheel_ready=False — the field is honest, not optimistic.
  3. After >= 1 knowledge.reused event is observable, the probe resolves
     flywheel_ready=True with knowledge_reuse_count >= 1 — proving the
     field is NON-VACUOUS (it can be both false and true).

These tests drive the real ``_probe_flywheel`` against tmp DB/events
paths via the ANTIEK_DUCKDB_PATH / ANTIEK_RESEARCH_EVENTS_DIR env
overrides — no operator credentials, no live API, no mocks of the probe
itself.

Repo convention: API/health tests live under ``tests/`` (see
``tests/test_api.py`` and ``tests/test_prod_parity.py``), not under
``interfaces/research/api/tests/`` (that package has no tests/ dir).
"""

from __future__ import annotations

import json
import os
import sys

from fastapi.testclient import TestClient

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(_HERE)
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from interfaces.research.api import create_app  # noqa: E402
from interfaces.research.api.app import _probe_flywheel  # noqa: E402
from substrate.graph.schema import init_database_at_path  # noqa: E402


def _client() -> TestClient:
    # register_wrestling=False / register_providers=False keeps the app
    # cheap and touches no operator credentials. The flywheel probe runs
    # at create_app() startup regardless.
    return TestClient(
        create_app(register_wrestling=False, register_providers=False, cors_origins=[])
    )


# ── M3 criterion: safe probe — missing/locked DB → False, /health 200 ───


def test_health_flywheel_false_and_200_on_missing_db(tmp_path, monkeypatch):
    # Point the probe at a graph DB path that does NOT exist. connect_read
    # cannot create a read-only file, so the probe must swallow the error
    # and resolve flywheel_ready=False — and /health must still be 200.
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(tmp_path / "nope" / "absent.duckdb"))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    r = _client().get("/health")
    assert r.status_code == 200, "/health must stay 200 even when the flywheel probe fails"
    body = r.json()
    assert body["flywheel_ready"] is False
    assert body["knowledge_reuse_count"] == 0


def test_probe_flywheel_never_raises_on_garbage_path(tmp_path, monkeypatch):
    # A directly-called probe against a nonexistent path returns (False, 0),
    # never raises — the unit-level guarantee /health relies on.
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(tmp_path / "absent.duckdb"))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    ready, count = _probe_flywheel()
    assert ready is False and count == 0


# ── M3 criterion: fresh graph (no reuse events) → False ─────────────────


def test_health_flywheel_false_on_fresh_graph(tmp_path, monkeypatch):
    # Initialise an EMPTY graph (schema present, opens read-only) but seed
    # NO knowledge.reused events. The DB opens, but reuse_count == 0, so the
    # flywheel is not yet live.
    db = str(tmp_path / "fresh.duckdb")
    init_database_at_path(db)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    body = _client().get("/health").json()
    assert body["flywheel_ready"] is False, "a fresh graph with zero reuse events is not live"
    assert body["knowledge_reuse_count"] == 0


# ── M3 criterion: >= 1 knowledge.reused → True (NON-VACUITY) ────────────


def _write_reuse_event(events_dir: str, investigation_id: str) -> None:
    """Append one minimal ``knowledge.reused`` JSONL row so ``action_counts``
    (which scans the events dir) reports a count of 1. Shaped like the
    event-log JSONL rows ``action_counts`` reads (it only inspects
    ``action_type``)."""
    os.makedirs(events_dir, exist_ok=True)
    path = os.path.join(events_dir, f"{investigation_id}.jsonl")
    row = {
        "event_id": "ev-spr11-reuse-1",
        "investigation_id": investigation_id,
        "action_type": "knowledge.reused",
        "emitted_at": "2026-06-01T00:00:00Z",
        "payload": {"reused_node_ids": ["n-1"]},
    }
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def test_health_flywheel_true_after_reuse_event(tmp_path, monkeypatch):
    # Graph opens read-only AND >= 1 knowledge.reused event is observable →
    # flywheel_ready=True. This is the NON-VACUITY proof for the field: the
    # SAME probe that returned False above returns True here.
    db = str(tmp_path / "live.duckdb")
    init_database_at_path(db)
    events_dir = str(tmp_path / "events")
    _write_reuse_event(events_dir, "inv-spr11-live")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events_dir)

    # Unit-level: the probe itself.
    ready, count = _probe_flywheel()
    assert ready is True, "graph open + >=1 knowledge.reused must resolve flywheel_ready=True"
    assert count >= 1

    # Route-level: /health reflects it.
    body = _client().get("/health").json()
    assert body["flywheel_ready"] is True
    assert body["knowledge_reuse_count"] >= 1


def test_health_response_model_declares_field():
    # The Pydantic model itself declares the field with a safe default —
    # a cheap guard that the field is on the MODEL, not only stamped at the
    # construction site. (We check the model directly rather than
    # /openapi.json, whose full-app schema build has unrelated forward-ref
    # state that is out of this sprint's scope.)
    from interfaces.research.api.app import HealthResponse

    assert "flywheel_ready" in HealthResponse.model_fields
    assert "knowledge_reuse_count" in HealthResponse.model_fields
    # Safe default: False / 0, so /health is honest on a never-compounded box.
    blank = HealthResponse(
        status="ok",
        param_version="x",
        schema_version=1,
        subscriber_count=0,
    )
    assert blank.flywheel_ready is False
    assert blank.knowledge_reuse_count == 0
