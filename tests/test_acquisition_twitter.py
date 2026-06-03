"""Tests for acquisition/twitter/ (Sprint 14)."""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import UTC, datetime

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from acquisition.twitter import (
    Tweet,
    TwitterThread,
    ingest_thread_payload,
    ingest_twitter_thread,
    twitter_doc_id,
)


class _StubEmbedder:
    def encode(self, text: str) -> list[float]:
        h = abs(hash(text)) % 64
        v = [0.0] * 16
        v[h % 16] = 1.0
        return v


@pytest.fixture
def temp_substrate(monkeypatch):
    tmp = tempfile.mkdtemp(prefix="antiek-x-test-")
    db_path = os.path.join(tmp, "graph.duckdb")
    events_dir = os.path.join(tmp, "events")
    os.makedirs(events_dir, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events_dir)
    yield {"db_path": db_path, "events_dir": events_dir, "tmpdir": tmp}


def _two_tweet_thread() -> TwitterThread:
    return TwitterThread(
        thread_url="https://x.com/foo/status/1234",
        root_tweet_id="1234",
        author_handle="foo",
        tweets=[
            Tweet(
                tweet_id="1234",
                text="This is the first substantive tweet about substrate compounding.",
                author_handle="foo",
                author_verified=True,
                posted_at=datetime(2026, 5, 18, tzinfo=UTC),
            ),
            Tweet(
                tweet_id="1235",
                text="And here is the reply explaining the multiplicative dynamics.",
                author_handle="foo",
                reply_to="1234",
                posted_at=datetime(2026, 5, 18, 0, 1, tzinfo=UTC),
            ),
        ],
    )


# ─────────────────────────────────────────────────────────────────────
# 1. Doc-id helper
# ─────────────────────────────────────────────────────────────────────


def test_twitter_doc_id_stable():
    assert twitter_doc_id("1234") == twitter_doc_id("1234")
    assert twitter_doc_id("1234").startswith("doc-x-")


def test_twitter_doc_id_distinct_per_root():
    assert twitter_doc_id("1234") != twitter_doc_id("5678")


def test_twitter_doc_id_empty_raises():
    with pytest.raises(ValueError):
        twitter_doc_id("")


# ─────────────────────────────────────────────────────────────────────
# 2. ingest_twitter_thread
# ─────────────────────────────────────────────────────────────────────


def test_ingest_writes_one_chunk_per_tweet(temp_substrate):
    import duckdb
    thread = _two_tweet_thread()
    r = ingest_twitter_thread(
        thread,
        investigation_id="inv-x-test",
        db_path=temp_substrate["db_path"],
        embedder=_StubEmbedder(),
    )
    assert r.skipped_reason is None
    assert r.chunks_written == 2  # one per tweet
    con = duckdb.connect(temp_substrate["db_path"])
    try:
        (doc_count,) = con.execute(
            "SELECT COUNT(*) FROM documents WHERE document_id = ?",
            [r.document_id],
        ).fetchone()
        (chunk_count,) = con.execute(
            "SELECT COUNT(*) FROM chunks WHERE document_id = ?",
            [r.document_id],
        ).fetchone()
        (doc_type,) = con.execute(
            "SELECT document_type FROM documents WHERE document_id = ?",
            [r.document_id],
        ).fetchone()
    finally:
        con.close()
    assert doc_count == 1
    assert chunk_count == 2
    assert doc_type == "social_thread"


def test_ingest_empty_thread_skipped(temp_substrate):
    thread = TwitterThread(
        thread_url="https://x.com/foo/status/1234",
        root_tweet_id="1234",
        author_handle="foo",
        tweets=[],
    )
    r = ingest_twitter_thread(
        thread,
        investigation_id="inv-x-test",
        db_path=temp_substrate["db_path"],
        embedder=_StubEmbedder(),
    )
    assert r.skipped_reason == "empty_thread"
    assert r.chunks_written == 0


def test_ingest_low_word_count_skipped(temp_substrate):
    thread = TwitterThread(
        thread_url="https://x.com/foo/status/1",
        root_tweet_id="1",
        author_handle="foo",
        tweets=[Tweet(tweet_id="1", text="hi", author_handle="foo")],
    )
    r = ingest_twitter_thread(
        thread,
        investigation_id="inv-x-test",
        db_path=temp_substrate["db_path"],
        embedder=_StubEmbedder(),
    )
    assert r.skipped_reason == "low_word_count"


def test_ingest_idempotent_on_same_root(temp_substrate):
    import duckdb
    thread = _two_tweet_thread()
    r1 = ingest_twitter_thread(
        thread, investigation_id="inv-x-test",
        db_path=temp_substrate["db_path"], embedder=_StubEmbedder(),
    )
    r2 = ingest_twitter_thread(
        thread, investigation_id="inv-x-test",
        db_path=temp_substrate["db_path"], embedder=_StubEmbedder(),
    )
    assert r1.document_id == r2.document_id
    con = duckdb.connect(temp_substrate["db_path"])
    try:
        (doc_count,) = con.execute(
            "SELECT COUNT(*) FROM documents WHERE document_id = ?",
            [r1.document_id],
        ).fetchone()
    finally:
        con.close()
    assert doc_count == 1


