"""Ads/Production: shorten agent_work lease write holds so fills can acquire.

Cite: #3111 to_thread; #3112 arxiv lock yield; fills fail-fast #3157–#3162.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from interfaces.research.api import agent_work_routes as awr
from runtime.db_lock import connect_write
from substrate.agent_work import service as aw_service
from substrate.agent_work.service import LeaseWorkCommand, lease_agent_work
from substrate.agent_work.store import AgentWorkStore
from substrate.feedback.domain import ArtifactVersionRef, NodeTextAnchor
from substrate.feedback.service import create_feedback_thread
from substrate.feedback.store import CreateThreadCommand
from substrate.graph.schema import init_database_at_path

TEST_NOW = datetime(2026, 9, 18, 19, 0, tzinfo=UTC)


def _seed_expired(db_path: str, n: int) -> None:
    init_database_at_path(db_path)
    for i in range(n):
        create_feedback_thread(
            db_path,
            CreateThreadCommand(
                thread_id=f"fth-yield-{i}",
                root_item_id=f"fit-yield-{i}",
                work_id=f"wrk-yield-{i}",
                owner_user_id="owner-1",
                investigation_id=f"inv-yield-{i}",
                logical_worker_id="research-owner",
                artifact=ArtifactVersionRef("artifact-1", 2, "a" * 64, "b" * 64),
                anchor=NodeTextAnchor(
                    "insight-1", "c" * 64, 0, 4, "fact", "", " remains"
                ),
                body_markdown="Please verify this.",
                operation_id=f"feedback:create:op-yield-{i}",
                request_sha256=("d" * 62) + f"{i:02d}",
                context_sha256=("e" * 62) + f"{i:02d}",
            ),
        )
    with connect_write(db_path, purpose="test/seed-expired-leases") as con:
        store = AgentWorkStore()
        for i in range(n):
            con.execute(
                "UPDATE agent_work SET not_before=? WHERE work_id=?",
                [TEST_NOW - timedelta(minutes=10), f"wrk-yield-{i}"],
            )
            lease = store.lease_one(
                con,
                logical_worker_id="research-owner",
                bridge_credential_id="cred-1",
                bridge_instance_id="mini-1",
                lease_id=f"lse-expired-{i}",
                now=TEST_NOW - timedelta(minutes=5),
                lease_seconds=30,
            )
            assert lease is not None
            con.execute(
                "UPDATE agent_work SET lease_expires_at=? WHERE work_id=?",
                [TEST_NOW - timedelta(seconds=1), lease.work_id],
            )


def test_reclaim_expired_respects_max_reclaim(tmp_path):
    db = str(tmp_path / "reclaim.duckdb")
    _seed_expired(db, n=4)
    with connect_write(db, purpose="test/reclaim-cap") as con:
        recovered = AgentWorkStore().reclaim_expired(
            con,
            logical_worker_id="research-owner",
            now=TEST_NOW,
            max_reclaim=2,
        )
    assert len(recovered) == 2


def test_lease_caps_reclaim_per_call(tmp_path, monkeypatch):
    db = str(tmp_path / "cap.duckdb")
    _seed_expired(db, n=4)
    monkeypatch.setattr(aw_service, "MAX_RECLAIM_PER_LEASE", 2)
    seen: list[int | None] = []
    real = AgentWorkStore.reclaim_expired

    def wrapped(self, *a, **k):
        seen.append(k.get("max_reclaim"))
        return real(self, *a, **k)

    monkeypatch.setattr(AgentWorkStore, "reclaim_expired", wrapped)
    cmd = LeaseWorkCommand(
        logical_worker_id="research-owner",
        bridge_credential_id="cred-cap",
        bridge_instance_id="mini-1",
        lease_id="lse-cap-1",
        lease_seconds=60,
        idempotency_key="ik-cap-1",
        now=TEST_NOW,
    )
    lease_agent_work(db, cmd)
    assert seen == [2]


@pytest.mark.asyncio
async def test_lease_work_yields_after_write_lock_released(monkeypatch):
    monkeypatch.setenv("ANTIEK_AGENT_WORK_LOCK_YIELD_S", "0.05")

    def fast_lease(db_path: str, cmd: LeaseWorkCommand):
        return None

    monkeypatch.setattr(awr, "lease_agent_work", fast_lease)
    monkeypatch.setattr(awr, "_db_path", lambda: "/tmp/unused.duckdb")
    monkeypatch.setattr(awr, "_require_enabled", lambda: None)
    monkeypatch.setattr(awr, "_require_scope", lambda *_a, **_k: None)
    monkeypatch.setattr(awr, "_idempotency_key", lambda v: (v or "x" * 16))

    principal = SimpleNamespace(
        credential_id="cred-1",
        logical_worker_id="research-owner",
        scopes={"lease"},
    )
    body = awr.LeaseIn(bridge_instance_id="mini-1", lease_seconds=60)
    t0 = time.perf_counter()
    result = await awr.lease_work(
        body,
        principal,  # type: ignore[arg-type]
        idempotency_key="bridge-lease-yield-0001",
    )
    elapsed = time.perf_counter() - t0
    assert result is None
    assert elapsed >= 0.05


def test_fills_write_timeout_raised_for_lease_contention():
    from interfaces.research.api import ad_routes

    assert ad_routes._FILLS_WRITE_TIMEOUT_S >= 15.0
