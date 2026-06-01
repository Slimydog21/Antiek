"""Tests for the Substack RSS acquisition connector (SPR-06).

No live network: feeds are inline RSS fixtures served via
``httpx.MockTransport``. The DB is a temp DuckDB initialized per test via
``ensure_initialized``. Embeddings use an injected stub (mirrors
``tests/test_acquisition_podcasts.py``).

Coverage maps to the SPR-06 milestones + verification gates:
- M1/M2: fixtured feed → personal_reading + dedup on GUID
- M3: truncation flagged, body never fabricated; full body stored verbatim
- M4: resolve_feed_url (substack/custom-domain/explicit), manifest loader
      errors, multi-publication driver + cross-feed idempotency
- lane invariants asserted directly
"""
from __future__ import annotations

import json
import os
import sys
from typing import List

import duckdb
import httpx
import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from acquisition import substack  # noqa: E402
from substrate import constants  # noqa: E402
from substrate.collective_graph import eligibility  # noqa: E402
from substrate.graph import ensure_initialized  # noqa: E402


# --------------------------------------------------------------------------
# Fixtures: inline RSS. Substack carries full body in content:encoded.
# --------------------------------------------------------------------------

_FULL_BODY = (
    "<p>This is a complete, fully-bodied essay with more than the minimum "
    "number of characters required to be considered a full post. It rambles "
    "on for a while about ideas, arguments, and conclusions, comfortably "
    "exceeding the short-body floor so the truncation heuristic leaves it "
    "alone. There is no paywall marker anywhere in this body at all.</p>"
)

FULL_FEED = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
  <channel>
    <title>Test Substack</title>
    <description>A subscribed publication</description>
    <item>
      <title>Full Post One</title>
      <guid>sub-guid-0001</guid>
      <link>https://test.substack.com/p/full-one</link>
      <author>Jane Author</author>
      <pubDate>Tue, 10 Jan 2023 12:00:00 GMT</pubDate>
      <content:encoded><![CDATA[{_FULL_BODY}]]></content:encoded>
    </item>
    <item>
      <title>Full Post Two</title>
      <guid>sub-guid-0002</guid>
      <link>https://test.substack.com/p/full-two</link>
      <author>Jane Author</author>
      <pubDate>Wed, 11 Jan 2023 12:00:00 GMT</pubDate>
      <content:encoded><![CDATA[{_FULL_BODY}]]></content:encoded>
    </item>
  </channel>
</rss>
"""

# A truncated paid post: the feed body ENDS at the paywall marker. There is
# deliberately NOTHING after the marker — proving we never fabricate a remainder.
_TRUNCATED_BODY = (
    "<p>Here is the free teaser opening of a paid post. It cuts off here.</p>"
    "<p>This post is for paid subscribers</p>"
)

TRUNCATED_FEED = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
  <channel>
    <title>Paid Substack</title>
    <item>
      <title>A Paywalled Post</title>
      <guid>sub-guid-paid-1</guid>
      <link>https://paid.substack.com/p/locked</link>
      <author>Paid Author</author>
      <pubDate>Thu, 12 Jan 2023 12:00:00 GMT</pubDate>
      <content:encoded><![CDATA[{_TRUNCATED_BODY}]]></content:encoded>
    </item>
  </channel>
</rss>
"""

# Custom-domain feed (not *.substack.com) that still exposes /feed; body only in
# <description>/summary (no content:encoded).
CUSTOM_DOMAIN_FEED = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Custom Domain Newsletter</title>
    <item>
      <title>Summary Only Post</title>
      <guid>cd-guid-0001</guid>
      <link>https://www.example-newsletter.com/p/post</link>
      <description><![CDATA[{_FULL_BODY}]]></description>
      <pubDate>Fri, 13 Jan 2023 12:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""

# A feed whose item has neither guid nor link — must be skipped, never minted.
NO_GUID_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>No GUID Substack</title>
    <item>
      <title>Anonymous Post</title>
      <description>Some body text here that is reasonably long enough.</description>
    </item>
  </channel>
</rss>
"""


class _StubEmbedder:
    def encode(self, text: str) -> List[float]:
        h = abs(hash(text)) % 64
        v = [0.0] * 16
        v[h % 16] = 1.0
        return v


def _mock_client(fixture: str) -> httpx.Client:
    """Single-fixture mock transport (mirrors podcast test)."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=fixture.encode("utf-8"))

    return httpx.Client(transport=httpx.MockTransport(handler), timeout=5.0)


