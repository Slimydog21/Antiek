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
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api import speak_routes as speak_routes_module
from interfaces.research.api.app import create_app

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


@pytest.fixture
def held() -> Iterator[tuple[TestClient, str, FastAPI]]:
    """(client, project_id, app) with the write lock held by another process.

    Seeding (project + invite) happens with the lock FREE so real ids exist
    and the schema memos (``_INITIALIZED_PATHS`` / ``ensure_speak_schema``)
    are warm — the contended request then never needs a DuckDB open before
    the flock, only the bounded flock wait.
    """
    tmpdir = tempfile.mkdtemp(prefix="speak-wlock-nb-")
    db = os.path.join(tmpdir, "t.duckdb")
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(tmpdir, "events"))
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    monkeypatch.delenv("ANTIEK_OPERATOR_EMAIL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(
        "acquisition.voice.adapter.default_embedding_provider",
        lambda: StubEmbedding(),
    )
    # Shrink the bounded wait so the 503 arrives in well under a second.
    # raising=False lets this same file run against the PRE-migration module
    # (no _WRITE_TIMEOUT_S attribute): it then fails on its behavioural
    # assertions, not on AttributeError.
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

    env = {**os.environ, "PYTHONPATH": str(_ROOT), "ANTIEK_WRITE_KEEPALIVE_S": "0"}
    proc = subprocess.Popen(
        [sys.executable, "-c", _HOLDER_CHILD, db],
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
        yield client, pid, app
    finally:
        if proc.stdin is not None:
            proc.stdin.close()
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:  # pragma: no cover — safety net
            proc.kill()
        monkeypatch.undo()


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
]


@pytest.mark.parametrize(("method", "path", "body"), _CASES)
def test_held_write_lock_yields_fast_503(
    held: tuple[TestClient, str, FastAPI],
    method: str,
    path: str,
    body: Any,
) -> None:
    """Test A — a held cross-process writer turns each migrated Speak write
    route into 503 speak_writer_busy inside the bounded wait, never a 300s
    stall (which would trip the 5s wall-clock bound) and never a 500."""
    client, pid, _app = held
    t0 = time.monotonic()
    r = client.request(method, path.format(pid=pid), json=body)
    elapsed = time.monotonic() - t0
    assert r.status_code == 503, (r.status_code, r.text)
    assert r.json()["detail"] == "speak_writer_busy", r.text
    assert elapsed < 5.0, f"{method} {path} took {elapsed:.3f}s under a held writer"


async def test_event_loop_stays_live_while_write_lock_is_held(
    held: tuple[TestClient, str, FastAPI],
) -> None:
    """Test B — the loop proof. While the request waits on the flock, a
    ticker coroutine keeps being serviced; its max gap stays at the tick
    interval. Pre-migration the flock poll ran on the loop thread, the gap
    equalled the whole wait (seconds), and the response was not a 503."""
    _client, _pid, app = held
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
