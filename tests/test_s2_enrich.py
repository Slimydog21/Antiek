import socket
from collections.abc import Iterator

import pytest

from acquisition.s2_enrich import BudgetExceeded, S2Client


@pytest.fixture(autouse=True)
def socket_guard(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    def blocked(*args: object, **kwargs: object) -> None:
        raise AssertionError("real network access is forbidden")

    monkeypatch.setattr(socket, "create_connection", blocked)
    yield


class R:
    status_code = 200

    def json(self) -> list[dict[str, object]]:
        return [{"paperId": "p"}]


def test_batch_key_optional_and_101_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("S2_API_KEY", raising=False)
    seen: list[dict[str, str]] = []
    c = S2Client(post=lambda u, h, b: seen.append(dict(h)) or R(), now=lambda: 0.0)
    assert c.enrich(["p"])[0]["paperId"] == "p" and seen == [{}]
    for _ in range(99):
        c.enrich(["p"])
    with pytest.raises(BudgetExceeded):
        c.enrich(["p"])


def test_authenticated_request_sends_key_without_repr_leak() -> None:
    secret = "s2-secret-value"
    seen: list[dict[str, str]] = []
    client = S2Client(
        post=lambda u, h, b: seen.append(dict(h)) or R(),
        now=lambda: 0.0,
        api_key=secret,
    )
    assert client.enrich(["p"])[0]["paperId"] == "p"
    assert seen == [{"x-api-key": secret}]
    assert secret not in repr(client)
    assert secret not in str(client)