def _routing_client(routes: dict) -> httpx.Client:
    """Multi-feed mock transport: route by request URL → fixture."""

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        for needle, fixture in routes.items():
            if needle in url:
                return httpx.Response(200, content=fixture.encode("utf-8"))
        return httpx.Response(404, content=b"<rss></rss>")

    return httpx.Client(transport=httpx.MockTransport(handler), timeout=5.0)


@pytest.fixture
def temp_db(tmp_path):
    db_path = str(tmp_path / "test.duckdb")
    ensure_initialized(db_path)
    return db_path


def _read_documents(db_path):
    con = duckdb.connect(db_path, read_only=True)
    try:
        rows = con.execute(
            "SELECT document_id, document_type, content_class, raw_text, metadata "
            "FROM documents ORDER BY document_id"
        ).fetchall()
    finally:
        con.close()
    return rows


# --------------------------------------------------------------------------
# M1: parsing + doc id
# --------------------------------------------------------------------------

def test_substack_doc_id_shape_and_empty():
    assert substack.substack_doc_id("g").startswith("doc-sub-")
    assert len(substack.substack_doc_id("g")) == len("doc-sub-") + 16
    with pytest.raises(ValueError):
        substack.substack_doc_id("")


def test_fetch_feed_parses_posts():
    client = _mock_client(FULL_FEED)
    pub = substack.fetch_feed("https://test.substack.com/feed", client=client)
    assert pub.title == "Test Substack"
    assert len(pub.posts) == 2
    assert pub.posts[0].guid == "sub-guid-0001"
    assert pub.posts[0].author == "Jane Author"
    assert pub.posts[0].published_at is not None
    assert "complete, fully-bodied essay" in pub.posts[0].body_markdown


def test_fetch_feed_skips_entry_with_no_guid_or_link():
    client = _mock_client(NO_GUID_FEED)
    pub = substack.fetch_feed("https://x.example.com/feed", client=client)
    # Rigor #3: no guid + no link → skipped, never minted.
    assert pub.posts == []


def test_custom_domain_summary_fallback_parses():
    client = _mock_client(CUSTOM_DOMAIN_FEED)
    pub = substack.fetch_feed(
        "https://www.example-newsletter.com/feed", client=client
    )
    assert len(pub.posts) == 1
    # Body falls back to <description>/summary when no content:encoded.
    assert "complete, fully-bodied essay" in pub.posts[0].body_markdown


# --------------------------------------------------------------------------
# M1/M2: ingest → personal_reading + dedup on GUID (gate: "ingest and dedup")
# --------------------------------------------------------------------------

def test_ingest_and_dedup_lands_personal_reading(temp_db):
    client = _mock_client(FULL_FEED)
    summary = substack.ingest_publication_feed(
        "https://test.substack.com/feed",
        investigation_id="inv-1",
        db_path=temp_db,
        embedder=_StubEmbedder(),
        client=client,
    )
    assert summary.ingested == 2
    assert summary.skipped == 0

    rows = _read_documents(temp_db)
    assert len(rows) == 2
    for (_id, dtype, cclass, _raw, _meta) in rows:
        assert dtype == "newsletter_post"
        # M2: lands personal_reading via the deny-by-default guard (option A).
        assert cclass == "personal_reading"

    # Capture chunk count after first ingest, so the re-ingest assertion below
    # compares a real BEFORE/AFTER rather than a value against itself.
    def _chunk_count(db):
        con = duckdb.connect(db, read_only=True)
        try:
            return con.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        finally:
            con.close()

    chunks_after_first = _chunk_count(temp_db)
    assert chunks_after_first > 0  # full bodies chunked

    # Re-ingest the SAME feed: zero new rows (on_conflict="ignore").
    client2 = _mock_client(FULL_FEED)
    summary2 = substack.ingest_publication_feed(
        "https://test.substack.com/feed",
        investigation_id="inv-1",
        db_path=temp_db,
        embedder=_StubEmbedder(),
        client=client2,
    )
    assert summary2.skipped == 2
    assert summary2.ingested == 0
    assert len(_read_documents(temp_db)) == 2
    # Chunk rows are unchanged across the re-ingest — a regression that
    # re-entered the chunk loop on a dedup would grow this count.
    assert _chunk_count(temp_db) == chunks_after_first


