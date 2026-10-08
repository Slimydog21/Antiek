"""Real private lock/account controls; no production database or mailbox."""

from __future__ import annotations

import asyncio
import json
import os
import selectors
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request
from test_operational_account_isolation import (
    ALICE,
    BOB,
    sign_in,
)
from test_operational_account_isolation import account_api as account_api

from runtime import db_lock
from substrate.graph import schema

_PUBLIC = "cold-reader-public"
_OWNED = "cold-reader-owned"
_TAKEN_DOWN = "cold-reader-taken-down"
_BODY = "SYNTHETIC PRIVATE TEST BOOK BODY"
_ROUTES = (
    f"/books/{_PUBLIC}",
    f"/books/{_PUBLIC}/full-text",
    f"/books/{_OWNED}/owner-full-text",
)
_HOLDER = r"""
import select, sys
from runtime import db_lock
db = sys.argv[1]
lease = db_lock.connect_write(db, purpose="test/reader-cold-external-holder",
                              timeout_s=5, keepalive_s=0)
lease.execute("SELECT count(*) FROM documents").fetchone()
print("ready", flush=True)
try:
    if not select.select([sys.stdin], [], [], 35)[0]:
        raise TimeoutError("private holder release deadline")
    if sys.stdin.readline() != "release\n":
        raise RuntimeError("private holder release protocol")
finally:
    lease.close()
    db_lock.flush_warm_writers(db)
"""


def _record(case: str, **values: object) -> None:
    directory = os.environ.get("ANTIEK_READER_COLD_EVIDENCE")
    if directory:
        with (Path(directory) / "observations.jsonl").open("a") as output:
            output.write(json.dumps({"case": case, **values}, sort_keys=True) + "\n")


def _release(holder: subprocess.Popen[bytes]) -> None:
    if holder.poll() is None:
        assert holder.stdin is not None
        holder.stdin.write(b"release\n")
        holder.stdin.flush()
        holder.wait(timeout=10)


@contextmanager
def _external_writer(db: str) -> Iterator[subprocess.Popen[bytes]]:
    db_lock.flush_warm_writers(db)
    holder = subprocess.Popen(
        [sys.executable, "-c", _HOLDER, db],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        assert holder.stdout is not None
        ready = b""
        deadline = time.monotonic() + 10
        with selectors.DefaultSelector() as selector:
            selector.register(holder.stdout, selectors.EVENT_READ)
            while not ready.endswith(b"\n"):
                remaining = deadline - time.monotonic()
                assert remaining > 0 and selector.select(remaining), "holder ready deadline"
                part = os.read(holder.stdout.fileno(), 256)
                assert part, "holder exited before ready"
                ready += part
                assert len(ready) <= 1024
        assert ready == b"ready\n"
        yield holder
    finally:
        try:
            if holder.poll() is None:
                assert holder.stdin is not None
                try:
                    holder.stdin.write(b"release\n")
                    holder.stdin.flush()
                except BrokenPipeError:
                    pass
            stdout, stderr = holder.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            holder.terminate()
            try:
                holder.communicate(timeout=7)
            except subprocess.TimeoutExpired:
                holder.kill()
                holder.communicate(timeout=3)
            raise
        assert holder.returncode == 0, stderr[:1024]
        assert stdout == b"" and stderr == b""


@dataclass
class PrivateReader:
    app: FastAPI
    alice: TestClient
    bob: TestClient
    db: str


@pytest.fixture
def private_reader(request: pytest.FixtureRequest) -> Iterator[PrivateReader]:
    from substrate.books.ingest import register_book
    from substrate.books.takedown import take_down
    from substrate.graph import ensure_initialized
    from substrate.graph.ops import insert_document

    app, sender, root = request.getfixturevalue("account_api")
    alice, _, _ = sign_in(app, sender, ALICE)
    bob, _, _ = sign_in(app, sender, BOB)
    subject = alice.get("/auth/me").json()["user_id"]
    assert subject.startswith("acct_")
    db = str(root / "graph.duckdb")
    ensure_initialized(db)
    with db_lock.connect_write(db, purpose="test/reader-cold-seed", keepalive_s=0) as con:
        for document, content_class, owner in (
            (_PUBLIC, "public_domain", subject),
            (_OWNED, "personal_reading", subject),
            (_TAKEN_DOWN, "personal_reading", subject),
        ):
            insert_document(
                con,
                document_id=document,
                source_tier=2,
                document_type="book",
                title=document,
                raw_text=_BODY,
                content_class=content_class,
                owner_user_id=owner,
            )
            register_book(con, document_id=document, content_class=content_class)
        assert take_down(con, _TAKEN_DOWN, reason="synthetic private control")
    db_lock.flush_warm_writers(db)
    try:
        yield PrivateReader(app, alice, bob, db)
    finally:
        alice.close()
        bob.close()
        db_lock.flush_warm_writers(db)
        schema._INITIALIZED_PATHS.discard(db)


@pytest.mark.parametrize("route", _ROUTES)
def test_cold_get_busy_refuses_without_schema_writer_and_recovers(
    private_reader: PrivateReader,
    route: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reader = private_reader
    schema._INITIALIZED_PATHS.discard(reader.db)
    writes: list[str] = []
    errors: list[str] = []
    real_write = schema.connect_write
    real_read = schema.connect_read

    def observed_write(*args, **kwargs):
        writes.append(kwargs["purpose"])
        return real_write(*args, **kwargs)

    def observed_read(*args, **kwargs):
        try:
            return real_read(*args, **kwargs)
        except db_lock.ReadLockTimeout as exc:
            errors.append(type(exc).__name__)
            raise

    monkeypatch.setattr(schema, "connect_write", observed_write)
    monkeypatch.setattr(schema, "connect_read", observed_read)
    with _external_writer(reader.db) as holder:

        async def exercise() -> None:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=reader.app),
                base_url="http://testserver",
                cookies=reader.alice.cookies,
            ) as client:
                start = time.monotonic()
                pending = asyncio.create_task(client.get(route))
                try:
                    response = await asyncio.wait_for(asyncio.shield(pending), 6)
                    elapsed = time.monotonic() - start
                    _record(
                        "cold_get_busy",
                        route=route,
                        status=response.status_code,
                        elapsed_s=elapsed,
                        schema_writer_attempts=writes,
                        typed_errors=errors,
                    )
                    assert response.status_code == 503
                    assert response.headers["Retry-After"] == "2"
                    assert response.json() == {
                        "detail": "database read is temporarily unavailable; retry shortly",
                    }
                    assert errors == ["ReadLockTimeout"]
                    assert writes == []
                    assert 1.8 <= elapsed < 6
                    assert reader.db not in response.text and _BODY not in response.text
                    assert reader.db not in schema._INITIALIZED_PATHS
                finally:
                    # Even the old-source red returns its real worker after release.
                    await asyncio.to_thread(_release, holder)
                    await asyncio.wait_for(pending, 10)

        asyncio.run(exercise())
    recovered = reader.alice.get(route)
    assert recovered.status_code == 200
    assert writes == []
    if route.endswith("full-text"):
        assert _BODY in recovered.text
    else:
        assert _BODY not in recovered.text
    _record("cold_get_recovered", route=route, status=recovered.status_code)


