from __future__ import annotations

import os
import time
from collections.abc import Callable, Mapping
from typing import Protocol

# Semantic Scholar authenticated API guidance (~100 requests/5 minutes): https://www.semanticscholar.org/product/api
WINDOW_SECONDS = 300.0
REQUESTS_PER_WINDOW = 100


class BudgetExceeded(RuntimeError):
    pass


class Response(Protocol):
    status_code: int

    def json(self) -> list[dict[str, object]]: ...


class S2Client:
    def __init__(
        self,
        *,
        post: Callable[[str, Mapping[str, str], dict[str, object]], Response],
        now: Callable[[], float] = time.time,
        api_key: str | None = None,
    ) -> None:
        self.post, self.now, self.api_key = (
            post,
            now,
            api_key if api_key is not None else os.getenv("S2_API_KEY"),
        )
        self.start = now()
        self.count = 0

    def enrich(
        self, ids: list[str], fields: tuple[str, ...] = ("title", "citationCount")
    ) -> list[dict[str, object]]:
        if self.now() - self.start >= WINDOW_SECONDS:
            self.start, self.count = self.now(), 0
        if self.count >= REQUESTS_PER_WINDOW:
            raise BudgetExceeded("S2 five-minute budget exhausted")
        self.count += 1
        headers = {"x-api-key": self.api_key} if self.api_key else {}
        response = self.post(
            "https://api.semanticscholar.org/graph/v1/paper/batch?fields=" + ",".join(fields),
            headers,
            {"ids": ids},
        )
        if response.status_code >= 400:
            raise RuntimeError(f"S2 HTTP {response.status_code}")
        return response.json()
