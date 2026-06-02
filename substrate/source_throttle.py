"""Persistent, cross-process, per-source throttle + banned_until sentinel.

The 2026-05-29 prod corpus run was defeated by state that did not survive a
process restart. ``acquisition.arxiv.throttle.ArxivThrottle`` already closed
that hole for the arXiv export API — a JSON state file under ``~/.antiek/``
with a ``banned_until`` sentinel — but the OTHER live fetch paths (the OA
aggregators, the public-domain ``SourceClient``, and the per-PDF host for the
arXiv bulk path) had only an in-process timer with NO persisted ban state. A
re-run therefore re-hit a source that had just 503/429'd and dug the hole
deeper.

This module generalizes the proven ``ArxivThrottle`` shape to ALL of those
sources, keyed by a source string (``gutendex``, ``oa_unpaywall``,
``arxiv_pdf``, ...), in ONE state file. It is deliberately NOT a daemon, NOT a
second DB engine, and NOT a queue (§16): the state is a small JSON file on the
one box, written atomically (tmp + ``os.replace``), and read-mostly. It NEVER
acquires the DuckDB single-writer lock, so consulting it cannot stop the live
``antiek.service``.

Contract, consulted in the LIVE fetch path before every request:

  - ``before_request(source)`` — call BEFORE each outbound request. Raises
    ``SourceBanned`` if a ban sentinel for that source is in the future
    (the caller must NOT swallow it and retry — pausing is the whole point);
    otherwise sleeps until ``min_interval`` has elapsed since this source's
    last request, then records the new request time.
  - ``note_response(source, status, headers)`` — call AFTER each request. A
    429 or 503 sets ``banned_until = now + retry-after (or a default)``; any
    other status is a no-op.
  - ``is_banned(source)`` / ``banned_until(source)`` — read the sentinel
    without issuing a request (used by source rotation in the orchestrator).

The arXiv EXPORT API keeps its own dedicated ``ArxivThrottle`` (it carries the
documented 1-req/3s ceiling and the IP-ban history, and #23's resilience tests
pin it). This module is the single home for every other source's persisted ban
state, and is what the M4 arXiv bulk path's per-PDF host consults.

Time + sleep are injectable so CI is deterministic and never sleeps for real.
"""

from __future__ import annotations

import json
import os
import random
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

# Default per-source spacing. A research-batch tool is not latency-sensitive,
# so a courteous floor keeps us off any rate-limiter's radar. OA polite pools
# serve ~10 req/s; gutendex and the arXiv PDF host are comparable. 1.0s is the
# conservative default used for any source without an explicit override, the
# same floor ``tools.run_corpus_ingest --pd-min-interval`` defaults to.
DEFAULT_MIN_INTERVAL_S = 1.0

# Per-source min-interval overrides, each with a WHY. A source NOT listed here
# uses DEFAULT_MIN_INTERVAL_S. (The arXiv EXPORT API is intentionally absent —
# it is governed by the dedicated ArxivThrottle's documented 3s ceiling.)
SOURCE_MIN_INTERVAL_S: Mapping[str, float] = {
    # arXiv's PDF host (arxiv.org/pdf) is separate from the export API but is
    # still arXiv infrastructure; space it at the same documented 3s ceiling
    # so the bulk path's per-PDF fetch cannot re-trigger an IP-scoped ban.
    "arxiv_pdf": 3.0,
    # gutendex 503'd under the real-run burst pattern; a 1.5s floor is more
    # conservative than the 1.0s default the prod run used and still finishes
    # a curated spine in minutes.
    "gutendex": 1.5,
}

# Default back-off when a 429/503 arrives without a usable Retry-After. A ban
# of unknown duration is treated as long: re-hitting early is exactly what
# extended the arXiv ban in the prod run. 30 minutes is the conservative floor
# ArxivThrottle settled on (minutes-to-hours observed), reused for parity.
DEFAULT_BAN_BACKOFF_S = 30 * 60.0