@pytest.mark.parametrize("entry", ("initializer", "resolver"))
def test_default_cold_writer_keeps_longer_budget(
    private_reader: PrivateReader,
    entry: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from interfaces.research.api.books import _resolve_db_path
    from substrate.graph import ensure_initialized

    db = private_reader.db
    schema._INITIALIZED_PATHS.discard(db)
    real_write = schema.connect_write
    entered = threading.Event()
    calls: list[dict[str, object]] = []

    def observed_write(*args, **kwargs):
        calls.append(dict(kwargs))
        entered.set()
        return real_write(*args, **kwargs)

    monkeypatch.setattr(schema, "connect_write", observed_write)
    with _external_writer(db) as holder, ThreadPoolExecutor(max_workers=1) as executor:
        started = time.monotonic()
        if entry == "initializer":
            future = executor.submit(ensure_initialized, db, timeout_s=8)
        else:
            future = executor.submit(_resolve_db_path)
        try:
            assert entered.wait(6)
            time.sleep(0.35)
            assert time.monotonic() - started > 2
            assert not future.done()
            assert calls == [
                {
                    "purpose": "graph_schema_init",
                    **({"timeout_s": 8} if entry == "initializer" else {}),
                }
            ]
        finally:
            _release(holder)
        assert future.result(timeout=10) == db
        assert db in schema._INITIALIZED_PATHS
    _record(
        "ordinary_writer_recovered",
        entry=entry,
        writer_kwargs=calls,
        elapsed_s=time.monotonic() - started,
    )


@pytest.mark.parametrize("opt_in", (False, True))
def test_missing_schema_uses_one_managed_writer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    opt_in: bool,
) -> None:
    from substrate.graph import ensure_initialized

    db = str(tmp_path / "new.duckdb")
    calls: list[dict[str, object]] = []
    real_write = schema.connect_write

    def observed_write(*args, **kwargs):
        calls.append(dict(kwargs))
        return real_write(*args, **kwargs)

    monkeypatch.setattr(schema, "connect_write", observed_write)
    assert ensure_initialized(db, timeout_s=5, refuse_reader_probe_busy=opt_in) == db
    assert calls == [{"purpose": "graph_schema_init", "timeout_s": 5}]
    with db_lock.connect_read(db) as con:
        assert con.execute("SELECT count(*) FROM nodes").fetchone() == (0,)
    assert db in schema._INITIALIZED_PATHS


