"""Cross-process throttle for the ingestion fetcher (M3).

Replaces the legacy in-process throttle (which didn't survive worker
restart — see memory ``project_researchmaxx_arxiv``, 2026-05-17) with
a Redis-backed sliding window.

Design:

- Per-domain key in Redis, ``ingest:throttle:{domain}``, holding the
  ISO-8601 timestamp of the next-allowed request as a string.
- ``acquire(domain)`` reads the key, computes the wait, ``time.sleep``s
  for the wait, then atomically (Redis SET) writes a new
  next-allowed = now + window. Atomic enough: in the worst-case race
  two workers both see "now-allowed" and both fire at once, then both
  write the same next-allowed — Redis serializes the SETs, so the
  next round honors the throttle. The Researchmaxx incident was about
  *no* throttle across processes, not about strict 100% fairness;
  this design fixes the failure mode without the complexity of a Lua
  CAS script.
- Per-domain windows: ``arxiv.org`` / ``export.arxiv.org`` → 3.0s
  (matches arXiv's published ToS — see INGESTION_NOTES.md). Others
  default to 1.0s.

If Redis is unreachable, the throttle degrades to *no throttle* and
emits a warning to stderr. Combined with the ``banned_until`` table
(``fetcher.py`` second gate), this keeps ingestion usable in dev
without Redis while still preventing 429-induced bans in production.
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse


# Throttle windows in seconds, per host. arxiv.org is tight because
# arXiv ToS asks for ≤ 1 query / 3s; everyone else gets a conservative
# 1s ceiling. Tune via env var ``ANTIEK_INGEST_THROTTLE_OVERRIDES``
# (JSON: ``{"example.com": 0.5}``).
DEFAULT_WINDOW_S = 1.0
HOST_WINDOWS_S: dict[str, float] = {
    "arxiv.org": 3.0,
    "export.arxiv.org": 3.0,
    "www.arxiv.org": 3.0,
}

# Redis URL via env; ``redis://localhost:6379/0`` is the dev default.
# ``ANTIEK_INGEST_REDIS_URL`` lets ops point at a different instance
# or DB number without touching code.
_REDIS_URL_ENV = "ANTIEK_INGEST_REDIS_URL"
_DEFAULT_REDIS_URL = "redis://localhost:6379/0"

_THROTTLE_KEY_PREFIX = "ingest:throttle:"


@dataclass(frozen=True)
class ThrottleResult:
    """What ``acquire`` returns. ``waited_s`` is how long we blocked
    before allowing the caller through. ``backend`` is ``"redis"``
    when the throttle ran against a live Redis, ``"noop"`` when Redis
    is unreachable and we degraded."""

    domain: str
    waited_s: float
    backend: str


def _host_of(url: str) -> str:
    """Bare host (no port) for use as the throttle key."""
    try:
        netloc = urlparse(url).netloc
    except ValueError:
        return ""
    host = netloc.split("@")[-1].split(":")[0]
    return host.lower()


def _window_for(domain: str) -> float:
    return HOST_WINDOWS_S.get(domain, DEFAULT_WINDOW_S)


# Module-level Redis client. We connect lazily and reuse — opening a
# new client per fetch would add ~ms of latency for no benefit. The
# client is None until first use; ``_get_redis`` connects and caches.
_REDIS_CLIENT: Optional[object] = None
_REDIS_DISABLED = False


def _get_redis(*, url: Optional[str] = None) -> Optional[object]:
    """Return a connected Redis client, or None if Redis is
    unreachable. Cached at module scope."""
    global _REDIS_CLIENT, _REDIS_DISABLED
    if _REDIS_CLIENT is not None:
        return _REDIS_CLIENT
    if _REDIS_DISABLED:
        return None
    try:
        import redis  # type: ignore[import-untyped]
    except ImportError:
        # Redis-py not installed → degrade. INGESTION_NOTES.md
        # documents this: throttle is best-effort, banned_until is the
        # second gate.
        _REDIS_DISABLED = True
        print(
            "services.ingestion.throttle: redis package not installed; "
            "throttle disabled. Fetcher still honors banned_until.",
            file=sys.stderr,
        )
        return None

    resolved_url = url or os.environ.get(_REDIS_URL_ENV, _DEFAULT_REDIS_URL)
    try:
        client = redis.Redis.from_url(resolved_url, decode_responses=True)
        client.ping()
    except Exception as exc:  # noqa: BLE001 — any connection failure degrades
        _REDIS_DISABLED = True
        print(
            f"services.ingestion.throttle: Redis at {resolved_url!r} "
            f"unreachable ({exc!r}); throttle disabled.",
            file=sys.stderr,
        )
        return None
    _REDIS_CLIENT = client
    return client


def reset_for_tests() -> None:
    """Reset module-level state. Tests call this in fixtures to
    inject a fresh fakeredis instance per test without leaking
    connections between tests."""
    global _REDIS_CLIENT, _REDIS_DISABLED
    _REDIS_CLIENT = None
    _REDIS_DISABLED = False


def set_client_for_tests(client: Optional[object]) -> None:
    """Inject a pre-built Redis client (fakeredis in tests)."""
    global _REDIS_CLIENT, _REDIS_DISABLED
    _REDIS_CLIENT = client
    _REDIS_DISABLED = client is None


def acquire(
    url: str,
    *,
    sleeper=time.sleep,  # injectable so tests don't actually block
    clock=time.monotonic,  # injectable so tests can advance time
) -> ThrottleResult:
    """Block until the per-domain throttle window allows the next
    request. Returns the wait time + which backend ran.

    The sliding-window algorithm:

      1. Read ``next_allowed`` from Redis. None / empty → window
         starts now (no wait).
      2. ``wait = max(0, next_allowed - now)``. Sleep that long.
      3. Write ``next_allowed = now + window`` (after the sleep, so
         the time we slept counts against the next caller's wait).

    Survives worker restart: the key persists in Redis after the
    worker dies; the next process to call acquire honors it.
    """
    domain = _host_of(url)
    if not domain:
        # Malformed URL — don't pretend to throttle; the fetcher will
        # raise on the actual GET.
        return ThrottleResult(domain="", waited_s=0.0, backend="noop")

    redis_client = _get_redis()
    if redis_client is None:
        return ThrottleResult(domain=domain, waited_s=0.0, backend="noop")

    window_s = _window_for(domain)
    key = _THROTTLE_KEY_PREFIX + domain

    now = clock()
    waited_s = 0.0
    try:
        raw = redis_client.get(key)  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        # Redis disappeared mid-call — degrade.
        return ThrottleResult(domain=domain, waited_s=0.0, backend="noop")

    if raw:
        try:
            next_allowed = float(raw)
        except (ValueError, TypeError):
            next_allowed = now
        wait = max(0.0, next_allowed - now)
        if wait > 0:
            sleeper(wait)
            waited_s = wait
            now = clock()

    new_next_allowed = now + window_s
    try:
        # Set with a TTL slightly longer than the window so abandoned
        # keys don't linger forever. 24h TTL is much longer than any
        # plausible window — the key is a "next allowed" pointer, not
        # a counter.
        redis_client.set(  # type: ignore[attr-defined]
            key, str(new_next_allowed), ex=24 * 60 * 60,
        )
    except Exception:  # noqa: BLE001
        # If we can't write, the next caller will compute a wait of 0
        # but that's fine — throttle is best-effort, banned_until is
        # the safety net.
        pass

    return ThrottleResult(domain=domain, waited_s=waited_s, backend="redis")
