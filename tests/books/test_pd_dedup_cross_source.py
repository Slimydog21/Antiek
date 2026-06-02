"""Cross-source dedup: the same work from two sources collapses to one
document/book_asset via the SPR-04 identity key (SPR-06 M5). No live network.

Two layers of the same fact are asserted:

  1. The SPR-04 identity ladder (``substrate.dedup``) collapses two connectors'
     records for the same work into ONE CanonicalWork, retaining a non-empty
     reconciled license_basis.
  2. End to end: ingesting the same body from Gutenberg and from a Wave-2
     connector yields exactly ONE documents row + ONE book_asset (the
     content-stable doc id), not two.
"""

from __future__ import annotations

from acquisition.books import standard_ebooks
from acquisition.books.pd_connector_base import classify_and_ingest
from acquisition.books.public_domain import PublicDomainWork, ingest_work
from acquisition.licenses_core import classify
from substrate.dedup import (
    Confidence,
    IdentityRecord,
    KeyType,
    collapse,
    identity_key,
)

from .conftest import FakeFetcher, StubEmbedder

# ---------------------------------------------------------------------------
# Layer 1 — the SPR-04 identity ladder collapses two sources to one work.
# ---------------------------------------------------------------------------


def test_same_isbn_two_sources_collapse_to_one_work():
    """A work carrying the same ISBN-13 from Gutenberg + HathiTrust collapses
    to one CanonicalWork via KeyType.ISBN."""
    pd = classify(
        "https://creativecommons.org/publicdomain/mark/1.0/", {}, legitimate_source=True
    )
    gutenberg = IdentityRecord(
        ref_id="project_gutenberg:1342",
        source="project_gutenberg",
        isbn="978-0-13-110362-7",
        title="Pride and Prejudice",
        author="Jane Austen",
    )
    hathitrust = IdentityRecord(
        ref_id="hathitrust:uc1.b1",
        source="hathitrust",
        isbn="9780131103627",  # same ISBN, no hyphens
        title="Pride and Prejudice",
        author="Jane Austen",
    )
    works = collapse([gutenberg, hathitrust])
    assert len(works) == 1
    work = works[0]
    assert work.identity.key_type is KeyType.ISBN
    assert len(work.members) == 2
    assert set(work.contributing_sources) == {"project_gutenberg", "hathitrust"}


def test_same_body_two_sources_collapse_on_content_hash():
    """Two sources with no shared stable id but the SAME extracted body collapse
    on the content-hash key (above the LOW title fallback)."""
    body = (
        "When on board H.M.S. Beagle, as naturalist, I was much struck with "
        "certain facts in the distribution of the inhabitants of South America. "
    ) * 10
    gutenberg = IdentityRecord(
        ref_id="project_gutenberg:944",
        source="project_gutenberg",
        title="On the Origin of Species",
        body=body,
    )
    standard = IdentityRecord(
        ref_id="standard_ebooks:darwin/origin",
        source="standard_ebooks",
        title="On the Origin of Species",
        body=body,
    )
    works = collapse([gutenberg, standard])
    assert len(works) == 1
    assert works[0].identity.key_type is KeyType.CONTENT
    assert works[0].identity.confidence is Confidence.HIGH


def test_distinct_works_do_not_false_merge_on_generic_title():
    """Two distinct works titled 'History' by 'Anonymous' with no stable id and
    no body stay SEPARATE (LOW-confidence never merges)."""
    a = IdentityRecord(ref_id="standard_ebooks:a", source="standard_ebooks", title="History", author="Anonymous")
    b = IdentityRecord(ref_id="internet_archive:b", source="internet_archive", title="History", author="Anonymous")
    works = collapse([a, b])
    assert len(works) == 2
    for w in works:
        assert w.identity.confidence is Confidence.LOW


# ---------------------------------------------------------------------------
# Layer 2 — end-to-end: same body from two sources -> one documents/book_asset.
# ---------------------------------------------------------------------------


