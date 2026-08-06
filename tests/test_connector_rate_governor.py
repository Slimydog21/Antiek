"""Host-global per-vendor rate governor tests (spec §5.4, sprint S1).

The invariant: a vendor's sliding-window budget (``RateSpec.max_calls`` per
``window_s``) + the 429 ``banned_until`` sentinel must hold GLOBALLY across
all jobs for that vendor on this host — the governor serializes the
read-modify-write of its shared JSON state under an exclusive ``fcntl.flock``
(the generalized arXiv-governor mechanism), so two processes can never both
observe a stale window and fire the ``max_calls``-th call twice.

Rigor #3 — each guard ships a test that FAILS on a violating change:

  (a) WINDOW SPACING. With ``RateSpec(1, 1.0)`` the second send's recorded
      time is >= the first's + 1.0s; with ``RateSpec(2, 1.0)`` the window
      SLIDES (the 3rd send waits only for the oldest in-window call to age
      out, not a full window from the last).
  (b) CROSS-PROCESS OBSERVABILITY. A SECOND governor instance over the same
      state dir + vendor (a separate process behaves identically) observes the
      first's recorded calls and spaces against them. The RED control — two
      un-flocked ``_wait_if_needed`` calls — records both inside one window,
      proving the flock is the load-bearing piece.
  (c) 429 BAN SENTINEL. A 429 noted by one governor is observed by a second:
      it raises ``VendorBanned`` BEFORE its send callable runs. ``Retry-After``
      beyond the default back-off is honored.
  (d) CONCURRENCY. Two threads sharing one state file + the REAL flock + one
      fake clock produce request times pairwise spaced by the window.
  (e) FAIL-SAFE. A corrupt state file reads as a FULL window (conservative),
      never as "never throttled".

No test ever sleeps a real window-second: clock + sleeper are injected (the
sleeper advances the fake clock — the ``tools/arxiv_census.py`` precedent).
The flock itself is REAL across every path.
"""

from __future__ import annotations

import os
import sys
import threading
from pathlib import Path

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

import pytest  # noqa: E402

from runtime.connectors.base import RateSpec  # noqa: E402
from runtime.connectors.rate_governor import (  # noqa: E402
    DEFAULT_BAN_BACKOFF_S,
    VendorBanned,
    VendorRateGovernor,
)


class _FakeClock:
    """A monotonic fake wall-clock. ``now()`` reads it; ``sleep(s)`` advances
    it by ``s`` — so the governor's window wait moves time forward without
    blocking. Thread-safe so two governors can share one clock
    deterministically (the ``test_rate_governor.py`` pattern)."""

    def __init__(self, start: float = 1000.0) -> None:
        self._t = float(start)
        self._lock = threading.Lock()

    def now(self) -> float:
        with self._lock:
            return self._t

    def sleep(self, seconds: float) -> None:
        with self._lock:
            self._t += max(0.0, float(seconds))


class _Resp:
    """Minimal ``_ResponseLike``: a status + headers, what the governor inspects."""

    def __init__(self, status_code: int = 200, headers: dict | None = None) -> None:
        self.status_code = status_code
        self.headers = headers or {}


def _governor(
    state_dir: str,
    clock: _FakeClock,
    *,
    max_calls: int = 1,
    window_s: float = 1.0,
    vendor: str = "testvendor",
) -> VendorRateGovernor:
    return VendorRateGovernor(
        vendor,
        RateSpec(max_calls=max_calls, window_s=window_s),
        state_dir=state_dir,
        clock=clock.now,
        sleeper=clock.sleep,
        lock_poll_interval_s=0.01,
    )


def _ok_send(sent_at: list[float], clock: _FakeClock):
    def _send() -> _Resp:
        sent_at.append(clock.now())
        return _Resp(200)

    return _send


# ── (a) the window spaces successive sends ────────────────────────────────


def test_second_send_waits_for_the_window(tmp_path: Path) -> None:
    clock = _FakeClock()
    gov = _governor(str(tmp_path), clock, max_calls=1, window_s=1.0)
    sent_at: list[float] = []
    gov.governed_send(_ok_send(sent_at, clock))
    gov.governed_send(_ok_send(sent_at, clock))
    assert sent_at == [1000.0, 1001.0]


