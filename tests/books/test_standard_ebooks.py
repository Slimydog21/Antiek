"""Standard Ebooks connector tests (SPR-06 M2). No live network."""

from __future__ import annotations

from acquisition.books import standard_ebooks
from acquisition.books.pd_connector_base import (
    ThrottledFetcher,
    classify_and_ingest,
)

from .conftest import FakeFetcher, book_asset_row

# A small SE OPDS feed: two entries, each with an epub acquisition link + a
# rights dedication. SE publishes only US-PD works.
_OPDS = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:dc="http://purl.org/dc/terms/">
  <entry>
    <id>url:https://standardebooks.org/ebooks/jane-austen/pride-and-prejudice</id>
    <title>Pride and Prejudice</title>
    <author><name>Jane Austen</name></author>
    <rights>This ebook is in the public domain in the United States.</rights>
    <link rel="alternate" type="text/html"
      href="https://standardebooks.org/ebooks/jane-austen/pride-and-prejudice"/>
    <link rel="http://opds-spec.org/acquisition" type="application/epub+zip"
      href="https://standardebooks.org/ebooks/jane-austen/pride-and-prejudice/downloads/pride.epub"/>
  </entry>
  <entry>
    <id>url:https://standardebooks.org/ebooks/herman-melville/moby-dick</id>
    <title>Moby-Dick</title>
    <author><name>Herman Melville</name></author>
    <rights>This ebook is in the public domain in the United States.</rights>
    <link rel="http://opds-spec.org/acquisition" type="application/epub+zip"
      href="https://standardebooks.org/ebooks/herman-melville/moby-dick/downloads/moby.epub"/>
  </entry>
</feed>
"""


def _feed_fetcher():
    return FakeFetcher(text_by_url={standard_ebooks.OPDS_FEED_URL: _OPDS})


def test_discover_returns_n_candidates_from_feed():
    fetcher = _feed_fetcher()
    cands = standard_ebooks.discover(fetcher, limit=2)
    assert len(cands) == 2
    titles = {c.title for c in cands}
    assert "Pride and Prejudice" in titles
    assert "Moby-Dick" in titles
    for c in cands:
        assert c.source == "standard_ebooks"
        assert c.source_id.startswith("standard_ebooks:")
        assert c.download_url.endswith(".epub")
        # PD established as a positive declaration, NOT a local content_class.
        assert c.pd_signal and "Standard Ebooks" in c.pd_signal


def test_discover_limit_caps_count():
    fetcher = _feed_fetcher()
    assert len(standard_ebooks.discover(fetcher, limit=1)) == 1


def test_classify_routes_to_public_domain_servable():
    """The verdict is classify()'s: a SE entry resolves to public_domain
    servable with a license_basis naming Standard Ebooks as the PD source."""
    fetcher = _feed_fetcher()
    (cand,) = standard_ebooks.discover(fetcher, limit=1)
    decision = cand.classification()
    assert decision.servable is True
    assert decision.content_class == "public_domain"
    assert decision.license_basis and "Standard Ebooks" in decision.license_basis


def test_ingest_fixture_epub_end_to_end_servable(temp_substrate, stub_embedder):
    """Ingest a fixture epub body end to end into a temp staging DB; the
    book_asset is servable with content_class=public_domain + a basis."""
    text_body = (
        "It is a truth universally acknowledged that a single man in "
        "possession of a good fortune must be in want of a wife. " * 30
    ).encode("utf-8")
    (cand,) = standard_ebooks.discover(_feed_fetcher(), limit=1)
    fetcher = FakeFetcher(bytes_by_url={cand.download_url: text_body})

    outcome = classify_and_ingest(
        cand, fetcher, db_path=temp_substrate["db_path"], embedder=stub_embedder
    )
    assert outcome.ingested is True
    assert outcome.content_class == "public_domain"
    assert outcome.servable is True
    assert outcome.servability == "public_domain"

    cc, basis, raw_text = book_asset_row(temp_substrate["db_path"], outcome.document_id)
    assert cc == "public_domain"
    assert basis and "Standard Ebooks" in basis
    assert raw_text and "universally acknowledged" in raw_text


def test_license_basis_names_standard_ebooks(temp_substrate, stub_embedder):
    """Every servable item carries a non-empty license_basis naming the PD
    source (defensibility #5)."""
    text_body = ("Call me Ishmael. " * 60).encode("utf-8")
    (cand,) = standard_ebooks.discover(_feed_fetcher(), limit=1)
    fetcher = FakeFetcher(bytes_by_url={cand.download_url: text_body})
    outcome = classify_and_ingest(
        cand, fetcher, db_path=temp_substrate["db_path"], embedder=stub_embedder
    )
    assert outcome.servable is True
    assert outcome.license_basis
    assert "Standard Ebooks" in outcome.license_basis


def test_no_raw_requests_uses_throttled_fetcher():
    """The real fetcher consults the SPR-03 throttle before each request — a
    banned source raises rather than hitting the network."""
    import time

    from substrate.source_throttle import SourceBanned, SourceThrottle

    class _BannedThrottle(SourceThrottle):
        def __init__(self):
            super().__init__(state_path="/tmp/nonexistent-se-test.json")

        def before_request(self, source):
            raise SourceBanned(source, time.time() + 999, time.time())

    fetcher = ThrottledFetcher(
        source="standard_ebooks", persistent=_BannedThrottle()
    )
    try:
        fetcher.get_text(standard_ebooks.OPDS_FEED_URL)
        assert False, "expected SourceBanned (no live network)"
    except SourceBanned:
        pass
