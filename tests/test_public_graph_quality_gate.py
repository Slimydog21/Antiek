"""Public-graph quality-gate tests (master-spec §13.9)."""

from __future__ import annotations

import os
import tempfile

import pytest

from runtime.db_lock import connect_write
from substrate.graph.schema import init_database
from substrate.public_graph import (
    MAX_EM_DASHES_PER_NOTE,
    MIN_WORDS_PER_NOTE,
    NoteQualityInput,
    QualityFailureReason,
    QualityGateOutcome,
    evaluate_quality,
    is_attribution_eligible,
)


@pytest.fixture
def db():
    tmpdir = tempfile.mkdtemp(prefix="antiek-qgate-test-")
    db_path = os.path.join(tmpdir, "test.duckdb")
    con = connect_write(db_path, purpose="qgate_test")
    init_database(con)
    yield con
    con.close()


def _seed_chunk(
    con, *, chunk_id: str, document_id: str = "doc-1",
    source_tier: int = 2,
) -> None:
    con.execute(
        "INSERT INTO documents (document_id, source_tier, document_type) "
        "VALUES (?, ?, 'web') ON CONFLICT DO NOTHING",
        [document_id, source_tier],
    )
    con.execute(
        "INSERT INTO chunks (chunk_id, document_id, chunk_index, text) "
        "VALUES (?, ?, 0, 'sample')",
        [chunk_id, document_id],
    )


# Sample long-enough text for the word-count check (~60 words).
_LONG_TEXT = (
    "The substrate ingests primary sources and produces typed claims "
    "with full provenance. Each chunk traces to a document and each "
    "document carries an ip_holder_id. The synthesizer enforces "
    "voice and style discipline at output time; the public-graph "
    "quality gate enforces it at input time. Together these prevent "
    "the public graph from becoming a content farm of low-tier "
    "regurgitations. Citation discipline closes the loop."
)


# ── Happy path ────────────────────────────────────────────────────


def test_well_formed_grounded_note_passes(db):
    _seed_chunk(db, chunk_id="chk-1", source_tier=2)
    result = evaluate_quality(db, NoteQualityInput(
        note_text=_LONG_TEXT,
        cited_chunk_ids=("chk-1",),
        hard_claim=True,
    ))
    assert result.outcome == QualityGateOutcome.PASS
    assert is_attribution_eligible(result) is True


# ── REJECT cases ───────────────────────────────────────────────────


def test_too_short_rejects(db):
    _seed_chunk(db, chunk_id="chk-1")
    result = evaluate_quality(db, NoteQualityInput(
        note_text="Short.",
        cited_chunk_ids=("chk-1",),
    ))
    assert result.outcome == QualityGateOutcome.REJECT
    assert QualityFailureReason.TOO_SHORT in result.reasons


def test_ungrounded_citation_rejects(db):
    # chk-1 not seeded in chunks table.
    result = evaluate_quality(db, NoteQualityInput(
        note_text=_LONG_TEXT,
        cited_chunk_ids=("chk-1",),
    ))
    assert result.outcome == QualityGateOutcome.REJECT
    assert QualityFailureReason.UNGROUNDED_CITATION in result.reasons


def test_hard_claim_with_no_citations_rejects(db):
    result = evaluate_quality(db, NoteQualityInput(
        note_text=_LONG_TEXT,
        cited_chunk_ids=(),
        hard_claim=True,
    ))
    assert result.outcome == QualityGateOutcome.REJECT
    assert QualityFailureReason.NO_CITATIONS in result.reasons


def test_source_tier_too_low_rejects(db):
    _seed_chunk(db, chunk_id="chk-1", source_tier=5)
    result = evaluate_quality(db, NoteQualityInput(
        note_text=_LONG_TEXT,
        cited_chunk_ids=("chk-1",),
        hard_claim=True,
    ))
    assert result.outcome == QualityGateOutcome.REJECT
    assert QualityFailureReason.SOURCE_TIER_TOO_LOW in result.reasons


# ── SOFT_REJECT cases ─────────────────────────────────────────────


def test_em_dash_overuse_soft_rejects(db):
    _seed_chunk(db, chunk_id="chk-1")
    em_dashes = "—" * (MAX_EM_DASHES_PER_NOTE + 1)
    text = _LONG_TEXT + " " + em_dashes
    result = evaluate_quality(db, NoteQualityInput(
        note_text=text,
        cited_chunk_ids=("chk-1",),
    ))
    assert result.outcome == QualityGateOutcome.SOFT_REJECT
    assert QualityFailureReason.EM_DASH_OVERUSE in result.reasons
    assert result.em_dash_count == MAX_EM_DASHES_PER_NOTE + 1


def test_padding_phrase_soft_rejects(db):
    _seed_chunk(db, chunk_id="chk-1")
    text = "It is important to note that " + _LONG_TEXT
    result = evaluate_quality(db, NoteQualityInput(
        note_text=text,
        cited_chunk_ids=("chk-1",),
    ))
    assert result.outcome == QualityGateOutcome.SOFT_REJECT
    assert QualityFailureReason.PADDING_CONSTRUCTION in result.reasons


def test_opinion_note_with_no_citations_soft_rejects(db):
    result = evaluate_quality(db, NoteQualityInput(
        note_text=_LONG_TEXT,
        cited_chunk_ids=(),
        hard_claim=False,
    ))
    assert result.outcome == QualityGateOutcome.SOFT_REJECT
    assert QualityFailureReason.NO_CITATIONS in result.reasons


# ── Composite ─────────────────────────────────────────────────────


def test_multiple_reasons_aggregated(db):
    text = "It is important to note: " + ("—" * 5)
    result = evaluate_quality(db, NoteQualityInput(
        note_text=text,  # too short + padding + em-dashes
        cited_chunk_ids=(),
        hard_claim=True,
    ))
    assert result.outcome == QualityGateOutcome.REJECT
    # TOO_SHORT + PADDING_CONSTRUCTION + NO_CITATIONS at minimum.
    assert QualityFailureReason.TOO_SHORT in result.reasons
    assert QualityFailureReason.PADDING_CONSTRUCTION in result.reasons
    assert QualityFailureReason.NO_CITATIONS in result.reasons


def test_is_attribution_eligible_only_true_on_pass(db):
    _seed_chunk(db, chunk_id="chk-1")
    pass_result = evaluate_quality(db, NoteQualityInput(
        note_text=_LONG_TEXT,
        cited_chunk_ids=("chk-1",),
    ))
    assert is_attribution_eligible(pass_result) is True

    soft_result = evaluate_quality(db, NoteQualityInput(
        note_text=_LONG_TEXT + ("—" * 10),
        cited_chunk_ids=("chk-1",),
    ))
    assert is_attribution_eligible(soft_result) is False
