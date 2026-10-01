"""GET /library must answer a RETRYABLE status when another process holds the DB.

Production 2026-10-01: the arXiv bulk sync held ``antiek.duckdb``\'s write lock for
~97% of a multi-hour run. ``library.py``\'s ``connect_read`` raised
``_duckdb.IOException: Could not set lock``, the route returned 500, and because
that 500 carried no ``Access-Control-Allow-Origin`` the browser reported a CORS
failure - so the SPA could not read the status at all and rendered
"The library catalog is unavailable. Try again."

``connect_read`` already supports an opt-in bounded wait
(``external_lock_timeout_s``). This module pins the route contract: a
contended read is a 503 with ``Retry-After``, never an undecorated 500.
"""

from __future__ import annotations

import os
import select
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api import library as library_routes
from interfaces.research.api.app import create_app

_ROOT = Path(__file__).resolve().parents[1]

# Hold the write lock in a second PROCESS - the production shape. DuckDB's file
# lock is per-process, so an in-process writer cannot reproduce it.
_HOLD_WRITER = """
import sys
from runtime.db_lock import connect_write

with connect_write(sys.argv[1], purpose="test:library-holder", timeout_s=5,
                   keepalive_s=0) as con:
    con.execute("SELECT 1")
    print("held", flush=True)
    sys.stdin.readline()
"""


@pytest.fixture()
def isolated_db(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="antiek-library-lock-")
    db_path = os.path.join(tmpdir, "antiek.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(tmpdir, "events"))
    # Absent token => the app is open to the test client, the same shape
    # tests/test_library_api.py and test_speak_economics_lock.py rely on.
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    monkeypatch.delenv("ANTIEK_OPERATOR_EMAIL", raising=False)
    try:
        from substrate.graph import ensure_initialized

        ensure_initialized(db_path)
        yield db_path
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _hold_writer(db_path):
    proc = subprocess.Popen(
        [sys.executable, "-u", "-c", _HOLD_WRITER, str(db_path)],
        cwd=_ROOT,
        env=os.environ.copy(),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert proc.stdout is not None
        ready, _, _ = select.select([proc.stdout], [], [], 10)
        assert ready, "writer subprocess did not acquire the DB"
        assert proc.stdout.readline().strip() == "held"
    except BaseException:
        _close_writer(proc)
        raise
    return proc


def _release_writer(proc):
    if proc.stdin is not None and not proc.stdin.closed:
        proc.stdin.write("release\n")
        proc.stdin.flush()


def _close_writer(proc):
    if proc.stdin is not None and not proc.stdin.closed:
        proc.stdin.close()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.terminate()
        proc.wait(timeout=5)


def _seed_servable(db_path, document_id="lib-lock-1", title="Locked Out"):
    from runtime.db_lock import connect_write
    from substrate.books import ingest as bingest
    from substrate.graph.ops import insert_document

    with connect_write(db_path, purpose="test:seed") as con:
        insert_document(
            con,
            document_id=document_id,
            source_tier=2,
            document_type="book",
            title=title,
            author="A. Author",
            raw_text="public domain body",
        )
        bingest.register_book(con, document_id=document_id, content_class="public_domain")


def test_library_is_servable_when_nobody_holds_the_db(isolated_db):
    """Control: the route answers normally, so a failure below is the lock."""
    _seed_servable(isolated_db)
    with TestClient(create_app(register_wrestling=False, register_providers=False)) as client:
        res = client.get("/library?filter=servable")
    assert res.status_code == 200
    assert res.json()["total"] == 1


def test_contended_library_read_is_retryable_not_a_500(isolated_db, monkeypatch):
    """The contract: another process holding the DB yields 503 + Retry-After.

    A 500 cannot be acted on by the client - production proved it: the 500 left
    the app without CORS headers, so the browser surfaced a CORS failure and the
    SPA could not distinguish "busy" from "broken".
    """
    _seed_servable(isolated_db)
    monkeypatch.setattr(library_routes, "_LOCK_WAIT_S", 1.0)
    proc = _hold_writer(isolated_db)
    try:
        with TestClient(
            create_app(register_wrestling=False, register_providers=False),
            raise_server_exceptions=False,
        ) as client:
            res = client.get("/library?filter=servable")
    finally:
        _release_writer(proc)
        _close_writer(proc)

    assert res.status_code != 500, (
        "a held DB lock must not surface as an undecorated 500: "
        f"got {res.status_code} {res.text[:200]}"
    )
    assert res.status_code == 503, f"expected 503, got {res.status_code} {res.text[:200]}"
    assert res.headers.get("Retry-After"), "a retryable 503 must carry Retry-After"


def test_library_recovers_once_the_writer_releases(isolated_db, monkeypatch):
    """The lock is transient; the route must serve again without a restart."""
    _seed_servable(isolated_db)
    monkeypatch.setattr(library_routes, "_LOCK_WAIT_S", 1.0)
    proc = _hold_writer(isolated_db)
    try:
        with TestClient(
            create_app(register_wrestling=False, register_providers=False),
            raise_server_exceptions=False,
        ) as client:
            first = client.get("/library?filter=servable")
            _release_writer(proc)
            _close_writer(proc)
            second = client.get("/library?filter=servable")
    finally:
        _close_writer(proc)

    assert first.status_code == 503
    assert second.status_code == 200
    assert second.json()["total"] == 1
