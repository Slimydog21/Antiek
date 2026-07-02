"""Typed Parallel Search HTTP client.

Wraps ``POST https://api.parallel.ai/v1/search``. httpx-based so tests
inject a ``MockTransport`` with no network. API key env: ``PARALLEL_API_KEY``.

This client returns typed result records ONLY. It does NOT emit events,
does NOT consult the legal gate, does NOT touch the graph. Higher-level
concerns live in ``adapter.py``.

Retry policy: 429 + 5xx retried with exponential backoff up to 3 attempts.
4xx other than 429 raises immediately.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal, cast

import httpx

DEFAULT_BASE_URL = "https://api.parallel.ai"
DEFAULT_USER_AGENT = "Antiek/0.1 (acquisition.search.parallel)"
DEFAULT_TIMEOUT_S = 45.0
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
_MAX_RETRIES = 3

# Back-of-envelope per-call estimate (USD). Invoiced Parallel usage is authoritative.
COST_PER_SEARCH_USD = 0.01

ParallelSearchMode = Literal["turbo", "basic", "advanced"]


class ParallelClientError(RuntimeError):
    """Parallel returned a non-retryable error or exhausted retries."""

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        url: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.url = url


@dataclass(frozen=True)
class ParallelSearchResult:
    url: str
    title: str | None
    published_date: str | None
    text_snippet_preview: str | None
    provider_response_id: str | None
    cost_usd_estimate: float


@dataclass
class ParallelSearchResponse:
    results: list[ParallelSearchResult] = field(default_factory=list)
    search_id: str | None = None
    session_id: str | None = None


def _resolve_api_key(api_key: str | None) -> str:
    if api_key:
        return api_key
    v = os.environ.get("PARALLEL_API_KEY")
    if not v:
        raise ParallelClientError(
            "PARALLEL_API_KEY not set. Configure the env var or pass api_key= "
            "explicitly. Do NOT alias to another service's key."
        )
    return v


def _resolve_base_url(base_url: str | None) -> str:
    if base_url:
        return base_url.rstrip("/")
    return os.environ.get("PARALLEL_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


class ParallelClient:
    """Typed Parallel Search client."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        self._api_key = _resolve_api_key(api_key)
        self._base_url = _resolve_base_url(base_url)
        self._timeout_s = timeout_s
        self._client = client
        self._sleep: Callable[[float], None] = sleep or time.sleep

    def search(
        self,
        *,
        objective: str,
        search_queries: list[str],
        max_results: int = 10,
        mode: ParallelSearchMode = "basic",
        session_id: str | None = None,
    ) -> ParallelSearchResponse:
        if not search_queries:
            raise ParallelClientError("search_queries must be non-empty")
        cleaned = [q.strip() for q in search_queries if q.strip()]
        if not cleaned:
            raise ParallelClientError("search_queries must contain at least one non-empty query")
        if max_results < 1 or max_results > 50:
            raise ParallelClientError("max_results must be 1..50")

        body: dict[str, Any] = {
            "objective": objective.strip() or None,
            "search_queries": cleaned,
            "mode": mode,
            "advanced_settings": {"max_results": max_results},
        }
        if session_id:
            body["session_id"] = session_id

        raw = self._post("/v1/search", body)
        return self._parse_search_response(raw, per_call_cost=COST_PER_SEARCH_USD)

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        headers = {
            "User-Agent": DEFAULT_USER_AGENT,
            "x-api-key": self._api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        owns_client = self._client is None
        client = self._client or httpx.Client()
        try:
            attempt = 0
            while True:
                attempt += 1
                try:
                    r = client.post(
                        url, json=body, headers=headers, timeout=self._timeout_s
                    )
                except httpx.HTTPError as e:
                    if attempt < _MAX_RETRIES:
                        self._sleep(self._backoff_seconds(attempt))
                        continue
                    raise ParallelClientError(
                        f"transport error: {e}", status=None, url=url
                    ) from e

                if r.status_code in _RETRYABLE_STATUS and attempt < _MAX_RETRIES:
                    delay = self._retry_after_seconds(r) or self._backoff_seconds(attempt)
                    self._sleep(min(delay, 30.0))
                    continue

                if r.status_code >= 400:
                    raise ParallelClientError(
                        f"parallel returned {r.status_code}: {r.text[:200]}",
                        status=r.status_code,
                        url=url,
                    )

                try:
                    return cast(dict[str, Any], r.json())
                except ValueError as e:
                    raise ParallelClientError(
                        f"non-json body from parallel: {e}", status=r.status_code, url=url
                    ) from e
        finally:
            if owns_client:
                client.close()

    @staticmethod
    def _backoff_seconds(attempt: int) -> float:
        return float(2 ** (attempt - 1))

    @staticmethod
    def _retry_after_seconds(r: httpx.Response) -> float | None:
        v = r.headers.get("retry-after")
        if not v:
            return None
        try:
            return float(v)
        except ValueError:
            return None

    @staticmethod
    def _parse_search_response(
        raw: dict[str, Any], *, per_call_cost: float
    ) -> ParallelSearchResponse:
        search_id = raw.get("search_id")
        session_id = raw.get("session_id")
        results_raw = raw.get("results") or []
        results: list[ParallelSearchResult] = []
        per_result_cost = (
            per_call_cost / len(results_raw) if results_raw else per_call_cost
        )
        for r in results_raw:
            excerpts = r.get("excerpts") or []
            snippet = None
            if excerpts:
                snippet = excerpts[0] if isinstance(excerpts[0], str) else None
                if isinstance(snippet, str) and len(snippet) > 300:
                    snippet = snippet[:300]
            results.append(
                ParallelSearchResult(
                    url=str(r.get("url", "")).strip(),
                    title=r.get("title"),
                    published_date=r.get("publish_date"),
                    text_snippet_preview=snippet,
                    provider_response_id=search_id,
                    cost_usd_estimate=per_result_cost,
                )
            )
        return ParallelSearchResponse(
            results=results,
            search_id=search_id,
            session_id=session_id,
        )