"""Tests for substrate.public_notes_ingest — Sprint 22 Phase 3 orchestrator."""

from __future__ import annotations

import pytest

from substrate.public_notes_ingest import (
    IngestEventKind,
    IngestPipeline,
    run_ingest,
)
from substrate.quality_gate import (
    CandidateNote,
    QualityGateVerdict,
)


def _good_note(note_id: str = "n-1", user_id: str = "u-1") -> CandidateNote:
    return CandidateNote(
        note_id=note_id, user_id=user_id,
        prose=(
            "The Hippo dispatch posture matured along two axes in 2026. "
            "The Hermes verify-tier acquired a chaos test that ratified "
            "the OAuth-refresh translation rule. The chaos test landed "
            "without changes to dispatch code; the bridge absorbed the "
            "responsibility cleanly. The synthesizer tier began its "
            "measurement window against Grok 4.3."
        ),
        claims=("c-1", "c-2"),
        claim_evidence={"c-1": ("ch-a",), "c-2": ("ch-b",)},
        cited_source_tiers=(1, 2),
    )


def _slop_note(note_id: str = "n-slop") -> CandidateNote:
    return CandidateNote(
        note_id=note_id, user_id="u-1",
        prose=(
            "Key takeaways:\n"
            "- bullet one\n- bullet two\n- bullet three\n- bullet four\n"
            "- bullet five\n- bullet six\n- bullet seven\n- bullet eight\n"
            "In conclusion."
        ),
        claims=("c-1",), claim_evidence={"c-1": ("ch-a",)},
        cited_source_tiers=(1,),
    )


def _empty_claims_note() -> CandidateNote:
    return CandidateNote(
        note_id="n-empty", user_id="u-1", prose="no claims",
        claims=(), claim_evidence={}, cited_source_tiers=(),
    )


def test_pass_public_writes_to_collective():
    pipeline = IngestPipeline()
    written: list[tuple[str, str]] = []

    def writer(note, gate_result):
        written.append((note.note_id, gate_result.verdict.value))

    outcome = run_ingest(pipeline, _good_note(), writer=writer)
    assert outcome.gate_result.verdict == QualityGateVerdict.PASS_PUBLIC
    assert outcome.written_to_collective is True
    assert len(written) == 1
    kinds = [e.kind for e in outcome.events]
    assert IngestEventKind.WRITE_TO_COLLECTIVE_OK in kinds
    assert IngestEventKind.GATED_PASS_PUBLIC in kinds
    assert pipeline.accepted == [_good_note().note_id]


def test_reroute_private_does_not_call_writer():
    pipeline = IngestPipeline()
    writer_calls: list[str] = []

    def writer(note, _gate):
        writer_calls.append(note.note_id)

    outcome = run_ingest(pipeline, _slop_note(), writer=writer)
    assert outcome.gate_result.verdict == QualityGateVerdict.REROUTE_PRIVATE
    assert outcome.written_to_collective is False
    assert writer_calls == []
    assert any(
        e.kind == IngestEventKind.GATED_REROUTE_PRIVATE for e in outcome.events
    )
    assert pipeline.rerouted_private == ["n-slop"]


def test_reject_does_not_call_writer():
    pipeline = IngestPipeline()
    writer_calls: list[str] = []

    def writer(note, _gate):
        writer_calls.append(note.note_id)

    outcome = run_ingest(pipeline, _empty_claims_note(), writer=writer)
    assert outcome.gate_result.verdict == QualityGateVerdict.REJECT
    assert outcome.written_to_collective is False
    assert writer_calls == []
    assert pipeline.rejected == ["n-empty"]


def test_writer_failure_recorded_not_raised():
    pipeline = IngestPipeline()

    def failing_writer(note, _gate):
        raise RuntimeError("DB unreachable")

    outcome = run_ingest(pipeline, _good_note(), writer=failing_writer)
    assert outcome.written_to_collective is False
    assert outcome.write_error == "DB unreachable"
    kinds = [e.kind for e in outcome.events]
    assert IngestEventKind.WRITE_TO_COLLECTIVE_FAILED in kinds
    # Pass-public still NOT in accepted because the write failed.
    assert pipeline.accepted == []


def test_pipeline_accumulates_across_calls():
    pipeline = IngestPipeline()

    def writer(_n, _g):
        pass

    run_ingest(pipeline, _good_note("n-1"), writer=writer)
    run_ingest(pipeline, _good_note("n-2"), writer=writer)
    run_ingest(pipeline, _slop_note("n-3"), writer=writer)
    run_ingest(pipeline, _empty_claims_note(), writer=writer)

    assert len(pipeline.accepted) == 2
    assert pipeline.rerouted_private == ["n-3"]
    assert pipeline.rejected == ["n-empty"]
    assert len(pipeline.events) >= 4


def test_custom_gate_runner_is_used():
    """Tests can inject a custom gate_runner for unit isolation."""
    from substrate.quality_gate import QualityGateResult

    pipeline = IngestPipeline()
    forced = QualityGateResult(verdict=QualityGateVerdict.PASS_PUBLIC)

    def writer(_n, _g):
        pass

    outcome = run_ingest(
        pipeline, _empty_claims_note(),  # would normally REJECT
        writer=writer,
        gate_runner=lambda _note: forced,
    )
    assert outcome.gate_result.verdict == QualityGateVerdict.PASS_PUBLIC
    assert outcome.written_to_collective is True
