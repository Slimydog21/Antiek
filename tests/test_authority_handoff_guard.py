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
