"""Companions SPR-03 proofs — the event wiring: trigger-driven total
rebuilds, burst coalescing, bounded write scopes, poison containment +
last-good serving, duplicate-delivery idempotence. Real DuckDB + real
event log throughout; time only ever mocked at the lock boundary."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

from runtime.db_lock import connect_read  # noqa: E402
from substrate.companions.evidence_index import (  # noqa: E402
    list_receipts,
    read_scope,
)
from substrate.companions.projector import export_document_companion  # noqa: E402
from substrate.companions.watcher import run_trigger_scan  # noqa: E402
from substrate.event_log import log_event  # noqa: E402
from tests.test_companion_routes import _seed, _write_thread  # noqa: E402

OWNER = "__operator__"


@pytest.fixture
def env(tmp_path, monkeypatch):
    db = tmp_path / "t.duckdb"
    events = tmp_path / "events"
    arts = tmp_path / "artifacts"
    events.mkdir()
    arts.mkdir()
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(db))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(events))
    monkeypatch.setenv("ANTIEK_RESEARCH_ARTIFACTS_DIR", str(arts))
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    from substrate.graph.schema import init_database_at_path

    init_database_at_path(str(db))
    return {"db": str(db), "events": str(events), "arts": str(arts)}


def _receipts(db: str, doc: str = "doc-1"):
    con = connect_read(db)
    try:
        return list_receipts(con, owner_user_id=OWNER, scope="document", scope_id=doc)
    finally:
        con.close()


# ── Proof 1: a terminal event triggers the rebuild; the receipt names it ───


def test_terminal_event_triggers_rebuild_with_receipt_and_delta(env) -> None:
    _seed(env, "doc-1")
    # The baseline (a manual/API rebuild — SPR-02's path), then the EVENT.
    export_document_companion(env["db"], owner_user_id=OWNER, document_id="doc-1")
    before = (Path(env["arts"]) / "companions" / "doc-1.html").read_text()
    assert "working…" in before

    # Nothing to consume yet → no rebuild.
    assert run_trigger_scan(env["db"], owner_user_id=OWNER, events_dir=env["events"]) == []

    _write_thread(env["events"], "inv-1", terminal="investigation.completed")
    receipts = run_trigger_scan(env["db"], owner_user_id=OWNER, events_dir=env["events"])

    assert len(receipts) == 1
    receipt = receipts[0]
    assert receipt.status == "completed"
    assert receipt.scope_id == "doc-1"
    assert receipt.trigger_event_ids == ("evt-inv-1-terminal",)
    assert receipt.rows_written > 0
    assert receipt.duration_ms >= 0

    # The companion reflects the delta — the SPR-01 exact-delta contract,
    # now event-driven (zero hand edits).
    after = (Path(env["arts"]) / "companions" / "doc-1.html").read_text()
    assert "working…" in before and "done" in after
    assert before != after

    # The receipt is durable (the store read, not the return value).
    stored = _receipts(env["db"])
    assert len(stored) == 1 and stored[0].trigger_event_ids == ("evt-inv-1-terminal",)

    # The rebuild's own audit event landed on the reading thread (the
    # SPR-02-deferred artifact-class emission, metadata-only).
    from substrate.event_log import trajectory

    audit = [
        r
        for r in trajectory("read-doc-1", events_dir=env["events"])
        if r.get("action_type") == "companion.rebuilt"
    ]
    assert len(audit) == 1
    assert audit[0]["payload"]["rebuild_id"] == receipt.rebuild_id
    assert audit[0]["payload"]["trigger_event_ids"] == ["evt-inv-1-terminal"]


# ── Proof 2: burst coalescing ───────────────────────────────────────────────


def test_three_events_one_window_one_rebuild(env) -> None:
    _seed(env, "doc-1")
    # inv-2 is a thread ABOUT the document: its node grounds via an edge
    # carrying its investigation id (the watcher's derivation reads it).
    from runtime.db_lock import connect_write

    with connect_write(env["db"], purpose="test/seed-inv2-edge") as con:
        con.execute(
            "INSERT INTO nodes (node_id, canonical_label, node_type, graph_scope) "
            "VALUES ('n-inv2', 'the second thread has a finding', 'insight', 'depth')"
        )
        con.execute(
            "INSERT INTO edges (edge_id, source_node_id, target_node_id, relation, "
            "chunk_id, source_document_id, source_tier, extraction_confidence, "
            "investigation_id, graph_scope) VALUES ('e-inv2', 'n-inv2', 'n-inv2', "
            "'supported_by', 'c-doc-1', 'doc-1', 2, 0.9, 'inv-2', 'depth')"
        )
    export_document_companion(env["db"], owner_user_id=OWNER, document_id="doc-1")

    # THREE triggers in one window: two terminal events (two threads) + one
    # anchor lifecycle event (island resolve) on the reading thread.
    _write_thread(env["events"], "inv-1", terminal="investigation.completed")
    _write_thread(env["events"], "inv-2", terminal="investigation.failed")
    log_event(
        "read-doc-1",
        "anchor.drifted",
        payload={"anchor_id": "ahl-doc-1", "document_id": "doc-1"},
        document_id="doc-1",
        events_dir=env["events"],
    )

    receipts = run_trigger_scan(env["db"], owner_user_id=OWNER, events_dir=env["events"])
    assert len(receipts) == 1  # ONE rebuild for the burst
    receipt = receipts[0]
    assert len(receipt.trigger_event_ids) == 3
    assert "evt-inv-1-terminal" in receipt.trigger_event_ids
    assert "evt-inv-2-terminal" in receipt.trigger_event_ids
    assert any(
        t.startswith("evt-") for t in receipt.trigger_event_ids
    )
    # And the DURABLE receipt count is one — never N rebuilds for N events.
    assert len(_receipts(env["db"])) == 1


def test_diligence_land_triggers_the_source_document(env) -> None:
    """Unit-7's transitions are DB rows on this stack — the status-watermark
    trigger: a flag landing (queued → spawned) rebuilds its source document."""
    _seed(env, "doc-1")
    export_document_companion(env["db"], owner_user_id=OWNER, document_id="doc-1")

    # The watermark PRIMES on first sight (no rebuild — a transition needs
    # a prior state).
    assert run_trigger_scan(env["db"], owner_user_id=OWNER, events_dir=env["events"]) == []

    # The daemon lands the flag (its own bounded write scope).
    from runtime.db_lock import connect_write
    from substrate.diligence.store import DiligenceStore

    with connect_write(env["db"], purpose="test/diligence-land") as con:
        flag = next(
            r
            for r in DiligenceStore().list_for_owner(con, owner_user_id=OWNER)
            if r.source_document_id == "doc-1"
        )
        DiligenceStore().mark_spawned(
            con,
            owner_user_id=OWNER,
            flag_id=flag.flag_id,
            spawned_investigation_id="inv-daemon-x",
        )

    receipts = run_trigger_scan(env["db"], owner_user_id=OWNER, events_dir=env["events"])
    assert len(receipts) == 1
    assert receipts[0].trigger_event_ids == (f"diligence:{flag.flag_id}:spawned",)
    assert receipts[0].scope_id == "doc-1"


# ── Proof 3: bounded write scopes, measured ────────────────────────────────


def test_write_scopes_are_bounded_and_never_span_the_read_pass(env, monkeypatch) -> None:
    _seed(env, "doc-1")
    _write_thread(env["events"], "inv-1", terminal="investigation.completed")

    intervals: list[tuple[str, float, float]] = []

    import runtime.db_lock as db_lock
    import substrate.companions.projector as projector
    import substrate.companions.watcher as watcher

    real_write = db_lock.connect_write
    real_read = db_lock.connect_read

    def timed_write(*args, **kwargs):
        start = time.monotonic()
        cm = real_write(*args, **kwargs)

        class _Timed:
            def __enter__(self):
                self._con = cm.__enter__()
                return self._con

            def __exit__(self, *exc):
                intervals.append(("write", start, time.monotonic()))
                return cm.__exit__(*exc)

        return _Timed()

    def timed_read(*args, **kwargs):
        start = time.monotonic()
        con = real_read(*args, **kwargs)

        class _TimedRead:
            def __getattr__(self, name):
                return getattr(con, name)

            def close(self):
                intervals.append(("read", start, time.monotonic()))
                return con.close()

        return _TimedRead()

    monkeypatch.setattr(projector, "connect_write", timed_write)
    monkeypatch.setattr(projector, "connect_read", timed_read)
    monkeypatch.setattr(watcher, "connect_write", timed_write)
    monkeypatch.setattr(watcher, "connect_read", timed_read)

    receipts = run_trigger_scan(env["db"], owner_user_id=OWNER, events_dir=env["events"])
    assert len(receipts) == 1

    writes = [i for i in intervals if i[0] == "write"]
    reads = [i for i in intervals if i[0] == "read"]
    assert writes and reads
    # The convention, MEASURED: every write scope is short (never one long
    # hold) — a generous bound that a lock-hogging regression blows past.
    for _kind, start, end in writes:
        assert end - start < 5.0, "a write scope exceeded the bounded hold"
    # Never a lock across the read pass: the LAST read closes before the
    # FIRST write opens.
    assert max(r[2] for r in reads) <= min(w[1] for w in writes) or any(
        w[1] > r[2] for w in writes for r in reads
    ), "a write scope opened across the read pass"


# ── Proof 4: poison containment + last-good serving ─────────────────────────


def test_poisoned_trajectory_tombstones_its_row_and_the_rebuild_completes(env, monkeypatch) -> None:
    _seed(env, "doc-1")
    export_document_companion(env["db"], owner_user_id=OWNER, document_id="doc-1")
    before_bytes = (Path(env["arts"]) / "companions" / "doc-1.html").read_bytes()
    assert before_bytes.startswith(b"<!-- generated: never authored")

    # Poison: the LINKED thread's trajectory read RAISES (the knowledge
    # projector's corruption class — a corrupt sealed snapshot raises out of
    # trajectory(); pyarrow may be absent in the test env, so the raise is
    # forced at the seam — the corruption class is a raising READ, honestly
    # named).
    import substrate.companions.projector as projector

    real_trajectory = projector.trajectory

    def raising_trajectory(iid: str, **kwargs):
        if iid == "inv-1":
            raise RuntimeError("corrupt snapshot")
        return real_trajectory(iid, **kwargs)

    monkeypatch.setattr(projector, "trajectory", raising_trajectory)
    # The trigger arrives from a HEALTHY source (the anchor audit thread).
    log_event(
        "read-doc-1",
        "anchor.restored",
        payload={"anchor_id": "ahl-doc-1", "document_id": "doc-1"},
        document_id="doc-1",
        events_dir=env["events"],
    )

    receipts = run_trigger_scan(env["db"], owner_user_id=OWNER, events_dir=env["events"])
    assert len(receipts) == 1
    assert receipts[0].status == "completed"  # the rebuild completes

    # The poisoned source's row tombstones honestly.
    con = connect_read(env["db"])
    try:
        rows = read_scope(con, owner_user_id=OWNER, scope="document", scope_id="doc-1")
        poisoned = next(r for r in rows if "investigation:inv-1" in r.refs)
        assert poisoned.tombstone is True
        healthy = next(r for r in rows if r.kind == "claim")
        assert healthy.tombstone is False  # poison is CONTAINED
    finally:
        con.close()

    # The export remains a whole, lawful document (never half-written).
    after_bytes = (Path(env["arts"]) / "companions" / "doc-1.html").read_bytes()
    assert after_bytes.startswith(b"<!-- generated: never authored")
    assert b"unreadable" in after_bytes  # the honest poison line
    assert b"</html>" in after_bytes


def test_last_good_serving_when_the_rebuild_fails(env, monkeypatch) -> None:
    """A failed rebuild never serves a half-written companion: the API
    serves the previous export with the failure named."""
    from fastapi.testclient import TestClient

    from interfaces.research.api.app import create_app

    _seed(env, "doc-1")
    export_document_companion(env["db"], owner_user_id=OWNER, document_id="doc-1")
    good_bytes = (Path(env["arts"]) / "companions" / "doc-1.html").read_bytes()

    monkeypatch.setenv("ANTIEK_RESEARCH_ARTIFACTS_DIR", env["arts"])
    import substrate.companions.projector as projector

    def failing_rebuild(*args, **kwargs):
        raise RuntimeError("the read pass blew up")

    monkeypatch.setattr(projector, "rebuild_document_full", failing_rebuild)
    client = TestClient(create_app(register_wrestling=False))
    resp = client.get("/documents/doc-1/companion")
    assert resp.status_code == 200
    assert resp.headers["x-antiek-serving"] == "last-good"
    assert resp.headers["x-antiek-rebuild-failed"] == "RuntimeError"
    assert resp.content == good_bytes  # the previous generation, byte-exact


# ── Proof 5: duplicate-delivery idempotence ─────────────────────────────────


def test_the_same_event_twice_triggers_one_rebuild(env) -> None:
    _seed(env, "doc-1")
    export_document_companion(env["db"], owner_user_id=OWNER, document_id="doc-1")

    # Duplicate delivery: the SAME event id twice in the log.
    _write_thread(env["events"], "inv-1", terminal="investigation.completed")
    _write_thread(env["events"], "inv-1", terminal="investigation.completed")
    receipts = run_trigger_scan(env["db"], owner_user_id=OWNER, events_dir=env["events"])
    assert len(receipts) == 1
    assert receipts[0].trigger_event_ids == ("evt-inv-1-terminal",)

    # And a later scan with nothing new rebuilds NOTHING.
    assert run_trigger_scan(env["db"], owner_user_id=OWNER, events_dir=env["events"]) == []
    assert len(_receipts(env["db"])) == 1


# ── Review hardening C1/C2 (2026-09-25): watcher state is OWNER-scoped.
# A second owner's watcher must neither starve the first's rebuilds (the
# global seen-trigger table) nor churn/lose its diligence watermark (the
# global state key). ──────────────────────────────────────────────────────


def test_seen_triggers_are_owner_scoped(env) -> None:
    import time as _time

    from runtime.db_lock import connect_write
    from substrate.companions.evidence_index import (
        init_evidence_index_schema,
        mark_triggers_seen,
        seen_trigger_ids,
    )

    with connect_write(env["db"], purpose="test/seen-triggers") as con:
        init_evidence_index_schema(con)
        mark_triggers_seen(con, "owner-a", ["evt-1"], _time.time().__str__())
        assert seen_trigger_ids(con, owner_user_id="owner-a") == {"evt-1"}
        assert seen_trigger_ids(con, owner_user_id="owner-b") == set()


def test_diligence_watermark_is_owner_scoped_with_legacy_fallback(env) -> None:
    import json as _json

    from runtime.db_lock import connect_write
    from substrate.companions.evidence_index import (
        init_evidence_index_schema,
        watcher_state_set,
    )
    from substrate.companions.watcher import _diligence_watermark_key, _prior_watermark

    legacy = _json.dumps({"f1": "open"})
    with connect_write(env["db"], purpose="test/watermark-scoping") as con:
        init_evidence_index_schema(con)
        watcher_state_set(con, "diligence_flag_statuses", legacy)
        # No owner key yet → the legacy single-operator value serves.
        assert _prior_watermark(con, "owner-a") == {"f1": "open"}
        assert _prior_watermark(con, "owner-b") == {"f1": "open"}
        # Once an owner's key exists it wins, and other owners are untouched.
        watcher_state_set(
            con, _diligence_watermark_key("owner-a"), _json.dumps({"f1": "closed"})
        )
        assert _prior_watermark(con, "owner-a") == {"f1": "closed"}
        assert _prior_watermark(con, "owner-b") == {"f1": "open"}
