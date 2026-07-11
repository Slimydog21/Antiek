"""Exa-shaped semantic discovery with injected transport and clock."""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Protocol, cast

from acquisition.web_layer.cost import estimate_cost
from acquisition.web_layer.interfaces import DiscoveryHit, DiscoveryResponse


class DiscoveryConfigurationError(RuntimeError):
    """Discovery cannot run because its isolated configuration is invalid."""


class JsonResponse(Protocol):
    def raise_for_status(self) -> None: ...

    def json(self) -> object: ...


class DiscoveryHttpClient(Protocol):
    def post(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        json: Mapping[str, object],
        timeout: float,
    ) -> JsonResponse: ...


class ExaDiscovery:
    """Reference discovery adapter for Exa's search and findSimilar shapes."""

    __slots__ = ("_api_key", "_base_url", "_clock", "_http", "_timeout")

    # Exa integration spec §6.4 specifies 30 seconds; re-read 2026-07-11.
    _DEFAULT_TIMEOUT_SECONDS = 30.0
    # Exa integration spec §1.1 documents numResults <= 100; re-read 2026-07-11.
    _MAX_RESULTS = 100

    def __init__(
        self,
        *,
        http: DiscoveryHttpClient,
        clock: Callable[[], datetime],
        api_key: str | None = None,
        environ: Mapping[str, str] | None = None,
        base_url: str = "https://api.exa.ai",
        timeout: float = _DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        environment = os.environ if environ is None else environ
        resolved_key = api_key if api_key is not None else environment.get("EXA_API_KEY")
        if resolved_key is None or not resolved_key.strip():
            raise DiscoveryConfigurationError("EXA_API_KEY is required")
        if timeout <= 0:
            raise DiscoveryConfigurationError("timeout must be positive")
        self._http = http
        self._clock = clock
        self._api_key = resolved_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}(base_url={self._base_url!r}, "
            f"timeout={self._timeout!r})"
        )

    __str__ = __repr__

    def search(self, query: str, *, limit: int) -> DiscoveryResponse:
        if not query.strip():
            raise ValueError("query must not be blank")
        return self._request(
            "search", {"query": query, "numResults": self._validate_limit(limit)}
        )

    def find_similar(self, seed_url: str, *, limit: int) -> DiscoveryResponse:
        if not seed_url.strip():
            raise ValueError("seed_url must not be blank")
        return self._request(
            "find_similar",
            {"url": seed_url, "numResults": self._validate_limit(limit)},
        )

    def _request(
        self, operation: str, payload: Mapping[str, object]
    ) -> DiscoveryResponse:
        endpoint = "findSimilar" if operation == "find_similar" else "search"
        response = self._http.post(
            f"{self._base_url}/{endpoint}",
            headers={"x-api-key": self._api_key, "content-type": "application/json"},
            json=payload,
            timeout=self._timeout,
        )
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, dict) or not isinstance(body.get("results"), list):
            raise ValueError("Exa response must contain a results list")
        discovered_at = self._clock()
        results = tuple(self._parse_hit(item) for item in body["results"])
        if operation == "find_similar":
            return DiscoveryResponse(
                results, estimate_cost("exa", "find_similar", 1), discovered_at
            )
        return DiscoveryResponse(results, estimate_cost("exa", "search", 1), discovered_at)

    @staticmethod
    def _validate_limit(limit: int) -> int:
        if not 1 <= limit <= ExaDiscovery._MAX_RESULTS:
            raise ValueError("limit must be between 1 and 100")
        return limit

    @staticmethod
    def _parse_hit(raw: object) -> DiscoveryHit:
        if not isinstance(raw, dict):
            raise ValueError("Exa result must be an object")
        item = cast("dict[str, object]", raw)
        url = item.get("url")
        title = item.get("title")
        if not isinstance(url, str) or not url:
            raise ValueError("Exa result url must be a non-empty string")
        if not isinstance(title, str):
            raise ValueError("Exa result title must be a string")
        score_raw = item.get("score")
        score = float(score_raw) if isinstance(score_raw, (int, float)) else None
        published_raw = item.get("publishedDate")
        published = (
            datetime.fromisoformat(published_raw.replace("Z", "+00:00"))
            if isinstance(published_raw, str)
            else None
        )
        return DiscoveryHit(url, title, score, published)
