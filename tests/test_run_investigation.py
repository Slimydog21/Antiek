"""Unit tests for ``tools.run_investigation`` — the D4 thought-partner loop CLI.

These cover the PURE pieces of the loop (no real LLM, no real corpus):

* ``_parse_document_notes`` — the custom document-distillation parser. This is
  the regression guard for the two non-obvious fixes documented on the tool:

    1. It does NOT drop a note for missing ``source_event_ids`` (the
       wrestling-session parser's rule-4 attribution defense is WRONG here —
       the source IS the document chunk, cited via ``promote_insight`` at
       deposit). Without this guard a future "consolidation" that swaps back
       to ``parse_notes_response`` would silently zero out every distillation.
    2. It tolerates markdown fences + leading prose (the flash model often
       wraps JSON in ```json … ``` or prefixes a sentence).

* ``_pick_substantive_chunk`` — the boilerplate-skipping chunk selector over an
  isolated in-memory DuckDB. Guards that bibliography / references / index /
  page-header / TOC pages are skipped so the model distills real content, not
  a citation list.

* ``LoopResult`` — the summary dataclass.

The full loop (license → distill → deposit → reuse) needs a real LLM + a
scratch copy of the corpus; it is exercised end-to-end out-of-band (the
cycle-27 proof) and is intentionally NOT run under pytest.
"""
from __future__ import annotations

import os
import sys
from collections.abc import Sequence
from typing import Any

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from tools.run_investigation import (  # noqa: E402
    LoopResult,
    _parse_document_notes,
    _pick_substantive_chunk,
)


# --------------------------------------------------------------------------- #
# _parse_document_notes
# --------------------------------------------------------------------------- #
def test_parse_well_formed_json_returns_notes_with_text_and_confidence() -> None:
    notes = _parse_document_notes(
        '{"notes": [{"text": "radar works by timing echoes", "confidence": "high"}, '
        '{"text": "shorter wavelengths sharpen resolution", "confidence": "moderate"}]}'
    )
    assert len(notes) == 2
    assert notes[0].text == "radar works by timing echoes"
    assert notes[0].confidence == "high"
    assert notes[1].text == "shorter wavelengths sharpen resolution"
    assert notes[1].confidence == "moderate"


def test_parse_keeps_notes_without_source_event_ids() -> None:
    """THE critical fix: a document-distilled note has no source_event_ids
    (the chunk is the source), yet it MUST be kept — not dropped like the
    wrestling parser would."""
    notes = _parse_document_notes(
        '{"notes": [{"text": "an insight", "confidence": "high"}]}'
    )
    assert len(notes) == 1
    assert notes[0].text == "an insight"
    assert notes[0].source_event_ids == ()


def test_parse_tolerates_markdown_json_fence() -> None:
    notes = _parse_document_notes(
        '```json\n{"notes": [{"text": "fenced", "confidence": "low"}]}\n```'
    )
    assert len(notes) == 1
    assert notes[0].text == "fenced"


def test_parse_tolerates_leading_prose_before_json() -> None:
    notes = _parse_document_notes(
        'Here are the insights:\n{"notes": [{"text": "after prose", "confidence": "high"}]}'
    )
    assert len(notes) == 1
    assert notes[0].text == "after prose"


def test_parse_empty_notes_list() -> None:
    assert _parse_document_notes('{"notes": []}') == []


def test_parse_missing_notes_key() -> None:
    assert _parse_document_notes('{"unrelated": 1}') == []


def test_parse_garbage_returns_empty() -> None:
    assert _parse_document_notes("the model went off the rails") == []
    assert _parse_document_notes("") == []


def test_parse_drops_notes_with_empty_text() -> None:
    notes = _parse_document_notes(
        '{"notes": [{"text": "   ", "confidence": "high"}, '
        '{"text": "real insight", "confidence": "high"}]}'
    )
    assert len(notes) == 1
    assert notes[0].text == "real insight"


def test_parse_recovers_unbalanced_inner_braces() -> None:
    """A note text containing a stray ``{`` must not break the brace matcher."""
    notes = _parse_document_notes(
        '{"notes": [{"text": "see the {x} pattern", "confidence": "high"}]}'
    )
    assert len(notes) == 1
    assert notes[0].text == "see the {x} pattern"


