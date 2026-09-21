"""SPR-05 Task 2 — an EXPIRED ban sentinel must stop being treated as a ban.

Two distinct leaks, one per test:

1. ``ArxivThrottle.wait_if_needed`` never cleared ``banned_until`` once the
   window had passed, so the field accumulated a permanent "we were banned
   once" flag. The operator's live ``~/.antiek/arxiv_throttle.json`` carried a
   ``banned_until`` from 2026-06-03 behind a ``last_request_at`` of today.
2. ``run_corpus_ingest``'s export-ban mirror copied ANY non-zero sentinel into
   the shared ``source_throttle.json``, so that dead 2026-06-03 value was
   re-published on every ingest run and the orchestrator's source rotation
   read it as live.

Both tests drive a fake clock; neither sleeps, touches the network, or opens a
DuckDB handle. Nothing here goes near ``runtime/db_lock.py`` — this state is
plain JSON beside the graph, never inside it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from acquisition.arxiv.throttle import ArxivBanned, ArxivThrottle
from substrate.source_throttle import SourceThrottle
from tools.run_corpus_ingest import ARXIV_EXPORT_KEY, _mirror_ban_if_active


class _FakeClock:
    def __init__(self, start: float = 1_700_000_000.0) -> None:
        self._t = start

    def now(self) -> float:
        return self._t

    def sleep(self, seconds: float) -> None:
        self._t += max(0.0, seconds)

    def advance(self, seconds: float) -> None:
        self._t += seconds


@pytest.fixture(autouse=True)
def _never_touch_the_live_state(tmp_path, monkeypatch):
    """Both throttles below are constructed with an explicit tmp ``state_path``.
    These env vars are the second lever, and the realpath comparison is the
    proof that neither lever quietly resolved back to the operator's live
    ``~/.antiek``. Resolve-and-compare, never a string compare, so a symlink
    alias is still caught."""
    monkeypatch.setenv(
        "ANTIEK_ARXIV_THROTTLE_PATH", str(tmp_path / "arxiv_throttle.json")
    )
    monkeypatch.setenv(
        "ANTIEK_SOURCE_THROTTLE_PATH", str(tmp_path / "source_throttle.json")
    )
    from acquisition.arxiv import throttle as arxiv_throttle
    from substrate import source_throttle as shared_throttle

    live = (Path.home() / ".antiek").resolve()
    for resolve in (arxiv_throttle.default_state_path, shared_throttle.default_state_path):
        resolved = Path(resolve()).resolve()
        assert resolved != live and live not in resolved.parents, (
            f"{resolve.__module__}.default_state_path() resolved to {resolved}, "
            f"inside the operator's live {live}"
        )
    yield


def test_expired_sentinel_is_ban_clear_on_the_next_successful_request(tmp_path):
    clock = _FakeClock()
    state_path = tmp_path / "arxiv.json"
    throttle = ArxivThrottle(
        state_path=str(state_path),
        default_ban_backoff_s=100.0,
        now=clock.now,
        sleep=clock.sleep,
    )

    throttle.note_response(429, headers={})
    armed = json.loads(state_path.read_text())["banned_until"]
    assert armed == pytest.approx(clock.now() + 100.0)

    # A LIVE ban must survive an attempted request. The fix clears expired
    # sentinels; it must not amount to deleting the sentinel feature.
    with pytest.raises(ArxivBanned):
        throttle.wait_if_needed()
    assert json.loads(state_path.read_text())["banned_until"] == pytest.approx(armed)

    clock.advance(101.0)  # past the window
    throttle.wait_if_needed()  # one successful request

    persisted = json.loads(state_path.read_text())
    assert persisted["banned_until"] == 0.0, (
        "an expired ban survived a successful request; it will be read back as "
        "a ban by arxiv_verify and mirrored forward by run_corpus_ingest"
    )
    assert persisted["last_request_at"] == pytest.approx(clock.now())
    assert throttle.banned_until() == 0.0
    assert throttle.is_banned() is False


def test_mirror_expired_export_ban_leaves_the_shared_sentinel_untouched(tmp_path):
    clock = _FakeClock()
    shared_path = tmp_path / "source_throttle.json"
    shared = SourceThrottle(
        state_path=str(shared_path), now=clock.now, sleep=clock.sleep
    )

    # Exactly the live-box shape: a sentinel whose window closed long ago.
    expired = clock.now() - 9_000_000.0
    assert (
        _mirror_ban_if_active(expired, shared, ARXIV_EXPORT_KEY, now=clock.now) is False
    )
    assert not shared_path.exists(), (
        "mirroring an expired ban wrote to the shared source sentinel"
    )
    assert shared.banned_until(ARXIV_EXPORT_KEY) == 0.0
    assert shared.is_banned(ARXIV_EXPORT_KEY) is False

    # Boundary: a sentinel expiring exactly now is over, not active.
    assert (
        _mirror_ban_if_active(clock.now(), shared, ARXIV_EXPORT_KEY, now=clock.now)
        is False
    )
    assert not shared_path.exists()

    # Positive control: a LIVE ban must still be mirrored, or the guard has
    # disabled the rotation bridge rather than tightened it.
    live_until = clock.now() + 600.0
    assert (
        _mirror_ban_if_active(live_until, shared, ARXIV_EXPORT_KEY, now=clock.now)
        is True
    )
    assert shared.banned_until(ARXIV_EXPORT_KEY) == pytest.approx(live_until)
    assert shared.is_banned(ARXIV_EXPORT_KEY) is True

    # And a dead sentinel arriving after a live one must not re-publish either.
    assert _mirror_ban_if_active(0.0, shared, ARXIV_EXPORT_KEY, now=clock.now) is False
    assert shared.banned_until(ARXIV_EXPORT_KEY) == pytest.approx(live_until)
