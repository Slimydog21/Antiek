from __future__ import annotations

import json
import time
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path
from typing import Protocol
from urllib.parse import urlencode

# OpenAlex rate limits: 100,000 requests/day and 10/second: https://docs.openalex.org/how-to-use-the-api/rate-limits-and-authentication
REQUESTS_PER_SECOND = 9


class RateLimitExceeded(RuntimeError):
    pass


class Response(Protocol):
    status_code: int

    def json(self) -> dict[str, object]: ...


class OpenAlexClient:
    def __init__(
        self,
        *,
        get: Callable[[str], Response],
        mailto: str,
        cache_dir: Path,
        now: Callable[[], float] = time.time,
    ) -> None:
        self.get, self.mailto, self.cache_dir, self.now = get, mailto, cache_dir, now
        self._window = int(now())
        self._count = 0

    def _permit(self) -> None:
        window = int(self.now())
        if window != self._window:
            self._window, self._count = window, 0
        if self._count >= REQUESTS_PER_SECOND:
            raise RateLimitExceeded("OpenAlex local rate ceiling")
        self._count += 1

    def works(self, *, search: str) -> Iterator[dict[str, object]]:
        cursor = "*"
        while cursor:
            self._permit()
            url = "https://api.openalex.org/works?" + urlencode(
                {"search": search, "cursor": cursor, "mailto": self.mailto}
            )
            response = self.get(url)
            if response.status_code >= 400:
                raise RuntimeError(f"OpenAlex HTTP {response.status_code}")
            payload = response.json()
            results = payload.get("results", [])
            if not isinstance(results, list):
                raise ValueError("invalid OpenAlex results")
            for item in results:
                if isinstance(item, dict):
                    item = {**item, "fetched_at": self.now()}
                    self.cache_dir.mkdir(parents=True, exist_ok=True)
                    (
                        self.cache_dir
                        / (str(item.get("id", "unknown")).rsplit("/", 1)[-1] + ".json")
                    ).write_text(json.dumps(item), encoding="utf-8")
                    yield item
            meta = payload.get("meta", {})
            cursor = str(meta.get("next_cursor") or "") if isinstance(meta, Mapping) else ""
