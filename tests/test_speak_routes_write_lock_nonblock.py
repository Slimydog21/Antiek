"""Speak write routes answer 503 fast — and keep the loop alive — while
another PROCESS holds the single-writer flock.

The 2026-09 Speak write migration moved every ``_write()`` call into a
nested sync ``def _sync()`` dispatched through ``_off_loop``
(``asyncio.to_thread`` + ``WriteLockTimeout`` → 503 ``speak_writer_busy``)
and bounded the flock wait at ``_WRITE_TIMEOUT_S`` (15s, not the 300s
``connect_write`` default). The source-shaped guards
(``test_speak_no_loop_blocking_write.py`` + the two write-in-async lints)
check the SHAPE of that migration; this file is the behavioural proof of
its two observable effects, holding the lock from a SEPARATE process so
the cross-process flock (not an in-process thread) is the contention:

  * Test A — a held writer turns every migrated write route into a fast
    503 ``speak_writer_busy`` rather than a stall or a 500.
  * Test B — while a request waits on the flock, the event loop keeps
    servicing other coroutines. Pre-migration, ``connect_write``'s
    ``time.sleep`` poll ran ON the loop of the ``--workers 1`` service,
    so the ticker's gap equalled the whole wait and this test failed.

The two-hop routes (``submit_answer``, ``next_followups``, ``decline``,
the pushes helpers) open ``connect_write`` themselves, out of ``_write``'s
reach. Before they took a ``timeout_s``, each such request waited out the
whole hold (``connect_write``'s 300s default) in an executor thread. Three
tests pin the bound on them:

  * Test A covers the two routes whose FIRST lock is the helper's own
    (answers, reping) with a cross-process holder.
  * Test C holds the in-process gate instead, which also reaches the
    routes that read before they write (followups, pushes): under a
    cross-process holder their read-only open fails first.
  * Test D runs all eight two-hop routes with the lock free and records
    the wait bound of every gate acquire the request makes, so the later
    hops (voice-note ingest, the answer turn, decline after the token
    resolve) are covered too, not only the first one.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, NamedTuple

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api import speak_routes as speak_routes_module
from interfaces.research.api.app import create_app
from runtime import db_lock

_ROOT = Path(__file__).resolve().parents[1]

# The lock holder. Runs in a SUBPROCESS (not a thread) so the flock is held
# cross-process exactly as an ingest cron or the nightly backup would hold
# it. Blocks until its stdin closes or 20s elapse, whichever comes first,
# then releases — the parent always terminates it in a finally, so the 20s
# is only a safety bound for a lost parent.
_HOLDER_CHILD = """
import select
import sys
import time

from runtime.db_lock import connect_write

with connect_write(sys.argv[1], purpose="test:hold", timeout_s=20) as con:
    con.execute("SELECT 1")
    print("held", flush=True)
    deadline = time.monotonic() + 20.0
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        ready, _, _ = select.select([sys.stdin.buffer], [], [], remaining)
        if not ready:
            break
        if not sys.stdin.buffer.read(1):
            break
