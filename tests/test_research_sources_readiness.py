"""Red-proofs for DRW arxiv/Substack source readiness (offline only)."""

from __future__ import annotations

import httpx

from substrate.research_sources import probe_arxiv, probe_source, probe_substack
from substrate.research_sources.readiness import readiness_to_preflight_fields


def _arxiv_atom(arxiv_id: str = "2402.03300") -> bytes:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
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
""".encode()


def _mock_arxiv_client(body: bytes | None = None) -> httpx.Client:
    payload = body if body is not None else _arxiv_atom()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=payload)

    return httpx.Client(transport=httpx.MockTransport(handler), timeout=5.0)


def test_probe_arxiv_importable_and_offline_fetch_by_id() -> None:
    """Drives real acquisition.arxiv.client.fetch_by_id under MockTransport."""
    with _mock_arxiv_client() as client:
        r = probe_arxiv(client=client, sample_id="2402.03300")
    assert r.source == "arxiv"
    assert r.adapter_importable is True
    assert r.callables_present is True
    assert r.offline_probe_ok is True
    assert r.runner_consumes_today is False  # DRW launch still not wired
    assert r.status == "ready"
    assert "fetch_by_id" in r.note or "importable" in r.note.lower()
    # Must not claim runner consumption while launch is unwired.
    assert r.external_call_would_be_required is True


def test_probe_arxiv_without_client_is_import_only() -> None:
    r = probe_arxiv(client=None)
    assert r.adapter_importable is True
    assert r.callables_present is True
    assert r.offline_probe_ok is True  # import-only path treats callables as ok
    assert r.runner_consumes_today is False


def test_probe_arxiv_empty_feed_is_gated_not_fake_ready() -> None:
    empty = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"></feed>"""
    with _mock_arxiv_client(empty) as client:
        r = probe_arxiv(client=client)
    assert r.adapter_importable is True
    assert r.offline_probe_ok is False
    assert r.status == "gated"


def test_probe_substack_importable() -> None:
    r = probe_substack()
    assert r.source == "substack"
    assert r.adapter_importable is True
    assert r.callables_present is True
    assert r.offline_probe_ok is True
    assert r.runner_consumes_today is False
    assert "fetch_feed" in r.note or "Substack" in r.note


def test_probe_source_dispatch_covers_closed_set() -> None:
    assert probe_source("operator_corpus").runner_consumes_today is True
    web = probe_source("web")
    assert web.source == "web"
    assert web.status in ("stub", "gated")
    with _mock_arxiv_client() as client:
        assert probe_source("arxiv", arxiv_client=client).offline_probe_ok is True
    assert probe_source("substack").adapter_importable is True


def test_readiness_maps_to_preflight_fields() -> None:
    r = probe_substack()
    fields = readiness_to_preflight_fields(r)
    assert fields["source"] == "substack"
    assert fields["adapter_importable"] is True
    assert "note" in fields and fields["note"]
    assert fields["runner_consumes_today"] is False


def test_fresh_consumer_import_returns_real_probe_values() -> None:
    """Library launch check: import from a clean consumer and assert content."""
    # Simulate external consumer (not re-implementing probe).
    from substrate.research_sources.readiness import probe_arxiv as consumer_probe

    with _mock_arxiv_client() as client:
        out = consumer_probe(client=client)
    assert out.adapter_importable is True
    assert out.offline_probe_ok is True
    assert isinstance(out.details, list) and len(out.details) >= 1
