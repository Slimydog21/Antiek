"""Host-global per-vendor rate governor for BYO-tools connectors (spec §5.4).

This GENERALIZES ``acquisition/arxiv/rate_governor.py`` — the mechanism is
reused, not re-implemented (the arXiv module's own warning at
``rate_governor.py:24-28``: re-implementing rate-limiting is the documented
historical cause of an IP ban). What is kept verbatim in spirit:

  * an EXCLUSIVE cross-process ``fcntl.flock`` (the canonical Antiek
    serialization mechanism — same shape as ``runtime/db_lock.py``) around the
    ENTIRE ``wait -> send -> note`` critical section, so no two processes can
    observe stale rate state and both fire inside one window;
  * a JSON state SIDECAR (atomic tmp+replace writes) so the rate state
    survives across separate process invocations;
  * a ``banned_until`` sentinel written on a 429 (honoring ``Retry-After``)
    and observed by the next process to take the lock;
  * injectable clock/sleep so CI tests never sleep real seconds (the
    ``tools/arxiv_census.py`` precedent).

What changes vs the arXiv engine:

  * the timing rule is vendor-parameterized: a SLIDING WINDOW of
    ``RateSpec.max_calls`` per ``RateSpec.window_s`` seconds (EDGAR
    ``(8, 1.0)``; Reddit ``(100, 60.0)``) instead of one hard-coded >=3s
    spacing;
  * state is PER-VENDOR: ``{state_dir}/{vendor}.json`` with its co-located
    ``{vendor}.json.governor.lock`` — each vendor's budget serializes
    independently, and one vendor's 429 ban never blocks another's egress.

Scope of the guarantee is the arXiv governor's honesty bar: MECHANICAL on this
host (every process routing through ``governed_send`` with the same state dir
serializes on the same flock + shares the same JSON state); OPERATIONAL, not
mechanical, across machines (a second box running its own client is invisible
to this flock — do not run one).

CLOCK CHOICE: the default clock is ``time.time`` (WALL clock), not the spec
sketch's ``time.monotonic`` — monotonic epochs are process-local, and the
state file's whole point is that a SECOND PROCESS observes the first's
timestamps + ban sentinel. The arXiv engine it generalizes uses ``time.time``
for exactly this reason.
"""

from __future__ import annotations

import contextlib
import errno
import fcntl
import json
import os
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import TracebackType
from typing import Literal, Protocol, TypeVar

from runtime.connectors.base import RateSpec

_ENV_RATE_DIR = "ANTIEK_CONNECTOR_RATE_DIR"

# How long to wait for a vendor's governor flock before giving up. The
# critical section is at most one window's sleep + one HTTP round-trip, and
# queued jobs serialize; 300s mirrors db_lock's DEFAULT_TIMEOUT_S (and the
# arXiv governor's own default).
DEFAULT_LOCK_TIMEOUT_S = 300.0
DEFAULT_LOCK_POLL_INTERVAL_S = 0.1

# Default back-off when a 429 arrives without a usable Retry-After header.
# SEC's IP blocks for breaching 10 req/s run ~10 minutes; 600s is the floor so
# a banned connector PAUSES instead of re-hitting and extending the block.
DEFAULT_BAN_BACKOFF_S = 600.0


def default_state_dir() -> str:
    """The cross-process per-vendor state directory.

    Honors ``ANTIEK_CONNECTOR_RATE_DIR`` for tests / alternate homes;
    otherwise ``(ANTIEK_HOME|~/.antiek)/connectors/rate/`` — alongside the
    other Antiek runtime state, never in the repo.
    """
    env = os.environ.get(_ENV_RATE_DIR)
    if env:
        return env
    home = os.environ.get("ANTIEK_HOME", os.path.expanduser("~/.antiek"))
    return str(Path(home) / "connectors" / "rate")


class _ResponseLike(Protocol):
    """The minimal response surface ``governed_send`` inspects — exactly what
    ``httpx.Response`` exposes. Declared structurally (the
    ``acquisition/arxiv/throttle.py`` pattern) so the governor stays free of
    an httpx import; ``headers`` is a read-only property so
    ``httpx.Headers``' covariant subtype still satisfies it."""

    status_code: int

    @property
    def headers(self) -> Mapping[str, str]: ...