# Status codes that arm the ban sentinel. 429 (rate-limited) and 503 (service
# unavailable / overloaded) are the two the prod run hit; both mean "stop
# hitting me." Other 5xx are transient and handled by retry-with-backoff
# (M3), not by a ban — a single 500 should not strand a source for 30 minutes.
_BAN_STATUS = frozenset({429, 503})

# Exponential-backoff defaults for transient (timeout / 5xx) retries (M3).
# Base * 2**attempt, capped, with jitter. Bounded so a genuinely-down endpoint
# fails the item rather than hanging the batch: 4 attempts at base 0.5s reach
# ~4s of cumulative delay before giving up, which is a courteous amount of
# patience for a transient blip without stalling a multi-source run.
DEFAULT_BACKOFF_BASE_S = 0.5
DEFAULT_BACKOFF_MAX_S = 30.0
DEFAULT_MAX_ATTEMPTS = 4


def default_state_path() -> str:
    """The cross-process state file. Honors ``ANTIEK_SOURCE_THROTTLE_PATH``
    for tests / alternate homes; otherwise lands under ``~/.antiek/`` alongside
    the other Antiek runtime state (the same convention ``ArxivThrottle`` and
    the event log use). It is NOT the DuckDB path — this state never goes
    through the single-writer lock."""
    env = os.environ.get("ANTIEK_SOURCE_THROTTLE_PATH")
    if env:
        return env
    return str(Path.home() / ".antiek" / "source_throttle.json")


class SourceBanned(RuntimeError):
    """Raised by ``before_request`` when a source's ``banned_until`` sentinel
    is in the future. The caller must PAUSE/skip that source — re-hitting the
    endpoint is what extends the ban. The orchestrator catches this to rotate
    to another source (M3) rather than abort the run."""

    def __init__(self, source: str, banned_until: float, now: float) -> None:
        self.source = source
        self.banned_until = banned_until
        self.remaining_s = max(0.0, banned_until - now)
        super().__init__(
            f"source {source!r} banned for another {self.remaining_s:.0f}s "
            f"(banned_until={banned_until:.0f}); not re-attempting."
        )


@dataclass
class _SourceState:
    last_request_at: float = 0.0
    banned_until: float = 0.0

    @classmethod
    def from_dict(cls, d: Mapping[str, object]) -> _SourceState:
        return cls(
            last_request_at=float(d.get("last_request_at", 0.0) or 0.0),
            banned_until=float(d.get("banned_until", 0.0) or 0.0),
        )

    def to_dict(self) -> dict:
        return {
            "last_request_at": self.last_request_at,
            "banned_until": self.banned_until,
        }


@dataclass
class _AllState:
    """The whole file: a map of source-key -> per-source state."""

    sources: dict[str, _SourceState] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: Mapping[str, object]) -> _AllState:
        raw = d.get("sources") if isinstance(d, Mapping) else None
        sources: dict[str, _SourceState] = {}
        if isinstance(raw, Mapping):
            for key, val in raw.items():
                if isinstance(val, Mapping):
                    sources[str(key)] = _SourceState.from_dict(val)
        return cls(sources=sources)

    def to_dict(self) -> dict:
        return {"sources": {k: v.to_dict() for k, v in self.sources.items()}}