print("released", flush=True)
"""


class StubEmbedding:
    dimension = 4

    def encode(self, text: str) -> list[float]:
        h = sum(ord(c) for c in text) or 1
        return [float(h % 7), float((h >> 2) % 5), 1.0, 0.0]


def _read_line_with_timeout(
    proc: subprocess.Popen[str], timeout_s: float
) -> str | None:
    """One stdout line, or None if the child stays silent past the timeout."""
    box: dict[str, str | None] = {}

    def _reader() -> None:
        if proc.stdout is not None:
            box["line"] = proc.stdout.readline()

    t = threading.Thread(target=_reader, daemon=True)
    t.start()
    t.join(timeout_s)
    if t.is_alive():
        return None
    return box.get("line")


class Seeded(NamedTuple):
    client: TestClient
    app: FastAPI
    db: str
    pid: str
    iid: str
    token: str


class _StubTranscript:
    text = "she grew up by the river"


class _StubTranscriber:
    def transcribe(
        self, audio: bytes, *, filename: str, language: str | None = None
    ) -> _StubTranscript:
        return _StubTranscript()


@pytest.fixture
def seeded() -> Iterator[Seeded]:
    """A project, an invite, ``record`` consent and one answer, written with
    the lock FREE, so real ids exist, the schema memos
    (``_INITIALIZED_PATHS`` / ``ensure_speak_schema``) are warm, and
    ``next_followups`` has an informant turn to follow up on (without one it
    generates nothing and never takes the lock)."""
    tmpdir = tempfile.mkdtemp(prefix="speak-wlock-nb-")
    db = os.path.join(tmpdir, "t.duckdb")
    monkeypatch = pytest.MonkeyPatch()
    try:
        monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
        monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(tmpdir, "events"))
        monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
        monkeypatch.delenv("ANTIEK_OPERATOR_EMAIL", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.setattr(
            "acquisition.voice.adapter.default_embedding_provider",
            lambda: StubEmbedding(),
        )
        monkeypatch.setattr(
            speak_routes_module, "_INVITEE_TRANSCRIBER", _StubTranscriber()
        )
        # Shrink the bounded wait so the 503 arrives in well under a second.
        # raising=False lets this same file run against the PRE-migration
        # module (no _WRITE_TIMEOUT_S attribute): it then fails on its
        # behavioural assertions, not on AttributeError.
        monkeypatch.setattr(speak_routes_module, "_WRITE_TIMEOUT_S", 0.5, raising=False)

        app = create_app(register_wrestling=False, register_providers=False, cors_origins=[])
        client = TestClient(app)
        proj = client.post(
            "/speak/projects",
            json={"title": "Dad", "publish_intent": "private_never_published"},
        )
        assert proj.status_code == 201, proj.text
        pid = proj.json()["project_id"]
        inv = client.post(
            f"/speak/projects/{pid}/invites",
            json={"informant_email": "aunt@x.com"},
        )
        assert inv.status_code == 201, inv.text
        iid, token = inv.json()["interview_id"], inv.json()["token"]
        consent = client.post(
            f"/speak/interviews/{iid}/consent", json={"scopes": ["record"]}
        )
        assert consent.status_code == 200, consent.text
        answer = client.post(
            f"/speak/interviews/{iid}/answers",
            json={"question_id": "q0", "transcript": "he fixed radios", "duration_seconds": 1.0},
        )
        assert answer.status_code == 201, answer.text
        yield Seeded(client, app, db, pid, iid, token)
    finally:
        monkeypatch.undo()


@pytest.fixture
def held(seeded: Seeded) -> Iterator[Seeded]:
    """``seeded`` with the write lock held by another PROCESS."""
    env = {**os.environ, "PYTHONPATH": str(_ROOT), "ANTIEK_WRITE_KEEPALIVE_S": "0"}
    proc = subprocess.Popen(
        [sys.executable, "-c", _HOLDER_CHILD, seeded.db],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        text=True,
    )
    try:
        line = _read_line_with_timeout(proc, 15.0)
        assert line is not None and "held" in line, (
            f"holder child never acquired the write lock "
            f"(returncode={proc.poll()!r}, line={line!r})"
        )
        yield seeded
    finally:
        if proc.stdin is not None:
            proc.stdin.close()
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:  # pragma: no cover — safety net
            proc.kill()


def _fmt(path: str, s: Seeded) -> str:
    return path.format(pid=s.pid, iid=s.iid, token=s.token)


_CASES: list[tuple[str, str, Any]] = [
    ("GET", "/speak/projects", None),
    ("GET", "/speak/projects/{pid}", None),
    (
        "POST",
        "/speak/projects",
        {"title": "Mum", "publish_intent": "private_never_published"},
    ),
    ("GET", "/speak/projects/{pid}/invites", None),
    ("POST", "/speak/projects/{pid}/corroborate", None),
    # TakedownRequestModel: target_kind + target_id required, rest optional.
    ("POST", "/speak/projects/{pid}/takedowns", {"target_kind": "claim", "target_id": "c1"}),
    # Two-hop routes whose first lock is the helper's own connect_write.
    (
        "POST",
        "/speak/interviews/{iid}/answers",
        {"question_id": "q1", "transcript": "hello there", "duration_seconds": 1.0},
    ),
    ("POST", "/speak/pushes/reping", {"interview_id": "{iid}"}),
]


@pytest.mark.parametrize(("method", "path", "body"), _CASES)
def test_held_write_lock_yields_fast_503(
    held: Seeded,
    method: str,
    path: str,
    body: Any,
) -> None:
    """Test A — a held cross-process writer turns each migrated Speak write
    route into 503 speak_writer_busy inside the bounded wait, never a 300s
    stall (which would trip the 5s wall-clock bound) and never a 500."""
    client = held.client
    if isinstance(body, dict):
        body = {k: _fmt(v, held) if isinstance(v, str) else v for k, v in body.items()}
    t0 = time.monotonic()
    r = client.request(method, _fmt(path, held), json=body)
    elapsed = time.monotonic() - t0
    assert r.status_code == 503, (r.status_code, r.text)
    assert r.json()["detail"] == "speak_writer_busy", r.text
    assert elapsed < 5.0, f"{method} {path} took {elapsed:.3f}s under a held writer"


async def test_event_loop_stays_live_while_write_lock_is_held(
    held: Seeded,
) -> None:
    """Test B — the loop proof. While the request waits on the flock, a
    ticker coroutine keeps being serviced; its max gap stays at the tick
    interval. Pre-migration the flock poll ran on the loop thread, the gap
    equalled the whole wait (seconds), and the response was not a 503."""
    app = held.app
    max_gap = 0.0
    stop = asyncio.Event()

    async def ticker() -> None:
        nonlocal max_gap
        last = time.monotonic()
        while not stop.is_set():
            await asyncio.sleep(0.02)
            now = time.monotonic()
            max_gap = max(max_gap, now - last)
            last = now

    tick = asyncio.create_task(ticker())
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as ac:
            t0 = time.monotonic()
            r = await ac.get("/speak/projects")
            elapsed = time.monotonic() - t0
    finally:
        stop.set()
        await tick

    assert r.status_code == 503, (r.status_code, r.text)
    assert r.json()["detail"] == "speak_writer_busy", r.text
    assert elapsed < 5.0, f"request took {elapsed:.3f}s under a held writer"
    assert max_gap < 0.5, (
        f"event loop stalled for {max_gap:.3f}s while the handler waited on "
        "the write flock — the flock poll is back on the loop thread"
    )


@contextmanager
def _in_process_writer_held(safety_s: float = 10.0) -> Iterator[None]:
    """Hold ``connect_write``'s in-process gate, as another request thread
    mid-write would. A timer releases it after ``safety_s`` so a handler
    that ignores the bound (and waits on the gate for 300s) fails the
    wall-clock assertion instead of hanging the suite."""
    gate = db_lock._PROCESS_WRITE_GATE
    assert gate.acquire(timeout=5), "in-process write gate already held"
    guard = threading.Lock()
    released = False

    def _release() -> None:
        nonlocal released
        with guard:
            if not released:
                released = True
                gate.release()

    timer = threading.Timer(safety_s, _release)
    timer.daemon = True
    timer.start()
    try:
        yield
    finally:
        timer.cancel()
        _release()


_IN_PROCESS_TWO_HOP_CASES: list[tuple[str, str, Any]] = [
    (
        "POST",
        "/speak/interviews/{iid}/answers",
        {"question_id": "q1", "transcript": "hello there", "duration_seconds": 1.0},
    ),
    ("POST", "/speak/interviews/{iid}/followups", None),
    ("GET", "/speak/pushes", None),
    ("POST", "/speak/pushes/reping", {"interview_id": "{iid}"}),
]


@pytest.mark.parametrize(("method", "path", "body"), _IN_PROCESS_TWO_HOP_CASES)
def test_in_process_writer_turns_two_hop_routes_into_fast_503(
    seeded: Seeded,
    method: str,
    path: str,
    body: Any,
) -> None:
    """Test C — with another thread of this process holding the write gate,
    each operator two-hop route answers 503 inside the bounded wait. Before
    the helpers took ``timeout_s`` they waited on the gate for 300s, so this
    ran until the safety timer released it (10s) and then returned 2xx."""
    if isinstance(body, dict):
        body = {k: _fmt(v, seeded) if isinstance(v, str) else v for k, v in body.items()}
    with _in_process_writer_held():
        t0 = time.monotonic()
        r = seeded.client.request(method, _fmt(path, seeded), json=body)
        elapsed = time.monotonic() - t0
    assert r.status_code == 503, (r.status_code, r.text, f"{elapsed:.2f}s")
    assert r.json()["detail"] == "speak_writer_busy", r.text
    assert elapsed < 5.0, f"{method} {path} took {elapsed:.3f}s under a held writer"


class _RecordingGate:
    """Delegates to the real in-process gate and records the wait bound of
    every acquire. Every ``connect_write`` in the process goes through this
    gate first, however the caller imported ``connect_write``."""

    def __init__(self, real: Any) -> None:
        self._real = real
        self.timeouts: list[float] = []

    def acquire(self, blocking: bool = True, timeout: float = -1) -> bool:
        self.timeouts.append(timeout)
        return bool(self._real.acquire(blocking, timeout))

    def release(self) -> None:
        self._real.release()

    def locked(self) -> bool:
        return bool(self._real.locked())


# (method, path, body, content_type, fewest write-gate acquires). The floor
# proves the helper's own writes ran and were recorded, not just the route's
# _write: e.g. the invite answer is token resolve + consent check + voice-note
# ingest + answer turn.
_TWO_HOP_ROUTES: list[tuple[str, str, Any, str | None, int]] = [
    (
        "POST",
        "/speak/interviews/{iid}/answers",
        {"question_id": "q1", "transcript": "hello there", "duration_seconds": 1.0},
        None,
        3,
    ),
    ("POST", "/speak/interviews/{iid}/followups", None, None, 1),
    ("GET", "/speak/pushes", None, None, 1),
    ("POST", "/speak/pushes/reping", {"interview_id": "{iid}"}, None, 2),
    (
        "POST",
        "/speak/invite/{token}/answer",
        {"question_id": "q1", "transcript": "hello there", "duration_seconds": 1.0},
        None,
        4,
    ),
    ("POST", "/speak/invite/{token}/voice?question_id=q1&duration_seconds=1", b"voice", "audio/webm", 4),
    ("POST", "/speak/invite/{token}/followups", None, None, 2),
    ("POST", "/speak/invite/{token}/decline", None, None, 2),
]


@pytest.mark.parametrize(
    ("method", "path", "body", "content_type", "min_acquires"), _TWO_HOP_ROUTES
)
def test_every_write_in_a_two_hop_route_carries_the_bound(
    seeded: Seeded,
    method: str,
    path: str,
    body: Any,
    content_type: str | None,
    min_acquires: int,
) -> None:
    """Test D — with the lock free, every write-gate acquire a two-hop route
    makes waits at most ``_WRITE_TIMEOUT_S``. A later hop a held-lock test
    cannot isolate (the voice-note ingest inside submit_answer, decline after
    the token resolve) is covered here: before the fix those hops recorded
    connect_write's 300s default."""
    recorder = _RecordingGate(db_lock._PROCESS_WRITE_GATE)
    mp = pytest.MonkeyPatch()
    mp.setattr(db_lock, "_PROCESS_WRITE_GATE", recorder)
    try:
        url = _fmt(path, seeded)
        if isinstance(body, bytes):
            r = seeded.client.request(
                method, url, content=body, headers={"Content-Type": str(content_type)}
            )
        else:
            if isinstance(body, dict):
                body = {k: _fmt(v, seeded) if isinstance(v, str) else v for k, v in body.items()}
            r = seeded.client.request(method, url, json=body)
    finally:
        mp.undo()
    assert 200 <= r.status_code < 300, (r.status_code, r.text)
    bound = speak_routes_module._WRITE_TIMEOUT_S
    assert len(recorder.timeouts) >= min_acquires, (
        f"{method} {path} made {len(recorder.timeouts)} write-gate acquires, "
        f"expected at least {min_acquires}: {recorder.timeouts}"
    )
    unbounded = [t for t in recorder.timeouts if t < 0 or t > bound]
    assert not unbounded, (
        f"{method} {path} took the write lock with waits {recorder.timeouts}; "
        f"every wait must be at most _WRITE_TIMEOUT_S={bound}"
    )
