from __future__ import annotations

import socket
from collections.abc import Iterator
from pathlib import Path

import pytest

from acquisition.oai_pmh import BannedUntil, OaiPmhHarvester


@pytest.fixture(autouse=True)
def socket_guard(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    def blocked(*args: object, **kwargs: object) -> None:
        raise AssertionError("real network access is forbidden")

    monkeypatch.setattr(socket, "create_connection", blocked)
    yield


class Clock:
    def __init__(self, value: float = 1_000.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value


class Response:
    def __init__(self, status: int, text: str = "", retry_after: str | None = None) -> None:
        self.status_code = status
        self.text = text
        self.headers = {} if retry_after is None else {"Retry-After": retry_after}


def test_ban_sentinel_survives_new_client_and_refuses_before_http(tmp_path: Path) -> None:
    clock = Clock()
    state = tmp_path / "ban.json"
    calls: list[str] = []

    def first_get(url: str) -> Response:
        calls.append(url)
        return Response(503, retry_after="120")

    first = OaiPmhHarvester(
        get=first_get, cache_dir=tmp_path / "cache", sentinel_path=state, now=clock
    )
    with pytest.raises(BannedUntil):
        list(first.harvest())
    second = OaiPmhHarvester(
        get=lambda url: (_ for _ in ()).throw(AssertionError(url)),
        cache_dir=tmp_path / "cache2",
        sentinel_path=state,
        now=clock,
    )
    with pytest.raises(BannedUntil):
        list(second.harvest())
    assert len(calls) == 1
    clock.value += 121
    assert second.sentinel.is_banned() is False


PAGE_1 = """<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/"><ListRecords><record><header><identifier>oai:arXiv.org:1</identifier><datestamp>2026-07-01</datestamp></header><metadata><arXiv xmlns="http://arxiv.org/OAI/arXiv/"><id>1</id><title>First</title></arXiv></metadata></record><resumptionToken>next</resumptionToken></ListRecords></OAI-PMH>"""
PAGE_2 = """<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/"><ListRecords><record><header><identifier>oai:arXiv.org:2</identifier><datestamp>2026-07-02</datestamp></header><metadata><arXiv xmlns="http://arxiv.org/OAI/arXiv/"><id>2</id><title>Second</title></arXiv></metadata></record><resumptionToken/></ListRecords></OAI-PMH>"""


def test_list_records_pages_and_caches(tmp_path: Path) -> None:
    urls: list[str] = []
    pages = iter((PAGE_1, PAGE_2))

    def get(url: str) -> Response:
        urls.append(url)
        return Response(200, next(pages))

    client = OaiPmhHarvester(
        get=get, cache_dir=tmp_path / "cache", sentinel_path=tmp_path / "ban", now=Clock()
    )
    records = list(
        client.harvest(set_spec="physics", from_date="2026-07-01", until_date="2026-07-02")
    )
    assert [record["id"] for record in records] == ["1", "2"]
    assert "set=physics" in urls[0] and "from=2026-07-01" in urls[0]
    assert "resumptionToken=next" in urls[1] and "metadataPrefix" not in urls[1]
    assert len(list((tmp_path / "cache").glob("*.json"))) == 2
