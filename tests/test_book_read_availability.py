"""Finite private-profile controls; these fixtures are not live book evidence."""
from __future__ import annotations

import asyncio
import concurrent.futures
import json
import os
import select
import socket
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field

import pytest
from fastapi.testclient import TestClient

from runtime import db_lock
from substrate.books.ingest import register_book
from substrate.graph.ops import insert_document
from substrate.multi_user import auth

EMAIL_A = "availability-a@example.test"
EMAIL_B = "availability-b@example.test"
PRIVATE_A = "mechanical private control A; never product book evidence"
PRIVATE_B = "mechanical private control B; never product book evidence"
PUBLIC = "mechanical public control; never product book evidence"
PATHS = ("/books", "/books/public", "/books/public/full-text", "/books/private-a/owner-full-text")


def receipt(case, **values):
    print("READ_AVAILABILITY_RECEIPT " + json.dumps({"case": case, **values}, sort_keys=True))


@dataclass
class Profile:
    db: str
    app: object
    client: TestClient
    cookies: dict[str, str]
    loop_threads: set[int] = field(default_factory=set)
    ticks: list[float] = field(default_factory=list)
    requests: list[object] = field(default_factory=list)

    def get(self, path, owner="a"):
        headers = {"Cookie": "ANTIEK_SESSION=" + self.cookies[owner]} if owner else {}
        started = time.monotonic()
        response = self.client.get(path, headers=headers)
        elapsed = time.monotonic() - started
        receipt(path, status=response.status_code, elapsed_s=elapsed,
                retry_after=response.headers.get("Retry-After"), fixture="disposable-schema/signed-cookie/current-middleware")
        assert elapsed < 5.0, "private profile request ceiling exceeded"
        return response


