import pytest

from acquisition.s2_enrich import BudgetExceeded, S2Client


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
