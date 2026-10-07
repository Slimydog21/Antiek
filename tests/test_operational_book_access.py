"""Real signed-session reads and external DuckDB contention in a temporary store.

These are local regression fixtures, not a production catalogue or journey.
No body, owner signal, connection error, or successful response is mocked.
"""

from __future__ import annotations

import asyncio
import os
import select
import subprocess
import sys
import threading
import time
from contextlib import contextmanager

import httpx
import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
from runtime import db_lock
from substrate.auth import mint_session_cookie
from substrate.books.ingest import register_book
from substrate.books.takedown import take_down
from substrate.graph import ensure_initialized
from substrate.graph.ops import insert_document

_EMAIL = "operator@example.test"
_ORIGIN = "https://antiek.ai"
_DOCUMENT = "operational-regression-fixture"
_BODY = "Private body for the local operational regression."
_HOLDER_CODE = """
import sys
import duckdb

con = duckdb.connect(sys.argv[1])
try:
    print('held', flush=True)
    sys.stdin.buffer.read(1)
finally:
    con.close()
"""


@pytest.fixture
def signed_api(monkeypatch, tmp_path):
    db = str(tmp_path / "graph.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", "local-operational-session-secret-" + "x" * 48)
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", _EMAIL)
    for name in (
        "ANTIEK_OPERATOR_TOKEN", "ANTIEK_DEV_LOGIN_TOKEN",
        "ANTIEK_OPERATOR_SERVICE_TOKEN_CLIENT_ID", "CF_ACCESS_CLIENT_SECRET",
    ):
        monkeypatch.delenv(name, raising=False)
    ensure_initialized(db)
    with db_lock.connect_write(db, purpose="test/operational-book", keepalive_s=0) as con:
        insert_document(
            con, document_id=_DOCUMENT, source_tier=2, document_type="book",
            title="Local regression fixture", raw_text=_BODY,
            content_class="personal_reading", owner_user_id="__operator__",
        )
        register_book(con, document_id=_DOCUMENT, content_class="personal_reading")
    db_lock.flush_warm_writers(db)
    app = create_app(register_wrestling=False, register_providers=False, cors_origins=[_ORIGIN])
    cookie = mint_session_cookie(user_id="__operator__", email=_EMAIL)
    return app, db, {"Cookie": f"ANTIEK_SESSION={cookie}", "Origin": _ORIGIN}


@contextmanager
def _external_writer(db):
    proc = subprocess.Popen(
        [sys.executable, "-c", _HOLDER_CODE, db],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    try:
        assert proc.stdout is not None
        ready = b""
        deadline = time.monotonic() + 10
        while b"\n" not in ready and len(ready) < 256:
            remaining = deadline - time.monotonic()
            assert remaining > 0, "external writer startup timed out"
            assert select.select([proc.stdout], [], [], remaining)[0]
            chunk = os.read(proc.stdout.fileno(), min(64, 256 - len(ready)))
            assert chunk, "external writer exited before taking its lock"
            ready += chunk
        assert ready == b"held\n", "external writer did not acquire its lock"
        yield proc
    finally:
        if proc.stdin is not None:
            proc.stdin.close()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=3)
        if proc.stdout is not None:
            proc.stdout.close()


@pytest.mark.parametrize("route", ["/books?status=all", f"/books/{_DOCUMENT}"])
def test_short_external_writer_does_not_fail_signed_metadata_read(
    signed_api, monkeypatch, route,
):
    app, db, headers = signed_api
    attempted = threading.Event()
    open_threads = []
    native_connect = db_lock.duckdb.connect

    def observed_connect(path, *args, **kwargs):
        try:
            return native_connect(path, *args, **kwargs)
        finally:
            if str(path) == db and kwargs.get("read_only") is True:
                open_threads.append(threading.get_ident())
                attempted.set()

    monkeypatch.setattr(db_lock.duckdb, "connect", observed_connect)

    async def exercise():
        with _external_writer(db) as writer:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="https://api.antiek.ai") as client:
                pending = asyncio.create_task(client.get(route, headers=headers))
                try:
                    assert await asyncio.to_thread(attempted.wait, 5), "book read never attempted"
                    session = await asyncio.wait_for(client.get("/auth/me", headers=headers), 1)
                    assert session.status_code == 200
                    assert session.json()["auth_method"] == "antiek_session_cookie"
                    assert not pending.done(), "metadata read refused before the short writer released"
                    assert writer.stdin is not None
                    writer.stdin.write(b"\n")
                    writer.stdin.flush()
                    response = await asyncio.wait_for(pending, 3)
                    assert response.status_code == 200, response.text
                    assert _BODY not in response.text
                    assert open_threads and all(t != threading.get_ident() for t in open_threads)
                    assert response.headers["access-control-allow-origin"] == _ORIGIN
                finally:
                    if not pending.done():
                        pending.cancel()
                    await asyncio.gather(pending, return_exceptions=True)

    asyncio.run(exercise())


@pytest.mark.parametrize("route", ["/books", f"/books/{_DOCUMENT}"])
def test_long_external_writer_retains_typed_retryable_refusal(signed_api, monkeypatch, route):
    app, db, headers = signed_api
    monkeypatch.setattr(db_lock, "_DEFAULT_LOCK_WAIT_S", 0.15)
    with _external_writer(db):
        response = TestClient(app).get(route, headers=headers)
    assert response.status_code == 503
    assert response.headers["Retry-After"] == "2"
    assert response.headers["access-control-allow-origin"] == _ORIGIN
    assert response.json() == {"detail": "database read is temporarily unavailable; retry shortly"}
    assert db not in response.text and _BODY not in response.text


@pytest.mark.parametrize(
    "route", ["/books", f"/books/{_DOCUMENT}",
              f"/books/{_DOCUMENT}/full-text", f"/books/{_DOCUMENT}/owner-full-text"],
)
def test_unauthenticated_book_reads_remain_closed(signed_api, route):
    app, _db, _headers = signed_api
    response = TestClient(app).get(route, headers={"Origin": _ORIGIN})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "operator_auth_required"
    assert response.headers["access-control-allow-origin"] == _ORIGIN
    assert _BODY not in response.text


def test_signed_owner_body_keeps_public_and_takedown_gates(signed_api):
    app, db, headers = signed_api
    client = TestClient(app)
    owner = client.get(f"/books/{_DOCUMENT}/owner-full-text", headers=headers)
    assert owner.status_code == 200
    assert owner.json()["full_text"] == _BODY
    public = client.get(f"/books/{_DOCUMENT}/full-text", headers=headers)
    assert public.status_code == 200
    assert public.json()["full_text"] is None
    with db_lock.connect_write(db, purpose="test/operational-takedown", keepalive_s=0) as con:
        take_down(con, _DOCUMENT, reason="local regression control")
    refused = client.get(f"/books/{_DOCUMENT}/owner-full-text", headers=headers)
    assert refused.status_code == 200
    assert refused.json()["full_text"] is None
    assert _BODY not in refused.text


def test_multiple_operators_do_not_gain_private_body_bypass(signed_api, monkeypatch):
    app, _db, headers = signed_api
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", _EMAIL + ",second@example.test")
    response = TestClient(app).get(f"/books/{_DOCUMENT}/owner-full-text", headers=headers)
    assert response.status_code == 403
    assert response.json() == {"detail": "owner_read_required"}
    assert _BODY not in response.text
