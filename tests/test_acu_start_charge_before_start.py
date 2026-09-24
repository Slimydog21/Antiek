"""The 1-ACU start charge is durable BEFORE a run starts (audit C07).

POST /investigations and POST /books/{id}/spin-research used to append and
broadcast the start event first and only then record the ACU charge. A
WriteLockTimeout on that late commit answered a retryable 503 for a run the
orchestrator had already been handed, with no ledger row (so the wall-time
top-up also found nothing to bill). And because the hard gate was evaluated
under one lock and the charge recorded under another, two starts racing at
``limit - 1`` both passed. The charge now happens, gated, under one writer
lock, before anything is appended or broadcast.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_acu_meter import _derived_owner, isolated_db  # noqa: F401  (fixture)

import interfaces.research.api.compute_capacity_gate as G
from interfaces.research.api.app import create_app
from interfaces.research.api.broadcast import EventBroadcaster
from runtime.db_lock import WriteLockTimeout, connect_write
from substrate.compute_capacity.acu_meter import record_investigation_start_acu
from substrate.compute_capacity.store import get_capacity, set_capacity

# The owner the gate charges for the local operator session. Since #3382
# (namespace Option A) that is derived from the verified e-mail, not the
# shared "__operator__" sentinel: seeding the sentinel would meter a
# different owner and leave the hard cap unset for the one being charged.
_OWNER = _derived_owner()


class _SpyBus(EventBroadcaster):
    def __init__(self) -> None:
        super().__init__()
        self.seen: list[str] = []

    async def broadcast(self, event):  # type: ignore[override]
        at = getattr(event, "action_type", None)
        self.seen.append(str(getattr(at, "value", at)))
        await super().broadcast(event)


def _seed(db: str, *, limit: int, used: int) -> None:
    with connect_write(db, purpose="test:seed") as con:
        set_capacity(con, owner_user_id=_OWNER, tier="custom", monthly_compute_units=limit)
        for i in range(used):
            record_investigation_start_acu(con, owner_user_id=_OWNER, investigation_id=f"seed-{i}")


def _ledger(db: str) -> tuple[list[str], int | None]:
    with connect_write(db, purpose="test:ledger") as con:
        rows = con.execute(
            "SELECT investigation_id FROM owner_compute_acu_ledger ORDER BY 1"
        ).fetchall()
        return [r[0] for r in rows], get_capacity(con, _OWNER).used_compute_units


def _appended_starts() -> int:
    root = Path(os.environ["ANTIEK_RESEARCH_EVENTS_DIR"])
    if not root.exists():
        return 0
    return sum(
        p.read_text().count("investigation.start_requested")
        for p in root.rglob("*") if p.is_file()
    )


def _fail_charge_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    real = G.connect_write

    def flaky(db, *, purpose, timeout_s=None, **kw):
        if purpose == "compute-capacity:record-acu":
            raise WriteLockTimeout("simulated writer contention")
        return real(db, purpose=purpose, timeout_s=timeout_s, **kw)

    monkeypatch.setattr(G, "connect_write", flaky)


def _client(bus: _SpyBus) -> TestClient:
    return TestClient(create_app(
        broadcaster=bus, register_wrestling=False, register_providers=False,
        cors_origins=[],
    ))


# ── POST /investigations ─────────────────────────────────────────────


def test_post_investigations_charges_before_broadcast(isolated_db, monkeypatch):  # noqa: F811
    """Positive control: a normal start is charged once and broadcast once."""
    monkeypatch.setenv("ANTIEK_COMPUTE_CAPACITY_ENFORCEMENT", "hard")
    _seed(isolated_db, limit=10, used=1)
    bus = _SpyBus()
    r = _client(bus).post("/investigations", json={"question": "What is ACU metering?"})
    assert r.status_code == 202, r.text
    inv = r.json()["investigation_id"]
    assert bus.seen == ["investigation.start_requested"]
    rows, used = _ledger(isolated_db)
    assert inv in rows and used == 2


def test_post_investigations_failed_charge_starts_nothing(isolated_db, monkeypatch):  # noqa: F811
    monkeypatch.setenv("ANTIEK_COMPUTE_CAPACITY_ENFORCEMENT", "hard")
    _seed(isolated_db, limit=10, used=1)
    _fail_charge_commit(monkeypatch)
    bus = _SpyBus()
    r = _client(bus).post("/investigations", json={"question": "What is ACU metering?"})
    assert r.status_code == 503
    assert r.json()["detail"] == "graph_busy_retry"
    # A retryable 503 must mean nothing started: no broadcast, no start event.
    assert bus.seen == []
    assert _appended_starts() == 0
    assert _ledger(isolated_db) == (["seed-0"], 1)


def test_post_investigations_hard_gate_is_atomic_with_charge(isolated_db, monkeypatch):  # noqa: F811
    """A twin start charged between precheck and commit exhausts the limit;
    the commit must refuse rather than record a charge past the hard cap."""
    monkeypatch.setenv("ANTIEK_COMPUTE_CAPACITY_ENFORCEMENT", "hard")
    _seed(isolated_db, limit=2, used=1)
    real_precheck = G.run_capacity_precheck

    def precheck_then_twin(request):
        gate = real_precheck(request)
        with connect_write(isolated_db, purpose="test:twin") as con:
            record_investigation_start_acu(con, owner_user_id=_OWNER, investigation_id="inv-twin")
        return gate

    monkeypatch.setattr(G, "run_capacity_precheck", precheck_then_twin)
    bus = _SpyBus()
    r = _client(bus).post("/investigations", json={"question": "Race me"})
    assert r.status_code == 429, r.text
    assert r.json()["detail"]["code"] == "compute_capacity_exhausted"
    assert bus.seen == []
    assert _appended_starts() == 0
    assert _ledger(isolated_db) == (["inv-twin", "seed-0"], 2)


# ── POST /books/{id}/spin-research ───────────────────────────────────


def _register_book(db: str, document_id: str) -> None:
    from substrate.books import ingest as bingest
    from substrate.graph.ops import insert_document

    with connect_write(db, purpose="test:book") as con:
        insert_document(con, document_id=document_id, source_tier=2,
                        document_type="book", title="A Book", author="Auth",
                        raw_text="A short owner note about citrus grafting.")
        bingest.register_book(con, document_id=document_id)


def test_spin_research_charges_before_broadcast(isolated_db, monkeypatch):  # noqa: F811
    monkeypatch.setenv("ANTIEK_COMPUTE_CAPACITY_ENFORCEMENT", "hard")
    _seed(isolated_db, limit=10, used=0)
    _register_book(isolated_db, "doc-spin-acu")
    bus = _SpyBus()
    r = _client(bus).post(
        "/books/doc-spin-acu/spin-research",
        json={"page_index": 0, "passage_text": "citrus grafting"},
    )
    assert r.status_code == 202, r.text
    assert bus.seen == ["investigation.start_requested"]
    rows, used = _ledger(isolated_db)
    assert rows == [r.json()["investigation_id"]] and used == 1


def test_spin_research_failed_charge_starts_nothing(isolated_db, monkeypatch):  # noqa: F811
    monkeypatch.setenv("ANTIEK_COMPUTE_CAPACITY_ENFORCEMENT", "hard")
    _seed(isolated_db, limit=10, used=0)
    _register_book(isolated_db, "doc-spin-acu")
    _fail_charge_commit(monkeypatch)
    bus = _SpyBus()
    r = _client(bus).post(
        "/books/doc-spin-acu/spin-research",
        json={"page_index": 0, "passage_text": "citrus grafting"},
    )
    assert r.status_code == 503
    assert bus.seen == []
    assert _appended_starts() == 0
    assert _ledger(isolated_db)[0] == []
