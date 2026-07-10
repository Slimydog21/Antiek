from __future__ import annotations

import hashlib
import json
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path
from typing import Protocol
from urllib.parse import urlencode

from .sentinel import BannedUntil, BanSentinel

OAI_URL = "https://export.arxiv.org/oai2"
# arXiv API Terms: one request per three seconds: https://info.arxiv.org/help/api/tou.html
DEFAULT_RETRY_SECONDS = 3.0


class Response(Protocol):
    status_code: int
    text: str

    @property
    def headers(self) -> Mapping[str, str]: ...


class OaiPmhHarvester:
    def __init__(
        self,
        *,
        get: Callable[[str], Response],
        cache_dir: Path,
        sentinel_path: Path,
        now: Callable[[], float] = time.time,
    ) -> None:
        self.get, self.cache_dir, self.now = get, cache_dir, now
        self.sentinel = BanSentinel(sentinel_path, now)

    def harvest(
        self,
        *,
        set_spec: str | None = None,
        from_date: str | None = None,
        until_date: str | None = None,
    ) -> Iterator[dict[str, object]]:
        token: str | None = None
        while True:
            params = (
                {"verb": "ListRecords", "resumptionToken": token}
                if token
                else {
                    "verb": "ListRecords",
                    "metadataPrefix": "arXiv",
                    **({"set": set_spec} if set_spec else {}),
                    **({"from": from_date} if from_date else {}),
                    **({"until": until_date} if until_date else {}),
                }
            )
            self.sentinel.refuse_if_banned()
            response = self.get(f"{OAI_URL}?{urlencode(params)}")
            if response.status_code in {429, 503}:
                self.sentinel.persist_retry_after(response.headers, DEFAULT_RETRY_SECONDS)
                raise BannedUntil("provider requested backoff")
            if response.status_code >= 400:
                raise RuntimeError(f"OAI-PMH HTTP {response.status_code}")
            root = ET.fromstring(response.text)
            ns = {"o": "http://www.openarchives.org/OAI/2.0/", "a": "http://arxiv.org/OAI/arXiv/"}
            for node in root.findall(".//o:record", ns):
                record: dict[str, object] = {
                    "id": node.findtext(".//a:id", default="", namespaces=ns),
                    "title": node.findtext(".//a:title", default="", namespaces=ns),
                    "datestamp": node.findtext("o:header/o:datestamp", default="", namespaces=ns),
                    "fetched_at": self.now(),
                    "source": "arxiv_oai_pmh",
                }
                self.cache_dir.mkdir(parents=True, exist_ok=True)
                key = hashlib.sha256(str(record["id"]).encode()).hexdigest()
                (self.cache_dir / f"{key}.json").write_text(json.dumps(record), encoding="utf-8")
                yield record
            raw_token = root.findtext(".//o:resumptionToken", default="", namespaces=ns).strip()
            token = raw_token or None
            if token is None:
                return