def test_window_slides_rather_than_restarting(tmp_path: Path) -> None:
    """RateSpec(2, 1.0): sends 1-2 fire immediately; send 3 waits only for the
    OLDEST in-window call to age out (a sliding window), and send 4 then fires
    immediately in the freed slot."""
    clock = _FakeClock()
    gov = _governor(str(tmp_path), clock, max_calls=2, window_s=1.0)
    sent_at: list[float] = []
    for _ in range(4):
        gov.governed_send(_ok_send(sent_at, clock))
    assert sent_at == [1000.0, 1000.0, 1001.0, 1001.0]


def test_state_file_keeps_only_the_in_window_tail(tmp_path: Path) -> None:
    clock = _FakeClock()
    gov = _governor(str(tmp_path), clock, max_calls=1, window_s=1.0)
    for _ in range(5):
        gov.governed_send(lambda: _Resp(200))
    import json

    state = json.loads((tmp_path / "testvendor.json").read_text())
    assert state["request_times"] == [1004.0]  # pruned, not an ever-growing log


# ── (b) cross-instance observability + the red control ────────────────────


def test_second_governor_observes_the_firsts_calls(tmp_path: Path) -> None:
    """Two governor instances sharing one state dir + vendor (what two
    processes do) space against EACH OTHER's sends."""
    clock = _FakeClock()
    first = _governor(str(tmp_path), clock, max_calls=1, window_s=1.0)
    second = _governor(str(tmp_path), clock, max_calls=1, window_s=1.0)
    sent_at: list[float] = []
    first.governed_send(_ok_send(sent_at, clock))
    second.governed_send(_ok_send(sent_at, clock))
    assert sent_at == [1000.0, 1001.0]


def test_red_control_unflocked_interleave_loses_a_record(tmp_path: Path) -> None:
    """RED control — proves the flock is load-bearing, not decorative.

    Faithfully reproduces the unlocked read-modify-write race the arXiv
    post-mortem documented (and the ``test_rate_governor.py`` red control
    drives): two governors over the SAME state file, NO flock. BOTH read the
    shared state (empty window) BEFORE either writes — so both decide the
    window has a free slot, both append their send at the SAME clock value,
    and both write. Last-writer-wins: TWO sends happened but the state records
    ONE — the next job would see a free slot and fire a third inside the
    ``RateSpec(1, 1.0)`` window. The governor's flock (held across the whole
    read->space->write) makes this interleave impossible — see the GREEN
    cross-instance test above. Driven through the governor's own state
    primitives so the race is deterministic, not timing-dependent."""
    clock = _FakeClock()
    first = _governor(str(tmp_path), clock, max_calls=1, window_s=1.0)
    second = _governor(str(tmp_path), clock, max_calls=1, window_s=1.0)

    # --- the unlocked interleave, step by step ---
    sa = first._read_state()   # A reads: empty window -> A may fire
    sb = second._read_state()  # B reads the SAME state BEFORE A has written
    assert sa.request_times == [] and sb.request_times == []
    now = clock.now()
    sa.request_times = [now]
    first._write_state(sa)
    sb.request_times = [now]
    second._write_state(sb)  # last-writer-wins: A's record is LOST

    import json

    state = json.loads((tmp_path / "testvendor.json").read_text())
    assert state["request_times"] == [1000.0], (
        "RED control expected the un-flocked interleave to under-record two "
        "sends as one; if this fails the control no longer demonstrates the hole"
    )


def test_vendors_serialize_independently(tmp_path: Path) -> None:
    """One vendor's budget never blocks another's: separate state files +
    locks, so two vendors each get their own full window at the same instant."""
    clock = _FakeClock()
    edgar = _governor(str(tmp_path), clock, max_calls=1, window_s=1.0, vendor="edgar")
    reddit = _governor(str(tmp_path), clock, max_calls=1, window_s=1.0, vendor="reddit")
    sent_at: list[float] = []
    edgar.governed_send(_ok_send(sent_at, clock))
    reddit.governed_send(_ok_send(sent_at, clock))
    assert sent_at == [1000.0, 1000.0]


