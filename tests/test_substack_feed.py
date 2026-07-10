from pathlib import Path

from acquisition.substack_feed import SubstackClient


class R:
    status_code = 200
    headers: dict[str, str] = {}

    def __init__(self, *, text: str = "", data: object = None):
        self.text, self.data = text, data

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
