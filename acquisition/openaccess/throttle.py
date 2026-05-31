"""Conservative request spacing + retry-with-backoff for OA sources.

In-process spacing + bounded retry-with-backoff is the per-request shape. The
2026-05-29 prod run showed that in-process-only state is NOT enough on its own:
an OA aggregator that 429/503s and a process re-run that re-hits it has no ban
knowledge. SPR-03 closes that by letting an ``OAThrottle`` carry the SHARED
persistent ``substrate.source_throttle.SourceThrottle`` (a cross-process JSON
sentinel under ``~/.antiek/``) keyed to a source string: ``before_request`` is
consulted before each request (raising ``SourceBanned`` while banned, which the
orchestrator catches to rotate) and 429/503 responses arm the sentinel via
``note_response``. The persistent throttle is OPTIONAL — when ``persistent`` is
None the OAThrottle behaves exactly as before (the polite-pool spacing alone),
so the recorded-response adapter tests need no sentinel.

Time + sleep are injectable so CI is deterministic and never actually sleeps.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Optional, TypeVar

import httpx

from substrate.source_throttle import SourceThrottle

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
    """In-process spacing + bounded retry-with-backoff, optionally fronted by
    the shared cross-process ``SourceThrottle`` ban sentinel.

    ``wait()`` consults the persistent throttle's ``before_request(source)``
    (raising ``SourceBanned`` while the source is banned), then blocks until
    ``min_spacing_s`` has elapsed since the previous in-process call.
    ``run_with_retry(fn)`` calls ``fn`` (which should issue one HTTP request),
    retrying on transient HTTP/connection errors with exponential backoff,
    re-raising the last error once the budget is exhausted — and feeding a
    429/503 status to the persistent sentinel via ``note_response`` so the next
    process honors the ban instead of re-hitting the endpoint.

    ``persistent`` + ``source`` are OPTIONAL: when ``persistent`` is None the
    sentinel machinery is inert and OAThrottle is the pre-SPR-03 in-process
    throttle (so the recorded-response adapter tests are unchanged).
    """

    min_spacing_s: float = DEFAULT_MIN_SPACING_S
    max_retries: int = DEFAULT_MAX_RETRIES
    backoff_base_s: float = DEFAULT_BACKOFF_BASE_S
    now: Callable[[], float] = time.monotonic
    sleep: Callable[[float], None] = time.sleep
    persistent: Optional[SourceThrottle] = None
    source: str = "open_access"
    _last_request_at: float = 0.0

    def wait(self) -> None:
        if self.persistent is not None:
            # Cross-process gate: raises SourceBanned while banned (the live
            # ban check before every outbound request) and enforces the
            # persisted per-source min-interval across process restarts.
            self.persistent.before_request(self.source)
        elapsed = self.now() - self._last_request_at
        if elapsed < self.min_spacing_s:
            self.sleep(self.min_spacing_s - elapsed)
        self._last_request_at = self.now()

    def _note_status(self, status_code: int, headers: Optional[dict]) -> None:
        if self.persistent is not None:
            self.persistent.note_response(self.source, status_code, headers)

    def run_with_retry(self, fn: Callable[[], T]) -> T:
        """Run ``fn`` with spacing + retry. ``fn`` should perform one request
        and raise ``httpx.HTTPStatusError`` / ``httpx.TransportError`` on
        failure. Transient errors retry with exponential backoff; permanent
        ones (e.g. a 404) re-raise immediately so the caller can record a
        per-item miss without burning the retry budget. A 429/503 also arms
        the persistent ban sentinel (when configured)."""
        last_exc: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            self.wait()
            try:
                return fn()
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                if status not in _TRANSIENT_STATUS:
                    raise
                # A 429/503 is a "stop hitting me" — persist it so a re-run
                # honors the ban instead of digging the hole deeper.
                self._note_status(status, dict(exc.response.headers))
                last_exc = exc
            except httpx.TransportError as exc:
                # Connection reset / timeout / DNS — transient by nature.
                last_exc = exc
            if attempt < self.max_retries:
                self.sleep(self.backoff_base_s * (2**attempt))
        assert last_exc is not None
        raise last_exc
