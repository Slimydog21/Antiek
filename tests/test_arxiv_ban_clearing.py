"""SPR-05 arXiv task 2 — an expired ban is history, not state.

Two independently load-bearing edits, each pinned by its own test:

1. ``ArxivThrottle.wait_if_needed`` resets ``banned_until`` to ``0.0`` on the
   first permitted request after a ban expires. Before, the live file carried
   ``banned_until`` = 2026-06-03 behind a same-day ``last_request_at`` for three
   and a half months: operationally benign (a past timestamp never blocks) but
   it poisoned every "were we banned recently?" read-out.
2. ``tools.run_corpus_ingest._mirror_export_ban`` copies the export ban into
   the shared ``source_throttle`` sentinel only while it is LIVE
   (``if until > now``). Before, ``if until > 0`` mirrored a months-dead ban
   forward on every ingest run, so source rotation skipped arXiv for nothing.

NO live HTTP and NO real state files: both throttle paths are redirected to
``tmp_path`` (the conftest autouse fixture covers the arXiv one; the shared
one is set explicitly here). ``now``/``sleep`` are injected where the API
allows so nothing sleeps for real.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import httpx

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

# The two CLIs are imported at collection time so their module-top
# `from acquisition.arxiv import search` bindings freeze to the ORIGINAL
# function. Otherwise the first lazy import of tools.ingest_arxiv from inside
# _arxiv_candidates (while acquisition.arxiv.search is patched below) would
# capture the fake permanently and leak it into later tests in the process.
from acquisition.arxiv.throttle import ArxivThrottle  # noqa: E402
from substrate.source_throttle import SourceThrottle  # noqa: E402
from tools import ingest_arxiv  # noqa: E402,F401
from tools import run_corpus_ingest as rci  # noqa: E402


class _FakeClock:
    def __init__(self, t: float = 1_000_000.0) -> None:
        self.t = t

    def now(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.t += seconds

    def advance(self, seconds: float) -> None:
        self.t += seconds


def test_expired_sentinel_is_ban_clear_on_the_next_successful_request(tmp_path):
    """Arm a ban, advance the clock past it, issue ONE permitted request: the
    PERSISTED ``banned_until`` is exactly ``0.0`` — read back from the JSON
    file, not from the in-memory object, because the file is the cross-process
    contract and what ``tools/arxiv_verify.py`` reports from."""
    clock = _FakeClock()
    state_path = tmp_path / "arxiv_throttle.json"
    t = ArxivThrottle(
        state_path=str(state_path),
        default_ban_backoff_s=100.0,
        now=clock.now,
        sleep=clock.sleep,
    )
    t.note_response(429, headers={})
    armed = t.banned_until()
    assert armed == clock.now() + 100.0
    assert json.loads(state_path.read_text())["banned_until"] == armed

    clock.advance(101.0)  # the ban is now in the past
    t.wait_if_needed()  # the one permitted request

    persisted = json.loads(state_path.read_text())
    assert persisted["banned_until"] == 0.0, persisted
    assert t.banned_until() == 0.0
    # And the request itself was recorded, so the reset did not eat the write.
    assert persisted["last_request_at"] == clock.now()


def test_mirror_expired_export_ban_leaves_the_shared_sentinel_untouched(
    monkeypatch, tmp_path
):
    """Feed ``_mirror_export_ban`` an EXPIRED export-ban timestamp and assert
    the shared ``source_throttle`` sentinel is untouched.

    The closure lives inside ``_arxiv_candidates`` and is reached from its
    HTTP-error handler, so the test drives the real function: a fake ``search``
    writes an already-expired ``banned_until`` into the throttle's state file
    (the shape a concurrent last-writer-wins rewrite, or a Retry-After that
    elapsed in flight, leaves behind) and then raises a 503 — a status the
    arXiv throttle does NOT turn into a fresh ban, so the only value the
    mirror can see is the expired one."""
    arxiv_state = Path(os.environ["ANTIEK_ARXIV_THROTTLE_PATH"])
    shared_state = tmp_path / "source_throttle.json"
    monkeypatch.setenv("ANTIEK_SOURCE_THROTTLE_PATH", str(shared_state))

    expired = time.time() - 100.0

    def _stale_then_503(**_kwargs):
        arxiv_state.write_text(
            json.dumps({"last_request_at": time.time(), "banned_until": expired})
        )
        req = httpx.Request("GET", "https://export.arxiv.org/api/query")
        resp = httpx.Response(503, request=req)
        raise httpx.HTTPStatusError("503 overloaded", request=req, response=resp)

    monkeypatch.setattr("acquisition.arxiv.search", _stale_then_503)

    out = rci._arxiv_candidates(
        query="quantum", category=None, ids=None, limit=3,
        investigation_id="inv-test",
    )
    assert out == []
    # The mirror DID see the expired value (the fake wrote it after the
    # pre-flight wait cleared the file), and refused to copy it forward.
    assert json.loads(arxiv_state.read_text())["banned_until"] == expired
    assert SourceThrottle().banned_until(rci.ARXIV_EXPORT_KEY) == 0.0
    if shared_state.exists():
        sources = json.loads(shared_state.read_text()).get("sources", {})
        assert rci.ARXIV_EXPORT_KEY not in sources, sources
