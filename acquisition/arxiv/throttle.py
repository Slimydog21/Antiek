"""Cross-process conservative throttle + ban sentinel for arXiv.

Post-mortem root causes this module closes (project_researchmaxx_arxiv.md,
2026-05-17): the previous throttle was *in-process only*, so a second shell
ignored the first's rate-limit history and re-triggered an IP-scoped 429
ban; and there was NO ``banned_until`` sentinel, so every fresh invocation
re-hit a banned endpoint and kept resetting the ban window.

This throttle is:

  (a) CONSERVATIVE — arXiv's stated guidance is "no more than one request
      every three seconds" (https://info.arxiv.org/help/api/tou.html). We
      enforce >= 3s spacing.
  (b) CROSS-PROCESS — spacing + ban state live in a small JSON state file
      (default ~/.antiek/arxiv_throttle.json) so they survive across separate
      invocations. A per-call in-process timer was the original bug; this is
      the fix. Each write is atomic (tmp + os.replace, no torn reads), but
      the read-modify-write is NOT locked: two processes that interleave are
      last-writer-wins. That is acceptable here — this is a single-operator,
      low-concurrency tool, and the conservative >= 3s spacing plus the
      30-min ban-backoff floor mean a lost write costs at most one ban
      window, while a banned_until already in the future is only ever pushed
      further out or harmlessly re-set.
  (c) BAN-AWARE — on a 429 we persist a ``banned_until`` timestamp (from
      Retry-After if present, else a conservative default). While banned,
      ``wait_if_needed`` raises ``ArxivBanned`` so the batch PAUSES/skips
      rather than re-hitting the endpoint.

Time + sleep are injectable (``now``/``sleep`` callables) so CI tests are
deterministic and never actually sleep 3 seconds.
"""

from __future__ import annotations

import contextlib
import json
import os
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

# arXiv API terms of use: at most one request per three seconds. We space at 3.5s
# — a deliberate 0.5s margin ABOVE the 3.0s ceiling — because clock skew, request
# jitter, and a redirect hop can push two nominally-3.0s-spaced calls inside the
# same wall-clock window, and the ban is IP-scoped with an hours-long recovery
# cost that dwarfs the extra half-second. Matches the ``~/.claude/skills/arxiv``
# governor's 3.5s spacing so the platform and the skill share one safe cadence.
MIN_REQUEST_SPACING_S = 3.5

# Default back-off when a 429 arrives without a usable Retry-After header.
# arXiv bans have historically lasted on the order of minutes-to-hours;
# 30 minutes is a conservative floor that avoids hammering while not
# stranding the operator for a full day.
DEFAULT_BAN_BACKOFF_S = 30 * 60.0


def default_state_path() -> str:
    """The cross-process state file. Honors ``ANTIEK_ARXIV_THROTTLE_PATH``
    for tests / alternate homes; defaults under ~/.antiek/ alongside the
    other Antiek runtime state."""
    env = os.environ.get("ANTIEK_ARXIV_THROTTLE_PATH")
    if env:
        return env
    return str(Path.home() / ".antiek" / "arxiv_throttle.json")


class _ResponseLike(Protocol):
    """The minimal response surface ``request`` inspects — exactly what
    ``httpx.Response`` exposes. Declared structurally so the throttle stays
    free of an httpx import (it is a pure timing/state module).

    ``headers`` is a read-only ``@property`` (not a bare mutable attribute) so
    a concrete response whose attribute is a covariant subtype —
    ``httpx.Response.headers`` is ``httpx.Headers``, a ``MutableMapping[str,
    str]`` — still satisfies the protocol. A mutable attribute would force
    invariant matching and reject ``httpx.Response``."""

    status_code: int

    @property
    def headers(self) -> Mapping[str, str]: ...


class ArxivBanned(RuntimeError):
    """Raised by ``wait_if_needed`` when a ``banned_until`` sentinel is in
    the future. The caller (batch CLI / adapter) must PAUSE — re-hitting the
    endpoint is exactly what extends an IP ban."""

    def __init__(self, banned_until: float, now: float) -> None:
        self.banned_until = banned_until
        self.remaining_s = max(0.0, banned_until - now)
        super().__init__(
            f"arXiv endpoint banned for another {self.remaining_s:.0f}s "
            f"(banned_until={banned_until:.0f}); not re-attempting."
        )


def _coerce_float(value: object) -> float:
    """Coerce a JSON-loaded state value to ``float``, defaulting falsy/absent
    values (``None``, ``0``, ``""``) to ``0.0`` — the exact ``or 0.0`` semantics
    the state file has always used, made type-safe (``json.loads`` hands back
    ``object`` cells)."""
    if not value:
        return 0.0
    if isinstance(value, (int, float, str)):
        return float(value)
    return 0.0