@pytest.fixture
def profile(monkeypatch, tmp_path):
    from interfaces.research.api.app import create_app
    from interfaces.research.api import books
    from starlette.concurrency import run_in_threadpool
    from fastapi import routing
    from substrate.graph.schema import init_database_at_path

    db = str(tmp_path / "availability.duckdb")
    for name, value in {
        "ANTIEK_HOME": str(tmp_path / "home"),
        "ANTIEK_DUCKDB_PATH": db,
        "ANTIEK_RESEARCH_EVENTS_DIR": str(tmp_path / "events"),
        "ANTIEK_RESEARCH_ARTIFACTS_DIR": str(tmp_path / "artifacts"),
        "ANTIEK_PASSKEY_STORE": str(tmp_path / "passkeys.json"),
        "ANTIEK_AUTH_SECRET": "availability-private-profile-synthetic-" + "x" * 48,
        "ANTIEK_OPERATOR_EMAIL": EMAIL_A + "," + EMAIL_B,
        "ANTIEK_COOKIE_INSECURE": "1",
        "ANTIEK_DISABLE_EVENT_PROJECTOR_RECOVERY": "1",
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    init_database_at_path(db)
    cookies = {
        "a": auth.mint_session_cookie("magic_link", EMAIL_A, EMAIL_A),
        "b": auth.mint_session_cookie("magic_link", EMAIL_B, EMAIL_B),
    }
    with db_lock.connect_write(db, purpose="finite-book-availability-control-seed") as con:
        for doc, body, content_class, owner in (
            ("private-a", PRIVATE_A, "user_authored_private", auth.subject_owner_id("magic_link", EMAIL_A)),
            ("private-b", PRIVATE_B, "user_authored_private", auth.subject_owner_id("magic_link", EMAIL_B)),
            ("public", PUBLIC, "public_domain", "__operator__"),
            ("gated", "withheld mechanical control", "restricted_pending_opt_in", "__operator__"),
            ("removed", "removed mechanical control", "public_domain", "__operator__"),
        ):
            insert_document(con, document_id=doc, source_tier=2, document_type="book",
                            title="Private profile " + doc, raw_text=body,
                            content_class=content_class, owner_user_id=owner)
            register_book(con, document_id=doc, content_class=content_class)
        con.execute("UPDATE book_assets SET taken_down=TRUE WHERE document_id='removed'")
    app = create_app(register_wrestling=False, register_providers=False, cors_origins=[])
    p = Profile(db, app, TestClient(app, raise_server_exceptions=False), cookies)
    real_resolve = auth.resolve_authenticated_principal
    real_audit = books._record_arxiv_serve_audit
    real_pool = getattr(books, "run_in_threadpool", run_in_threadpool)

    def observed_resolve(request):
        started = time.monotonic()
        try:
            return real_resolve(request)
        finally:
            receipt("authority-phase", elapsed_s=time.monotonic() - started, thread=threading.get_ident(),
                    signed_resolver="unchanged canonical export")

    def observed_audit(*args):
        started = time.monotonic()
        try:
            return real_audit(*args)
        finally:
            receipt("audit-phase", elapsed_s=time.monotonic() - started, post_close=True)

    async def observed_pool(operation, *args, **kwargs):
        admitted = time.monotonic()

        def worker():
            receipt("queue-phase", elapsed_s=time.monotonic() - admitted, thread=threading.get_ident())
            return operation(*args, **kwargs)

        return await real_pool(worker)

    monkeypatch.setattr(auth, "resolve_authenticated_principal", observed_resolve)
    monkeypatch.setattr(books, "_record_arxiv_serve_audit", observed_audit)
    monkeypatch.setattr(books, "run_in_threadpool", observed_pool, raising=False)
    monkeypatch.setattr(routing, "run_in_threadpool", observed_pool)

    def observe_dto(model):
        original = model.__init__

        def construct(instance, *args, **kwargs):
            started = time.monotonic()
            try:
                original(instance, *args, **kwargs)
            finally:
                receipt("dto-phase", model=model.__name__, elapsed_s=time.monotonic() - started)

        monkeypatch.setattr(model, "__init__", construct)

    for model in (books.BookDetail, books.BookSummary, books.BookListResponse, books.FullTextResponse):
        observe_dto(model)

    @app.middleware("http")
    async def observe_loop(request, call_next):
        p.loop_threads.add(threading.get_ident())
        p.requests.append(request)

        async def tick():
            while True:
                p.ticks.append(time.monotonic())
                await asyncio.sleep(0.005)

        ticker = asyncio.create_task(tick())
        try:
            return await call_next(request)
        finally:
            ticker.cancel()
            try:
                await ticker
            except asyncio.CancelledError:
                pass

    yield p
    p.client.close()
    db_lock.flush_warm_writers(db)


class ObservedConnection:
    def __init__(self, con, events, *, pause=None, failure=None):
        self.con, self.events, self.pause, self.failure = con, events, pause, failure

    def execute(self, sql, *args):
        started = time.monotonic()
        label = sql.strip().split()[0].upper()
        self.events.append((label, threading.get_ident(), time.monotonic()))
        if self.failure and self.failure[0] == label:
            raise self.failure[1]
        result = self.con.execute(sql, *args)
        if self.pause:
            self.pause(sql)
        receipt("snapshot-query-phase", operation=label, elapsed_s=time.monotonic() - started)
        return result

    def close(self):
        started = time.monotonic()
        self.events.append(("close", threading.get_ident(), time.monotonic()))
        self.con.close()
        receipt("cleanup-phase", elapsed_s=time.monotonic() - started, thread=threading.get_ident())
        if self.failure and self.failure[0] == "close":
            raise self.failure[1]


def observe_route(monkeypatch, *, before_open=None, pause=None, failure=None):
    events = []
    real_open = db_lock.connect_read

    def open_read(db, **kwargs):
        events.append(("open", threading.get_ident(), time.monotonic()))
        if before_open:
            before_open()
        if failure and failure[0] == "open":
            raise failure[1]
        started = time.monotonic()
        con = real_open(db, **kwargs)
        events.append(("opened", threading.get_ident(), time.monotonic()))
        receipt("route-open", elapsed_s=time.monotonic() - started, budget_s=kwargs.get("external_lock_timeout_s", 0))
        return ObservedConnection(con, events, pause=pause, failure=failure)

    monkeypatch.setattr(db_lock, "connect_read", open_read)
    return events


@contextmanager
def external_writer(db, *, revoke=False):
    """A real canonical writer in an owned, bounded child process."""
    db_lock.flush_warm_writers(db)
    child_source = (
        "import select,sys\n"
        "from runtime.db_lock import connect_write\n"
        "with connect_write(sys.argv[1],purpose='finite-availability-external-writer',keepalive_s=0) as con:\n"
        " if sys.argv[2]=='revoke': con.execute(\"DELETE FROM auth_subjects WHERE subject=?\",[sys.argv[3]])\n"
        " print('ready',flush=True)\n"
        " if select.select([sys.stdin],[],[],8)[0]: sys.stdin.readline()\n"
    )
    child = subprocess.Popen([sys.executable, "-c", child_source, db, "revoke" if revoke else "keep", EMAIL_A],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=True, start_new_session=True)
    try:
        assert select.select([child.stdout], [], [], 5)[0], "canonical writer readiness timeout"
        assert child.stdout.readline().strip() == "ready", "canonical writer failed admission"
        receipt("external-writer-ready", pid=child.pid, writer="runtime.db_lock.connect_write", disposable_db=True)
        yield child
    finally:
        if child.poll() is None:
            child.stdin.write("release\n")
            child.stdin.flush()
        try:
            child.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            child.kill()
            child.communicate(timeout=3)
            pytest.fail("owned canonical writer did not cleanly stop")
        assert child.returncode == 0, "canonical writer cleanup failed"
        receipt("external-writer-closed", pid=child.pid, exit=child.returncode)


def test_signed_public_and_private_routes_preserve_refusals(profile):
    for doc, owner, body, foreign in (("private-a", "a", PRIVATE_A, "b"), ("private-b", "b", PRIVATE_B, "a")):
        assert profile.get("/books/" + doc, owner).status_code == 200
        response = profile.get("/books/" + doc + "/owner-full-text", owner)
        assert response.status_code == 200 and response.json()["full_text"] == body
        assert response.json()["ad_eligible"] is False
        foreign_response = profile.get("/books/" + doc + "/owner-full-text", foreign)
        missing = profile.get("/books/absent/owner-full-text", foreign)
        assert foreign_response.status_code == missing.status_code == 404
        assert foreign_response.text == missing.text
        assert body not in foreign_response.text
        assert profile.get("/books/" + doc + "/full-text", owner).status_code == 404
    listed = profile.get("/books?status=all", "a").json()["books"]
    assert "private-a" in {book["document_id"] for book in listed}
    assert "private-b" not in {book["document_id"] for book in listed}
    public = profile.get("/books/public/full-text")
    assert public.status_code == 200 and public.json()["full_text"] == PUBLIC
    for doc in ("gated", "removed"):
        assert profile.get("/books/" + doc).status_code == 200
        body = profile.get("/books/" + doc + "/full-text")
        assert body.status_code == 200 and body.json()["full_text"] is None
    assert profile.get("/books/absent").status_code == 404
    assert profile.get("/books/private-a/owner-full-text", None).status_code == 401


@pytest.mark.parametrize("path", PATHS)
def test_read_has_no_initializer_and_connection_stays_in_worker(profile, monkeypatch, path):
    from substrate import graph

    def forbidden_initializer(*args, **kwargs):
        pytest.fail("a read called the schema initializer")

    monkeypatch.setattr(graph, "ensure_initialized", forbidden_initializer)
    events = observe_route(monkeypatch)
    response = profile.get(path)
    assert response.status_code == 200, response.text
    labels = [event[0] for event in events]
    assert labels[0:3] == ["open", "opened", "BEGIN"]
    assert labels[-2:] == ["COMMIT", "close"]
    assert len({event[1] for event in events}) == 1
    assert not ({event[1] for event in events} & profile.loop_threads)
    receipt("single-worker", path=path, operations=labels, worker_ids=sorted({e[1] for e in events}))


@pytest.mark.parametrize("path", PATHS)
@pytest.mark.parametrize("release", (True, False), ids=("release-within-budget", "exhaust-budget"))
def test_real_external_contention(profile, monkeypatch, path, release):
    entered, admit = threading.Event(), threading.Event()

    def gate():
        entered.set()
        assert admit.wait(5), "controlled request never admitted"

    events = observe_route(monkeypatch, before_open=gate)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as requests:
        pending = requests.submit(profile.get, path)
        assert entered.wait(3), "route never reached acquisition"
        with external_writer(profile.db) as writer:
            before = len(profile.ticks)
            started = time.monotonic()
            admit.set()
            if release:
                time.sleep(0.3)
                writer.stdin.write("release\n")
                writer.stdin.flush()
            response = pending.result(timeout=5)
            elapsed = time.monotonic() - started
            ticks = profile.ticks[before:]
            assert len(ticks) >= 10, "read contention blocked the ASGI event loop"
            if release:
                assert response.status_code == 200, response.text
                assert [e[0] for e in events][-2:] == ["COMMIT", "close"]
            else:
                assert response.status_code == 503, response.text
                assert response.headers["Retry-After"] == "2"
                assert 1.9 <= elapsed < 5.0
                assert not any(e[0] == "opened" for e in events)
            receipt("real-contention", path=path, released=release, status=response.status_code,
                    elapsed_s=elapsed, loop_ticks=len(ticks), max_tick_gap_s=max((b-a for a,b in zip(ticks,ticks[1:])), default=0))
        assert profile.get(path).status_code == 200, "recovery required a process restart"


@pytest.mark.parametrize("stage", ("open", "SELECT", "close"))
@pytest.mark.parametrize("path", PATHS)
def test_ordinary_route_errors_do_not_inherit_retry(profile, monkeypatch, stage, path):
    events = observe_route(monkeypatch, failure=(stage, RuntimeError("controlled ordinary failure")))
    response = profile.get(path)
    assert response.status_code == (503 if path == "/books" else 500)
    assert "Retry-After" not in response.headers
    if stage != "open":
        assert [e[0] for e in events].count("close") == 1
    if stage == "SELECT":
        assert [e[0] for e in events][-2:] == ["ROLLBACK", "close"]


@pytest.mark.parametrize("path", PATHS)
def test_cleanup_error_overrides_earlier_lock_timeout(profile, monkeypatch, path):
    real = db_lock.connect_read

    class FailingCleanup(ObservedConnection):
        def execute(self, sql, *args):
            if sql.strip().startswith("SELECT"):
                raise db_lock.ReadLockTimeout("controlled query timeout")
            return super().execute(sql, *args)

        def close(self):
            self.con.close()
            raise RuntimeError("controlled cleanup failure")

    monkeypatch.setattr(db_lock, "connect_read", lambda db, **kw: FailingCleanup(real(db, **kw), []))
    response = profile.get(path)
    assert response.status_code == (503 if path == "/books" else 500)
    assert "Retry-After" not in response.headers


@pytest.mark.parametrize("path", PATHS)
def test_ordinary_rollback_failure_overrides_query_timeout(profile, monkeypatch, path):
    real = db_lock.connect_read
    events = []

    class FailingRollback(ObservedConnection):
        def execute(self, sql, *args):
            self.events.append((sql.strip().split()[0].upper(), threading.get_ident(), time.monotonic()))
            if sql.strip().startswith("SELECT"):
                raise db_lock.ReadLockTimeout("controlled query timeout")
            if sql == "ROLLBACK":
                raise RuntimeError("controlled ordinary rollback failure")
            return self.con.execute(sql, *args)

    monkeypatch.setattr(db_lock, "connect_read", lambda db, **kw: FailingRollback(real(db, **kw), events))
    response = profile.get(path)
    assert response.status_code == (503 if path == "/books" else 500)
    assert "Retry-After" not in response.headers
    assert [e[0] for e in events][-3:] == ["SELECT", "ROLLBACK", "close"]
    assert [e[0] for e in events].count("close") == 1
    if path == "/books":
        assert response.json()["detail"] == "read_unavailable"


@pytest.mark.parametrize("when", ("before-acquire", "before-release"))
def test_actual_signed_binding_change_refuses_private_release(profile, monkeypatch, when):
    from interfaces.research.api import books

    def revoke():
        with db_lock.connect_write(profile.db, purpose="finite-binding-revocation") as con:
            con.execute("DELETE FROM auth_subjects WHERE subject=?", [EMAIL_A])

    if when == "before-acquire":
        observe_route(monkeypatch, before_open=revoke)
    else:
        original = books._record_arxiv_serve_audit

        def audit(*args):
            original(*args)
            revoke()

        monkeypatch.setattr(books, "_record_arxiv_serve_audit", audit)
    response = profile.get("/books/private-a/owner-full-text")
    assert response.status_code == 401 and response.json()["detail"] == "authenticated_principal_required"
    assert PRIVATE_A not in response.text


def test_actual_signed_binding_revoked_during_external_wait(profile, monkeypatch):
    entered, admit = threading.Event(), threading.Event()

    def gate():
        entered.set()
        assert admit.wait(5)

    events = observe_route(monkeypatch, before_open=gate)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as requests:
        pending = requests.submit(profile.get, "/books/private-a/owner-full-text")
        assert entered.wait(3)
        with external_writer(profile.db, revoke=True) as writer:
            admit.set()
            time.sleep(0.3)
            writer.stdin.write("release\n")
            writer.stdin.flush()
            response = pending.result(timeout=5)
    assert response.status_code == 401
    assert PRIVATE_A not in response.text
    assert not any(label == "SELECT" for label, _, _ in events), "private document hydrated before fresh authority"
    assert [e[0] for e in events][-2:] == ["ROLLBACK", "close"]


def test_pre_middleware_contention_preserves_legacy_refusal(profile):
    # No middleware ownership is granted here. With no initial concrete
    # principal, a later read must preserve the carrier's opaque refusal.
    with external_writer(profile.db) as writer:
        timer = threading.Timer(0.3, lambda: (writer.stdin.write("release\n"), writer.stdin.flush()))
        timer.start()
        try:
            response = profile.get("/books/private-a/owner-full-text")
        finally:
            timer.join(timeout=2)
    assert response.status_code == 404 and PRIVATE_A not in response.text
    assert profile.get("/books/private-a/owner-full-text").status_code == 200
    receipt("pre-middleware-contention-limit", first_status=404, next_status=200,
            initial_concrete_principal=False, availability_acceptance=False)


def test_changed_actual_signed_credential_refuses_expected_account(profile, monkeypatch):
    from interfaces.research.api import books
    original = books._private_owner_id
    captured = []

    def observe_expected(request, **kwargs):
        if not kwargs.get("refresh"):
            captured.append(request)
        return original(request, **kwargs)

    def replace_credential():
        # A controlled server-side byte change uses a genuinely minted B
        # credential; neither principal nor Request state is fabricated.
        captured[-1]._cookies = {"ANTIEK_SESSION": profile.cookies["b"]}

    monkeypatch.setattr(books, "_private_owner_id", observe_expected)
    events = observe_route(monkeypatch, before_open=replace_credential)
    response = profile.get("/books/private-a/owner-full-text")
    assert response.status_code == 409 and response.json()["detail"] == "account_context_changed"
    assert PRIVATE_A not in response.text
    assert not any(label == "SELECT" for label, _, _ in events)
    receipt("changed-signed-credential", status=409, controlled_request_cookie_replacement=True,
            mocked_principal=False, live_account_transition=False)


@pytest.mark.parametrize("failure", ("invalid", "invalid-cause", "schema", "subject-conflict", "unknown-subclass", "unknown-invalid-cause", "unknown-lock-cause", "ordinary-cause", "lock-cause", "raw-lock", "context-only"))
def test_canonical_typed_failures_only_inherit_direct_lock_retry(profile, monkeypatch, failure):
    from substrate.auth.magic_link import InvalidSessionCookie

    class UnknownAuthError(auth.AuthError):
        pass

    exc = {
        "invalid": auth.AuthError("controlled invalid proof"),
        "invalid-cause": auth.AuthError("controlled invalid proof"),
        "schema": auth.AuthSchemaMigrationError("controlled schema failure"),
        "subject-conflict": auth.AuthSubjectConflict("controlled subject conflict"),
        "unknown-subclass": UnknownAuthError("controlled unknown auth failure"),
        "unknown-invalid-cause": UnknownAuthError("controlled unknown auth failure"),
        "unknown-lock-cause": UnknownAuthError("controlled unknown auth failure"),
        "ordinary-cause": auth.AuthError("controlled operational failure"),
        "lock-cause": auth.AuthError("controlled lock failure"),
        "raw-lock": db_lock.ReadLockTimeout("controlled escaping cleanup timeout"),
        "context-only": RuntimeError("controlled escaping cleanup failure"),
    }[failure]
    if failure in ("invalid-cause", "unknown-invalid-cause"):
        exc.__cause__ = InvalidSessionCookie("controlled expired proof")
    if failure == "ordinary-cause":
        exc.__cause__ = RuntimeError("controlled ordinary failure")
    if failure in ("lock-cause", "unknown-lock-cause"):
        exc.__cause__ = db_lock.ReadLockTimeout("controlled direct lock cause")
    if failure == "context-only":
        exc.__context__ = db_lock.ReadLockTimeout("earlier unrelated timeout")
    real = auth.resolve_authenticated_principal
    calls = 0

    def fail_only_refresh(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            return real(request)
        raise exc

    monkeypatch.setattr(auth, "resolve_authenticated_principal", fail_only_refresh)
    events = observe_route(monkeypatch)
    response = profile.get("/books/private-a/owner-full-text")
    assert response.status_code == (401 if failure in ("invalid", "invalid-cause") else 503)
    assert (response.headers.get("Retry-After") == "2") is (failure in ("lock-cause", "raw-lock"))
    assert PRIVATE_A not in response.text
    assert not any(label == "SELECT" for label, _, _ in events)
    assert [e[0] for e in events][-2:] == ["ROLLBACK", "close"]


@pytest.mark.parametrize("path", PATHS)
def test_actual_binding_revoked_during_cleanup_refuses_final_release(profile, monkeypatch, path):
    real = db_lock.connect_read

    class RevokeAfterClose(ObservedConnection):
        def close(self):
            super().close()
            with db_lock.connect_write(profile.db, purpose="finite-revoke-during-cleanup") as con:
                con.execute("DELETE FROM auth_subjects WHERE subject=?", [EMAIL_A])

    monkeypatch.setattr(db_lock, "connect_read", lambda db, **kw: RevokeAfterClose(real(db, **kw), []))
    response = profile.get(path)
    assert response.status_code == 401
    assert response.json()["detail"] == "authenticated_principal_required"
    assert PRIVATE_A not in response.text


@pytest.mark.parametrize("invalid", ("expired", "missing-binding"))
def test_invalid_actual_signed_session_cannot_read_private(profile, monkeypatch, invalid):
    if invalid == "expired":
        from substrate.auth import magic_link
        real_time = time.time
        monkeypatch.setattr(magic_link.time, "time", lambda: real_time() + magic_link.SESSION_TTL_SECONDS + 1)
    else:
        with db_lock.connect_write(profile.db, purpose="finite-missing-binding") as con:
            con.execute("DELETE FROM auth_subjects WHERE subject=?", [EMAIL_A])
    response = profile.get("/books/private-a/owner-full-text")
    assert response.status_code == (401 if invalid == "expired" else 404)
    assert PRIVATE_A not in response.text


def test_snapshot_does_not_mix_admission_and_later_body(profile, monkeypatch):
    # Use the real supported RW coexistence path for a local concurrent writer.
    # A pure RO handle cannot acquire a differently configured RW connection.
    with db_lock.connect_write(profile.db, purpose="finite-snapshot-rw-coexistence", keepalive_s=10) as con:
        con.execute("SELECT 1")
    changed = False

    def change_after_admission(sql):
        nonlocal changed
        if not changed and "SELECT d.content_class, d.owner_user_id" in sql:
            changed = True
            with db_lock.connect_write(profile.db, purpose="finite-resource-snapshot-change") as con:
                con.execute("UPDATE documents SET owner_user_id=?,raw_text=? WHERE document_id='private-a'",
                            [auth.subject_owner_id("magic_link", EMAIL_B), PRIVATE_B])
                con.execute("UPDATE book_assets SET taken_down=TRUE WHERE document_id='private-a'")

    events = observe_route(monkeypatch, pause=change_after_admission)
    response = profile.get("/books/private-a/owner-full-text")
    assert changed and response.status_code == 200
    assert response.json()["full_text"] == PRIVATE_A, "body did not use admission snapshot"
    assert response.json()["reason"] != "taken_down"
    assert profile.get("/books/private-a/owner-full-text").status_code == 404
    assert [e[0] for e in events].count("close") == 2


@pytest.mark.parametrize("path", ("/books", "/books/private-a", "/books/public/full-text", "/books/private-a/owner-full-text"))
@pytest.mark.parametrize("repeat", (False, True), ids=("one-cancel", "repeated-cancel"))
def test_cancelled_asgi_request_discards_body_and_finishes_worker(profile, monkeypatch, path, repeat):
    entered, release, closed = threading.Event(), threading.Event(), threading.Event()
    events = []
    real = db_lock.connect_read

    class PausedConnection(ObservedConnection):
        def execute(self, sql, *args):
            result = super().execute(sql, *args)
            if sql == "COMMIT":
                entered.set()
                assert release.wait(4), "cancelled worker release timeout"
            return result

        def close(self):
            super().close()
            closed.set()

    monkeypatch.setattr(db_lock, "connect_read", lambda db, **kw: PausedConnection(real(db, **kw), events))

    async def run():
        sent = []
        request_complete = False
        disconnected = asyncio.Event()
        scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
                 "method": "GET", "scheme": "http", "path": path, "raw_path": path.encode(),
                 "query_string": b"", "root_path": "", "server": ("test", 80), "client": ("test", 1),
                 "headers": [(b"host", b"test"), (b"cookie", ("ANTIEK_SESSION=" + profile.cookies["a"]).encode())]}

        async def receive():
            nonlocal request_complete
            if not request_complete:
                request_complete = True
                return {"type": "http.request", "body": b"", "more_body": False}
            await disconnected.wait()
            return {"type": "http.disconnect"}

        async def send(message):
            sent.append(message)

        async with profile.app.router.lifespan_context(profile.app):
            pending = asyncio.create_task(profile.app(scope, receive, send))
            try:
                assert await asyncio.to_thread(entered.wait, 3), "worker never reached controlled native pause"
                pending.cancel()
                await asyncio.sleep(0.03)
                if repeat:
                    pending.cancel()
                    await asyncio.sleep(0.03)
                assert not closed.is_set(), "connection closed outside the paused worker"
                assert not any(m.get("body") for m in sent), "cancelled request released a response body"
            finally:
                release.set()
                disconnected.set()
            try:
                await asyncio.wait_for(pending, 4)
            except asyncio.CancelledError:
                pass
            assert await asyncio.to_thread(closed.wait, 3), "worker cleanup remains unresolved"
            assert not any(PRIVATE_A.encode() in m.get("body", b"") for m in sent)
            assert not any(m.get("body") for m in sent), "cancelled request released a late response body"
        assert len({e[1] for e in events}) == 1
        assert [e[0] for e in events][-1] == "close"
        receipt("cancel-and-lifespan", path=path, private_body_released=False, worker_closed=True,
                operations=[e[0] for e in events], actual_asgi=True, repeated_cancel=repeat,
                shutdown_after_owned_request_cleanup=True, native_pause="controlled COMMIT gate, not thread termination")

    asyncio.run(run())


def test_application_shutdown_observes_cancelled_worker_still_paused(profile, monkeypatch):
    """Observe existing ASGI lifespan behavior without changing its ownership policy."""
    entered, release, closed = threading.Event(), threading.Event(), threading.Event()
    events = []
    real = db_lock.connect_read
    path = "/books/private-a/owner-full-text"

    class PausedConnection(ObservedConnection):
        def execute(self, sql, *args):
            result = super().execute(sql, *args)
            if sql == "COMMIT":
                entered.set()
                assert release.wait(4), "shutdown control worker release timeout"
            return result

        def close(self):
            super().close()
            closed.set()

    monkeypatch.setattr(db_lock, "connect_read", lambda db, **kw: PausedConnection(real(db, **kw), events))

    async def run():
        lifespan_input = asyncio.Queue()
        lifespan_sent, sent = [], []
        startup_done = asyncio.Event()
        request_complete = False
        disconnected = asyncio.Event()

        async def lifespan_receive():
            return await lifespan_input.get()

        async def lifespan_send(message):
            lifespan_sent.append(message)
            if message["type"] in ("lifespan.startup.complete", "lifespan.startup.failed"):
                startup_done.set()

        scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
                 "method": "GET", "scheme": "http", "path": path, "raw_path": path.encode(),
                 "query_string": b"", "root_path": "", "server": ("test", 80), "client": ("test", 1),
                 "headers": [(b"host", b"test"), (b"cookie", ("ANTIEK_SESSION=" + profile.cookies["a"]).encode())]}

        async def receive():
            nonlocal request_complete
            if not request_complete:
                request_complete = True
                return {"type": "http.request", "body": b"", "more_body": False}
            await disconnected.wait()
            return {"type": "http.disconnect"}

        async def send(message):
            sent.append(message)

        lifecycle = asyncio.create_task(profile.app(
            {"type": "lifespan", "asgi": {"version": "3.0", "spec_version": "2.0"}, "state": {}},
            lifespan_receive, lifespan_send,
        ))
        pending = None
        shutdown_started = False
        try:
            await lifespan_input.put({"type": "lifespan.startup"})
            assert await asyncio.wait_for(startup_done.wait(), 3), "application startup unresolved"
            assert lifespan_sent[-1]["type"] == "lifespan.startup.complete"
            pending = asyncio.create_task(profile.app(scope, receive, send))
            assert await asyncio.to_thread(entered.wait, 3), "worker did not reach controlled COMMIT pause"
            pending.cancel()
            await asyncio.sleep(0.03)
            assert not closed.is_set(), "worker closed before shutdown observation"
            assert not any(m.get("body") for m in sent), "cancelled read released a body"
            shutdown_started = True
            shutdown_at = time.monotonic()
            await lifespan_input.put({"type": "lifespan.shutdown"})
            done, _ = await asyncio.wait({lifecycle}, timeout=0.3)
            complete_before_release = any(m["type"] == "lifespan.shutdown.complete" for m in lifespan_sent)
            if done:
                await lifecycle
                assert complete_before_release, "application teardown failed"
            assert not closed.is_set(), "observation no longer has a paused worker"
            assert not any(m.get("body") for m in sent), "shutdown released a late body"
            receipt("shutdown-while-worker-paused", path=path,
                    lifecycle="actual unchanged application ASGI lifespan protocol",
                    observation_s=time.monotonic() - shutdown_at,
                    application_shutdown_complete_before_worker_release=complete_before_release,
                    teardown_pending_before_release=not lifecycle.done(),
                    request_pending_before_release=not pending.done(),
                    worker_cleanup_unresolved_before_release=True,
                    private_body_released=False,
                    shutdown_acceptance="OPEN" if complete_before_release else "teardown observed pending; cleanup required",
                    server_process_or_native_termination_proved=False)
        finally:
            release.set()
            disconnected.set()
            if pending is not None:
                try:
                    await asyncio.wait_for(pending, 4)
                except asyncio.CancelledError:
                    pass
            if not shutdown_started:
                await lifespan_input.put({"type": "lifespan.shutdown"})
            await asyncio.wait_for(lifecycle, 4)
        assert await asyncio.to_thread(closed.wait, 1), "worker cleanup remains unresolved after release"
        assert [e[0] for e in events].count("close") == 1
        assert len({e[1] for e in events}) == 1
        assert [e[0] for e in events][-1] == "close"
        assert not any(m.get("body") for m in sent), "cancelled request released a late body after cleanup"
        receipt("shutdown-paused-worker-final-cleanup", path=path, close_count=1,
                worker_thread_owned_close=True, private_body_released=False,
                application_shutdown_complete=any(m["type"] == "lifespan.shutdown.complete" for m in lifespan_sent),
                native_pause="controlled COMMIT gate, not thread termination")

    asyncio.run(run())