_ResponseT = TypeVar("_ResponseT", bound=_ResponseLike)


class VendorBanned(RuntimeError):
    """Raised inside ``governed_send`` BEFORE sending when a 429-written
    ``banned_until`` sentinel is in the future.

    The caller must PAUSE, not retry — re-hitting a rate-limiting vendor is
    exactly what extends its IP block (the arXiv post-mortem's lesson)."""

    def __init__(self, vendor: str, banned_until: float, now: float) -> None:
        self.vendor = vendor
        self.banned_until = banned_until
        self.remaining_s = max(0.0, banned_until - now)
        super().__init__(
            f"{vendor} rate-limited for another {self.remaining_s:.0f}s "
            f"(banned_until={banned_until:.0f}); not re-attempting."
        )


class GovernorLockTimeout(RuntimeError):
    """Raised when a vendor's governor flock could not be acquired within the
    timeout. Mirrors ``runtime.db_lock.WriteLockTimeout`` / the arXiv
    governor's own: a stuck holder is diagnosable via the PID + purpose
    stamped in the lock file."""


def _coerce_float(value: object) -> float:
    """Coerce a JSON-loaded state value to ``float``, defaulting falsy/absent
    values to ``0.0`` (the arXiv throttle's ``or 0.0`` semantics, type-safe)."""
    if not value:
        return 0.0
    if isinstance(value, (int, float, str)):
        return float(value)
    return 0.0


@dataclass
class _State:
    request_times: list[float] = field(default_factory=list)
    banned_until: float = 0.0

    @classmethod
    def from_dict(cls, d: Mapping[str, object]) -> _State:
        raw_times = d.get("request_times")
        times = (
            [_coerce_float(t) for t in raw_times]
            if isinstance(raw_times, list)
            else []
        )
        return cls(
            request_times=sorted(times),
            banned_until=_coerce_float(d.get("banned_until")),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "request_times": self.request_times,
            "banned_until": self.banned_until,
        }


def _stale_pid_check(lock_path: str) -> None:
    """Remove the lock file if its stamped PID is no longer alive.

    Best-effort hygiene before ``os.open()`` — the real serialization is the
    flock; lifted in spirit from ``runtime.db_lock._stale_pid_check`` via the
    arXiv governor.
    """
    try:
        with open(lock_path) as f:
            content = f.read(64)
    except (FileNotFoundError, OSError):
        return
    pid_str = content.split()[0] if content.strip() else ""
    if not pid_str or not pid_str.isdigit():
        return
    pid = int(pid_str)
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, PermissionError):
        with contextlib.suppress(OSError):
            os.unlink(lock_path)