class SourceThrottle:
    """Process-wide per-source throttle backed by one JSON state file.

    Cross-process: the state file is re-read on every ``before_request`` /
    ``note_response`` so a second process (e.g. a re-run after a crash) sees
    the first's ``banned_until``. The read-modify-write is unlocked
    (last-writer-wins) — identical to ``ArxivThrottle``'s rationale: a single
    low-concurrency operator tool where a lost write costs at most one ban
    window, while a banned_until already in the future is only pushed further
    out or harmlessly re-set.

    ``now`` / ``sleep`` are injectable for deterministic CI.
    """

    def __init__(
        self,
        *,
        state_path: str | None = None,
        default_min_interval_s: float = DEFAULT_MIN_INTERVAL_S,
        min_interval_overrides: Mapping[str, float] | None = None,
        default_ban_backoff_s: float = DEFAULT_BAN_BACKOFF_S,
        now: Callable[[], float] = time.time,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._path = Path(state_path or default_state_path())
        self._default_min_interval = float(default_min_interval_s)
        self._overrides = dict(min_interval_overrides or SOURCE_MIN_INTERVAL_S)
        self._default_ban_backoff = float(default_ban_backoff_s)
        self._now = now
        self._sleep = sleep

    # -- min-interval lookup -------------------------------------------------

    def min_interval_for(self, source: str) -> float:
        """The configured min spacing for ``source`` (override or default)."""
        return float(self._overrides.get(source, self._default_min_interval))

    # -- state file I/O (atomic write; unlocked, last-writer-wins) -----------

    def _read_all(self) -> _AllState:
        try:
            raw = self._path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return _AllState()
        except OSError:
            # An unreadable state file must not silently disable the throttle.
            # Return empty so callers still space out from "now"; the next
            # before_request will record fresh timestamps.
            return _AllState()
        try:
            return _AllState.from_dict(json.loads(raw))
        except (json.JSONDecodeError, ValueError, TypeError):
            return _AllState()

    def _write_all(self, state: _AllState) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # Atomic-ish: tmp + replace so a crash mid-write cannot leave a
        # truncated file that reads as "never throttled, never banned".
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.write_text(json.dumps(state.to_dict()), encoding="utf-8")
        os.replace(tmp, self._path)

    def _source_state(self, all_state: _AllState, source: str) -> _SourceState:
        return all_state.sources.get(source, _SourceState())

    # -- public API ----------------------------------------------------------

    def is_banned(self, source: str) -> bool:
        return self._now() < self._source_state(self._read_all(), source).banned_until

    def banned_until(self, source: str) -> float:
        return self._source_state(self._read_all(), source).banned_until

    def before_request(self, source: str) -> None:
        """Block (or no-op) until it is safe to issue the next request for
        ``source``. Raises ``SourceBanned`` when a ban sentinel is active —
        the caller must not swallow it and retry.

        This is the call the live fetch paths make BEFORE every request.
        """
        all_state = self._read_all()
        state = self._source_state(all_state, source)
        now = self._now()
        if now < state.banned_until:
            raise SourceBanned(source, state.banned_until, now)

        elapsed = now - state.last_request_at
        min_interval = self.min_interval_for(source)
        if elapsed < min_interval:
            self._sleep(min_interval - elapsed)
            now = self._now()

        state.last_request_at = now
        all_state.sources[source] = state
        self._write_all(all_state)

    def note_response(
        self,
        source: str,
        status_code: int,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        """Record a request outcome for ``source``. On a 429/503 arm the
        ``banned_until`` sentinel; any other status is a no-op.

        ``Retry-After`` (integer seconds — the form arXiv and most servers
        emit) is honored when present and parseable, taking the LONGER of the
        header value and the conservative default so a tiny advertised window
        cannot under-cut the floor that protects the IP.
        """
        if status_code not in _BAN_STATUS:
            return
        backoff = self._default_ban_backoff
        if headers:
            retry_after = headers.get("Retry-After") or headers.get("retry-after")
            if retry_after:
                try:
                    backoff = max(backoff, float(int(str(retry_after).strip())))
                except (ValueError, TypeError):
                    pass
        all_state = self._read_all()
        state = self._source_state(all_state, source)
        state.banned_until = self._now() + backoff
        all_state.sources[source] = state
        self._write_all(all_state)

    def note_response_at(self, source: str, banned_until: float) -> None:
        """Arm ``source``'s ban sentinel at an EXPLICIT absolute expiry, taking
        the LATER of any existing ban and the new one so a mirror never shortens
        an active ban. Used to bridge a ban computed elsewhere (e.g. the
        dedicated ``ArxivThrottle``'s export-endpoint ban) into this shared file
        so the orchestrator's source rotation can see it — without re-deriving a
        default that could disagree with the source-of-truth expiry."""
        all_state = self._read_all()
        state = self._source_state(all_state, source)
        state.banned_until = max(state.banned_until, float(banned_until))
        all_state.sources[source] = state
        self._write_all(all_state)


# ---------------------------------------------------------------------------
# M3 — exponential backoff with jitter (transient-failure retry schedule).
# ---------------------------------------------------------------------------


def backoff_delays(
    *,
    base_s: float = DEFAULT_BACKOFF_BASE_S,
    max_s: float = DEFAULT_BACKOFF_MAX_S,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    jitter: Callable[[], float] = random.random,
) -> tuple[float, ...]:
    """The bounded exponential-backoff schedule for transient retries.

    Delay before retry ``i`` (0-indexed) is ``base * 2**i`` capped at
    ``max_s``, then multiplied by a jitter factor in ``[0.5, 1.0]`` to spread
    concurrent retries (decorrelation) without ever exceeding the deterministic
    ceiling. There are ``max_attempts - 1`` delays (no delay after the final
    attempt — it just fails).

    ``jitter`` is injectable: a test passes a constant (e.g. ``lambda: 1.0``)
    to assert the exact deterministic schedule, so the backoff is unit-tested
    rather than asserted only by "it slept some." With the default
    ``random.random`` it returns a value in [0, 1); we map it to [0.5, 1.0] so
    jitter only ever REDUCES the capped delay, never extends past ``max_s``.
    """
    delays: list[float] = []
    for i in range(max(0, max_attempts - 1)):
        capped = min(base_s * (2 ** i), max_s)
        factor = 0.5 + 0.5 * jitter()  # map [0,1) -> [0.5, 1.0)
        delays.append(capped * factor)
    return tuple(delays)


# ---------------------------------------------------------------------------
# M3 — source rotation on hard ban.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RotationDecision:
    """The outcome of picking the next source to try from a configured set.

    ``next_source`` is the first non-banned source in priority order, or
    ``None`` when EVERY configured source is banned. ``skipped`` records the
    banned sources passed over (source + its banned_until) so the decision is
    observable. ``soonest_banned_until`` is the earliest ban expiry across all
    configured sources when all are banned (0.0 otherwise) — so a halt records
    when a resume could first succeed.
    """

    next_source: str | None
    skipped: tuple[tuple[str, float], ...]
    soonest_banned_until: float = 0.0

    @property
    def all_banned(self) -> bool:
        return self.next_source is None

    def render(self) -> str:
        parts: list[str] = []
        for src, until in self.skipped:
            parts.append(f"skip {src} (banned_until={until:.0f})")
        if self.next_source is not None:
            parts.append(f"-> try {self.next_source}")
        else:
            parts.append(
                f"ALL sources banned; soonest resume at "
                f"{self.soonest_banned_until:.0f}"
            )
        return "; ".join(parts)


def next_available_source(
    throttle: SourceThrottle, sources: Sequence[str]
) -> RotationDecision:
    """Pick the next non-banned source from ``sources``, in priority order.

    Walks ``sources`` left-to-right; the first whose ban sentinel is NOT in
    the future is chosen, with the banned ones it passed over recorded in
    ``skipped``. When all are banned, ``next_source`` is None and
    ``soonest_banned_until`` carries the earliest expiry so the orchestrator
    can halt cleanly with an informed resume time (M3 acceptance criterion).
    """
    skipped: list[tuple[str, float]] = []
    expiries: list[float] = []
    for src in sources:
        until = throttle.banned_until(src)
        if not throttle.is_banned(src):
            return RotationDecision(next_source=src, skipped=tuple(skipped))
        skipped.append((src, until))
        expiries.append(until)
    return RotationDecision(
        next_source=None,
        skipped=tuple(skipped),
        soonest_banned_until=min(expiries) if expiries else 0.0,
    )
