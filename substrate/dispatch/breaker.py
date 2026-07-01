"""Per-process, per-provider circuit breaker for the dispatch router (nygard SPR-04).

State machine (per provider name)::

    closed --(N infra failures)--> open --(cooldown elapsed)--> half_open
      ^                                                            |
      |------------------(probe succeeds)--------------------------|
                          (probe fails) --> open

**In-memory only** — no DB, no second writer (§16 / I-WRITER). The router consults
``is_open(provider)`` before calling a provider and, when open, SKIPS it, reusing
the exact "skip + fall through to the next tier" mechanism the unregistered/no-key
path already uses (``router.dispatch`` converts an unregistered provider into a
fall-through). So an open provider degrades to the existing tier-fallback chain,
fast, with no new control flow and no retry (I-NORETRY — the breaker decides
*whether* to call, it never re-calls).

Why it counts what it counts (the classifier question):
The breaker is hooked at the provider ``.call`` site. The router resolves config
conditions BEFORE the call — an unregistered / no-API-key provider raises
``KeyError`` at ``get_provider`` and never reaches ``.call``. So every failure the
breaker observes at ``.call`` is a genuine provider-health failure (a
``ProviderError``: HTTP 5xx / timeout / network / bad body). That is precisely the
"infra fault, not an expected degradation" this sprint wants to trip on. Note this
is a DELIBERATE divergence from ``substrate.errors.is_expected_degradation``: that
helper classifies a ``ProviderError`` as an *expected* degradation because at the
RETRIEVER seam any dispatch failure degrades benignly to a no-provider fallback —
the opposite lens from this seam, where a provider's own call failing is the exact
signal to open. The router's pre-call config filtering, not the helper, is what
keeps expected conditions from tripping the breaker here.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from enum import Enum

__all__ = [
    "BreakerState",
    "CircuitBreaker",
    "default_breaker",
    "DEFAULT_FAILURE_THRESHOLD",
    "DEFAULT_COOLDOWN_S",
]

# Defensible defaults; the operator tunes after first-light (not perf-guessed).
# 5 consecutive infra failures before shedding is a common breaker default that
# tolerates a transient blip while still shedding a genuinely-down provider fast;
# a 30s cooldown before a single probe matches typical upstream recovery windows.
DEFAULT_FAILURE_THRESHOLD = 5
DEFAULT_COOLDOWN_S = 30.0


class BreakerState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Thread-safe, per-provider circuit breaker. One instance per process holds
    the state for every provider name it has seen; state is keyed by provider.

    ``clock`` is injectable (defaults to ``time.monotonic``) so tests drive the
    cooldown deterministically rather than sleeping.
    """

    def __init__(
        self,
        *,
        failure_threshold: int = DEFAULT_FAILURE_THRESHOLD,
        cooldown_s: float = DEFAULT_COOLDOWN_S,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be >= 1")
        if cooldown_s < 0:
            raise ValueError("cooldown_s must be >= 0")
        self._threshold = failure_threshold
        self._cooldown = cooldown_s
        self._clock = clock
        self._lock = threading.Lock()
        self._failures: dict[str, int] = {}
        self._state: dict[str, BreakerState] = {}
        self._opened_at: dict[str, float] = {}

    def _state_locked(self, provider: str) -> BreakerState:
        """Current state, applying the OPEN->HALF_OPEN cooldown transition.
        Caller must hold the lock."""
        st = self._state.get(provider, BreakerState.CLOSED)
        if st is BreakerState.OPEN:
            opened = self._opened_at.get(provider, 0.0)
            if self._clock() - opened >= self._cooldown:
                # Cooldown elapsed: allow a single probe.
                st = BreakerState.HALF_OPEN
                self._state[provider] = st
        return st

    def state(self, provider: str) -> BreakerState:
        """Observable current state (applies the cooldown transition)."""
        with self._lock:
            return self._state_locked(provider)

    def is_open(self, provider: str) -> bool:
        """True when the router should SKIP this provider (fall through to the
        next tier). OPEN within its cooldown returns True; once the cooldown has
        elapsed the breaker moves to HALF_OPEN and returns False so exactly the
        recovery probe is allowed. CLOSED / HALF_OPEN return False."""
        with self._lock:
            return self._state_locked(provider) is BreakerState.OPEN

    def record_success(self, provider: str) -> None:
        """A successful call closes the breaker and clears the failure count."""
        with self._lock:
            self._state[provider] = BreakerState.CLOSED
            self._failures[provider] = 0
            self._opened_at.pop(provider, None)

    def record_failure(self, provider: str) -> None:
        """An infra failure at the provider's call. In CLOSED, increments toward
        the threshold and opens on reaching it. A failure while HALF_OPEN (the
        probe failed) re-opens immediately and restarts the cooldown."""
        with self._lock:
            st = self._state_locked(provider)
            if st is BreakerState.HALF_OPEN:
                self._state[provider] = BreakerState.OPEN
                self._opened_at[provider] = self._clock()
                self._failures[provider] = self._threshold
                return
            n = self._failures.get(provider, 0) + 1
            self._failures[provider] = n
            if n >= self._threshold:
                self._state[provider] = BreakerState.OPEN
                self._opened_at[provider] = self._clock()

    def failure_count(self, provider: str) -> int:
        with self._lock:
            return self._failures.get(provider, 0)

    def snapshot(self, provider: str) -> dict[str, object]:
        """Read-only view for /health or logging (no state transition)."""
        with self._lock:
            return {
                "provider": provider,
                "state": self._state.get(provider, BreakerState.CLOSED).value,
                "failures": self._failures.get(provider, 0),
                "threshold": self._threshold,
                "cooldown_s": self._cooldown,
            }

    def reset(self) -> None:
        """Clear all state — for tests and a clean process boot."""
        with self._lock:
            self._failures.clear()
            self._state.clear()
            self._opened_at.clear()


# The process-wide breaker the router consults. Tuned by construction; callers
# (and tests) may pass their own CircuitBreaker where isolation is needed.
default_breaker = CircuitBreaker()