# --------------------------------------------------------------------------- #
# _pick_substantive_chunk — isolated in-memory DuckDB
# --------------------------------------------------------------------------- #
def _seeded_chunks_con(rows: Sequence[tuple[str, str, int, str]]) -> Any:
    """Build an in-memory DuckDB with a minimal ``chunks`` table seeded with
    ``rows`` = list of (chunk_id, document_id, chunk_index, text)."""
    import duckdb

    con = duckdb.connect()
    con.execute(
        "CREATE TABLE chunks ("
        "chunk_id TEXT PRIMARY KEY, document_id TEXT, "
        "chunk_index INTEGER, section_path TEXT, text TEXT)"
    )
    for chunk_id, document_id, chunk_index, text in rows:
        con.execute(
            "INSERT INTO chunks (chunk_id, document_id, chunk_index, text) "
            "VALUES (?, ?, ?, ?)",
            [chunk_id, document_id, chunk_index, text],
        )
    return con


def test_pick_returns_longest_substantive_chunk() -> None:
    body = "x" * 600
    long_body = "y" * 1200
    con = _seeded_chunks_con(
        [
            ("c-short", "doc-1", 0, "z" * 500),
            ("c-long", "doc-1", 1, long_body),
            ("c-mid", "doc-1", 2, body),
        ]
    )
    try:
        chunk_id, text = _pick_substantive_chunk(con, "doc-1")
    finally:
        con.close()
    assert chunk_id == "c-long"
    assert text == long_body


def test_pick_skips_bibliography_references_and_index() -> None:
    """A long references/bibliography/index page must lose to a shorter real
    content chunk — otherwise the model distills a citation list."""
    real = "r" * 700
    con = _seeded_chunks_con(
        [
            ("c-refs", "doc-1", 0, "Bibliography\n" + "ref " * 400),
            ("c-index", "doc-1", 1, "Index\n" + "alpha " * 400),
            ("c-real", "doc-1", 2, real),
        ]
    )
    try:
        chunk_id, text = _pick_substantive_chunk(con, "doc-1")
    finally:
        con.close()
    assert chunk_id == "c-real"
    assert text == real


def test_pick_skips_page_headers_and_table_of_contents() -> None:
    real = "content about radar resolution and beamwidth " * 20
    con = _seeded_chunks_con(
        [
            ("c-page", "doc-1", 0, "## Page 12\nsome header text " * 40),
            ("c-toc", "doc-1", 1, "Contents\nChapter 1 ...\nChapter 2 ..." * 30),
            ("c-real", "doc-1", 2, real),
        ]
    )
    try:
        chunk_id, text = _pick_substantive_chunk(con, "doc-1")
    finally:
        con.close()
    assert chunk_id == "c-real"


def test_pick_returns_none_when_all_chunks_too_short() -> None:
    con = _seeded_chunks_con(
        [("c-tiny", "doc-1", 0, "too short to matter")]
    )
    try:
        chunk_id, text = _pick_substantive_chunk(con, "doc-1")
    finally:
        con.close()
    assert chunk_id is None
    assert text == ""


def test_pick_is_scoped_to_the_named_document() -> None:
    """Only the requested document_id's chunks are candidates."""
    con = _seeded_chunks_con(
        [
            ("c-other", "doc-other", 0, "q" * 2000),
            ("c-this", "doc-1", 0, "p" * 800),
        ]
    )
    try:
        chunk_id, _ = _pick_substantive_chunk(con, "doc-1")
    finally:
        con.close()
    assert chunk_id == "c-this"


# --------------------------------------------------------------------------- #
# LoopResult
# --------------------------------------------------------------------------- #
def test_loop_result_summarize_round_trips_fields() -> None:
    result = LoopResult(
        source_doc="doc-book-radar",
        chunk_id="c-123",
        distilled_notes=3,
        deposited_insights=["ins-1", "ins-2", "ins-3"],
        units_retrieved=5,
        reuse_injected=True,
        reused_unit_ids=["ins-1", "ins-2"],
        applied=True,
    )
    summary = result.summarize()
    assert "source_doc=doc-book-radar chunk=c-123" in summary
    assert "distilled_notes=3 deposited_insights=3" in summary
    assert "units_retrieved=5 reuse_injected=True" in summary
    assert "applied=True" in summary
    assert "['ins-1', 'ins-2']" in summary


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
