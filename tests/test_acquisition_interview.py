"""Tests for the Interview transcript → substrate adapter (§4.4 + §11).

Verifies:
  - Refuses to ingest mid-conversation transcripts (status != "completed")
  - Refuses to ingest without consent recorded (§11 binding gate)
  - Successfully writes a completed consented transcript with a stable
    doc_id, ``document_type="interview_transcript"``, and per-turn
    chunks ordered by ``section_path``
  - Idempotent: re-ingesting the same interview_id writes one document
  - low_word_count short-circuits with skipped_reason rather than raise
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

# Repo root on path so the tests run from any working directory.
_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

from acquisition.interview.adapter import (  # noqa: E402
    DEFAULT_INTERVIEW_SOURCE_TIER,
    InterviewIngestError,
    ingest_interview,
    interview_doc_id,
)
from orchestration.interview.orchestrator import (  # noqa: E402
    InterviewState,
    InterviewTurn,
)
from processing.embedding.embed import EmbeddingProvider  # noqa: E402


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    """Redirect the substrate DB to tmp_path so each test gets a fresh
    DuckDB. Same pattern as the voice adapter tests."""
    db_path = tmp_path / "graph.duckdb"
    events_dir = tmp_path / "events"
    events_dir.mkdir()
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(events_dir))
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(db_path))
    return {"db_path": str(db_path), "events_dir": str(events_dir)}


class _StubEmbedder:
    """Deterministic 4-dim embedding stub. Avoids loading
    sentence-transformers in the test path."""

    def encode(self, text):  # noqa: ARG002 (signature compat)
        return [0.1, 0.2, 0.3, 0.4]


@pytest.fixture
def stub_embedder() -> EmbeddingProvider:
    return _StubEmbedder()  # type: ignore[return-value]


def _completed_state(
    *,
    interview_id: str = "interview-abc123",
    informant: str | None = "mit-press-rep",
    turns_text: list[tuple[str, str]] | None = None,
    consent: bool = True,
) -> InterviewState:
    """Build a completed-and-consented InterviewState fixture."""
    state = InterviewState(
        interview_id=interview_id,
        project_id="proj-x",
        informant_handle=informant,
        interview_guide={"must_cover": []},
    )
    state.status = "completed"
    state.consent_recorded = consent
    pairs = turns_text or [
        ("interviewer", "Can you tell me about your team's approach?"),
        ("informant", "We use a substrate-first discipline across all surfaces."),
        ("interviewer", "What is the operator-graph compounding pattern?"),
        ("informant", "Each investigation contributes nodes and edges back."),
    ]
    for i, (speaker, text) in enumerate(pairs):
        state.turns.append(
            InterviewTurn(
                turn_id=f"turn-{i}",
                speaker=speaker,
                text=text,
                emitted_at="2026-05-22T00:00:00Z",
            )
        )
    return state


# ── Tests ─────────────────────────────────────────────────────────────


def test_interview_doc_id_is_stable_and_unique():
    a = interview_doc_id("interview-abc")
    b = interview_doc_id("interview-abc")
    c = interview_doc_id("interview-xyz")
    assert a == b
    assert a != c
    assert a.startswith("doc-iv-")
    assert len(a) == len("doc-iv-") + 16


def test_interview_doc_id_rejects_empty():
    with pytest.raises(ValueError, match="empty interview_id"):
        interview_doc_id("")


def test_refuses_to_ingest_in_progress_interview(isolated_db, stub_embedder):
    state = _completed_state()
    state.status = "in_progress"  # override
    with pytest.raises(InterviewIngestError, match="status='in_progress'"):
        ingest_interview(
            state,
            investigation_id="inv-1",
            db_path=isolated_db["db_path"],
            embedder=stub_embedder,
        )


def test_refuses_to_ingest_without_consent(isolated_db, stub_embedder):
    state = _completed_state(consent=False)
    with pytest.raises(InterviewIngestError, match="no consent recorded"):
        ingest_interview(
            state,
            investigation_id="inv-1",
            db_path=isolated_db["db_path"],
            embedder=stub_embedder,
        )


def test_ingest_writes_document_with_interview_transcript_type(
    isolated_db, stub_embedder,
):
    state = _completed_state()
    result = ingest_interview(
        state,
        investigation_id="inv-1",
        db_path=isolated_db["db_path"],
        embedder=stub_embedder,
    )
    assert result.skipped_reason is None
    assert result.document_id == interview_doc_id(state.interview_id)
    assert result.turn_count == 4
    assert result.chunks_written > 0
    assert result.document_loaded_event_id is not None

    # Verify the DB row
    import duckdb
    con = duckdb.connect(isolated_db["db_path"], read_only=True)
    try:
        row = con.execute(
            "SELECT document_type, source_tier, title FROM documents "
            "WHERE document_id = ?",
            [result.document_id],
        ).fetchone()
        assert row is not None
        assert row[0] == "interview_transcript"
        assert row[1] == DEFAULT_INTERVIEW_SOURCE_TIER
        assert "Interview interview-abc123" in row[2]
    finally:
        con.close()


def test_ingest_chunks_preserve_speaker_section_path(isolated_db, stub_embedder):
    """Each turn should produce at least one chunk whose section_path
    references the speaker — the chunker splits on the level-3 headings
    that ``_format_interview_markdown`` emits."""
    state = _completed_state()
    result = ingest_interview(
        state,
        investigation_id="inv-1",
        db_path=isolated_db["db_path"],
        embedder=stub_embedder,
    )
    import duckdb
    con = duckdb.connect(isolated_db["db_path"], read_only=True)
    try:
        rows = con.execute(
            "SELECT section_path, text FROM chunks "
            "WHERE document_id = ? "
            "ORDER BY chunk_index ASC",
            [result.document_id],
        ).fetchall()
    finally:
        con.close()
    assert len(rows) > 0
    # At least one chunk per speaker should be reachable.
    interviewer_seen = any(
        "Interviewer" in (r[0] or "") or "Interviewer" in (r[1] or "") for r in rows
    )
    informant_seen = any(
        "Informant" in (r[0] or "") or "Informant" in (r[1] or "") for r in rows
    )
    assert interviewer_seen, f"no interviewer chunk: {[r[0] for r in rows]}"
    assert informant_seen, f"no informant chunk: {[r[0] for r in rows]}"


def test_ingest_is_idempotent_on_reingest(isolated_db, stub_embedder):
    state = _completed_state()
    r1 = ingest_interview(
        state,
        investigation_id="inv-1",
        db_path=isolated_db["db_path"],
        embedder=stub_embedder,
    )
    r2 = ingest_interview(
        state,
        investigation_id="inv-1",
        db_path=isolated_db["db_path"],
        embedder=stub_embedder,
    )
    assert r1.document_id == r2.document_id
    import duckdb
    con = duckdb.connect(isolated_db["db_path"], read_only=True)
    try:
        count = con.execute(
            "SELECT count(*) FROM documents WHERE document_id = ?",
            [r1.document_id],
        ).fetchone()[0]
    finally:
        con.close()
    assert count == 1


def test_short_transcript_returns_skipped_reason(isolated_db, stub_embedder):
    state = _completed_state(
        turns_text=[("interviewer", "Hi."), ("informant", "Ok.")],
    )
    result = ingest_interview(
        state,
        investigation_id="inv-1",
        db_path=isolated_db["db_path"],
        embedder=stub_embedder,
    )
    assert result.skipped_reason == "low_word_count"
    assert result.chunks_written == 0
    # Event still emitted so the trajectory records the attempt.
    assert result.document_loaded_event_id is not None