class _GovernorLock:
    """An acquired exclusive flock on a vendor's lock sidecar, released on
    ``__exit__``. Same acquire shape as ``runtime.db_lock.connect_write`` and
    the arXiv governor: ``LOCK_EX | LOCK_NB`` polled to a deadline (so a
    timeout is enforceable), stale-PID cleanup before open, PID + purpose
    stamped for ops debugging, release + close on exit.

    NOT re-entrant: ``governed_send`` must not nest for the same vendor on one
    thread (the nested flock on a second fd would block to the timeout and
    raise :class:`GovernorLockTimeout` — an honest failure, not a hang). The
    arXiv governor's re-entrancy exists for its redirect-hop hooks, which this
    governor does not have.
    """

    def __init__(
        self,
        lock_path: str,
        *,
        timeout_s: float,
        poll_interval_s: float,
        purpose: str,
        sleep: Callable[[float], None],
    ) -> None:
        self._lock_path = lock_path
        self._timeout_s = float(timeout_s)
        self._poll_interval_s = float(poll_interval_s)
        self._purpose = purpose or "-"
        # The poll sleep uses REAL monotonic time, not the injected throttle
        # clock: the lock wait is wall-clock contention, independent of the
        # governor's fake test clock (the arXiv governor's own split).
        self._sleep = sleep
        self._fd: int | None = None

    def __enter__(self) -> _GovernorLock:
        parent = os.path.dirname(self._lock_path)
        if parent and not os.path.exists(parent):
            os.makedirs(parent, exist_ok=True)
        _stale_pid_check(self._lock_path)
        fd = os.open(self._lock_path, os.O_CREAT | os.O_WRONLY, 0o600)
        deadline = time.monotonic() + self._timeout_s
        try:
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError as e:
                    if e.errno not in (errno.EWOULDBLOCK, errno.EAGAIN):
                        raise
                    if time.monotonic() >= deadline:
                        os.close(fd)
                        raise GovernorLockTimeout(
                            f"Could not acquire connector governor lock on "
                            f"{self._lock_path} within {self._timeout_s}s. "
                            f"Another {self._purpose} job is holding it; inspect "
                            f"with `cat {self._lock_path}` (PID + purpose)."
                        ) from e
                    self._sleep(self._poll_interval_s)
        except GovernorLockTimeout:
            raise
        except Exception:
            with contextlib.suppress(OSError):
                os.close(fd)
            raise
        # Stamp pid + purpose + timestamp for ops debugging (best-effort).
        try:
            os.ftruncate(fd, 0)
            stamp = (
                f"{os.getpid()} {self._purpose} "
                f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n"
            )
            os.write(fd, stamp.encode())
        except OSError:
            pass
        self._fd = fd
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> Literal[False]:
        if self._fd is not None:
            try:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
            finally:
                with contextlib.suppress(OSError):
                    os.close(self._fd)
        self._fd = None
        return False