@dataclass
class _State:
    last_request_at: float = 0.0
    banned_until: float = 0.0

    @classmethod
    def from_dict(cls, d: Mapping[str, object]) -> _State:
        return cls(
            last_request_at=_coerce_float(d.get("last_request_at")),
            banned_until=_coerce_float(d.get("banned_until")),
        )

    def to_dict(self) -> dict[str, float]:
        return {
            "last_request_at": self.last_request_at,
            "banned_until": self.banned_until,
        }


class ArxivThrottle:
    """Process-wide throttle backed by a JSON state file.

    ``wait_if_needed()`` is called BEFORE each request: it raises
    ``ArxivBanned`` if a ban is active, else sleeps until >= 3s have elapsed
    since the last request, then records the new request time.

    ``note_response(status, headers)`` is called AFTER each request: on a
    429 it persists a ``banned_until`` sentinel.

    ``now`` returns a wall-clock epoch float (``time.time`` in prod). It is
    injectable so tests advance a fake clock instead of sleeping. ``sleep``
    likewise; the default sleeps for real but tests pass a no-op that
    advances the fake clock.
    """

    def __init__(
        self,
        *,
        state_path: str | None = None,
        min_spacing_s: float = MIN_REQUEST_SPACING_S,
        default_ban_backoff_s: float = DEFAULT_BAN_BACKOFF_S,
        now: Callable[[], float] = time.time,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._path = Path(state_path or default_state_path())
        self._min_spacing = float(min_spacing_s)
        self._default_ban_backoff = float(default_ban_backoff_s)
        self._now = now
        self._sleep = sleep

    # -- state file I/O (atomic write; unlocked, last-writer-wins) ----------

    def _read_state(self) -> _State:
        try:
            raw = self._path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return _State()
        except OSError:
            # An unreadable state file must not silently disable the
            # throttle — fail safe by assuming we just made a request so the
            # next one still spaces out.
            return _State(last_request_at=self._now())
        try:
            return _State.from_dict(json.loads(raw))
        except (json.JSONDecodeError, ValueError, TypeError):
            return _State(last_request_at=self._now())

    def _write_state(self, state: _State) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # Atomic-ish write: tmp + replace so a crash mid-write can't leave a
        # truncated state file that reads as "never throttled".
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.write_text(json.dumps(state.to_dict()), encoding="utf-8")
        os.replace(tmp, self._path)

    # -- public API ---------------------------------------------------------

    def is_banned(self) -> bool:
        return self._now() < self._read_state().banned_until

    def banned_until(self) -> float:
        return self._read_state().banned_until

    def wait_if_needed(self) -> None:
        """Block (or no-op) until it is safe to issue the next request.

        Raises ``ArxivBanned`` if a ban sentinel is active — the caller
        must NOT swallow this and retry; pausing is the whole point.
        """
        state = self._read_state()
        now = self._now()
        if now < state.banned_until:
            raise ArxivBanned(state.banned_until, now)

        elapsed = now - state.last_request_at
        if elapsed < self._min_spacing:
            self._sleep(self._min_spacing - elapsed)
            now = self._now()

        state.last_request_at = now
        self._write_state(state)

    def note_response(
        self, status_code: int, headers: Mapping[str, str] | None = None
    ) -> None:
        """Record the outcome of a request. On 429, set ``banned_until``.

        ``Retry-After`` (seconds, the form arXiv/most servers emit) is
        honored when present and parseable; otherwise we fall back to the
        conservative default back-off. A non-429 status is a no-op.
        """
        if status_code != 429:
            return
        backoff = self._default_ban_backoff
        if headers:
            retry_after = headers.get("Retry-After") or headers.get("retry-after")
            if retry_after:
                # Only the integer-seconds form is honored; the HTTP-date form
                # is rare here and parsing it adds surface for little gain — the
                # default back-off covers it safely.
                with contextlib.suppress(ValueError, TypeError):
                    backoff = max(backoff, float(int(retry_after.strip())))
        state = self._read_state()
        state.banned_until = self._now() + backoff
        self._write_state(state)

    def request(
        self,
        send: Callable[[], _ResponseLike],
    ) -> _ResponseLike:
        """Issue one throttled request and record its outcome.

        ``send`` performs the actual HTTP GET and returns a response exposing
        ``.status_code`` and ``.headers`` (an ``httpx.Response`` does). This
        is the single seam every OAI-PMH page goes through, so the throttle's
        >=3s spacing and 429 ban-sentinel are not re-implemented by the
        harvester (re-implementing rate-limiting is exactly the bug that
        IP-banned the box — see the module docstring). The wait BEFORE and the
        ``note_response`` AFTER are paired here so a caller cannot accidentally
        skip one half of the protocol.

        Raises ``ArxivBanned`` (before sending) if a ban sentinel is active.
        """
        self.wait_if_needed()
        resp = send()
        self.note_response(resp.status_code, resp.headers)
        return resp
