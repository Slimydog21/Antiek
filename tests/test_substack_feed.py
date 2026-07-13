import socket
from collections.abc import Iterator
from pathlib import Path

import pytest

from acquisition.oai_pmh import BannedUntil
from acquisition.substack_feed import SubstackClient


@pytest.fixture(autouse=True)
def socket_guard(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    def blocked(*args: object, **kwargs: object) -> None:
        raise AssertionError("real network access is forbidden")

    monkeypatch.setattr(socket, "create_connection", blocked)
    yield


class R:
    def __init__(
        self,
        *,
        status_code: int = 200,
        text: str = "",
        data: object = None,
        headers: dict[str, str] | None = None,
    ):
        self.status_code, self.text, self.data = status_code, text, data
        self.headers = headers or {}

    def json(self) -> object:
        return self.data


def test_feed_archive_paging_and_paywall_honesty(tmp_path: Path) -> None:
    xml = '<rss xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel><item><title>T</title><link>https://x/p</link><content:encoded><![CDATA[<p>B</p>]]></content:encoded></item></channel></rss>'
    calls: list[str] = []

    def get(url: str) -> R:
        calls.append(url)
        if url.endswith("/feed"):
            return R(text=xml)
        if "offset=0" in url:
            return R(data=[{"id": 1, "audience": "only_paid"}])
        raise AssertionError(url)

    c = SubstackClient(
        base_url="https://x", get=get, sentinel_path=tmp_path / "ban", now=lambda: 1.0
    )
    assert c.feed()[0]["body_html"] == "<p>B</p>"
    item = list(c.archive(limit=2))[0]
    assert item["accessible"] is False and item["body_html"] is None
    assert calls == ["https://x/feed", "https://x/api/v1/archive?sort=new&search=&offset=0&limit=2"]


def test_archive_requests_all_offsets_and_aggregates_pages(tmp_path: Path) -> None:
    calls: list[str] = []
    pages = iter(
        (
            [{"id": 1}, {"id": 2}],
            [{"id": 3}, {"id": 4}],
            [{"id": 5}],
        )
    )

    def get(url: str) -> R:
        calls.append(url)
        return R(data=next(pages))

    client = SubstackClient(
        base_url="https://x", get=get, sentinel_path=tmp_path / "ban", now=lambda: 1.0
    )
    assert [item["id"] for item in client.archive(limit=2)] == [1, 2, 3, 4, 5]
    assert calls == [
        "https://x/api/v1/archive?sort=new&search=&offset=0&limit=2",
        "https://x/api/v1/archive?sort=new&search=&offset=2&limit=2",
        "https://x/api/v1/archive?sort=new&search=&offset=4&limit=2",
    ]


def test_retry_after_ban_survives_new_client(tmp_path: Path) -> None:
    state = tmp_path / "ban.json"
    calls: list[str] = []

    def first_get(url: str) -> R:
        calls.append(url)
        return R(status_code=429, headers={"Retry-After": "120"})

    first = SubstackClient(
        base_url="https://x", get=first_get, sentinel_path=state, now=lambda: 1_000.0
    )
    with pytest.raises(BannedUntil):
        first.feed()
    second = SubstackClient(
        base_url="https://x",
        get=lambda url: (_ for _ in ()).throw(AssertionError(url)),
        sentinel_path=state,
        now=lambda: 1_000.0,
    )
    with pytest.raises(BannedUntil):
        second.feed()
    assert len(calls) == 1