@pytest.mark.parametrize("opt_in", (False, True))
def test_unrelated_probe_failure_keeps_real_initialization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    opt_in: bool,
) -> None:
    from substrate.graph import ensure_initialized

    db = str(tmp_path / "probe-error.duckdb")
    real_read = schema.connect_read

    def refused_open(*args, **kwargs):
        raise OSError("synthetic unrelated read-open failure")

    monkeypatch.setattr(schema, "connect_read", refused_open)
    assert ensure_initialized(db, refuse_reader_probe_busy=opt_in) == db
    monkeypatch.setattr(schema, "connect_read", real_read)
    schema._INITIALIZED_PATHS.discard(db)
    assert schema._schema_is_present(db, refuse_reader_probe_busy=opt_in)


def test_opt_in_warm_memo_and_cold_read_probe_never_write(
    private_reader: PrivateReader,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from substrate.graph import ensure_initialized

    db = private_reader.db
    real_read = schema.connect_read
    reads: list[str] = []

    def observed_read(path):
        reads.append(path)
        return real_read(path)

    def forbidden_write(*args, **kwargs):
        raise AssertionError("present schema must not acquire writer")

    monkeypatch.setattr(schema, "connect_read", observed_read)
    monkeypatch.setattr(schema, "connect_write", forbidden_write)
    assert ensure_initialized(db, refuse_reader_probe_busy=True) == db
    assert reads == []
    schema._INITIALIZED_PATHS.discard(db)
    assert ensure_initialized(db, refuse_reader_probe_busy=True) == db
    assert reads == [db]


def test_incomplete_schema_reader_opt_in_uses_managed_writer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from substrate.graph import ensure_initialized

    db = str(tmp_path / "incomplete.duckdb")
    ensure_initialized(db)
    with db_lock.connect_write(db, purpose="test/reader-cold-incomplete", keepalive_s=0) as con:
        con.execute("DROP TABLE arxiv_bulk_progress")
    db_lock.flush_warm_writers(db)
    schema._INITIALIZED_PATHS.discard(db)
    real_write = schema.connect_write
    purposes: list[str] = []

    def observed_write(*args, **kwargs):
        purposes.append(kwargs["purpose"])
        return real_write(*args, **kwargs)

    monkeypatch.setattr(schema, "connect_write", observed_write)
    assert ensure_initialized(db, refuse_reader_probe_busy=True) == db
    assert purposes == ["graph_schema_init"]
    schema._INITIALIZED_PATHS.discard(db)
    assert schema._schema_is_present(db, refuse_reader_probe_busy=True)


@pytest.mark.parametrize("suffix", ("", "/full-text", "/owner-full-text"))
def test_foreign_account_remains_denied(private_reader: PrivateReader, suffix: str) -> None:
    schema._INITIALIZED_PATHS.discard(private_reader.db)
    response = private_reader.bob.get(f"/books/{_OWNED}{suffix}")
    assert response.status_code == 403
    assert _BODY not in response.text


def test_same_owner_public_and_takedown_contracts(private_reader: PrivateReader) -> None:
    reader = private_reader
    for document in (_PUBLIC, _OWNED):
        schema._INITIALIZED_PATHS.discard(reader.db)
        assert reader.alice.get(f"/books/{document}").status_code == 200
    assert _BODY in reader.alice.get(f"/books/{_PUBLIC}/full-text").text
    assert reader.bob.get(f"/books/{_PUBLIC}").status_code == 200
    assert _BODY in reader.bob.get(f"/books/{_PUBLIC}/full-text").text
    assert _BODY in reader.alice.get(f"/books/{_OWNED}/owner-full-text").text
    gated = reader.alice.get(f"/books/{_OWNED}/full-text")
    assert gated.status_code == 200
    assert gated.json()["full_text"] is None
    assert gated.json()["snippet"] == _BODY
    assert gated.json()["reason"] == "gated_metadata_only"
    assert gated.json()["servable"] is False
    metadata = reader.alice.get(f"/books/{_TAKEN_DOWN}")
    assert metadata.status_code == 200 and metadata.json()["taken_down"] is True
    for suffix in ("/full-text", "/owner-full-text"):
        response = reader.alice.get(f"/books/{_TAKEN_DOWN}{suffix}")
        assert response.status_code == 200
        assert response.json()["servable"] is False
        assert _BODY not in response.text


def test_owner_guard_precedes_initializer(monkeypatch: pytest.MonkeyPatch) -> None:
    from interfaces.research.api import books

    app = FastAPI()
    books.register_book_routes(app)
    endpoint = next(
        route.endpoint
        for route in app.routes
        if getattr(route, "path", None) == "/books/{document_id}/owner-full-text"
    )

    def forbidden_resolver(*args, **kwargs):
        raise AssertionError("unproven owner must not initialize")

    monkeypatch.setattr(books, "_resolve_db_path", forbidden_resolver)
    request = Request({"type": "http", "method": "GET", "path": "/", "headers": []})
    with pytest.raises(HTTPException) as denied:
        endpoint(_OWNED, request)
    assert denied.value.status_code == 403
    assert denied.value.detail == "owner_read_required"