def test_dedup_is_document_keyed_not_chunk_keyed(temp_db):
    """The 'skipped' label must come from DOCUMENT presence, not chunk presence.

    Regression guard for the SPR-06 sharpen that moved the dedup probe from the
    chunks table to the documents table. We ingest a post, then DELETE its
    chunks while leaving the documents row in place, and re-ingest. Because the
    document row still exists, the re-ingest MUST report 'skipped' and MUST NOT
    re-enter the chunk loop. The OLD chunk-presence probe would see zero chunks,
    wrongly report 'ingested', and re-run the chunk loop — so this test bites on
    exactly that defect. This is also the real shape of an empty-bodied post
    (chunk_markdown('') -> [] leaves a document with zero chunks forever).
    """
    client = _mock_client(FULL_FEED)
    pub = substack.fetch_feed("https://test.substack.com/feed", client=client)
    post = pub.posts[0]
    document_id = substack.substack_doc_id(post.guid)

    first = substack.ingest_post(
        post,
        publication=pub,
        investigation_id="inv-dockey",
        db_path=temp_db,
        embedder=_StubEmbedder(),
    )
    assert first.status == "ingested"

    # Drop this document's chunks but keep the documents row, via the single
    # write lock (no second writer — §16).
    from runtime.db_lock import connect_write

    with connect_write(temp_db, purpose="test/teardown") as con:
        con.execute("DELETE FROM chunks WHERE document_id = ?", [document_id])
    con2 = duckdb.connect(temp_db, read_only=True)
    try:
        assert (
            con2.execute(
                "SELECT COUNT(*) FROM chunks WHERE document_id = ?", [document_id]
            ).fetchone()[0]
            == 0
        )
    finally:
        con2.close()

    # Re-ingest: the documents row still exists → must skip, must not re-chunk.
    second = substack.ingest_post(
        post,
        publication=pub,
        investigation_id="inv-dockey",
        db_path=temp_db,
        embedder=_StubEmbedder(),
    )
    assert second.status == "skipped"
    assert second.chunks_written == 0
    con3 = duckdb.connect(temp_db, read_only=True)
    try:
        # No chunks were re-created, and exactly one document row exists.
        assert (
            con3.execute(
                "SELECT COUNT(*) FROM chunks WHERE document_id = ?", [document_id]
            ).fetchone()[0]
            == 0
        )
        assert (
            con3.execute(
                "SELECT COUNT(*) FROM documents WHERE document_id = ?",
                [document_id],
            ).fetchone()[0]
            == 1
        )
    finally:
        con3.close()


# --------------------------------------------------------------------------
# Lane invariants (gate)
# --------------------------------------------------------------------------

def test_lane_invariants_hold():
    assert "personal_reading" not in constants.SERVABLE_CONTENT_CLASSES
    assert "personal_reading" in eligibility.NON_ATTRIBUTABLE_CONTENT_CLASSES


def test_newsletter_post_is_third_party_type():
    # M2 option-A precondition: the guard maps newsletter_post → personal_reading.
    assert "newsletter_post" in constants.THIRD_PARTY_DOCUMENT_TYPES


# --------------------------------------------------------------------------
# M3: truncation flagged, body never fabricated (gate: "truncat")
# --------------------------------------------------------------------------

def test_truncation_marker_flagged_and_body_not_fabricated(temp_db):
    client = _mock_client(TRUNCATED_FEED)
    summary = substack.ingest_publication_feed(
        "https://paid.substack.com/feed",
        investigation_id="inv-paid",
        db_path=temp_db,
        embedder=_StubEmbedder(),
        client=client,
    )
    assert summary.ingested == 1
    assert summary.truncated == 1

    rows = _read_documents(temp_db)
    assert len(rows) == 1
    (_id, _dtype, cclass, raw_text, meta_json) = rows[0]
    # Even a truncated post lands personal_reading (lawful partial read).
    assert cclass == "personal_reading"
    meta = json.loads(meta_json)
    assert meta["truncated"] is True
    assert meta["truncation_reason"] == "marker"
    # Body contains the partial text and NOTHING after the marker — no
    # fabricated continuation, no placeholder lorem (rigor #1).
    assert "free teaser opening" in raw_text
    assert "this post is for paid subscribers" in raw_text.lower()
    after = raw_text.lower().split("this post is for paid subscribers", 1)[1]
    assert after.strip() == ""


