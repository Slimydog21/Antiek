"""Request-path write-lock discipline (2026-09-05 outage regression).

Two properties, both load-bearing for a single-worker uvicorn on an embedded
single-writer DuckDB:

  1. Route handlers that take the write lock are synchronous ``def`` so FastAPI
     runs them in its threadpool — a blocking lock wait inside ``async def``
     freezes the event loop for EVERY request (this is what turned a
     30s-cadence bridge poll into a dead ``/health``).
  2. A lock wait past the interactive budget surfaces as 503 + Retry-After,
     never a 300s hang and never a 500.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import threading

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from interfaces.research.api import agent_work_routes, feedback_routes
from interfaces.research.api.app import create_app
from runtime import db_lock
from runtime.db_lock import interactive_lock_timeout_s
from substrate.graph import ensure_initialized


def _lock_taking_routes(router):
    return [r for r in router.routes if isinstance(r, APIRoute)]


@pytest.mark.parametrize("router", [agent_work_routes.agent_work_router, feedback_routes.feedback_router])
def test_write_lock_routes_are_sync_so_they_run_in_the_threadpool(router):
    routes = _lock_taking_routes(router)
    assert routes, "router has no routes"
    offenders = [r.path for r in routes if inspect.iscoroutinefunction(r.endpoint)]
    assert offenders == [], f"async handlers would block the event loop on the write lock: {offenders}"


def test_interactive_timeout_is_short_and_env_tunable(monkeypatch):
    monkeypatch.delenv(db_lock.INTERACTIVE_TIMEOUT_ENV, raising=False)
    assert interactive_lock_timeout_s() == db_lock.INTERACTIVE_TIMEOUT_S
    assert interactive_lock_timeout_s() < db_lock.DEFAULT_TIMEOUT_S / 10
    monkeypatch.setenv(db_lock.INTERACTIVE_TIMEOUT_ENV, "2.5")
    assert interactive_lock_timeout_s() == 2.5
    for bad in ("0", "-1", "nope"):
        monkeypatch.setenv(db_lock.INTERACTIVE_TIMEOUT_ENV, bad)
        assert interactive_lock_timeout_s() == db_lock.INTERACTIVE_TIMEOUT_S


@pytest.fixture()
def bridge_client(monkeypatch, tmp_path):
    db_path = str(tmp_path / "graph.duckdb")
    secret = "bridge-test-secret"
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("ANTIEK_AGENT_WORK_BRIDGE_ENABLED", "1")
    monkeypatch.setenv("ANTIEK_FEEDBACK_ENABLED", "1")
    monkeypatch.setenv(db_lock.INTERACTIVE_TIMEOUT_ENV, "0.3")
    monkeypatch.setenv(
        "ANTIEK_BRIDGE_CREDENTIALS_JSON",
        json.dumps(
            {
                "credential-1": {
                    "secret_sha256": hashlib.sha256(secret.encode()).hexdigest(),
                    "logical_worker_id": "research-owner",
                    "scopes": ["lease", "renew", "submitted", "working", "result"],
                }
            }
        ),
    )
    ensure_initialized(db_path)
    return TestClient(create_app(register_wrestling=False)), secret, db_path


class _HeldLock:
    """Hold the substrate write lock from another thread (a stand-in for the
    multi-hour ingest that caused the outage)."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._acquired = threading.Event()
        self._release = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        with db_lock.connect_write(self._db_path, timeout_s=5, purpose="test/ingest-standin"):
            self._acquired.set()
            self._release.wait(30)

    def __enter__(self):
        self._thread.start()
        assert self._acquired.wait(5), "could not take the write lock"
        return self

    def __exit__(self, *exc):
        self._release.set()
        self._thread.join(10)
        return False


def test_bridge_lease_returns_503_retry_after_when_writer_holds_the_lock(bridge_client):
    client, secret, db_path = bridge_client
    with _HeldLock(db_path):
        response = client.post(
            "/internal/agent-work/lease",
            headers={
                "Authorization": f"AntiekBridge credential-1.{secret}",
                "Idempotency-Key": "bridge-lease-lockbusy-0001",
            },
            json={"bridge_instance_id": "mini-1", "lease_seconds": 120},
        )
    assert response.status_code == 503
    assert response.headers.get("Retry-After") == "30"
    assert "write lock" in response.json()["detail"]


def test_feedback_read_returns_503_not_hang_when_writer_holds_the_lock(bridge_client):
    client, _, db_path = bridge_client
    with _HeldLock(db_path):
        response = client.get("/feedback/threads/fth-missing")
    assert response.status_code == 503
    assert response.headers.get("Retry-After") == "30"


def test_bridge_lease_still_works_once_the_lock_is_free(bridge_client):
    client, secret, _ = bridge_client
    response = client.post(
        "/internal/agent-work/lease",
        headers={
            "Authorization": f"AntiekBridge credential-1.{secret}",
            "Idempotency-Key": "bridge-lease-lockfree-0001",
        },
        json={"bridge_instance_id": "mini-1", "lease_seconds": 120},
    )
    assert response.status_code == 200
    assert response.json() is None  # no queued work, honest empty lease
