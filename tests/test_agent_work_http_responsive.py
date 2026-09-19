"""Agent-work lease must not stall uvicorn HTTP under --workers 1.

Prod 2026-09-18: herdr-bridge /internal/agent-work/lease ran ensure_initialized
+ connect_write on the asyncio loop; a concurrent DuckDB writer (arxiv sync)
held the write lock and /health timed out for minutes.
"""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

import pytest

from interfaces.research.api import agent_work_routes as awr
from substrate.agent_work.service import LeaseWorkCommand
from substrate.graph.health import DuckDBHealth


@pytest.mark.asyncio
async def test_lease_work_offloads_db_and_keeps_loop_responsive(monkeypatch):
    monkeypatch.setenv("ANTIEK_AGENT_WORK_LOCK_YIELD_S", "0")
    """lease_work must asyncio.to_thread DB work so /health heartbeats continue."""

    def slow_lease(db_path: str, cmd: LeaseWorkCommand):
        time.sleep(0.35)

    monkeypatch.setattr(awr, "lease_agent_work", slow_lease)
    monkeypatch.setattr(awr, "_db_path", lambda: "/tmp/unused.duckdb")
    monkeypatch.setattr(awr, "_require_enabled", lambda: None)
    monkeypatch.setattr(awr, "_require_scope", lambda *_a, **_k: None)
    monkeypatch.setattr(awr, "_idempotency_key", lambda v: (v or "x" * 16))

    heartbeats: list[float] = []

    async def heartbeat() -> None:
        while len(heartbeats) < 4:
            t0 = time.perf_counter()
            await asyncio.sleep(0.05)
            heartbeats.append(time.perf_counter() - t0)

    principal = SimpleNamespace(
        credential_id="cred-1",
        logical_worker_id="research-owner",
        scopes={"lease"},
    )
    body = awr.LeaseIn(bridge_instance_id="mini-1", lease_seconds=60)

    hb_task = asyncio.create_task(heartbeat())
    t0 = time.perf_counter()
    result = await awr.lease_work(
        body,
        principal,  # type: ignore[arg-type]
        idempotency_key="bridge-lease-key-0001",
    )
    elapsed = time.perf_counter() - t0
    await hb_task

    assert result is None
    assert len(heartbeats) >= 4
    assert max(heartbeats) < 0.25, heartbeats
    assert elapsed >= 0.3
    assert elapsed < 0.8


def test_health_response_uses_cached_duckdb_snapshot_only() -> None:
    """/health DuckDB fields are last-known snapshot — no write-lock path."""
    from interfaces.research.api.app import HealthResponse

    cached = DuckDBHealth(
        ready=True,
        status="ok",
        db_path="/tmp/health-ban.duckdb",
        schema_present=True,
        database_size_ok=True,
        integrity_check="not_run",
        wal_present=False,
        wal_bytes=0,
        error=None,
    )
    resp = HealthResponse(
        status="ok",
        param_version="0.2.0",
        schema_version=40,
        subscriber_count=0,
        registered_providers=[],
        providers_ready=False,
        build_sha="deadbeef",
        flywheel_ready=False,
        knowledge_reuse_count=0,
        duckdb_ready=cached.ready,
        duckdb_status=cached.status,
        duckdb_schema_present=cached.schema_present,
        duckdb_database_size_ok=cached.database_size_ok,
        duckdb_integrity_check=cached.integrity_check,
        duckdb_wal_present=cached.wal_present,
        duckdb_wal_bytes=cached.wal_bytes,
        duckdb_error=cached.error,
    )
    assert resp.duckdb_ready is True
    assert resp.duckdb_status == "ok"
