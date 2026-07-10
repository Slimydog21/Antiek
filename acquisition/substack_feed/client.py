from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path
from typing import Protocol

from acquisition.oai_pmh.sentinel import BannedUntil, BanSentinel

# Substack has no published numeric public API quota; Retry-After is authoritative: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Retry-After
DEFAULT_RETRY_SECONDS = 60.0


class Response(Protocol):
    status_code: int
    text: str

    @property
    def headers(self) -> Mapping[str, str]: ...
    def json(self) -> object: ...


class SubstackClient:
    def __init__(
        self,
        *,
        base_url: str,
        get: Callable[[str], Response],
        sentinel_path: Path,
        now: Callable[[], float] = time.time,
    ) -> None:
        self.base_url, self.get, self.now = base_url.rstrip("/"), get, now
        self.sentinel = BanSentinel(sentinel_path, now)

    def _get(self, url: str) -> Response:
        self.sentinel.refuse_if_banned()
        r = self.get(url)
        if r.status_code in {429, 503}:
            self.sentinel.persist_retry_after(r.headers, DEFAULT_RETRY_SECONDS)
            raise BannedUntil("Substack backoff")
        if r.status_code >= 400:
            raise RuntimeError(f"Substack HTTP {r.status_code}")
        return r

    def feed(self) -> list[dict[str, object]]:
        root = ET.fromstring(self._get(self.base_url + "/feed").text)
        out: list[dict[str, object]] = []
        for item in root.findall(".//item"):
            body = item.findtext("{http://purl.org/rss/1.0/modules/content/}encoded")
            out.append(
                {
                    "title": item.findtext("title", ""),
                    "url": item.findtext("link", ""),
                    "body_html": body,
                    "accessible": body is not None,
                    "fetched_at": self.now(),
                }
            )
        return out

    def archive(self, *, limit: int = 12) -> Iterator[dict[str, object]]:
        offset = 0
        while True:
            data = self._get(
                f"{self.base_url}/api/v1/archive?sort=new&search=&offset={offset}&limit={limit}"
            ).json()
            if not isinstance(data, list):
                raise ValueError("invalid archive")
            for raw in data:
                if isinstance(raw, dict):
                    paywalled = bool(raw.get("audience") not in (None, "everyone"))
                    yield {
                        **raw,
                        "accessible": not paywalled,
                        "body_html": None if paywalled else raw.get("body_html"),
                        "fetched_at": self.now(),
                    }
            if len(data) < limit:
                return
            offset += limit