class VendorRateGovernor:
    """The single seam every egress for one connector vendor routes through.

    Enforces the vendor's :class:`~runtime.connectors.base.RateSpec` sliding
    window + a 429 ``banned_until`` sentinel, with the read-modify-write of
    the shared per-vendor JSON state serialized under an exclusive
    cross-process flock — so the budget holds GLOBALLY across all jobs for
    this vendor on this host, not merely per-process.

    Construct one per job (or inject one into a connector client) and call
    :meth:`governed_send` for each HTTP send. All governors that point at the
    same state dir + vendor serialize against each other across processes.
    """

    def __init__(
        self,
        vendor: str,
        rate: RateSpec,
        *,
        state_dir: str | None = None,
        default_ban_backoff_s: float = DEFAULT_BAN_BACKOFF_S,
        lock_timeout_s: float = DEFAULT_LOCK_TIMEOUT_S,
        lock_poll_interval_s: float = DEFAULT_LOCK_POLL_INTERVAL_S,
        clock: Callable[[], float] = time.time,
        sleeper: Callable[[float], None] = time.sleep,
        lock_sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if rate.max_calls < 1:
            raise ValueError("rate.max_calls must be >= 1")
        if rate.window_s <= 0:
            raise ValueError("rate.window_s must be > 0")
        self._vendor = vendor
        self._rate = rate
        state_root = Path(state_dir or default_state_dir())
        self._state_path = state_root / f"{vendor}.json"
        self._lock_path = str(state_root / f"{vendor}.json.governor.lock")
        self._default_ban_backoff_s = float(default_ban_backoff_s)
        self._lock_timeout_s = float(lock_timeout_s)
        self._lock_poll_interval_s = float(lock_poll_interval_s)
        self._clock = clock
        self._sleeper = sleeper
        self._lock_sleeper = lock_sleeper

    @property
    def vendor(self) -> str:
        return self._vendor

    @property
    def rate(self) -> RateSpec:
        return self._rate

    @property
    def state_path(self) -> str:
        return str(self._state_path)

    @property
    def lock_path(self) -> str:
        return self._lock_path

    # -- state file I/O (atomic write; serialized by the caller's flock) -----

    def _read_state(self) -> _State:
        try:
            raw = self._state_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return _State()
        except OSError:
            # An unreadable state file must not silently disable the governor
            # — fail safe by treating the window as FULL at now, so the next
            # send still spaces out (the arXiv throttle's fail-safe).
            return _State(request_times=[self._clock()] * self._rate.max_calls)
        try:
            return _State.from_dict(json.loads(raw))
        except (json.JSONDecodeError, ValueError, TypeError):
            return _State(request_times=[self._clock()] * self._rate.max_calls)

    def _write_state(self, state: _State) -> None:
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        # Atomic write: tmp + replace so a crash mid-write can't leave a
        # truncated state file that reads as "never throttled".
        tmp = self._state_path.with_suffix(self._state_path.suffix + ".tmp")
        tmp.write_text(json.dumps(state.to_dict()), encoding="utf-8")
        os.replace(tmp, self._state_path)

    # -- the throttle halves (called only under the flock) -------------------

    def _wait_if_needed(self) -> None:
        """Block (or no-op) until the sliding window has a slot free.

        Raises :class:`VendorBanned` if a ban sentinel is active — the caller
        must NOT swallow this and retry; pausing is the whole point.
        """
        state = self._read_state()
        now = self._clock()
        if now < state.banned_until:
            raise VendorBanned(self._vendor, state.banned_until, now)

        window = self._rate.window_s
        times = [t for t in state.request_times if t > now - window]
        if len(times) >= self._rate.max_calls:
            # Window full: sleep until the OLDEST in-window call ages out.
            delay = times[0] + window - now
            if delay > 0:
                self._sleeper(delay)
                now = self._clock()
            times = [t for t in times if t > now - window]
        times.append(now)
        # Persist only the in-window tail so the file can't grow unboundedly.
        state.request_times = times
        self._write_state(state)

    def _note_response(
        self, status_code: int, headers: Mapping[str, str] | None = None
    ) -> None:
        """Record the outcome of a send. On 429, set ``banned_until``.

        ``Retry-After`` (integer-seconds form) is honored when present and
        parseable; otherwise the conservative default back-off. A non-429
        status is a no-op.
        """
        if status_code != 429:
            return
        backoff = self._default_ban_backoff_s
        if headers:
            retry_after = headers.get("Retry-After") or headers.get("retry-after")
            if retry_after:
                with contextlib.suppress(ValueError, TypeError):
                    backoff = max(backoff, float(int(retry_after.strip())))
        state = self._read_state()
        state.banned_until = self._clock() + backoff
        self._write_state(state)

    # -- the public seam ------------------------------------------------------

    def governed_send(self, send: Callable[[], _ResponseT]) -> _ResponseT:
        """Issue ONE vendor request with the host-global rate gate held.

        The ENTIRE ``wait -> send -> note`` sequence runs inside the exclusive
        cross-process flock: the sliding-window read + sleep + record AND the
        429 sentinel write are one atomic, globally-serialized critical
        section, so no second job can observe a stale window (two jobs can
        never both fire the ``max_calls``-th call of a window) and a 429's
        ``banned_until`` is observed atomically by the next job to acquire the
        lock.

        ``send`` performs the actual HTTP call and returns a response exposing
        ``.status_code`` + ``.headers`` (an ``httpx.Response`` does). Raises
        :class:`VendorBanned` (before sending, inside the lock) if a ban
        sentinel is active; :class:`GovernorLockTimeout` if the lock cannot be
        acquired in time. NOT re-entrant for the same vendor on one thread
        (see :class:`_GovernorLock`).
        """
        with _GovernorLock(
            self._lock_path,
            timeout_s=self._lock_timeout_s,
            poll_interval_s=self._lock_poll_interval_s,
            purpose=f"connector-{self._vendor}",
            sleep=self._lock_sleeper,
        ):
            self._wait_if_needed()
            resp = send()
            self._note_response(resp.status_code, resp.headers)
            return resp


__all__ = [
    "DEFAULT_BAN_BACKOFF_S",
    "DEFAULT_LOCK_POLL_INTERVAL_S",
    "DEFAULT_LOCK_TIMEOUT_S",
    "GovernorLockTimeout",
    "VendorBanned",
    "VendorRateGovernor",
    "default_state_dir",
]
