"""Ingest-path tests for the research bridge.

Covers the load-bearing invariants from SPR-01:

- Round-trip byte equality (the documents.raw_text matches the input
  byte-for-byte across every fixture).
- Single-writer invariant (only one INSERT statement target the
  research_pastes table, and it lives in ingest.py).
- Append-only audit (no UPDATE / DELETE statements in the research
  bridge module).
- Idempotency (paste-same-bytes twice does not create two document
  rows; the audit log captures both calls).
- Size limits (PasteTooLargeError; PasteEmptyError).
- Source override path.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import duckdb
import pytest

from runtime.db_lock import connect_write
from substrate.research_bridge.ingest import (
    DEFAULT_PASTE_TIER,
    MAX_PASTE_BYTES,
    PASTE_DOCUMENT_TYPE,
    PasteEmptyError,
    PasteTooLargeError,
    ingest_paste,
)
from substrate.research_bridge.paste_log import list_paste_events
from substrate.research_bridge.source_detection import KNOWN_SOURCES


def _paste(db_path: Path, **kwargs):
    """Convenience wrapper that acquires a lock, calls ingest, and
    closes. Mirrors how the API route uses it.
    """
    con = connect_write(str(db_path), purpose="test_ingest_paste")
    try:
        return ingest_paste(con, **kwargs)
    finally:
        con.close()


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("source", ["chatgpt", "anthropic", "grok", "alphasense"])
def test_round_trip_byte_equality(
    tmp_db_with_bridge: Path, fixture_text, source: str
) -> None:
    """The load-bearing test of SPR-01. Every byte of raw_text is
    preserved across paste → DB → read.
    """
    text = fixture_text(source)
    result = _paste(tmp_db_with_bridge, raw_text=text, call_site="test")
    assert result.source == source, (
        f"fixture '{source}' classified as '{result.source}'"
    )

    con = duckdb.connect(str(tmp_db_with_bridge), read_only=True)
    try:
        row = con.execute(
            "SELECT raw_text FROM documents WHERE document_id = ?",
            [result.document_id],
        ).fetchone()
    finally:
        con.close()
    assert row is not None
    assert row[0] == text, (
        f"round-trip mismatch for '{source}': "
        f"input {len(text)} bytes, output {len(row[0])} bytes"
    )


def test_round_trip_with_non_ascii(tmp_db_with_bridge: Path) -> None:
    """Smart quotes, em-dashes, footnote markers — verbatim or bust."""
    text = (
        "## Smart-quote test — em-dash here\n\n"
        "“This is a curly-quoted sentence,” the author wrote, "
        "with a footnote marker¹ and an en–dash.\n\n"
        "Bullets:\n"
        "• one\n"
        "• two\n"
        "• three\n\n"
        "Currency: $1,234.56 and €987,65.\n\n"
        "[1] References\n"
        "[2] More references\n"
        "[3] Yet more references\n\n"
        "## End\n"
    )
    result = _paste(tmp_db_with_bridge, raw_text=text, call_site="test")

    con = duckdb.connect(str(tmp_db_with_bridge), read_only=True)
    try:
        row = con.execute(
            "SELECT raw_text FROM documents WHERE document_id = ?",
            [result.document_id],
        ).fetchone()
    finally:
        con.close()
    assert row is not None
    assert row[0] == text
    # And the SHA matches the raw bytes.
    import hashlib
    assert result.raw_sha256 == hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Single-writer invariant
# ---------------------------------------------------------------------------


def test_single_writer_invariant() -> None:
    """Grep proves: exactly one INSERT INTO research_pastes statement
    in the entire codebase, in ingest.py.

    If this test fails, someone added a second writer. Refuse to ship
    until reconverged to one call site.
    """
    repo = Path(__file__).resolve().parents[2]
    # Match the actual SQL string literal — leading double quote
    # eliminates docstring references to this invariant.
    out = subprocess.run(
        ["rg", "--no-heading", "-n", '"INSERT INTO research_pastes', str(repo)],
        capture_output=True, text=True, check=False,
    )
    # rg returns 1 when no matches; turn it into an empty result.
    matches = out.stdout.strip().splitlines() if out.returncode == 0 else []
    # Exclude .venv, __pycache__, .git, and any virtualenv contents,
    # and exclude this test file itself.
    matches = [
        m for m in matches
        if "/.venv/" not in m
        and "/__pycache__/" not in m
        and "/.git/" not in m
        and "tests/research_bridge/test_ingest.py" not in m
    ]
    assert len(matches) == 1, (
        f"expected exactly one INSERT INTO research_pastes in code, found "
        f"{len(matches)}: {matches}"
    )
    # And the one match must be in ingest.py.
    assert "substrate/research_bridge/ingest.py" in matches[0], (
        f"single INSERT INTO research_pastes lives outside ingest.py: {matches[0]}"
    )


def test_paste_events_append_only_in_code() -> None:
    """No UPDATE or DELETE statements in the research_bridge module
    target the paste_events table. The audit row is sacred.
    """
    bridge_dir = Path(__file__).resolve().parents[2] / "substrate" / "research_bridge"
    bad_patterns = [
        "UPDATE research_paste_events",
        "DELETE FROM research_paste_events",
    ]
    for f in bridge_dir.rglob("*.py"):
        text = f.read_text(encoding="utf-8")
        for pat in bad_patterns:
            assert pat not in text, (
                f"found append-only violation '{pat}' in {f}"
            )


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


def test_repeat_paste_same_bytes_is_idempotent_at_document(
    tmp_db_with_bridge: Path, fixture_text
) -> None:
    text = fixture_text("anthropic")
    r1 = _paste(tmp_db_with_bridge, raw_text=text, call_site="test1")
    r2 = _paste(tmp_db_with_bridge, raw_text=text, call_site="test2")

    # Same document_id (content-addressed).
    assert r1.document_id == r2.document_id

    con = duckdb.connect(str(tmp_db_with_bridge), read_only=True)
    try:
        n_docs = con.execute(
            "SELECT COUNT(*) FROM documents WHERE document_id = ?",
            [r1.document_id],
        ).fetchone()[0]
        n_pastes = con.execute(
            "SELECT COUNT(*) FROM research_pastes WHERE document_id = ?",
            [r1.document_id],
        ).fetchone()[0]
        events = list_paste_events(con, document_id=r1.document_id)
    finally:
        con.close()

    assert n_docs == 1, "duplicate documents row on re-paste"
    assert n_pastes == 1, "duplicate research_pastes row on re-paste"
    # But TWO audit events — re-paste IS an event, even if no new row.
    assert len(events) == 2, f"expected 2 audit events, got {len(events)}"
    assert {e.call_site for e in events} == {"test1", "test2"}


def test_extractor_cache_lookup_by_sha_works(
    tmp_db_with_bridge: Path, fixture_text
) -> None:
    """SPR-02's extractor cache pivots on (raw_sha256, parser_version).
    Verify the column we'll JOIN against is populated and indexed.
    """
    text = fixture_text("alphasense")
    r = _paste(tmp_db_with_bridge, raw_text=text)

    con = duckdb.connect(str(tmp_db_with_bridge), read_only=True)
    try:
        row = con.execute(
            "SELECT raw_sha256, parser_version FROM research_pastes "
            "WHERE document_id = ?",
            [r.document_id],
        ).fetchone()
    finally:
        con.close()
    assert row is not None
    assert row[0] == r.raw_sha256
    assert row[1] == r.parser_version


# ---------------------------------------------------------------------------
# Documents-side correctness
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("source", ["chatgpt", "anthropic", "grok", "alphasense"])
def test_documents_row_has_external_deep_research_type(
    tmp_db_with_bridge: Path, fixture_text, source: str
) -> None:
    r = _paste(tmp_db_with_bridge, raw_text=fixture_text(source))
    con = duckdb.connect(str(tmp_db_with_bridge), read_only=True)
    try:
        row = con.execute(
            "SELECT document_type, source_tier FROM documents WHERE document_id = ?",
            [r.document_id],
        ).fetchone()
    finally:
        con.close()
    assert row is not None
    assert row[0] == PASTE_DOCUMENT_TYPE
    assert row[1] == DEFAULT_PASTE_TIER


def test_chunks_are_created(tmp_db_with_bridge: Path, fixture_text) -> None:
    text = fixture_text("alphasense")
    r = _paste(tmp_db_with_bridge, raw_text=text)
    assert len(r.chunk_ids) >= 1, "expected at least one chunk"

    con = duckdb.connect(str(tmp_db_with_bridge), read_only=True)
    try:
        n_chunks = con.execute(
            "SELECT COUNT(*) FROM chunks WHERE document_id = ?",
            [r.document_id],
        ).fetchone()[0]
        # Re-assemble chunks; they should cover (most of) the raw text,
        # though we don't require strict byte-coverage — raw is the
        # source of truth, chunks are derived for retrieval.
        chunks = con.execute(
            "SELECT text FROM chunks WHERE document_id = ? ORDER BY chunk_index",
            [r.document_id],
        ).fetchall()
    finally:
        con.close()
    assert n_chunks == len(r.chunk_ids)
    # Each chunk is non-empty.
    for (c,) in chunks:
        assert c.strip(), "found empty chunk"


def test_skip_chunking_when_do_chunk_false(
    tmp_db_with_bridge: Path, fixture_text
) -> None:
    r = _paste(
        tmp_db_with_bridge,
        raw_text=fixture_text("chatgpt"),
        do_chunk=False,
    )
    assert r.chunk_ids == ()
    con = duckdb.connect(str(tmp_db_with_bridge), read_only=True)
    try:
        n_chunks = con.execute(
            "SELECT COUNT(*) FROM chunks WHERE document_id = ?",
            [r.document_id],
        ).fetchone()[0]
    finally:
        con.close()
    assert n_chunks == 0


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


def test_empty_paste_raises(tmp_db_with_bridge: Path) -> None:
    with pytest.raises(PasteEmptyError):
        _paste(tmp_db_with_bridge, raw_text="   \n\n  \t  ")


def test_oversized_paste_raises(tmp_db_with_bridge: Path) -> None:
    """A paste above MAX_PASTE_BYTES raises before touching the DB."""
    too_big = "x" * (MAX_PASTE_BYTES + 1)
    with pytest.raises(PasteTooLargeError):
        _paste(tmp_db_with_bridge, raw_text=too_big)

    # Verify the DB is unchanged.
    con = duckdb.connect(str(tmp_db_with_bridge), read_only=True)
    try:
        n = con.execute("SELECT COUNT(*) FROM research_pastes").fetchone()[0]
    finally:
        con.close()
    assert n == 0


def test_unknown_source_override_rejected(
    tmp_db_with_bridge: Path, fixture_text
) -> None:
    with pytest.raises(ValueError, match="not in KNOWN_SOURCES"):
        _paste(
            tmp_db_with_bridge,
            raw_text=fixture_text("chatgpt"),
            source_override="hypothetical_provider",
        )


def test_invalid_source_tier_rejected(
    tmp_db_with_bridge: Path, fixture_text
) -> None:
    with pytest.raises(ValueError):
        _paste(
            tmp_db_with_bridge,
            raw_text=fixture_text("chatgpt"),
            source_tier=99,
        )


def test_source_override_recorded(
    tmp_db_with_bridge: Path, fixture_text
) -> None:
    """When operator overrides the source, the row reflects the
    override but the confidence is still the detector's reading."""
    text = fixture_text("anthropic")
    r = _paste(
        tmp_db_with_bridge,
        raw_text=text,
        source_override="other",
    )
    assert r.source == "other"
    # Detector ran and probably DID classify as anthropic.
    assert "anthropic" in r.detection.per_source
    assert r.detection.per_source["anthropic"] > 0


def test_known_sources_constant_complete() -> None:
    """KNOWN_SOURCES must include 'other' so operator override of
    ambiguous pastes works."""
    assert "other" in KNOWN_SOURCES