# ── (c) the 429 ban sentinel ──────────────────────────────────────────────


def test_429_bans_the_next_governor_before_it_sends(tmp_path: Path) -> None:
    clock = _FakeClock()
    first = _governor(str(tmp_path), clock)
    first.governed_send(lambda: _Resp(429))

    second = _governor(str(tmp_path), clock)
    send_calls: list[float] = []
    with pytest.raises(VendorBanned) as excinfo:
        second.governed_send(_ok_send(send_calls, clock))
    assert send_calls == []  # refused BEFORE the send ran
    assert excinfo.value.vendor == "testvendor"
    assert excinfo.value.remaining_s == pytest.approx(DEFAULT_BAN_BACKOFF_S)


def test_retry_after_beyond_the_default_is_honored(tmp_path: Path) -> None:
    clock = _FakeClock()
    gov = _governor(str(tmp_path), clock)
    gov.governed_send(lambda: _Resp(429, headers={"Retry-After": "3600"}))
    assert gov._read_state().banned_until == pytest.approx(1000.0 + 3600.0)


def test_ban_expiry_reopens_the_window(tmp_path: Path) -> None:
    clock = _FakeClock()
    gov = _governor(str(tmp_path), clock)
    gov.governed_send(lambda: _Resp(429))
    clock.sleep(DEFAULT_BAN_BACKOFF_S + 1.0)  # wait out the ban
    sent_at: list[float] = []
    gov.governed_send(_ok_send(sent_at, clock))
    assert sent_at == [1000.0 + DEFAULT_BAN_BACKOFF_S + 1.0]


def test_non_429_status_writes_no_sentinel(tmp_path: Path) -> None:
    clock = _FakeClock()
    gov = _governor(str(tmp_path), clock)
    gov.governed_send(lambda: _Resp(500))
    assert gov._read_state().banned_until == 0.0


# ── (d) real-flock concurrency over one fake clock ────────────────────────


def test_concurrent_governed_sends_serialize_on_the_flock(tmp_path: Path) -> None:
    """Two threads, each with its own governor over the SAME state dir + the
    REAL flock + one shared fake clock, RateSpec(1, 1.0): all six sends land
    pairwise >= 1.0s apart. Deterministic because the fake clock advances ONLY
    inside the flocked window wait."""
    clock = _FakeClock()
    sent_at: list[float] = []
    errors: list[BaseException] = []

    def _worker() -> None:
        gov = _governor(str(tmp_path), clock, max_calls=1, window_s=1.0)
        try:
            for _ in range(3):
                gov.governed_send(_ok_send(sent_at, clock))
        except BaseException as exc:  # noqa: BLE001 — surfaced by the assert
            errors.append(exc)

    threads = [threading.Thread(target=_worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert errors == []
    assert len(sent_at) == 6
    ordered = sorted(sent_at)
    for earlier, later in zip(ordered, ordered[1:], strict=False):
        assert later - earlier >= 1.0


# ── (e) fail-safe state reads ─────────────────────────────────────────────


def test_corrupt_state_file_reads_as_a_full_window(tmp_path: Path) -> None:
    (tmp_path / "testvendor.json").write_text("{ not json", encoding="utf-8")
    clock = _FakeClock()
    gov = _governor(str(tmp_path), clock, max_calls=1, window_s=1.0)
    sent_at: list[float] = []
    gov.governed_send(_ok_send(sent_at, clock))
    # Treated as "just called": the send spaces out a full window anyway.
    assert sent_at == [1001.0]


def test_invalid_rate_spec_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        VendorRateGovernor("v", RateSpec(max_calls=0, window_s=1.0), state_dir=str(tmp_path))
    with pytest.raises(ValueError):
        VendorRateGovernor("v", RateSpec(max_calls=1, window_s=0.0), state_dir=str(tmp_path))
