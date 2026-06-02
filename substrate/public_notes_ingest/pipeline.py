"""Public-notes ingest orchestrator."""

from __future__ import annotations

import enum
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from substrate.quality_gate import (
    CandidateNote,
    QualityGateResult,
    QualityGateVerdict,
    check_source_tier,
    check_verification,
    check_voice_style,
    run_quality_gate,
)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class IngestEventKind(str, enum.Enum):
    """Lifecycle events the orchestrator emits."""

    GATED_PASS_PUBLIC = "gated_pass_public"
    GATED_REROUTE_PRIVATE = "gated_reroute_private"
    GATED_REJECT = "gated_reject"
    WRITE_TO_COLLECTIVE_FAILED = "write_to_collective_failed"
    WRITE_TO_COLLECTIVE_OK = "write_to_collective_ok"


@dataclass(frozen=True)
class IngestEvent:
    """One step in the orchestrator's trajectory."""

    event_id: str = field(default_factory=lambda: f"ie-{uuid.uuid4().hex[:12]}")
    kind: IngestEventKind = IngestEventKind.GATED_REJECT
    note_id: str = ""
    user_id: str = ""
    gate_id: str | None = None
    error: str | None = None
    at: str = field(default_factory=_now_iso)


@dataclass(frozen=True)
class IngestOutcome:
    """The result of running the pipeline on one note."""

    note: CandidateNote
    gate_result: QualityGateResult
    events: tuple[IngestEvent, ...]
    written_to_collective: bool
    write_error: str | None = None


# Writer protocol: caller-injected; takes the accepted note + the
# verdict for audit traceability. Production wires a real DB write;
# tests use a recording stub.
Writer = Callable[[CandidateNote, QualityGateResult], None]


@dataclass
class IngestPipeline:
    """Stateful orchestrator. Aggregates ingest events across calls
    so the operator dashboard can render a recent-ingests timeline."""

    events: list[IngestEvent] = field(default_factory=list)
    accepted: list[str] = field(default_factory=list)  # note_ids written
    rerouted_private: list[str] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)


def _default_full_gate(note: CandidateNote) -> QualityGateResult:
    return run_quality_gate(
        note,
        verification_check=check_verification,
        voice_style_check=check_voice_style,
        source_tier_check=check_source_tier,
    )


def run_ingest(
    pipeline: IngestPipeline,
    note: CandidateNote,
    *,
    writer: Writer,
    gate_runner: Callable[[CandidateNote], QualityGateResult] = _default_full_gate,
) -> IngestOutcome:
    """Run one note through the gate + write conditionally.

    Discipline:
    - PASS_PUBLIC → writer(note, gate_result); on success emit
      WRITE_TO_COLLECTIVE_OK + GATED_PASS_PUBLIC; on failure emit
      WRITE_TO_COLLECTIVE_FAILED and leave the note unwritten (the
      audit log shows the gate accepted it, the writer failed —
      operator queue picks up the retry)
    - REROUTE_PRIVATE → no writer call; emit GATED_REROUTE_PRIVATE
    - REJECT → no writer call; emit GATED_REJECT
    """
    gate_result = gate_runner(note)
    events: list[IngestEvent] = []
    written = False
    write_error: str | None = None

    if gate_result.verdict == QualityGateVerdict.PASS_PUBLIC:
        try:
            writer(note, gate_result)
            written = True
            events.append(IngestEvent(
                kind=IngestEventKind.WRITE_TO_COLLECTIVE_OK,
                note_id=note.note_id,
                user_id=note.user_id,
                gate_id=gate_result.gate_id,
            ))
            events.append(IngestEvent(
                kind=IngestEventKind.GATED_PASS_PUBLIC,
                note_id=note.note_id,
                user_id=note.user_id,
                gate_id=gate_result.gate_id,
            ))
            pipeline.accepted.append(note.note_id)
        except Exception as e:
            write_error = str(e)
            events.append(IngestEvent(
                kind=IngestEventKind.WRITE_TO_COLLECTIVE_FAILED,
                note_id=note.note_id,
                user_id=note.user_id,
                gate_id=gate_result.gate_id,
                error=write_error,
            ))
    elif gate_result.verdict == QualityGateVerdict.REROUTE_PRIVATE:
        events.append(IngestEvent(
            kind=IngestEventKind.GATED_REROUTE_PRIVATE,
            note_id=note.note_id,
            user_id=note.user_id,
            gate_id=gate_result.gate_id,
        ))
        pipeline.rerouted_private.append(note.note_id)
    else:  # REJECT
        events.append(IngestEvent(
            kind=IngestEventKind.GATED_REJECT,
            note_id=note.note_id,
            user_id=note.user_id,
            gate_id=gate_result.gate_id,
        ))
        pipeline.rejected.append(note.note_id)

    pipeline.events.extend(events)

    return IngestOutcome(
        note=note,
        gate_result=gate_result,
        events=tuple(events),
        written_to_collective=written,
        write_error=write_error,
    )