def test_truncated_post_makes_no_public_page_backfill_request(temp_db):
    """A truncated paid post must be stored verbatim from the FEED — the
    connector must never make a second request to backfill the paid remainder
    from the public web page (rigor #1; the §9.0 acquisition-ToS line).

    We count every HTTP request the connector issues. Exactly ONE request is
    allowed (the feed GET); any second request — the kind a public-page
    backfill would make — fails this test. We also re-assert that the stored
    body ends at the marker, so 'no backfill request' is paired with 'no
    fabricated body'.
    """
    requests_seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests_seen.append(str(request.url))
        return httpx.Response(200, content=TRUNCATED_FEED.encode("utf-8"))

    client = httpx.Client(transport=httpx.MockTransport(handler), timeout=5.0)
    substack.ingest_publication_feed(
        "https://paid.substack.com/feed",
        investigation_id="inv-no-backfill",
        db_path=temp_db,
        embedder=_StubEmbedder(),
        client=client,
    )
    # Exactly the feed fetch — no public-page backfill round-trip.
    assert len(requests_seen) == 1
    assert requests_seen[0].endswith("/feed")

    rows = _read_documents(temp_db)
    (_id, _dtype, _cclass, raw_text, _meta) = rows[0]
    after = raw_text.lower().split("this post is for paid subscribers", 1)[1]
    assert after.strip() == ""


def test_truncation_full_post_not_flagged_body_verbatim(temp_db):
    # Capture the expected markdown the same way the connector renders it.
    fetch_client = _mock_client(FULL_FEED)
    pub = substack.fetch_feed(
        "https://test.substack.com/feed", client=fetch_client
    )
    post = pub.posts[0]  # "Full Post One", guid sub-guid-0001
    expected_md = post.body_markdown
    expected_doc_id = substack.substack_doc_id(post.guid)
    assert post.truncated is False
    assert post.truncation_reason == "none"

    client = _mock_client(FULL_FEED)
    substack.ingest_publication_feed(
        "https://test.substack.com/feed",
        investigation_id="inv-full",
        db_path=temp_db,
        embedder=_StubEmbedder(),
        client=client,
    )
    # Look up the SPECIFIC document by its deterministic doc id — _read_documents
    # orders by document_id (a sha256-derived id), which is NOT the feed order,
    # so we must select the row we captured expected_md from rather than rows[0].
    rows = {r[0]: r for r in _read_documents(temp_db)}
    assert expected_doc_id in rows
    (_id, _dtype, _cclass, raw_text, meta_json) = rows[expected_doc_id]
    meta = json.loads(meta_json)
    assert meta["truncated"] is False
    assert meta["truncation_reason"] == "none"
    # Full body stored verbatim: the stored raw_text is EXACTLY the markdown the
    # connector rendered from the feed body (no padding, no fabrication).
    assert raw_text == expected_md


def test_detect_truncation_unit():
    # Marker hit (primary signal).
    t, r = substack.detect_truncation(
        body_markdown="intro. subscribe to keep reading", summary_html=""
    )
    assert t is True and r == "marker"
    # Short body with a longer summary (secondary signal).
    t, r = substack.detect_truncation(
        body_markdown="tiny", summary_html="a" * 500
    )
    assert t is True and r == "short_body"
    # Short body but NO longer summary → not flagged (avoids false positives).
    t, r = substack.detect_truncation(body_markdown="tiny", summary_html="")
    assert t is False and r == "none"
    # Long clean body → not flagged.
    t, r = substack.detect_truncation(
        body_markdown="x" * 1000, summary_html="short"
    )
    assert t is False and r == "none"


# --------------------------------------------------------------------------
# M4: resolve_feed_url (gate: "resolve_feed_url or custom_domain")
# --------------------------------------------------------------------------

def test_resolve_feed_url_substack_base():
    assert (
        substack.resolve_feed_url({"base_url": "https://x.substack.com"})
        == "https://x.substack.com/feed"
    )


def test_resolve_feed_url_custom_domain_base():
    # Custom domain (not *.substack.com) still gets /feed appended.
    assert (
        substack.resolve_feed_url(
            {"base_url": "https://www.example-newsletter.com/"}
        )
        == "https://www.example-newsletter.com/feed"
    )


def test_resolve_feed_url_explicit_feed_url_wins():
    assert (
        substack.resolve_feed_url(
            {"feed_url": "https://x.substack.com/feed", "base_url": "ignored"}
        )
        == "https://x.substack.com/feed"
    )


def test_resolve_feed_url_base_already_has_feed_suffix():
    assert (
        substack.resolve_feed_url({"base_url": "https://x.substack.com/feed"})
        == "https://x.substack.com/feed"
    )


