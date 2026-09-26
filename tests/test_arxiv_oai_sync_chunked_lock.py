"""arXiv OAI sync must release DuckDB write.lock between persist batches.

Prod 2026-09-18: `incremental --bulk` held connect_write for ~5.5h (arxiv
timer), starving uvicorn /health via agent-work lease. Chunked persist opens
a fresh lock per batch (and respects max_lock_seconds).
"""

from __future__ import annotations

import os
import subprocess
import sys
import time

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from runtime import db_lock  # noqa: E402
from runtime.db_lock import connect_write  # noqa: E402
from substrate.schemas.documents import ArxivOaiRecord  # noqa: E402
from tools import arxiv_oai_sync as sync  # noqa: E402

_CC_BY = "http://creativecommons.org/licenses/by/4.0/"


def _rec(i: int, *, deleted: bool = False) -> ArxivOaiRecord:
    aid = f"2401.{i:05d}"
    return ArxivOaiRecord(
        arxiv_id=aid,
        datestamp=f"2024-01-{(i % 28) + 1:02d}",
        deleted=deleted,
        title=None if deleted else f"Paper {i}",
        categories=("cs.AI",),
        license_uri=None if deleted else _CC_BY,
    )


@pytest.fixture(autouse=True)
def _tmp_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(tmp_path / "graph.duckdb"))
    monkeypatch.setenv("ANTIEK_ARXIV_OAI_SYNC_PATH", str(tmp_path / "sync.json"))
    monkeypatch.setenv("ANTIEK_ARXIV_OAI_STATE_PATH", str(tmp_path / "harvest.json"))


def test_chunked_persist_acquires_lock_per_batch(tmp_path, monkeypatch):
    db = str(tmp_path / "graph.duckdb")
    from substrate.graph import ensure_initialized

    ensure_initialized(db)

    acquires: list[float] = []
    real_connect = connect_write

    def counting_connect(path, **kwargs):
        acquires.append(time.monotonic())
        return real_connect(path, **kwargs)

    monkeypatch.setattr(sync, "connect_write", counting_connect)

    tally = {"inserted": 0, "updated": 0, "skipped_deleted": 0}
    records = [_rec(i) for i in range(10)]
    out = list(
        sync._chunked_persist_tap(
            iter(records),
            db,
            tally,
            batch_size=3,
            max_lock_s=60.0,
            yield_s=0.0,
        )
    )

    assert len(out) == 10
    # 10 records / batch_size 3 → 4 flushes (3+3+3+1)
    assert len(acquires) == 4
    assert tally["inserted"] + tally["updated"] == 10


def test_chunked_persist_yields_flock_and_rw_handle_to_competing_process(
    tmp_path, monkeypatch
):
    db = str(tmp_path / "graph.duckdb")
    from substrate.graph import ensure_initialized

    ensure_initialized(db)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("ANTIEK_WRITE_KEEPALIVE_S", "30")
    tally = {"inserted": 0, "updated": 0, "skipped_deleted": 0}
    stream = sync._chunked_persist_tap(
        iter([_rec(0), _rec(1)]), db, tally, batch_size=1, yield_s=0
    )
    assert next(stream).arxiv_id == _rec(0).arxiv_id
    try:
        subprocess.run(
            [
                sys.executable,
                "-c",
                "import duckdb, fcntl, os, sys; "
                "db = sys.argv[1]; "
                "fd = os.open(db + '.write.lock', os.O_WRONLY); "
                "fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB); "
                "con = duckdb.connect(db); "
                "assert con.execute('SELECT count(*) FROM documents').fetchone()[0] >= 1; "
                "con.close(); os.close(fd)",
                db,
            ],
            check=True,
            timeout=5,
        )
        assert next(stream).arxiv_id == _rec(1).arxiv_id
        assert tally["inserted"] == 2
    finally:
        stream.close()
        db_lock.flush_warm_writers(db)


def test_chunked_persist_releases_when_max_lock_seconds_elapsed(
    tmp_path, monkeypatch
):
    db = str(tmp_path / "graph.duckdb")
    from substrate.graph import ensure_initialized

    ensure_initialized(db)

    acquires: list[int] = []
    real_connect = connect_write
    persist_calls = {"n": 0}

    def counting_connect(path, **kwargs):
        acquires.append(1)
        return real_connect(path, **kwargs)

    real_persist = sync.persist_oai_record

    def slow_persist(con, record):
        persist_calls["n"] += 1
        time.sleep(0.05)
        return real_persist(con, record)

    monkeypatch.setattr(sync, "connect_write", counting_connect)
    monkeypatch.setattr(sync, "persist_oai_record", slow_persist)

    tally = {"inserted": 0, "updated": 0, "skipped_deleted": 0}
    records = [_rec(i) for i in range(6)]
    list(
        sync._chunked_persist_tap(
            iter(records),
            db,
            tally,
            batch_size=100,  # would be one batch without time cap
            max_lock_s=0.08,  # force mid-batch release (~2 records @ 50ms)
            yield_s=0.0,
        )
    )

    assert persist_calls["n"] == 6
    assert len(acquires) >= 2


def test_chunked_persist_empty_stream_never_locks(tmp_path, monkeypatch):
    db = str(tmp_path / "graph.duckdb")
    acquires = []

    def ban_connect(*_a, **_k):
        acquires.append(1)
        raise AssertionError("empty stream must not take write lock")

    monkeypatch.setattr(sync, "connect_write", ban_connect)
    tally = {"inserted": 0, "updated": 0, "skipped_deleted": 0}
    assert list(sync._chunked_persist_tap(iter([]), db, tally, batch_size=10)) == []
    assert acquires == []


def test_resolve_helpers_prefer_cli_over_env(monkeypatch):
    monkeypatch.setenv("ANTIEK_ARXIV_PERSIST_BATCH_SIZE", "50")
    monkeypatch.setenv("ANTIEK_ARXIV_MAX_LOCK_SECONDS", "9")
    monkeypatch.setenv("ANTIEK_ARXIV_LOCK_YIELD_SECONDS", "1.5")
    assert sync.resolve_persist_batch_size(None) == 50
    assert sync.resolve_persist_batch_size(12) == 12
    assert sync.resolve_max_lock_seconds(None) == 9.0
    assert sync.resolve_max_lock_seconds(3.0) == 3.0
    assert sync.resolve_lock_yield_seconds(None) == 1.5
