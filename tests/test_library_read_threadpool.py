"""Library dispatch, snapshot cleanup and real cross-process read admission."""

from __future__ import annotations

import asyncio
import os
import selectors
import subprocess
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager

import duckdb
import httpx
import pytest
from fastapi import FastAPI

from interfaces.research.api import library
from runtime import db_lock
from substrate.books.model import BookAsset


def _seed(db: str, document_id: str) -> None:
    from substrate.books.ingest import register_book
    from substrate.graph import ensure_initialized
    from substrate.graph.ops import insert_document

    ensure_initialized(db)
    with db_lock.connect_write(db, purpose="test:library-threadpool") as con:
        insert_document(
            con,
            document_id=document_id,
            document_type="book",
            source_tier=2,
            title=document_id,
            raw_text="PRIVATE_TEST_BODY_NOT_CATALOGUE_METADATA",
        )
        register_book(con, document_id=document_id, content_class="public_domain")


def _app() -> FastAPI:
    app = FastAPI()
    library.register_library_routes(app)
    _add_probe(app)
    return app


def _add_probe(app: FastAPI) -> None:
    @app.get("/threadpool-probe")
    async def probe() -> dict[str, bool]:
        return {"responsive": True}


async def _wait_for(event: threading.Event) -> None:
    async with asyncio.timeout(5):
        while not event.is_set():
            await asyncio.sleep(0.005)


@pytest.mark.parametrize("blocked_stage", ["open", "batch", "close"])
def test_catalogue_work_and_close_leave_the_loop_responsive(
    monkeypatch: pytest.MonkeyPatch, blocked_stage: str
) -> None:
    db = os.environ["ANTIEK_DUCKDB_PATH"]
    _seed(db, "public-test-book")
    entered, release = threading.Event(), threading.Event()
    calls: list[tuple[str, int]] = []
    real_open = db_lock.connect_read
    real_batch = library.list_book_assets

    def observed(stage: str) -> None:
        calls.append((stage, threading.get_ident()))
        if stage == blocked_stage:
            entered.set()
            if not release.wait(timeout=5):
                raise TimeoutError("test catalogue barrier was not released")

    class Connection:
        def __init__(self, con: db_lock.ReadConnection) -> None:
            self.con = con

        def execute(self, sql: str) -> db_lock.ReadConnection:
            observed(sql)
            return self.con.execute(sql)

        def close(self) -> None:
            observed("close")
            self.con.close()

    def open_read(path: str) -> Connection:
        observed("open")
        return Connection(real_open(path))

    def batch(con: Connection, *, servable_only: bool, limit: int, offset: int) -> list[BookAsset]:
        observed("batch")
        return real_batch(con.con, servable_only=servable_only, limit=limit, offset=offset)

    monkeypatch.setattr(db_lock, "connect_read", open_read)
    monkeypatch.setattr(library, "list_book_assets", batch)

    async def exercise() -> None:
        loop_thread = threading.get_ident()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=_app()), base_url="http://test"
        ) as client:
            catalogue = asyncio.create_task(client.get("/library"))
            try:
                await _wait_for(entered)
                assert not catalogue.done()
                probe = await asyncio.wait_for(client.get("/threadpool-probe"), 1)
                assert probe.status_code == 200
                assert probe.json() == {"responsive": True}
                assert not release.is_set() and not catalogue.done()
            finally:
                release.set()
                response = await asyncio.wait_for(catalogue, 5)
            assert response.status_code == 200
            assert response.json()["total"] == 1
            assert "PRIVATE_TEST_BODY" not in response.text
        assert [stage for stage, _ in calls] == [
            "open",
            "BEGIN TRANSACTION",
            "batch",
            "COMMIT",
            "close",
        ]
        assert len({thread for _, thread in calls}) == 1
        assert all(thread != loop_thread for _, thread in calls)

    asyncio.run(exercise())


def test_offset_batches_share_a_snapshot_despite_a_concurrent_insert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = os.environ["ANTIEK_DUCKDB_PATH"]
    for document_id in ("original-a", "original-b", "original-c"):
        _seed(db, document_id)
    first_batch, release = threading.Event(), threading.Event()
    real_batch = library.list_book_assets
    offsets: list[int] = []

    def batch(
        con: db_lock.ReadConnection, *, servable_only: bool, limit: int, offset: int
    ) -> list[BookAsset]:
        assets = real_batch(con, servable_only=servable_only, limit=limit, offset=offset)
        offsets.append(offset)
        if offset == 0:
            first_batch.set()
            if not release.wait(timeout=5):
                raise TimeoutError("test snapshot barrier was not released")
        return assets

    monkeypatch.setattr(library, "_CATALOG_BATCH_SIZE", 1)
    monkeypatch.setattr(library, "list_book_assets", batch)

    async def exercise() -> None:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=_app()), base_url="http://test"
        ) as client:
            pending = asyncio.create_task(client.get("/library"))
            try:
                await _wait_for(first_batch)
                await asyncio.to_thread(_seed, db, "inserted-between-batches")
            finally:
                release.set()
                response = await asyncio.wait_for(pending, 5)
            assert response.status_code == 200
            body = response.json()
            assert body["total"] == 3
            assert {row["document_id"] for row in body["works"]} == {
                "original-a",
                "original-b",
                "original-c",
            }
            assert offsets == [0, 1, 2, 3]
            subsequent = await client.get("/library")
            assert subsequent.status_code == 200
            assert subsequent.json()["total"] == 4

    # A real same-process RW handle allows a second connection to commit
    # during the read snapshot. connect_read selects its guarded RW fallback.
    with duckdb.connect(db):
        asyncio.run(exercise())