def test_resolve_feed_url_no_basis_raises():
    with pytest.raises(substack.SubscriptionManifestError):
        substack.resolve_feed_url({"name": "no urls"})


# --------------------------------------------------------------------------
# M4: manifest loader + malformed-entry error naming
# --------------------------------------------------------------------------

def test_load_subscriptions_parses_example_shape(tmp_path):
    manifest = {
        "publications": [
            {"name": "Sub A", "base_url": "https://a.substack.com"},
            {"name": "Sub B", "feed_url": "https://b.substack.com/feed"},
            {
                "name": "Custom",
                "base_url": "https://www.c.com",
                "source_tier": 4,
            },
        ]
    }
    path = tmp_path / "subs.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    subs = substack.load_subscriptions(str(path))
    assert [s.feed_url for s in subs] == [
        "https://a.substack.com/feed",
        "https://b.substack.com/feed",
        "https://www.c.com/feed",
    ]


def test_load_subscriptions_malformed_entry_names_offender(tmp_path):
    manifest = {
        "publications": [
            {"name": "Good", "base_url": "https://good.substack.com"},
            {"name": "Bad Entry No Feed"},  # neither feed_url nor base_url
        ]
    }
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(substack.SubscriptionManifestError) as exc:
        substack.load_subscriptions(str(path))
    # Error names the offending entry (not a bare KeyError).
    assert "Bad Entry No Feed" in str(exc.value)
    assert not isinstance(exc.value, KeyError)


def test_load_subscriptions_missing_name_raises(tmp_path):
    manifest = {"publications": [{"base_url": "https://x.substack.com"}]}
    path = tmp_path / "noname.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(substack.SubscriptionManifestError) as exc:
        substack.load_subscriptions(str(path))
    assert "name" in str(exc.value)


def test_example_manifest_loads_cleanly():
    here = os.path.dirname(substack.__file__)
    path = os.path.join(here, "subscriptions.example.json")
    subs = substack.load_subscriptions(path)
    # The shipped example resolves three entries with no live network.
    assert len(subs) == 3
    for s in subs:
        assert s.feed_url.endswith("/feed")


# --------------------------------------------------------------------------
# M4: multi-publication driver + cross-feed GUID idempotency
# --------------------------------------------------------------------------

def test_ingest_subscriptions_two_feeds(tmp_path, temp_db):
    manifest = {
        "publications": [
            {"name": "Full", "feed_url": "https://test.substack.com/feed"},
            {"name": "Paid", "feed_url": "https://paid.substack.com/feed"},
        ]
    }
    mpath = tmp_path / "m.json"
    mpath.write_text(json.dumps(manifest), encoding="utf-8")

    client = _routing_client(
        {
            "test.substack.com": FULL_FEED,
            "paid.substack.com": TRUNCATED_FEED,
        }
    )
    summaries = substack.ingest_subscriptions(
        str(mpath),
        investigation_id="inv-multi",
        db_path=temp_db,
        embedder=_StubEmbedder(),
        client=client,
    )
    assert len(summaries) == 2
    total_ingested = sum(s.ingested for s in summaries)
    total_truncated = sum(s.truncated for s in summaries)
    assert total_ingested == 3  # 2 full + 1 paid
    assert total_truncated == 1
    assert len(_read_documents(temp_db)) == 3


def test_cross_feed_duplicate_guid_written_once(tmp_path, temp_db):
    # Same GUID appearing in two feeds in one run → written exactly once.
    dup_feed_a = FULL_FEED.replace("sub-guid-0002", "shared-guid")
    dup_feed_b = TRUNCATED_FEED.replace("sub-guid-paid-1", "shared-guid")
    manifest = {
        "publications": [
            {"name": "A", "feed_url": "https://a.substack.com/feed"},
            {"name": "B", "feed_url": "https://b.substack.com/feed"},
        ]
    }
    mpath = tmp_path / "dup.json"
    mpath.write_text(json.dumps(manifest), encoding="utf-8")
    client = _routing_client(
        {"a.substack.com": dup_feed_a, "b.substack.com": dup_feed_b}
    )
    substack.ingest_subscriptions(
        str(mpath),
        investigation_id="inv-dup",
        db_path=temp_db,
        embedder=_StubEmbedder(),
        client=client,
    )
    rows = _read_documents(temp_db)
    ids = [r[0] for r in rows]
    # shared-guid maps to one doc id, written exactly once.
    shared_id = substack.substack_doc_id("shared-guid")
    assert ids.count(shared_id) == 1
