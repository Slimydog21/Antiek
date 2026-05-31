"""Tests for acquisition/youtube/ (Sprint 12).

Strategy: youtube-transcript-api + yt-dlp both make network calls;
substrate tests stay offline. We monkeypatch the fetch + transcript
functions inside the client module, then exercise the adapter
end-to-end against a temp substrate.
"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime, timezone
from typing import List

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from acquisition.youtube import (
    TranscriptSegment,
    YouTubeVideo,
    ingest_youtube,
    parse_video_id,
    youtube_doc_id,
)
from acquisition.youtube.adapter import (
    _format_timestamp,
    _group_transcript_into_chunks,
)


# ── 1. parse_video_id ──────────────────────────────────────────────


def test_parse_video_id_bare():
    assert parse_video_id("dQw4w9WgXcQ") == "dQw4w9WgXcQ"


def test_parse_video_id_watch_url():
    assert (
        parse_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=42s")
        == "dQw4w9WgXcQ"
    )


def test_parse_video_id_shortlink():
    assert parse_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"


def test_parse_video_id_embed():
    assert (
        parse_video_id("https://www.youtube.com/embed/dQw4w9WgXcQ")
        == "dQw4w9WgXcQ"
    )


def test_parse_video_id_invalid():
    assert parse_video_id("not a youtube url") is None
    assert parse_video_id("https://example.com") is None


# ── 2. Doc id ──────────────────────────────────────────────────────


def test_youtube_doc_id_format():
    assert youtube_doc_id("dQw4w9WgXcQ") == "doc-yt-dQw4w9WgXcQ"


def test_youtube_doc_id_empty_raises():
    with pytest.raises(ValueError):
        youtube_doc_id("")


# ── 3. Timestamp formatting ────────────────────────────────────────


def test_format_timestamp_zero():
    assert _format_timestamp(0) == "00:00:00"


def test_format_timestamp_under_hour():
    assert _format_timestamp(125.5) == "00:02:05"


def test_format_timestamp_over_hour():
    assert _format_timestamp(3725) == "01:02:05"


# ── 4. Transcript segmentation ─────────────────────────────────────


def test_segmentation_one_chunk_when_under_target():
    segs = [
        TranscriptSegment(text="hello world", start_seconds=0.0, duration_seconds=2.0),
        TranscriptSegment(text="more text here", start_seconds=2.0, duration_seconds=2.0),
    ]
    chunks = _group_transcript_into_chunks(segs, target_words=250)
    assert len(chunks) == 1
    assert "hello world" in chunks[0].text
    assert chunks[0].section.startswith("Timestamp: 00:00:00")


def test_segmentation_splits_at_target():
    # 60 segments of 5 words = 300 words; target 100 → 3 chunks
    segs = [
        TranscriptSegment(
            text="word1 word2 word3 word4 word5",
            start_seconds=float(i * 2),
            duration_seconds=2.0,
        )
        for i in range(60)
    ]
    chunks = _group_transcript_into_chunks(segs, target_words=100)
    assert len(chunks) == 3


def test_segmentation_empty_returns_empty():
    assert _group_transcript_into_chunks([], target_words=100) == []


# ── 5. End-to-end adapter via injected video record ────────────────


@pytest.fixture(autouse=True)
def _reset_youtube_rate_cap():
    """The YouTube fetch cap (SPR-07) is a per-PROCESS in-process counter
    (§16 box-bounded, no DB/daemon). Within one pytest process every test
    shares that module global, so the rate-cap tests would otherwise leave
    the counter advanced and trip YouTubeRateCapExceeded in a later test
    whose video reaches the live fetch() path. Reset before and after every
    test for deterministic, order-independent isolation."""
    from acquisition.youtube import reset_youtube_fetch_counter

    reset_youtube_fetch_counter()
    yield
    reset_youtube_fetch_counter()


@pytest.fixture
def temp_substrate(monkeypatch):
    tmp = tempfile.mkdtemp(prefix="antiek-yt-test-")
    db_path = os.path.join(tmp, "graph.duckdb")
    events_dir = os.path.join(tmp, "events")
    os.makedirs(events_dir, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events_dir)
    yield {"db_path": db_path, "events_dir": events_dir, "tmpdir": tmp}


class _StubEmbedder:
    def encode(self, text: str) -> List[float]:
        h = abs(hash(text)) % 64
        v = [0.0] * 16
        v[h % 16] = 1.0
        return v


def _fake_video(transcript_segments: int = 30) -> YouTubeVideo:
    segs = [
        TranscriptSegment(
            text=f"This is transcript segment number {i} with some real content.",
            start_seconds=float(i * 5),
            duration_seconds=5.0,
        )
        for i in range(transcript_segments)
    ]
    return YouTubeVideo(
        video_id="aaaaaaaaaaa",
        title="Test Video on Phased Array Radar",
        channel="Test Channel",
        duration_seconds=transcript_segments * 5,
        upload_date=datetime(2024, 1, 15, tzinfo=timezone.utc),
        description="A test video about radar concepts.",
        transcript=segs,
        transcript_source="youtube",
        watch_url="https://www.youtube.com/watch?v=aaaaaaaaaaa",
    )


def test_ingest_writes_documents_chunks_nodes(temp_substrate):
    import duckdb

    res = ingest_youtube(
        "doesntmatter",
        investigation_id="inv-yt-test",
        db_path=temp_substrate["db_path"],
        embedder=_StubEmbedder(),
        video=_fake_video(30),
    )
    assert res.skipped_reason is None
    assert res.document_id == "doc-yt-aaaaaaaaaaa"
    assert res.document_loaded_event_id is not None
    con = duckdb.connect(temp_substrate["db_path"])
    try:
        (doc_count,) = con.execute(
            "SELECT COUNT(*) FROM documents WHERE document_id = ?",
            [res.document_id],
        ).fetchone()
        (chunk_count,) = con.execute(
            "SELECT COUNT(*) FROM chunks WHERE document_id = ?",
            [res.document_id],
        ).fetchone()
    finally:
        con.close()
    assert doc_count == 1
    assert chunk_count == res.chunks_written
    assert chunk_count >= 1


def test_ingest_low_word_count_skipped(temp_substrate):
    """Tiny video should skip graph writes."""
    tiny = YouTubeVideo(
        video_id="bbbbbbbbbbb",
        title="Tiny",
        channel="C",
        duration_seconds=5,
        upload_date=None,
        description="",
        transcript=[
            TranscriptSegment(text="one two", start_seconds=0.0, duration_seconds=1.0),
        ],
        transcript_source="youtube",
        watch_url="https://www.youtube.com/watch?v=bbbbbbbbbbb",
    )
    res = ingest_youtube(
        "doesntmatter",
        investigation_id="inv-yt-test",
        db_path=temp_substrate["db_path"],
        embedder=_StubEmbedder(),
        video=tiny,
    )
    assert res.skipped_reason == "low_word_count"
    assert res.chunks_written == 0


def test_ingest_timestamp_section_paths(temp_substrate):
    """Chunk section_paths must encode timestamp ranges."""
    import duckdb

    res = ingest_youtube(
        "doesntmatter",
        investigation_id="inv-yt-test",
        db_path=temp_substrate["db_path"],
        embedder=_StubEmbedder(),
        video=_fake_video(30),
    )
    con = duckdb.connect(temp_substrate["db_path"])
    try:
        sections = con.execute(
            "SELECT section_path FROM chunks WHERE document_id = ? ORDER BY chunk_index",
            [res.document_id],
        ).fetchall()
    finally:
        con.close()
    assert all(
        s[0] and s[0].startswith("Timestamp: ") for s in sections
    ), sections


def test_ingest_idempotent_on_rows(temp_substrate):
    """Re-ingest of the same video → no new rows, second event still fires."""
    import duckdb

    video = _fake_video(30)
    r1 = ingest_youtube(
        "doesntmatter",
        investigation_id="inv-yt-test",
        db_path=temp_substrate["db_path"],
        embedder=_StubEmbedder(),
        video=video,
    )
    r2 = ingest_youtube(
        "doesntmatter",
        investigation_id="inv-yt-test",
        db_path=temp_substrate["db_path"],
        embedder=_StubEmbedder(),
        video=video,
    )
    assert r1.document_id == r2.document_id
    assert r1.chunk_ids == r2.chunk_ids
    assert r1.document_loaded_event_id != r2.document_loaded_event_id
    con = duckdb.connect(temp_substrate["db_path"])
    try:
        (doc_count,) = con.execute(
            "SELECT COUNT(*) FROM documents WHERE document_id = ?",
            [r1.document_id],
        ).fetchone()
    finally:
        con.close()
    assert doc_count == 1


# ── 6. Personal-Reading Lane (SPR-02) ──────────────────────────────


def test_ingest_video_transcript_lands_personal_reading(temp_substrate):
    """A third-party YouTube transcript fetched for the owner's reading lands
    content_class='personal_reading', document_type='video_transcript'. Read
    back off the temp DB (rigor #1 — proven, not assumed)."""
    import duckdb

    res = ingest_youtube(
        "doesntmatter",
        investigation_id="inv-yt-test",
        db_path=temp_substrate["db_path"],
        embedder=_StubEmbedder(),
        video=_fake_video(30),
    )
    assert res.skipped_reason is None
    con = duckdb.connect(temp_substrate["db_path"])
    try:
        (content_class, document_type) = con.execute(
            "SELECT content_class, document_type FROM documents WHERE document_id = ?",
            [res.document_id],
        ).fetchone()
    finally:
        con.close()
    assert content_class == "personal_reading", (
        "a third-party video_transcript must land personal_reading, never a "
        f"servable default; got {content_class!r}"
    )
    assert document_type == "video_transcript"
    from substrate.constants import PERSONAL_READING_CONTENT_CLASS, SERVABLE_CONTENT_CLASSES

    assert content_class == PERSONAL_READING_CONTENT_CLASS
    assert content_class not in SERVABLE_CONTENT_CLASSES


def test_ingest_video_transcript_lane_stable_on_reingest(temp_substrate):
    """on_conflict='ignore' on re-ingest must not flip content_class away from
    personal_reading."""
    import duckdb

    video = _fake_video(30)
    r1 = ingest_youtube(
        "doesntmatter",
        investigation_id="inv-yt-test",
        db_path=temp_substrate["db_path"],
        embedder=_StubEmbedder(),
        video=video,
    )
    ingest_youtube(
        "doesntmatter",
        investigation_id="inv-yt-test",
        db_path=temp_substrate["db_path"],
        embedder=_StubEmbedder(),
        video=video,
    )
    con = duckdb.connect(temp_substrate["db_path"])
    try:
        rows = con.execute(
            "SELECT content_class FROM documents WHERE document_id = ?",
            [r1.document_id],
        ).fetchall()
    finally:
        con.close()
    assert len(rows) == 1
    assert rows[0][0] == "personal_reading"


# ── 7. SPR-07 M1: default class proven, skip paths write no row ─────


def test_default_content_class_imported_constant_not_servable(temp_substrate):
    """Default ingest persists the personal-lane CONSTANT, which is absent
    from SERVABLE and present in NON_ATTRIBUTABLE — asserted by importing the
    frozensets, no DB serve call needed (rigor #3, mechanically checkable)."""
    import duckdb

    from substrate.collective_graph.eligibility import (
        NON_ATTRIBUTABLE_CONTENT_CLASSES,
    )
    from substrate.constants import (
        PERSONAL_READING_CONTENT_CLASS,
        SERVABLE_CONTENT_CLASSES,
    )

    res = ingest_youtube(
        "doesntmatter",
        investigation_id="inv-yt-test",
        db_path=temp_substrate["db_path"],
        embedder=_StubEmbedder(),
        video=_fake_video(30),
    )
    assert res.content_class == PERSONAL_READING_CONTENT_CLASS
    con = duckdb.connect(temp_substrate["db_path"])
    try:
        (cc,) = con.execute(
            "SELECT content_class FROM documents WHERE document_id = ?",
            [res.document_id],
        ).fetchone()
    finally:
        con.close()
    assert cc == PERSONAL_READING_CONTENT_CLASS
    assert cc not in SERVABLE_CONTENT_CLASSES
    assert cc in NON_ATTRIBUTABLE_CONTENT_CLASSES


def test_no_transcript_skip_writes_no_documents_row(temp_substrate):
    """The no_transcript early return must write ZERO documents rows, so a
    skipped ingest cannot leak a rights class (M1 acceptance)."""
    import duckdb

    # No transcript at all, but a description long enough to clear
    # min_word_count (50) so we do NOT hit the low_word_count branch —
    # we want to exercise the no_transcript branch specifically. The
    # description stays under min_word_count*4 (200) total markdown words
    # so word_count lands in [50, 200) and the no_transcript guard fires.
    long_desc = " ".join(f"word{i}" for i in range(80))  # 80 words, no captions
    no_caps = YouTubeVideo(
        video_id="ccccccccccc",
        title="No captions here",
        channel="C",
        duration_seconds=600,
        upload_date=None,
        description=long_desc,
        transcript=[],  # no transcript at all
        transcript_source="missing",
        watch_url="https://www.youtube.com/watch?v=ccccccccccc",
        caption_kind="missing",
    )
    res = ingest_youtube(
        "doesntmatter",
        investigation_id="inv-yt-test",
        db_path=temp_substrate["db_path"],
        embedder=_StubEmbedder(),
        video=no_caps,
    )
    # The MILESTONE contract (M1) is: a skipped ingest writes ZERO documents
    # rows, so it cannot leak a rights class. A no-captions video takes one of
    # the two skip branches (no_transcript / low_word_count) — BOTH return
    # before any insert_document and BOTH leave content_class=None. Assert the
    # load-bearing property, not which incidental branch label fired.
    assert res.skipped_reason in ("no_transcript", "low_word_count")
    assert res.content_class is None  # nothing persisted
    # The skip early-returns BEFORE ensure_initialized + any connect_write, so
    # for a fresh temp db the documents table may not even exist — itself proof
    # that zero rows (and zero rights classes) were written. Treat "table
    # absent" and "table present with 0 matching rows" identically.
    if not os.path.exists(temp_substrate["db_path"]):
        doc_count = 0
    else:
        con = duckdb.connect(temp_substrate["db_path"])
        try:
            tables = {
                r[0]
                for r in con.execute(
                    "SELECT table_name FROM information_schema.tables"
                ).fetchall()
            }
            if "documents" not in tables:
                doc_count = 0
            else:
                (doc_count,) = con.execute(
                    "SELECT COUNT(*) FROM documents WHERE document_id = ?",
                    [res.document_id],
                ).fetchone()
        finally:
            con.close()
    assert doc_count == 0


# ── 8. SPR-07 M2: operator-only rate cap ───────────────────────────


def test_rate_cap_at_cap_ok_then_over_cap_raises():
    """note_youtube_fetch allows exactly YOUTUBE_MAX_FETCHES_PER_RUN
    fetches per process; the (cap+1)-th raises YouTubeRateCapExceeded.
    In-process only — reset between assertions (rigor #3 boundary case)."""
    from acquisition.youtube import (
        YOUTUBE_MAX_FETCHES_PER_RUN,
        YouTubeRateCapExceeded,
        note_youtube_fetch,
        reset_youtube_fetch_counter,
    )

    reset_youtube_fetch_counter()
    try:
        # Exactly at the cap: no raise.
        for _ in range(YOUTUBE_MAX_FETCHES_PER_RUN):
            note_youtube_fetch()
        # One over the cap: raises.
        with pytest.raises(YouTubeRateCapExceeded):
            note_youtube_fetch()
    finally:
        reset_youtube_fetch_counter()


def test_rate_cap_resets_per_process():
    """Reset clears the in-process counter (no DB / daemon state)."""
    from acquisition.youtube import (
        YOUTUBE_MAX_FETCHES_PER_RUN,
        YouTubeRateCapExceeded,
        note_youtube_fetch,
        reset_youtube_fetch_counter,
    )

    reset_youtube_fetch_counter()
    for _ in range(YOUTUBE_MAX_FETCHES_PER_RUN):
        note_youtube_fetch()
    with pytest.raises(YouTubeRateCapExceeded):
        note_youtube_fetch()
    reset_youtube_fetch_counter()
    # Fresh budget after reset.
    assert note_youtube_fetch() == 1
    reset_youtube_fetch_counter()


# ── 9. SPR-07 M3: narrow CC-BY servable exception (both branches) ───


def test_cc_by_no_flag_stays_personal_reading_not_servable(temp_substrate):
    """No confirmation flag → personal_reading, not servable, empty basis."""
    import duckdb

    from substrate.constants import (
        PERSONAL_READING_CONTENT_CLASS,
        SERVABLE_CONTENT_CLASSES,
    )

    res = ingest_youtube(
        "doesntmatter",
        investigation_id="inv-yt-test",
        db_path=temp_substrate["db_path"],
        embedder=_StubEmbedder(),
        video=_fake_video(30),
        # operator_confirmed_cc_by defaults to False — the safe path.
    )
    assert res.content_class == PERSONAL_READING_CONTENT_CLASS
    con = duckdb.connect(temp_substrate["db_path"])
    try:
        # license_basis lives on book_assets (the column corpus_audit reads),
        # NOT on documents — LEFT JOIN so a personal_reading row with no
        # book_assets entry yields a NULL basis (which is the correct state:
        # the private lane carries no positive servable basis).
        (cc, basis) = con.execute(
            "SELECT d.content_class, b.license_basis "
            "FROM documents d LEFT JOIN book_assets b "
            "ON d.document_id = b.document_id "
            "WHERE d.document_id = ?",
            [res.document_id],
        ).fetchone()
    finally:
        con.close()
    assert cc == PERSONAL_READING_CONTENT_CLASS
    assert cc not in SERVABLE_CONTENT_CLASSES
    assert not basis  # no positive servable basis on the private lane


def test_cc_by_flag_promotes_to_source_declared_open_servable(temp_substrate):
    """operator_confirmed_cc_by=True → source_declared_open (servable) with a
    non-empty, truthful license_basis. Both proven by reading the temp DB."""
    import duckdb

    from substrate.constants import (
        SERVABLE_CONTENT_CLASSES,
        SOURCE_DECLARED_OPEN_CONTENT_CLASS,
    )

    res = ingest_youtube(
        "doesntmatter",
        investigation_id="inv-yt-test",
        db_path=temp_substrate["db_path"],
        embedder=_StubEmbedder(),
        video=_fake_video(30),
        operator_confirmed_cc_by=True,
    )
    assert res.content_class == SOURCE_DECLARED_OPEN_CONTENT_CLASS
    con = duckdb.connect(temp_substrate["db_path"])
    try:
        # license_basis is recorded on book_assets when a transcript is
        # promoted to a servable class — the exact column corpus_audit's
        # servable-basis / third-party-servable checks LEFT JOIN and read.
        (cc, basis) = con.execute(
            "SELECT d.content_class, b.license_basis "
            "FROM documents d LEFT JOIN book_assets b "
            "ON d.document_id = b.document_id "
            "WHERE d.document_id = ?",
            [res.document_id],
        ).fetchone()
    finally:
        con.close()
    assert cc == SOURCE_DECLARED_OPEN_CONTENT_CLASS
    assert cc in SERVABLE_CONTENT_CLASSES
    assert basis and "CC-BY" in basis  # truthful, non-empty positive basis


def test_cc_by_promotion_honored_even_with_auto_captions(temp_substrate):
    """Provenance and license are orthogonal: an auto-captioned video the
    operator confirms as CC-BY is still promoted (the CC-BY claim is about
    the video's license, not the caption track)."""
    import duckdb

    from substrate.constants import SOURCE_DECLARED_OPEN_CONTENT_CLASS

    auto_caps = _fake_video(30)
    # Rebuild with caption_kind="auto" (frozen dataclass).
    from dataclasses import replace

    auto_caps = replace(auto_caps, caption_kind="auto")
    res = ingest_youtube(
        "doesntmatter",
        investigation_id="inv-yt-test",
        db_path=temp_substrate["db_path"],
        embedder=_StubEmbedder(),
        video=auto_caps,
        operator_confirmed_cc_by=True,
    )
    assert res.content_class == SOURCE_DECLARED_OPEN_CONTENT_CLASS
    assert res.caption_kind == "auto"
    con = duckdb.connect(temp_substrate["db_path"])
    try:
        (cc,) = con.execute(
            "SELECT content_class FROM documents WHERE document_id = ?",
            [res.document_id],
        ).fetchone()
    finally:
        con.close()
    assert cc == SOURCE_DECLARED_OPEN_CONTENT_CLASS


# ── 10. SPR-07 M4: caption provenance (human/auto/unknown) round-trip


def _fake_video_with_caption_kind(kind: str) -> YouTubeVideo:
    from dataclasses import replace

    return replace(_fake_video(30), caption_kind=kind)


@pytest.mark.parametrize("kind", ["human", "auto", "unknown"])
def test_caption_kind_round_trips_into_metadata_and_result(
    temp_substrate, kind
):
    """A fake video's caption provenance round-trips into
    documents.metadata.caption_kind AND onto the result — no live network,
    set on the injected YouTubeVideo via the video= seam (M4 acceptance)."""
    import json

    import duckdb

    res = ingest_youtube(
        "doesntmatter",
        investigation_id="inv-yt-test",
        db_path=temp_substrate["db_path"],
        embedder=_StubEmbedder(),
        video=_fake_video_with_caption_kind(kind),
    )
    assert res.caption_kind == kind
    con = duckdb.connect(temp_substrate["db_path"])
    try:
        (meta_raw,) = con.execute(
            "SELECT metadata FROM documents WHERE document_id = ?",
            [res.document_id],
        ).fetchone()
    finally:
        con.close()
    meta = meta_raw if isinstance(meta_raw, dict) else json.loads(meta_raw)
    assert meta.get("caption_kind") == kind
    # transcript_source still co-exists (not clobbered).
    assert "transcript_source" in meta


def test_transcript_provenance_unknown_not_defaulted_to_human(temp_substrate):
    """Honesty (rigor #1): an 'unknown'-provenance track is persisted as
    'unknown', never silently upgraded to 'human'."""
    import json

    import duckdb

    res = ingest_youtube(
        "doesntmatter",
        investigation_id="inv-yt-test",
        db_path=temp_substrate["db_path"],
        embedder=_StubEmbedder(),
        video=_fake_video_with_caption_kind("unknown"),
    )
    assert res.caption_kind == "unknown"
    con = duckdb.connect(temp_substrate["db_path"])
    try:
        (meta_raw,) = con.execute(
            "SELECT metadata FROM documents WHERE document_id = ?",
            [res.document_id],
        ).fetchone()
    finally:
        con.close()
    meta = meta_raw if isinstance(meta_raw, dict) else json.loads(meta_raw)
    assert meta.get("caption_kind") == "unknown"
    assert meta.get("caption_kind") != "human"
