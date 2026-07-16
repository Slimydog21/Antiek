"""Integrity-checked read model for authoritative living-note outcomes."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Literal

from runtime.db_lock import connect_read
from substrate.graph.insight_question import graph_db_path
from substrate.schemas.events import Event, NoteRefinedPayload


class LivingNoteHistoryNotFound(LookupError):
    pass


class LivingNoteHistoryIntegrityError(RuntimeError):
    pass


@dataclass(frozen=True)
class LivingNoteHistoryEntry:
    event_id: str
    sequence: int
    previous_sequence: int
    previous_text: str
    new_text: str
    reason: str
    outcome: Literal["applied", "superseded"]
    delivery_state: Literal["pending", "delivered"]
    emitted_at: str


@dataclass(frozen=True)
class LivingNoteHistory:
    investigation_id: str
    node_id: str
    current_text: str
    current_sequence: int
    refinement_count: int
    authoritative_applied_count: int
    superseded_count: int
    complete: bool
    entries: tuple[LivingNoteHistoryEntry, ...]


def _strict_metadata(raw: object) -> dict:
    if not isinstance(raw, str) or not raw:
        raise LivingNoteHistoryIntegrityError("living-note metadata is missing")
    try:
        value = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise LivingNoteHistoryIntegrityError("living-note metadata is invalid") from exc
    if not isinstance(value, dict):
        raise LivingNoteHistoryIntegrityError("living-note metadata is not an object")
    return value


def living_note_history(
    investigation_id: str,
    node_id: str,
    *,
    db_path: str | None = None,
) -> LivingNoteHistory:
    """Read committed refinement decisions; never infer history from JSONL."""
    con = connect_read(db_path or graph_db_path())
    try:
        node = con.execute(
            "SELECT node_type, canonical_label, metadata FROM nodes WHERE node_id=?",
            [node_id],
        ).fetchone()
        if node is None:
            raise LivingNoteHistoryNotFound("no such living note")
        node_type, current_text, metadata_raw = node
        metadata = _strict_metadata(metadata_raw)
        if node_type != "insight" or metadata.get("investigation_id") != investigation_id:
            raise LivingNoteHistoryNotFound("no such living note")

        refinement_count = metadata.get("refinement_count", 0)
        current_sequence = metadata.get("last_update_seq", -1)
        if (
            isinstance(refinement_count, bool)
            or not isinstance(refinement_count, int)
            or refinement_count < 0
            or isinstance(current_sequence, bool)
            or not isinstance(current_sequence, int)
            or current_sequence < -1
        ):
            raise LivingNoteHistoryIntegrityError("living-note counters are invalid")
        if (refinement_count == 0) != (current_sequence == -1):
            raise LivingNoteHistoryIntegrityError("living-note counters disagree")

        rows = con.execute(
            "SELECT event_id, event_json, event_sha256, state "
            "FROM write_event_outbox WHERE investigation_id=? "
            "AND aggregate_kind='living_note' AND aggregate_id=? "
            "ORDER BY outbox_sequence",
            [investigation_id, node_id],
        ).fetchall()
    finally:
        con.close()

    entries: list[LivingNoteHistoryEntry] = []
    chain_sequence: int | None = None
    chain_text: str | None = None
    applied_count = 0
    superseded_count = 0
    for event_id, encoded, digest, delivery_state in rows:
        if delivery_state not in {"pending", "delivered"}:
            raise LivingNoteHistoryIntegrityError("living-note delivery state is invalid")
        if hashlib.sha256(encoded.encode()).hexdigest() != digest:
            raise LivingNoteHistoryIntegrityError("living-note history digest mismatch")
        try:
            event = Event.model_validate_json(encoded)
        except Exception as exc:
            raise LivingNoteHistoryIntegrityError("living-note history event is invalid") from exc
        if event.event_id != event_id or event.investigation_id != investigation_id:
            raise LivingNoteHistoryIntegrityError("living-note history identity conflicts")
        payload = event.payload
        if not isinstance(payload, NoteRefinedPayload):
            continue
        if (
            payload.note_id != node_id
            or payload.sequence is None
            or payload.previous_sequence is None
            or payload.outcome not in {"applied", "superseded"}
        ):
            raise LivingNoteHistoryIntegrityError("living-note history authority is incomplete")
        if (
            payload.sequence < 0
            or payload.previous_sequence < -1
            or (payload.outcome == "applied" and payload.sequence <= payload.previous_sequence)
            or (payload.outcome == "superseded" and payload.sequence > payload.previous_sequence)
        ):
            raise LivingNoteHistoryIntegrityError("living-note history outcome conflicts")
        if chain_sequence is None:
            chain_sequence = payload.previous_sequence
            chain_text = payload.previous_text
        if payload.previous_sequence != chain_sequence or payload.previous_text != chain_text:
            raise LivingNoteHistoryIntegrityError("living-note history chain is broken")
        if payload.outcome == "applied":
            applied_count += 1
            chain_sequence = payload.sequence
            chain_text = payload.new_text
        else:
            superseded_count += 1
        entries.append(
            LivingNoteHistoryEntry(
                event_id=event.event_id,
                sequence=payload.sequence,
                previous_sequence=payload.previous_sequence,
                previous_text=payload.previous_text,
                new_text=payload.new_text,
                reason=payload.refinement_reason,
                outcome=payload.outcome,
                delivery_state=delivery_state,
                emitted_at=event.emitted_at.isoformat(),
            )
        )

    if applied_count > refinement_count:
        raise LivingNoteHistoryIntegrityError("living-note history exceeds graph count")
    if entries and (chain_sequence != current_sequence or chain_text != current_text):
        raise LivingNoteHistoryIntegrityError("living-note history diverges from graph truth")
    complete = applied_count == refinement_count and (
        refinement_count == 0 or (bool(entries) and entries[0].previous_sequence == -1)
    )
    return LivingNoteHistory(
        investigation_id=investigation_id,
        node_id=node_id,
        current_text=current_text,
        current_sequence=current_sequence,
        refinement_count=refinement_count,
        authoritative_applied_count=applied_count,
        superseded_count=superseded_count,
        complete=complete,
        entries=tuple(entries),
    )