# ─────────────────────────────────────────────────────────────────────
# 3. ingest_thread_payload (extension entry point)
# ─────────────────────────────────────────────────────────────────────


def test_ingest_payload_parses_iso_timestamps(temp_substrate):
    import duckdb
    payload = {
        "thread_url": "https://x.com/foo/status/9999",
        "root_tweet_id": "9999",
        "author_handle": "foo",
        "tweets": [
            {
                "tweet_id": "9999",
                "text": "Substrate compounds nonlinearly per the prior thread.",
                "author_handle": "foo",
                "posted_at": "2026-05-18T14:30:00Z",
            },
            {
                "tweet_id": "10000",
                "text": "And here is the reply that elaborates the mechanism.",
                "author_handle": "foo",
                "posted_at": "2026-05-18T14:31:00Z",
                "reply_to": "9999",
            },
        ],
    }
    r = ingest_thread_payload(
        payload,
        investigation_id="inv-x-test",
        db_path=temp_substrate["db_path"],
        embedder=_StubEmbedder(),
    )
    assert r.chunks_written == 2
    con = duckdb.connect(temp_substrate["db_path"])
    try:
        (published_at,) = con.execute(
            "SELECT published_at FROM documents WHERE document_id = ?",
            [r.document_id],
        ).fetchone()
    finally:
        con.close()
    # DuckDB returns timezone-naive (we normalize to UTC at write time)
    assert published_at is not None


def test_ingest_payload_strips_leading_at(temp_substrate):
    """author_handle accepts '@foo' or 'foo'; the adapter strips."""
    payload = {
        "thread_url": "https://x.com/foo/status/1",
        "root_tweet_id": "1",
        "author_handle": "@foo",
        "tweets": [{
            "tweet_id": "1",
            "text": "Long enough thread substantive content here today.",
            "author_handle": "@foo",
        }],
    }
    r = ingest_thread_payload(
        payload, investigation_id="inv-x-test",
        db_path=temp_substrate["db_path"], embedder=_StubEmbedder(),
    )
    import duckdb
    con = duckdb.connect(temp_substrate["db_path"])
    try:
        (author,) = con.execute(
            "SELECT author FROM documents WHERE document_id = ?",
            [r.document_id],
        ).fetchone()
    finally:
        con.close()
    assert author == "foo"


# ─────────────────────────────────────────────────────────────────────
# 4. Personal-Reading Lane (SPR-02) — a social_thread lands personal_reading
#    on BOTH entry points (ingest_twitter_thread + ingest_thread_payload,
#    which routes through the former — rigor #3.ii: every insert site covered).
# ─────────────────────────────────────────────────────────────────────


def test_ingest_thread_lands_personal_reading(temp_substrate):
    """ingest_twitter_thread → content_class='personal_reading',
    document_type='social_thread'. Read back off the temp DB."""
    import duckdb

    r = ingest_twitter_thread(
        _two_tweet_thread(),
        investigation_id="inv-x-test",
        db_path=temp_substrate["db_path"],
        embedder=_StubEmbedder(),
    )
    assert r.skipped_reason is None
    con = duckdb.connect(temp_substrate["db_path"])
    try:
        (content_class, document_type) = con.execute(
            "SELECT content_class, document_type FROM documents WHERE document_id = ?",
            [r.document_id],
        ).fetchone()
    finally:
        con.close()
    assert content_class == "personal_reading", (
        "a third-party social_thread must land personal_reading, never a "
        f"servable default; got {content_class!r}"
    )
    assert document_type == "social_thread"
    from substrate.constants import PERSONAL_READING_CONTENT_CLASS, SERVABLE_CONTENT_CLASSES

    assert content_class == PERSONAL_READING_CONTENT_CLASS
    assert content_class not in SERVABLE_CONTENT_CLASSES


def test_ingest_payload_lands_personal_reading(temp_substrate):
    """ingest_thread_payload (the browser-extension entry point) inherits the
    lane because it routes through ingest_twitter_thread — confirmed by reading
    the row's content_class. This closes the 'second insert site' edge case
    (rigor #3.ii) without a second insert_document call existing."""
    import duckdb

    payload = {
        "thread_url": "https://x.com/foo/status/9999",
        "root_tweet_id": "9999",
        "author_handle": "foo",
        "tweets": [
            {
                "tweet_id": "9999",
                "text": "Substrate compounds nonlinearly per the prior thread.",
                "author_handle": "foo",
                "posted_at": "2026-05-18T14:30:00Z",
            },
            {
                "tweet_id": "10000",
                "text": "And here is the reply that elaborates the mechanism.",
                "author_handle": "foo",
                "posted_at": "2026-05-18T14:31:00Z",
                "reply_to": "9999",
            },
        ],
    }
    r = ingest_thread_payload(
        payload,
        investigation_id="inv-x-test",
        db_path=temp_substrate["db_path"],
        embedder=_StubEmbedder(),
    )
    con = duckdb.connect(temp_substrate["db_path"])
    try:
        (content_class, document_type) = con.execute(
            "SELECT content_class, document_type FROM documents WHERE document_id = ?",
            [r.document_id],
        ).fetchone()
    finally:
        con.close()
    assert content_class == "personal_reading"
    assert document_type == "social_thread"
