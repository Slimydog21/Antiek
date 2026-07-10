from pathlib import Path

import pytest

from acquisition.openalex import OpenAlexClient, RateLimitExceeded


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
    limiter = OpenAlexClient(
        get=lambda u: R({"results": [], "meta": {}}),
        mailto="a@example.com",
        cache_dir=tmp_path,
        now=lambda: 1.0,
    )
    for _ in range(9):
        list(limiter.works(search="x"))
    with pytest.raises(RateLimitExceeded):
        list(limiter.works(search="x"))
