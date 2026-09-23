from __future__ import annotations

import threading
from pathlib import Path

import pytest

from runtime.db_lock import (
    WriteLockTimeout,
    authority_handoff_guard,
    connect_write,
)


def test_authority_handoff_guard_has_bounded_timeout(tmp_path: Path) -> None:
    db = str(tmp_path / "graph.duckdb")
    con = connect_write(db, purpose="holder")
    try:
        with pytest.raises(WriteLockTimeout), authority_handoff_guard(
            db, timeout_s=0.05, poll_interval_s=0.01,
        ):
            pytest.fail("contended handoff must not enter")
    finally:
        con.close()


def test_document_transfer_writer_waits_for_handoff(tmp_path: Path) -> None:
    db = str(tmp_path / "graph.duckdb")
    initial = connect_write(db, purpose="initial")
    initial.execute("CREATE TABLE IF NOT EXISTS handoff_probe(owner_user_id TEXT)")
    initial.close()
    acquired = threading.Event()

    def transfer() -> None:
        con = connect_write(
            db, timeout_s=2, poll_interval_s=0.01, purpose="owner-transfer",
        )
        acquired.set()
        con.close()

    with authority_handoff_guard(db, timeout_s=1, purpose="test-handoff"):
        worker = threading.Thread(target=transfer)
        worker.start()
        assert not acquired.wait(0.1)
    worker.join(timeout=2)
    assert acquired.is_set()


def test_guard_does_not_create_the_store_when_it_is_absent(tmp_path: Path) -> None:
    """A guard over a path that does not exist must leave it not existing.

    ``authority_handoff_guard``'s release log sits in a ``finally`` and fires on
    every exit. It reaches ``duckdb.connect``, which CREATES the file. Production
    passes a **SQLite** path here (``~/.antiek/owner-launches.sqlite3``,
    research_owner_dispatch), so creating it wrote a DuckDB header over the
    claims store and broke it permanently — every later ``sqlite3.connect``
    raised "file is not a database".
    """
    store = tmp_path / "owner-launches.sqlite3"
    with authority_handoff_guard(str(store), purpose="probe-clean"):
        pass
    assert not store.exists(), "guard created the store it was only meant to lock"


def test_guard_does_not_create_the_store_when_the_body_raises(tmp_path: Path) -> None:
    """The exception path is the one that shipped.

    ``_claim_owner_launch_locked`` raises ``OwnerLaunchConflict`` on the
    parent-permission check BEFORE ``sqlite3.connect`` ever creates the file, so
    this ordering — absent store, body raises — is the reachable one.
    """
    store = tmp_path / "owner-launches.sqlite3"
    with (
        pytest.raises(RuntimeError, match="body failed"),
        authority_handoff_guard(str(store), purpose="probe-raise"),
    ):
        raise RuntimeError("body failed before the store was created")
    assert not store.exists(), "guard created the store on the exception path"


def test_guard_leaves_an_existing_sqlite_store_byte_identical(tmp_path: Path) -> None:
    """Steady state: the store exists and is SQLite. Do not mutate it."""
    import hashlib
    import sqlite3

    store = tmp_path / "owner-launches.sqlite3"
    con = sqlite3.connect(store)
    con.execute("CREATE TABLE owner_launch_claims (op_id TEXT, state TEXT)")
    con.execute("INSERT INTO owner_launch_claims VALUES ('op-1', 'claimed')")
    con.commit()
    con.close()
    before = hashlib.sha256(store.read_bytes()).hexdigest()

    with authority_handoff_guard(str(store), purpose="probe-existing"):
        pass

    assert hashlib.sha256(store.read_bytes()).hexdigest() == before, (
        "guard mutated a foreign SQLite store"
    )
    rows = sqlite3.connect(store).execute(
        "SELECT op_id, state FROM owner_launch_claims"
    ).fetchall()
    assert rows == [("op-1", "claimed")]