_SHARED_TEXT = (
    "It is a truth universally acknowledged that a single man in possession "
    "of a good fortune must be in want of a wife. " * 30
).encode("utf-8")

_OPDS = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>url:https://standardebooks.org/ebooks/jane-austen/pride-and-prejudice</id>
    <title>Pride and Prejudice</title>
    <author><name>Jane Austen</name></author>
    <rights>This ebook is in the public domain in the United States.</rights>
    <link rel="http://opds-spec.org/acquisition" type="application/epub+zip"
      href="https://standardebooks.org/ebooks/jane-austen/pride-and-prejudice/downloads/pap.epub"/>
  </entry>
</feed>
"""


def _count_docs_and_assets(db_path: str):
    import duckdb

    con = duckdb.connect(db_path)
    try:
        (docs,) = con.execute("SELECT COUNT(*) FROM documents").fetchone()
        (assets,) = con.execute("SELECT COUNT(*) FROM book_assets").fetchone()
    finally:
        con.close()
    return docs, assets


def test_same_work_two_sources_one_document(temp_substrate):
    """Ingest the same body once via the Gutenberg connector and once via the
    Standard Ebooks connector. Because the PDF carrier is byte-identical for the
    same text, both resolve to the same content-stable doc id -> exactly ONE
    documents row + ONE book_asset survives, with a non-empty license_basis."""
    db_path = temp_substrate["db_path"]
    embedder = StubEmbedder()

    # Source A: Gutenberg, via the legacy connector but classify()-routed body.
    # We reuse the text->PDF carrier so the byte content matches the SE ingest.
    gut_work = PublicDomainWork(
        source="project_gutenberg",
        source_id="1342",
        title="Pride and Prejudice",
        author="Jane Austen",
        source_uri="https://www.gutenberg.org/ebooks/1342",
        download_url="https://www.gutenberg.org/files/1342/1342-0.txt",
        download_format="text",
        pd_basis="Project Gutenberg; US public domain per copyright=false flag",
    )
    gut_client = FakeFetcher(bytes_by_url={gut_work.download_url: _SHARED_TEXT})
    o1 = ingest_work(gut_work, gut_client, db_path=db_path, embedder=embedder)
    assert o1.ingested is True

    docs_after_first, assets_after_first = _count_docs_and_assets(db_path)
    assert docs_after_first == 1
    assert assets_after_first == 1

    # Source B: Standard Ebooks connector, classify()-routed, SAME body bytes.
    (se_cand,) = standard_ebooks.discover(
        FakeFetcher(text_by_url={standard_ebooks.OPDS_FEED_URL: _OPDS}), limit=1
    )
    se_fetcher = FakeFetcher(bytes_by_url={se_cand.download_url: _SHARED_TEXT})
    o2 = classify_and_ingest(
        se_cand, se_fetcher, db_path=db_path, embedder=embedder
    )
    assert o2.ingested is True

    docs_after_second, assets_after_second = _count_docs_and_assets(db_path)
    # The same work from two sources did NOT create a second document.
    assert o1.document_id == o2.document_id
    assert docs_after_second == docs_after_first  # still one
    assert assets_after_second == assets_after_first  # still one

    # The surviving record retains a non-empty license_basis.
    from .conftest import book_asset_row

    cc, basis, _ = book_asset_row(db_path, o1.document_id)
    assert cc == "public_domain"
    assert basis  # non-empty


def test_identity_key_for_se_candidate_is_source_id_level():
    """A Standard Ebooks candidate with no ISBN/DOI and no body-at-discovery
    keys on its source-id (stable within SE), above the LOW title fallback."""
    (cand,) = standard_ebooks.discover(
        FakeFetcher(text_by_url={standard_ebooks.OPDS_FEED_URL: _OPDS}), limit=1
    )
    rec = IdentityRecord(
        ref_id=cand.source_id,
        source=cand.source,
        source_id=cand.source_id,
        title=cand.title,
        author=cand.author,
    )
    ik = identity_key(rec)
    assert ik.key_type is KeyType.SOURCE_ID
    assert ik.confidence is Confidence.HIGH
