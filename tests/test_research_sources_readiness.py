"""Red-proofs for DRW arxiv/Substack source readiness (offline only)."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from acquisition.arxiv.throttle import ArxivThrottle
from substrate.research_sources import probe_arxiv, probe_source, probe_substack
from substrate.research_sources.readiness import readiness_to_preflight_fields


def _arxiv_atom(arxiv_id: str = "2402.03300") -> bytes:
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/{arxiv_id}v1</id>
    <updated>2024-02-15T12:00:00Z</updated>
    <published>2024-02-05T09:15:33Z</published>
    <title>Paper {arxiv_id}</title>
    <summary>Abstract for {arxiv_id}.</summary>
    <author><name>Jane Doe</name></author>
    <arxiv:primary_category term="cs.AI"/>
    <category term="cs.AI"/>
  </entry>
</feed>
"""
    return xml.encode()


def _substack_rss() -> bytes:
    return b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Example Substack</title>
    <link>https://example.substack.com</link>
    <item>
      <title>Hello research</title>
      <link>https://example.substack.com/p/hello</link>
      <guid>hello-1</guid>
      <description>Body of the post for offline parse.</description>
      <pubDate>Mon, 01 Jan 2024 00:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""


@pytest.fixture
def isolated_arxiv_governor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ArxivThrottle:
    """Isolate governor lock + throttle state under tmp (no ~/.antiek writes)."""
    lock = tmp_path / "arxiv_throttle.json.governor.lock"
    state = tmp_path / "arxiv_throttle.json"
    monkeypatch.setenv("ANTIEK_ARXIV_GOVERNOR_LOCK_PATH", str(lock))
    clock = {"t": 1_000_000.0}

    def now() -> float:
        return clock["t"]

    def sleep(dt: float) -> None:
        clock["t"] += float(dt)

    return ArxivThrottle(
        state_path=str(state),
        min_spacing_s=0.0,
        now=now,
        sleep=sleep,
    )


def _mock_client(body: bytes) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body)

    return httpx.Client(transport=httpx.MockTransport(handler), timeout=5.0)


def test_probe_arxiv_importable_and_offline_fetch_by_id(
    isolated_arxiv_governor: ArxivThrottle,
) -> None:
    """Drives real acquisition.arxiv.client.fetch_by_id under MockTransport."""
    with _mock_client(_arxiv_atom()) as client:
        r = probe_arxiv(
            client=client,
            sample_id="2402.03300",
            throttle=isolated_arxiv_governor,
        )
    assert r.source == "arxiv"
    assert r.adapter_importable is True
    assert r.callables_present is True
    assert r.offline_probe_ok is True
    assert r.runner_consumes_today is False
    assert r.status == "ready"
    assert r.external_call_would_be_required is True


def test_probe_arxiv_without_client_import_only_not_offline_ok() -> None:
    r = probe_arxiv(client=None)
    assert r.adapter_importable is True
    assert r.callables_present is True
    assert r.offline_probe_ok is False  # callable ≠ offline probe
    assert r.status == "gated"
    assert r.runner_consumes_today is False


def test_probe_arxiv_empty_feed_is_gated_not_fake_ready(
    isolated_arxiv_governor: ArxivThrottle,
) -> None:
    empty = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"></feed>"""
    with _mock_client(empty) as client:
        r = probe_arxiv(client=client, throttle=isolated_arxiv_governor)
    assert r.adapter_importable is True
    assert r.offline_probe_ok is False
    assert r.status == "gated"


def test_probe_substack_offline_rss_parse() -> None:
    with _mock_client(_substack_rss()) as client:
        r = probe_substack(client=client)
    assert r.source == "substack"
    assert r.adapter_importable is True
    assert r.callables_present is True
    assert r.offline_probe_ok is True
    assert r.status == "ready"
    assert r.runner_consumes_today is False


def test_probe_substack_without_client_not_offline_ok() -> None:
    r = probe_substack(client=None)
    assert r.adapter_importable is True
    assert r.callables_present is True
    assert r.offline_probe_ok is False
    assert r.status == "gated"


def test_probe_substack_empty_feed_gated() -> None:
    empty = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>x</title></channel></rss>"""
    with _mock_client(empty) as client:
        r = probe_substack(client=client)
    assert r.offline_probe_ok is False
    assert r.status == "gated"


def test_probe_source_dispatch_covers_closed_set(
    isolated_arxiv_governor: ArxivThrottle,
) -> None:
    assert probe_source("operator_corpus").runner_consumes_today is True
    web = probe_source("web")
    assert web.source == "web"
    assert web.status in ("stub", "gated")
    with _mock_client(_arxiv_atom()) as client:
        assert (
            probe_source(
                "arxiv",
                arxiv_client=client,
                arxiv_throttle=isolated_arxiv_governor,
            ).offline_probe_ok
            is True
        )
    with _mock_client(_substack_rss()) as client:
        assert probe_source("substack", substack_client=client).offline_probe_ok is True


def test_readiness_maps_to_preflight_fields() -> None:
    r = probe_substack(client=None)
    fields = readiness_to_preflight_fields(r)
    assert fields["source"] == "substack"
    assert fields["adapter_importable"] is True
    assert fields["offline_probe_ok"] is False
    assert fields["runner_consumes_today"] is False


def test_fresh_consumer_import_returns_real_probe_values(
    isolated_arxiv_governor: ArxivThrottle,
) -> None:
    from substrate.research_sources.readiness import probe_arxiv as consumer_probe

    with _mock_client(_arxiv_atom()) as client:
        out = consumer_probe(client=client, throttle=isolated_arxiv_governor)
    assert out.adapter_importable is True
    assert out.offline_probe_ok is True
    assert isinstance(out.details, list) and len(out.details) >= 1


def test_import_failure_reports_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    import builtins

    real_import = builtins.__import__

    def boom(name: str, *args: object, **kwargs: object) -> object:
        if name.startswith("acquisition.arxiv") or name.startswith("acquisition.substack"):
            raise ImportError("forced missing acquisition surface")
        return real_import(name, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(builtins, "__import__", boom)
    ra = probe_arxiv(client=None)
    rs = probe_substack(client=None)
    assert ra.status == "unavailable" and ra.adapter_importable is False
    assert rs.status == "unavailable" and rs.adapter_importable is False