@pytest.mark.parametrize("failed_stage", ["batch", "COMMIT"])
def test_primary_failure_survives_rollback_and_close_errors(
    monkeypatch: pytest.MonkeyPatch, failed_stage: str
) -> None:
    from substrate.graph import ensure_initialized

    db = os.environ["ANTIEK_DUCKDB_PATH"]
    ensure_initialized(db)
    real_open = db_lock.connect_read
    stages: list[str] = []
    primary = RuntimeError("primary catalogue failure")

    class Connection:
        def __init__(self, con: db_lock.ReadConnection) -> None:
            self.con = con

        def execute(self, sql: str) -> db_lock.ReadConnection:
            stages.append(sql)
            if sql == failed_stage:
                raise primary
            if sql == "ROLLBACK":
                self.con.execute(sql)
                raise RuntimeError("secondary rollback failure")
            return self.con.execute(sql)

        def close(self) -> None:
            stages.append("close")
            self.con.close()
            raise RuntimeError("secondary close failure")

    def open_read(path: str) -> Connection:
        return Connection(real_open(path))

    def batch(con: Connection, *, servable_only: bool, limit: int, offset: int) -> list[BookAsset]:
        stages.append("batch")
        if failed_stage == "batch":
            raise primary
        return []

    monkeypatch.setattr(db_lock, "connect_read", open_read)
    monkeypatch.setattr(library, "list_book_assets", batch)

    async def exercise() -> None:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=_app()), base_url="http://test"
        ) as client:
            with pytest.raises(RuntimeError) as error:
                await client.get("/library")
            assert error.value is primary

    asyncio.run(exercise())
    expected = ["BEGIN TRANSACTION", "batch"]
    if failed_stage == "COMMIT":
        expected.append("COMMIT")
    assert stages == expected + ["ROLLBACK", "close"]


_HOLDER = """
import sys
import select
import duckdb
con = duckdb.connect(sys.argv[1])
try:
    print('held', flush=True)
    if not select.select([sys.stdin], [], [], 15)[0]:
        raise TimeoutError('private holder release timed out')
    if sys.stdin.readline() != 'release\\n':
        raise RuntimeError('private holder received no release')
finally:
    con.close()
"""


@contextmanager
def _writer_holds(db: str) -> Iterator[subprocess.Popen[bytes]]:
    db_lock.flush_warm_writers(db)
    process = subprocess.Popen(
        [sys.executable, "-c", _HOLDER, db],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        assert process.stdout is not None
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            assert selector.select(timeout=10), "private writer did not announce"
            assert os.read(process.stdout.fileno(), 5) == b"held\n"
        yield process
    finally:
        if process.poll() is None:
            assert process.stdin is not None
            process.stdin.write(b"release\n")
            process.stdin.flush()
        try:
            stdout, stderr = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate(timeout=5)
            raise
        assert process.returncode == 0, stderr[:1024]
        assert stdout == b"" and stderr == b""


def _full_app() -> FastAPI:
    from interfaces.research.api.app import create_app

    app = create_app(register_wrestling=False, register_providers=False)
    _add_probe(app)
    return app


def test_default_admission_waits_for_an_actual_external_writer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = os.environ["ANTIEK_DUCKDB_PATH"]
    _seed(db, "public-test-book")
    app = _full_app()
    conflict = threading.Event()
    real_connect = duckdb.connect

    def connect(database: str, *, read_only: bool = False) -> duckdb.DuckDBPyConnection:
        try:
            return real_connect(database, read_only=read_only)
        except duckdb.IOException:
            conflict.set()
            raise

    monkeypatch.setattr(duckdb, "connect", connect)
    with _writer_holds(db) as writer:

        async def exercise() -> None:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                pending = asyncio.create_task(client.get("/library"))
                await _wait_for(conflict)
                assert not pending.done()
                probe = await asyncio.wait_for(client.get("/threadpool-probe"), 1)
                assert probe.status_code == 200
                assert not pending.done() and writer.poll() is None
                assert writer.stdin is not None
                writer.stdin.write(b"release\n")
                writer.stdin.flush()
                await asyncio.to_thread(writer.wait, 5)
                response = await asyncio.wait_for(pending, 5)
                assert response.status_code == 200
                assert response.json()["total"] == 1
                assert "PRIVATE_TEST_BODY" not in response.text

        asyncio.run(exercise())


def test_unreleased_writer_retains_typed_bounded_http_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = os.environ["ANTIEK_DUCKDB_PATH"]
    _seed(db, "public-test-book")
    app = _full_app()
    monkeypatch.setattr(db_lock, "_DEFAULT_LOCK_WAIT_S", 0.1)
    with _writer_holds(db):

        async def exercise() -> None:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await asyncio.wait_for(client.get("/library"), 5)
                assert response.status_code == 503
                assert response.headers["Retry-After"] == "2"
                assert response.json() == {
                    "detail": "database read is temporarily unavailable; retry shortly"
                }

        asyncio.run(exercise())
