"""Conservative request spacing + retry-with-backoff for OA sources.

Deliberately SIMPLER than ``acquisition.arxiv.throttle``: OA aggregators
(OpenAlex / Unpaywall / PMC / DOAJ) do not have arXiv's documented
IP-ban-on-burst failure history, so we do NOT carry the cross-process
ban-sentinel machinery. The polite-pool convention (a ``mailto`` query param,
handled by each adapter) plus conservative in-process spacing plus
retry-with-backoff on transient (5xx / connection) errors is the right size.

Time + sleep are injectable so CI is deterministic and never actually sleeps.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Optional, TypeVar

import httpx

# OpenAlex's polite pool serves up to 10 req/s; the others are comparable. We
# space well under that — a research-batch tool is not latency-sensitive and a
# courteous floor keeps us off any rate-limiter's radar.
DEFAULT_MIN_SPACING_S = 0.2

# Retry budget for transient failures. Bounded so a genuinely-down endpoint
# fails the item rather than hanging the batch.
DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_BASE_S = 0.5

# Polite-pool contact. Adapters append this as ``mailto=`` so the source can
# reach us before throttling rather than silently rate-limiting.
POLITE_POOL_MAILTO = "antiek-acquisition@antiek.ai"

T = TypeVar("T")

# Status codes worth retrying: server-side transients. 4xx (except 429) are
# client errors a retry won't fix.
_TRANSIENT_STATUS = frozenset({429, 500, 502, 503, 504})


@dataclass
class OAThrottle:
    """In-process spacing + bounded retry-with-backoff.

    ``wait()`` blocks until ``min_spacing_s`` has elapsed since the previous
    call. ``run_with_retry(fn)`` calls ``fn`` (which should issue one HTTP
    request), retrying on transient HTTP/connection errors with exponential
    backoff, re-raising the last error once the budget is exhausted.
    """

    min_spacing_s: float = DEFAULT_MIN_SPACING_S
    max_retries: int = DEFAULT_MAX_RETRIES
    backoff_base_s: float = DEFAULT_BACKOFF_BASE_S
    now: Callable[[], float] = time.monotonic
    sleep: Callable[[float], None] = time.sleep
    _last_request_at: float = 0.0

    def wait(self) -> None:
        elapsed = self.now() - self._last_request_at
        if elapsed < self.min_spacing_s:
            self.sleep(self.min_spacing_s - elapsed)
        self._last_request_at = self.now()

    def run_with_retry(self, fn: Callable[[], T]) -> T:
        """Run ``fn`` with spacing + retry. ``fn`` should perform one request
        and raise ``httpx.HTTPStatusError`` / ``httpx.TransportError`` on
        failure. Transient errors retry with exponential backoff; permanent
        ones (e.g. a 404) re-raise immediately so the caller can record a
        per-item miss without burning the retry budget."""
        last_exc: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            self.wait()
            try:
                return fn()
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code not in _TRANSIENT_STATUS:
                    raise
                last_exc = exc
            except httpx.TransportError as exc:
                # Connection reset / timeout / DNS — transient by nature.
                last_exc = exc
            if attempt < self.max_retries:
                self.sleep(self.backoff_base_s * (2**attempt))
        assert last_exc is not None
        raise last_exc