@pytest.mark.parametrize("path", ("/books/private-a", "/books/private-a/owner-full-text"),
                         ids=("async-detail", "sync-owner-body"))
def test_uvicorn_graceful_shutdown_drains_cancelled_reader_worker(profile, monkeypatch, path):
    """Profile-only real loopback server; no process, pool, or lifecycle policy change."""
    import hashlib
    import inspect
    from pathlib import Path

    import uvicorn
    from uvicorn.protocols.http.h11_impl import RequestResponseCycle

    entered, release, closed = threading.Event(), threading.Event(), threading.Event()
    events, sent, cleanup = [], [], {}
    real_open = db_lock.connect_read
    real_send = RequestResponseCycle.send

    class PausedConnection(ObservedConnection):
        def execute(self, sql, *args):
            result = super().execute(sql, *args)
            if sql == "COMMIT":
                entered.set()
                assert release.wait(4), "Uvicorn profile worker release timeout"
            return result

        def close(self):
            super().close()
            cleanup["closed_at"] = time.monotonic()
            cleanup["close_thread"] = threading.get_ident()
            closed.set()

    async def observed_send(cycle, message):
        sent.append({"type": message["type"], "body": message.get("body", b""),
                     "status": message.get("status"), "transport_disconnected": cycle.disconnected,
                     "at": time.monotonic()})
        await real_send(cycle, message)

    monkeypatch.setattr(db_lock, "connect_read", lambda db, **kw: PausedConnection(real_open(db, **kw), events))
    monkeypatch.setattr(RequestResponseCycle, "send", observed_send)

    async def run():
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(("127.0.0.1", 0))
        listener.listen(16)
        port = listener.getsockname()[1]
        config = uvicorn.Config(profile.app, host="127.0.0.1", port=port, workers=1,
                                loop="asyncio", http="h11", lifespan="on", access_log=False,
                                log_config=None, timeout_graceful_shutdown=2)
        server = uvicorn.Server(config)
        server_task = asyncio.create_task(server.serve(sockets=[listener]))
        writer = request_task = monitor = None
        observed = {}
        received = b""

        async def watch_shutdown():
            while True:
                if closed.is_set():
                    observed.setdefault("worker_cleanup_observed_at", time.monotonic())
                if hasattr(server, "lifespan") and server.lifespan.shutdown_event.is_set():
                    observed.setdefault("application_shutdown_observed_at", time.monotonic())
                if server_task.done():
                    observed.setdefault("server_shutdown_observed_at", time.monotonic())
                    return
                await asyncio.sleep(0.005)

        try:
            deadline = time.monotonic() + 3
            while not server.started:
                assert not server_task.done(), "Uvicorn stopped before startup"
                assert time.monotonic() < deadline, "Uvicorn startup unresolved"
                await asyncio.sleep(0.005)
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.write(("GET " + path + " HTTP/1.1\r\nHost: 127.0.0.1\r\nCookie: ANTIEK_SESSION="
                          + profile.cookies["a"] + "\r\nConnection: close\r\n\r\n").encode())
            await writer.drain()
            assert await asyncio.to_thread(entered.wait, 3), "real server worker never reached COMMIT pause"
            tasks = tuple(server.server_state.tasks)
            assert len(tasks) == 1, "request ownership is ambiguous"
            request_task = tasks[0]
            request_task.add_done_callback(lambda task: observed.setdefault("request_task_done_at", time.monotonic()))
            server_task.add_done_callback(lambda task: observed.setdefault("server_task_done_at", time.monotonic()))
            monitor = asyncio.create_task(watch_shutdown())
            writer.close()
            await writer.wait_closed()
            request_task.cancel("finite profile cancellation of real Uvicorn request task")
            observed["request_cancel_at"] = time.monotonic()
            server.should_exit = True
            observed["graceful_shutdown_requested_at"] = time.monotonic()
            await asyncio.sleep(0.3)
            assert not closed.is_set(), "worker escaped controlled pause"
            assert not any(m["body"] for m in sent), "cancelled read released a body before cleanup"
            observed["server_done_before_release"] = server_task.done()
            observed["application_done_before_release"] = server.lifespan.shutdown_event.is_set()
            observed["request_done_before_release"] = request_task.done()
            receipt("uvicorn-shutdown-while-paused", path=path, **observed,
                    real_loopback_request=True, host="127.0.0.1", ephemeral_port=port,
                    server_pid=os.getpid(), workers=1, worker_cleanup_unresolved=True,
                    private_body_released=False,
                    shutdown_acceptance="OPEN" if server_task.done() or server.lifespan.shutdown_event.is_set() else "drain observed pending")
        finally:
            release.set()
            observed["worker_release_at"] = time.monotonic()
            server.should_exit = True
            if writer is not None:
                writer.close()
                await writer.wait_closed()
            try:
                await asyncio.wait_for(asyncio.shield(server_task), 5)
                if request_task is not None:
                    await asyncio.wait_for(asyncio.shield(request_task), 3)
                if monitor is not None:
                    await asyncio.wait_for(monitor, 1)
            finally:
                listener.close()
                receipt("uvicorn-owned-cleanup", path=path, server_task_done=server_task.done(),
                        request_task_done=request_task.done() if request_task is not None else None,
                        worker_closed=closed.is_set(), close_count=[e[0] for e in events].count("close"),
                        unresolved=not server_task.done() or not closed.is_set())
            if writer is not None:
                received = await asyncio.wait_for(reader.read(), 1)
        assert closed.is_set(), "worker cleanup unresolved"
        assert [e[0] for e in events].count("close") == 1
        assert len({e[1] for e in events}) == 1
        assert [e[0] for e in events][-1] == "close"
        close_at = cleanup["closed_at"]
        assert observed["request_task_done_at"] >= close_at
        assert observed["server_task_done_at"] >= close_at
        assert observed["application_shutdown_observed_at"] >= close_at
        assert observed["server_shutdown_observed_at"] >= close_at
        receipt("uvicorn-shutdown-order", path=path, **observed, worker_close_at=close_at,
                close_count=1, same_worker_close=True, private_body_released=False,
                asgi_body_count=sum(bool(m["body"]) for m in sent), late_wire_bytes=len(received),
                observation_resolution_s=0.005, configured_graceful_timeout_s=2,
                uvicorn_version=uvicorn.__version__,
                uvicorn_server_sha256=hashlib.sha256(Path(inspect.getfile(uvicorn.Server)).read_bytes()).hexdigest(),
                server_process_or_native_termination_proved=False, live_acceptance=False)
        receipt("uvicorn-post-cancel-response-observation", path=path,
                messages=[{"type": m["type"], "status": m["status"], "at": m["at"],
                           "body_bytes": len(m["body"]),
                           "body_sha256": hashlib.sha256(m["body"]).hexdigest() if m["body"] else None,
                           "ordinary_internal_server_error": m["body"] == b"Internal Server Error",
                           "private_fixture_present": PRIVATE_A.encode() in m["body"],
                           "transport_disconnected": m["transport_disconnected"]} for m in sent],
                late_wire_bytes=len(received), close_count=1, unresolved_owned_work=False,
                generic_disconnected_500_attempt=bool(sent),
                no_private_result_release=not any(PRIVATE_A.encode() in m["body"] for m in sent))
        if sent:
            assert len(sent) in (1, 2), "unexpected additional post-cancel ASGI frame"
            start = sent[0]
            assert start["type"] == "http.response.start" and start["status"] == 500 and not start["body"]
            for message in sent:
                assert message["transport_disconnected"], "post-cancel error targeted a connected transport"
                assert message["at"] >= close_at, "post-cancel error preceded completed worker cleanup"
            if len(sent) == 2:
                body = sent[1]
                assert body["type"] == "http.response.body" and body["status"] is None
                assert body["body"] == b"Internal Server Error", "unexpected post-cancel result or error payload"
                assert len(body["body"]) == 21
                assert hashlib.sha256(body["body"]).hexdigest() == "e41656eb2ba6c6293bf6dd928e5a88cdbc50535cab661c1969e0f598e497ed62"
        assert not received, "closed client received late HTTP bytes"
        receipt("uvicorn-disconnected-error-contract", path=path,
                no_private_result_release=True, generic_disconnected_500_attempt=bool(sent),
                exact_error_body_bytes=21 if len(sent) == 2 else 0,
                actual_late_wire_bytes=0, close_count=1, observed_drain_before_lifespan=True,
                disposition_sha256="61afc9e6d3ac7eef0b52ba14c4a0b681625ad570500c5f328bcadbbe4b1ae31b",
                forced_timeout_or_native_termination_proved=False, live_acceptance=False)

    asyncio.run(run())
