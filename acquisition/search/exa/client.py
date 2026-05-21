"""Typed Exa HTTP client.

Wraps the `POST https://api.exa.ai/search` endpoint (and, optionally,
`/findSimilar`). httpx-based so tests inject a `MockTransport` with
no network. Honors a configurable base URL via `EXA_BASE_URL` for
staging.

This client returns typed result records ONLY. It does NOT emit
events, does NOT consult the legal gate, does NOT touch the graph.
Higher-level concerns live in `adapter.py`.

Spec: `docs/integration_exa_browserbase.md` §6.4. API key env:
`EXA_API_KEY`. Never aliased to other services' keys (silent
misrouting is worse than loud failure).

Retry policy: 429 + 5xx retried with exponential backoff up to 3
attempts. 4xx other than 429 raises immediately (configuration
error).

Pricing notes (2026-Q1, verify quarterly): roughly $5/1k searches,
$5/1k contents pages, $1/1k findSimilar calls. The per-call
`cost_usd_estimate` recorded on each result is a back-of-envelope
estimate — Exa's invoiced cost is authoritative.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Iterable, List, Literal, Optional

import httpx

DEFAULT_BASE_URL = "https://api.exa.ai"
DEFAULT_USER_AGENT = "Antiek/0.1 (acquisition.search.exa)"
DEFAULT_TIMEOUT_S = 30.0  # Exa's crawl-on-demand path is slow; URL-fetch timeout is 20s for comparison.
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
_MAX_RETRIES = 3

# Per-call cost estimates (USD). $5/1k = $0.005/call.
COST_PER_SEARCH_USD = 0.005
COST_PER_FIND_SIMILAR_USD = 0.001

# Exa categorical filter values. Keeping this as a Literal pins what
# we serialize over the wire — Exa's docs list more categories than
# we currently surface; add here as the operator needs them.
ExaSearchCategory = Literal[
    "research paper",
    "news",
    "company",
    "github",
    "tweet",
    "linkedin profile",
    "personal site",
]


class ExaClientError(RuntimeError):
    """Exa returned a non-retryable error or exhausted retries.

    Carries the HTTP status when known (None for transport errors).
    """

    def __init__(
        self,
        message: str,
        *,
        status: Optional[int] = None,
        url: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.url = url


@dataclass(frozen=True)
class ExaSearchResult:
    """One result from Exa /search or /findSimilar.

    The fields are the union we care about across both endpoints —
    Exa returns a richer body but we only retain what's useful for
    the discovery layer (URL + provenance + truncated preview).
    """

    url: str
    title: Optional[str]
    published_date: Optional[str]  # ISO-8601 when provided; we don't parse
    author: Optional[str]
    relevance_score: Optional[float]
    text_snippet_preview: Optional[str]
    provider_response_id: Optional[str]
    cost_usd_estimate: float


@dataclass
class ExaSearchResponse:
    """Wrapper for one /search or /findSimilar HTTP call.

    The `request_id` is Exa's id for the request; recorded on every
    result for cross-reference with Exa's dashboard.
    """

    results: List[ExaSearchResult] = field(default_factory=list)
    request_id: Optional[str] = None


def _resolve_api_key(api_key: Optional[str]) -> str:
    if api_key:
        return api_key
    v = os.environ.get("EXA_API_KEY")
    if not v:
        raise ExaClientError(
            "EXA_API_KEY not set. Configure the env var or pass api_key= "
            "explicitly. Do NOT alias to another service's key."
        )
    return v


def _resolve_base_url(base_url: Optional[str]) -> str:
    if base_url:
        return base_url.rstrip("/")
    return os.environ.get("EXA_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


class ExaClient:
    """Typed Exa HTTP client. One instance per (api_key, base_url)
    pair; thread-unsafe (httpx.Client is thread-safe but the client's
    retry/sleep semantics are not).

    Inject `client` (an `httpx.Client`) for tests with a
    `MockTransport`. Production code constructs without `client`,
    in which case a short-lived client is built per call.
    """

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        client: Optional[httpx.Client] = None,
        sleep: Optional[object] = None,
    ) -> None:
        self._api_key = _resolve_api_key(api_key)
        self._base_url = _resolve_base_url(base_url)
        self._timeout_s = timeout_s
        self._client = client
        self._sleep = sleep or time.sleep

    # ── /search ──────────────────────────────────────────────────

    def search(
        self,
        *,
        query: str,
        num_results: int = 10,
        category: Optional[ExaSearchCategory] = None,
        include_domains: Optional[Iterable[str]] = None,
        exclude_domains: Optional[Iterable[str]] = None,
        start_published_date: Optional[str] = None,
        end_published_date: Optional[str] = None,
        search_type: Literal["neural", "keyword", "auto"] = "auto",
    ) -> ExaSearchResponse:
        if not query.strip():
            raise ExaClientError("empty query")
        if num_results < 1 or num_results > 100:
            raise ExaClientError("num_results must be 1..100")

        body: dict = {"query": query, "numResults": num_results, "type": search_type}
        if category is not None:
            body["category"] = category
        if include_domains:
            body["includeDomains"] = list(include_domains)
        if exclude_domains:
            body["excludeDomains"] = list(exclude_domains)
        if start_published_date:
            body["startPublishedDate"] = start_published_date
        if end_published_date:
            body["endPublishedDate"] = end_published_date

        raw = self._post("/search", body)
        return self._parse_search_response(raw, per_call_cost=COST_PER_SEARCH_USD)

    # ── /findSimilar ─────────────────────────────────────────────

    def find_similar(
        self,
        *,
        url: str,
        num_results: int = 10,
        exclude_source_domain: bool = True,
    ) -> ExaSearchResponse:
        """Spec §17.3 recommends including findSimilar in Wedge 1."""
        if not url.strip():
            raise ExaClientError("empty url")
        if num_results < 1 or num_results > 100:
            raise ExaClientError("num_results must be 1..100")
        body = {
            "url": url,
            "numResults": num_results,
            "excludeSourceDomain": exclude_source_domain,
        }
        raw = self._post("/findSimilar", body)
        return self._parse_search_response(raw, per_call_cost=COST_PER_FIND_SIMILAR_USD)

    # ── internals ────────────────────────────────────────────────

    def _post(self, path: str, body: dict) -> dict:
        url = f"{self._base_url}{path}"
        headers = {
            "User-Agent": DEFAULT_USER_AGENT,
            "Authorization": f"Bearer {self._api_key}",
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
                    raise ExaClientError(
                        f"transport error: {e}", status=None, url=url
                    ) from e

                if r.status_code in _RETRYABLE_STATUS and attempt < _MAX_RETRIES:
                    # Honor Retry-After when present; cap at 30s so a
                    # misbehaving server can't park us forever.
                    delay = self._retry_after_seconds(r) or self._backoff_seconds(attempt)
                    self._sleep(min(delay, 30.0))
                    continue

                if r.status_code >= 400:
                    raise ExaClientError(
                        f"exa returned {r.status_code}: {r.text[:200]}",
                        status=r.status_code,
                        url=url,
                    )

                try:
                    return r.json()
                except ValueError as e:
                    raise ExaClientError(
                        f"non-json body from exa: {e}", status=r.status_code, url=url
                    ) from e
        finally:
            if owns_client:
                client.close()

    @staticmethod
    def _backoff_seconds(attempt: int) -> float:
        # 1s, 2s, 4s with no jitter — single-operator substrate, jitter is
        # overengineering. Sprint 18+ may add jitter when multi-user lands.
        return 2 ** (attempt - 1)

    @staticmethod
    def _retry_after_seconds(r: httpx.Response) -> Optional[float]:
        v = r.headers.get("retry-after")
        if not v:
            return None
        try:
            return float(v)
        except ValueError:
            return None

    @staticmethod
    def _parse_search_response(
        raw: dict, *, per_call_cost: float
    ) -> ExaSearchResponse:
        request_id = raw.get("requestId") or raw.get("autopromptString") or None
        results_raw = raw.get("results") or []
        results: List[ExaSearchResult] = []
        # Per-result cost is the per-call cost amortized across results.
        # An empty response still charged once; we attribute that to a
        # synthetic zero-cost result list (caller's responsibility to log).
        per_result_cost = (
            per_call_cost / len(results_raw) if results_raw else per_call_cost
        )
        for r in results_raw:
            snippet = r.get("text") or r.get("highlight") or None
            if isinstance(snippet, str) and len(snippet) > 300:
                snippet = snippet[:300]
            results.append(
                ExaSearchResult(
                    url=str(r.get("url", "")).strip(),
                    title=r.get("title"),
                    published_date=r.get("publishedDate"),
                    author=r.get("author"),
                    relevance_score=r.get("score"),
                    text_snippet_preview=snippet,
                    provider_response_id=r.get("id") or request_id,
                    cost_usd_estimate=per_result_cost,
                )
            )
        return ExaSearchResponse(results=results, request_id=request_id)
