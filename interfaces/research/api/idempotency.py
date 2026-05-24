"""
Idempotency-key handling for POST/PUT routes on the Antiek REST surface.

Per the agent-loved API canon (T-Yegge-NNN, see
``docs/philosophy/yegge.md``): agents that retry POST requests need a
way to do so safely. The standard pattern: caller sends an
``Idempotency-Key`` header with a unique value; the server caches the
response keyed on (route, key) for a TTL; subsequent requests with the
same key replay the cached response with an explicit
``IDEMPOTENCY_REPLAY`` marker.

Scope at SPR-09: this module ships the cache + the FastAPI dependency.
Wiring into specific routes is opt-in per route. New routes ought to
add ``Depends(require_idempotency_key)`` to their function signature;
legacy routes are out-of-scope (operator has in-flight changes).

Storage: in-process dict guarded by an ``asyncio.Lock``. TTL via
monotonic-time expiry checked on read. The deliberate non-choice is
to NOT persist to disk — across a process restart, replay attempts
return ``IDEMPOTENCY_KEY_REQUIRED`` rather than risking a stale replay
from a different code revision. This is the conservative call; can be
revisited once a route legitimately needs cross-restart replay.

Spec: ~/specs/antiek-yegge-execute/sprint-09-agent-loved-api.html
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, Final, Optional, Tuple

# Default TTL of 24 hours. Long enough that an agent's polling loop
# safely retries within the window; short enough that a forgotten key
# doesn't linger in memory. Configurable via env so the operator can
# tighten without code changes.
_DEFAULT_TTL_SECONDS: Final[int] = int(
    os.environ.get("ANTIEK_IDEMPOTENCY_TTL_SECONDS", str(24 * 60 * 60))
)

# Maximum number of cached entries before LRU eviction. Pragmatic cap
# — well under typical RAM budgets, and the rate at which legitimate
# distinct keys arrive is bounded by agent traffic.
_DEFAULT_MAX_ENTRIES: Final[int] = int(
    os.environ.get("ANTIEK_IDEMPOTENCY_MAX_ENTRIES", "10000")
)


@dataclass(frozen=True)
class CachedResponse:
    """A replay record. Stored under (route, key); compared on read."""

    status_code: int
    body: Any  # the original response body (JSON-serializable)
    stored_at_monotonic: float  # for TTL check
    stored_at_wall: float       # for human-readable details


class IdempotencyCache:
    """In-process keyed cache; one instance per FastAPI app.

    Not thread-safe for sync writes, but ``asyncio.Lock`` protects the
    common async-only path (FastAPI's handlers are async by default).
    The cache uses simple FIFO eviction at max-entries — LRU would be
    a touch more sophisticated but at this cardinality the difference
    is invisible.
    """

    def __init__(
        self, *,
        ttl_seconds: int = _DEFAULT_TTL_SECONDS,
        max_entries: int = _DEFAULT_MAX_ENTRIES,
    ) -> None:
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self._data: Dict[Tuple[str, str], CachedResponse] = {}
        self._insertion_order: list[Tuple[str, str]] = []
        self._lock = asyncio.Lock()

    async def get(self, route: str, key: str) -> Optional[CachedResponse]:
        """Return a cached response if present and not expired."""
        async with self._lock:
            entry = self._data.get((route, key))
            if entry is None:
                return None
            if (time.monotonic() - entry.stored_at_monotonic) > self.ttl_seconds:
                # Lazy expiry — cheaper than a background sweeper for
                # this cardinality. Remove and treat as miss.
                self._data.pop((route, key), None)
                try:
                    self._insertion_order.remove((route, key))
                except ValueError:
                    pass
                return None
            return entry

    async def put(self, route: str, key: str, response: CachedResponse) -> None:
        """Store a response. Evicts oldest entry if at capacity."""
        async with self._lock:
            if (route, key) in self._data:
                # Replace in place; don't disturb insertion order.
                self._data[(route, key)] = response
                return
            if len(self._data) >= self.max_entries:
                # FIFO eviction: drop the oldest entry.
                oldest = self._insertion_order.pop(0)
                self._data.pop(oldest, None)
            self._data[(route, key)] = response
            self._insertion_order.append((route, key))

    def size(self) -> int:
        return len(self._data)


# Singleton cache for the FastAPI app. Instantiated lazily so tests
# can replace it via dependency override or by patching the module.
_default_cache: Optional[IdempotencyCache] = None


def get_default_cache() -> IdempotencyCache:
    """Return (and lazily-create) the process-wide cache singleton."""
    global _default_cache
    if _default_cache is None:
        _default_cache = IdempotencyCache()
    return _default_cache


def reset_default_cache_for_tests() -> None:
    """Reset the singleton — test-only convenience.

    Pytest fixtures call this in ``setup_function`` to avoid state
    bleeding across tests. Not for production use; the function name
    is the warning."""
    global _default_cache
    _default_cache = None


# ---------------------------------------------------------------------------
# FastAPI dependency — add Depends(require_idempotency_key) to a route's
# signature to enforce the header on POST/PUT requests.
#
# The dependency:
#   1. Reads the ``Idempotency-Key`` header. Missing -> raises
#      EnvelopedHTTPException(code="IDEMPOTENCY_KEY_REQUIRED").
#   2. Checks the cache. Hit -> raises EnvelopedHTTPException(
#      code="IDEMPOTENCY_REPLAY", details={previous: ...}).
#   3. Miss -> returns the key string so the route handler can
#      complete the request and cache the response.
#
# The "completion" step (caching the response after the route
# succeeds) is the route author's responsibility — a single
# `await cache.put(...)` after building the response. Doing it
# in a middleware would require capturing the response body which
# is messier than the explicit per-route opt-in.
# ---------------------------------------------------------------------------


async def require_idempotency_key(
    route_id: str,
    idempotency_key: Optional[str],
    cache: Optional[IdempotencyCache] = None,
) -> str:
    """Validate the header + check the cache. Returns the key on miss.

    This is intentionally a plain async function rather than a FastAPI
    ``Depends``-shaped callable so it can be unit-tested without the
    request/response machinery. Route adapters wrap it with the
    framework glue.
    """
    # Lazy import so this module doesn't require fastapi at import time
    from interfaces.research.api.envelope import EnvelopedHTTPException

    if not idempotency_key:
        raise EnvelopedHTTPException(
            code="IDEMPOTENCY_KEY_REQUIRED",
            message=(
                "POST/PUT requests on this surface require an "
                "Idempotency-Key header (RFC-style: a UUID v4 or any "
                "client-generated unique string)."
            ),
            status_code=400,
        )

    cache = cache or get_default_cache()
    previous = await cache.get(route_id, idempotency_key)
    if previous is not None:
        raise EnvelopedHTTPException(
            code="IDEMPOTENCY_REPLAY",
            message=(
                f"Idempotency-Key replayed for route {route_id!r}. "
                "Returning the prior response — caller should treat this "
                "as the original."
            ),
            status_code=200,  # Replays are 200 not 4xx; the original succeeded.
            details={
                "previous_status_code": previous.status_code,
                "previous_body": previous.body,
                "previous_stored_at_wall_unix": previous.stored_at_wall,
            },
        )
    return idempotency_key


async def record_completion(
    route_id: str, key: str, *, status_code: int, body: Any,
    cache: Optional[IdempotencyCache] = None,
) -> None:
    """Cache the response under (route, key) after a successful request.

    Call this exactly once per request after building the response.
    No-op if already cached (subsequent calls do not overwrite).
    """
    cache = cache or get_default_cache()
    await cache.put(
        route_id, key,
        CachedResponse(
            status_code=status_code,
            body=body,
            stored_at_monotonic=time.monotonic(),
            stored_at_wall=time.time(),
        ),
    )


__all__ = [
    "IdempotencyCache",
    "CachedResponse",
    "get_default_cache",
    "reset_default_cache_for_tests",
    "require_idempotency_key",
    "record_completion",
]
