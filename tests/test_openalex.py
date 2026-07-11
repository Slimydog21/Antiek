import socket
from collections.abc import Iterator
from pathlib import Path

import pytest

import acquisition.openalex.client as openalex_client
from acquisition.openalex import OpenAlexClient, RateLimitExceeded


@pytest.fixture(autouse=True)
def socket_guard(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    def blocked(*args: object, **kwargs: object) -> None:
        raise AssertionError("real network access is forbidden")

    monkeypatch.setattr(socket, "create_connection", blocked)
    yield


class R:
    status_code = 200

    def __init__(self, data: dict[str, object]):
        self.data = data

    def json(self) -> dict[str, object]:
        return self.data


def test_cursor_cache_and_local_ceiling(tmp_path: Path) -> None:
    calls: list[str] = []
    pages = iter(
        (
            {"results": [{"id": "https://openalex.org/W1"}], "meta": {"next_cursor": "x"}},
            {"results": [], "meta": {"next_cursor": None}},
        )
    )
    client = OpenAlexClient(
        get=lambda u: calls.append(u) or R(next(pages)),
        mailto="a@example.com",
        cache_dir=tmp_path,
        now=lambda: 1.0,
    )
    assert [x["id"] for x in client.works(search="ai")] == ["https://openalex.org/W1"]
    assert "cursor=x" in calls[1] and (tmp_path / "W1.json").exists()
    rate_calls: list[str] = []
    limiter = OpenAlexClient(
        get=lambda u: rate_calls.append(u) or R({"results": [], "meta": {}}),
        mailto="a@example.com",
        cache_dir=tmp_path,
        now=lambda: 1.0,
    )
    for _ in range(9):
        list(limiter.works(search="x"))
    with pytest.raises(RateLimitExceeded):
        list(limiter.works(search="x"))
    assert len(rate_calls) == 9


def test_daily_ceiling_refuses_before_http(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(openalex_client, "REQUESTS_PER_DAY", 1)
    calls: list[str] = []
    client = OpenAlexClient(
        get=lambda u: calls.append(u) or R({"results": [], "meta": {}}),
        mailto="a@example.com",
        cache_dir=tmp_path,
        now=lambda: 1.0,
    )
    assert list(client.works(search="first")) == []
    with pytest.raises(RateLimitExceeded, match="daily"):
        list(client.works(search="second"))
    assert len(calls) == 1
