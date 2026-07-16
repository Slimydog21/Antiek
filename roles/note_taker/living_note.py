"""DRW SPR-03 M3 + M6 — living notes.

A note is not frozen at emission: when a user challenges it or new evidence
arrives, the note *updates in place* rather than spawning a duplicate. That
is the "living note". The hazard is concurrency — a user challenge and a
background re-distillation can target the same note at once — so updates
need a deterministic resolution rule.

The rule: **single logical writer per note, ordered by event sequence;
last-writer-by-event-seq wins; the full history is preserved in the event
log.** Each refinement carries a monotonic ``seq`` (in production, the
emission order of the driving event). The note node records the highest
``seq`` it has applied in ``metadata.last_update_seq``. An incoming
refinement is applied to the node iff its ``seq`` is strictly greater;
otherwise it is the *loser* — the node is left untouched. An authoritative
``note.refined`` outcome is committed to the durable outbox in the same
transaction as a winning graph mutation; losing attempts are explicitly
recorded as ``superseded``. Determinism is therefore independent of arrival
order, and a crash cannot separate graph truth from its event intent.

Worked example (the docstring the maintainer should not have to guess):
a background pass refines a note at ``seq=11`` and a user challenge refines
it at ``seq=12``. Whichever lands first, the node's final text is the
``seq=12`` text; the ``seq=11`` refinement is preserved in the event log
(``previous_text`` + ``new_text`` + the decision) but not reflected on the node.

Escalation seam (M6): a challenge the existing graph cannot resolve emits
``question.escalated_to_research`` on the relevant question node, carrying a
*reserved* (not launched) child ``investigation_id``. SPR-06 / SPR-10 launch
into that reserved id later. **Nothing is launched here.**
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

try:
    from ...graph.insight_question import (
        canonical_text,
        graph_db_path,
        promote_question,
        question_node_id,
    )
    from ...graph.node_membership import membership_for
    from ...runtime.db_lock import connect_write
    from ...schemas.events import NoteRefinedPayload, QuestionEscalatedToResearchPayload
    from ...write.event_outbox import (
        build_typed_envelope,
        dispatch_aggregate_pending,
        enqueue_event,
        event_for_operation,
        eventful_transaction,
    )
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from runtime.db_lock import connect_write  # type: ignore[no-redef]
    from substrate.graph.insight_question import (  # type: ignore[no-redef]
        canonical_text,
        graph_db_path,
        promote_question,
        question_node_id,
    )
    from substrate.graph.node_membership import membership_for  # type: ignore[no-redef]
    from substrate.schemas.events import (  # type: ignore[no-redef]
        NoteRefinedPayload,
        QuestionEscalatedToResearchPayload,
    )
    from substrate.write.event_outbox import (  # type: ignore[no-redef]
        build_typed_envelope,
        dispatch_aggregate_pending,
        enqueue_event,
        event_for_operation,
        eventful_transaction,
    )


# A resolver decides whether a challenge can be answered from what's known.
# It returns the refined note text (resolved) or None (escalate). Production
# wires an LLM; tests inject a deterministic function.
Resolver = Callable[[str, str], str | None]


@dataclass
class ChallengeResult:
    note_node_id: str
    applied: bool                       # did the node text change?
    superseded: bool = False            # lost the seq race (older seq)?
    new_text: str | None = None
    escalated: bool = False
    escalated_question_id: str | None = None
    reserved_child_investigation_id: str | None = None


class ChallengeRequestConflict(RuntimeError):
    """An idempotency key was reused for a different command."""


class ChallengeRequestInProgress(RuntimeError):
    """A prior resolver dispatch has no durable decision yet."""


class LivingNoteScopeConflict(RuntimeError):
    """The requested investigation does not own this living note."""


def _assert_note_scope(con, node_id: str, investigation_id: str):
    membership = membership_for(con, node_id, investigation_id)
    if membership is None or membership.node_type != "insight":
        raise LivingNoteScopeConflict("living note does not belong to this investigation")
    return membership


def _open(con):
    return con if con is not None else connect_write(graph_db_path(), purpose="living_note")


def _read_node(con, node_id: str) -> tuple[str | None, dict]:
    row = con.execute(
        "SELECT canonical_label, metadata FROM nodes WHERE node_id = ?", [node_id]
    ).fetchone()
    if row is None:
        return None, {}
    meta = {}
    if row[1]:
        try:
            meta = json.loads(row[1])
        except (TypeError, ValueError):
            meta = {}
    return row[0], meta


def _refinement_operation_id(
    *,
    investigation_id: str,
    note_node_id: str,
    new_text: str,
    reason: str,
    seq: int,
    document_id: str | None,
) -> str:
    identity = json.dumps(
        {
            "document_id": document_id,
            "investigation_id": investigation_id,
            "new_text": new_text,
            "note_node_id": note_node_id,
            "reason": reason,
            "sequence": seq,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return "note-refinement:v1:" + hashlib.sha256(identity.encode()).hexdigest()


def _result_from_outcome(payload: NoteRefinedPayload) -> ChallengeResult:
    if payload.outcome not in {"applied", "superseded"}:
        raise RuntimeError("stored note refinement has no authoritative outcome")
    return ChallengeResult(
        payload.note_id,
        applied=payload.outcome == "applied",
        superseded=payload.outcome == "superseded",
        new_text=payload.new_text if payload.outcome == "applied" else None,
    )


def _escalation_operation_id(
    *,
    investigation_id: str,
    note_node_id: str,
    challenge_text: str,
    seq: int,
    document_id: str | None,
) -> str:
    identity = json.dumps(
        {
            "challenge_text": canonical_text(challenge_text),
            "document_id": document_id,
            "investigation_id": investigation_id,
            "note_node_id": note_node_id,
            "sequence": seq,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return "note-escalation:v1:" + hashlib.sha256(identity.encode()).hexdigest()


def _escalation_result(
    note_node_id: str,
    payload: QuestionEscalatedToResearchPayload,
) -> ChallengeResult:
    return ChallengeResult(
        note_node_id,
        applied=False,
        escalated=True,
        escalated_question_id=payload.question_id,
        reserved_child_investigation_id=payload.child_investigation_id,
    )


def _challenge_request_digest(
    investigation_id: str, note_node_id: str, challenge_text: str
) -> str:
    request = json.dumps(
        {
            "challenge_text": canonical_text(challenge_text),
            "investigation_id": investigation_id,
            "note_node_id": note_node_id,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(request.encode()).hexdigest()


def _result_json(result: ChallengeResult) -> str:
    return json.dumps(vars(result), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _result_from_json(raw: str) -> ChallengeResult:
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise RuntimeError("stored challenge response is not an object")
    return ChallengeResult(**value)


def apply_refinement(
    note_node_id: str,
    new_text: str,
    *,
    seq: int,
    investigation_id: str,
    reason: str = "challenge",
    document_id: str | None = None,
    events_dir: str | None = None,
    con: Any = None,
    _checkpoint: Callable[[str], None] | None = None,
) -> ChallengeResult:
    """Atomically decide a refinement and enqueue its authoritative outcome."""
    if isinstance(seq, bool) or not isinstance(seq, int) or seq < 0:
        raise ValueError("refinement sequence must be a non-negative integer")
    owned = con is None
    c = _open(con)
    try:
        outcome_event = None
        result = ChallengeResult(note_node_id, applied=False)
        aggregate_id = note_node_id
        with eventful_transaction(c, investigation_id, events_dir=events_dir):
            prev_text, meta = _read_node(c, note_node_id)
            if prev_text is None:
                return result
            membership = _assert_note_scope(c, note_node_id, investigation_id)
            # note.refined requires the source document on its envelope. The
            # promoted note carries both source and emerged-note identity.
            resolved_document_id = document_id or meta.get("source_document_id")
            operation_id = _refinement_operation_id(
                investigation_id=investigation_id,
                note_node_id=note_node_id,
                new_text=new_text,
                reason=reason,
                seq=seq,
                document_id=resolved_document_id,
            )
            existing = event_for_operation(c, operation_id)
            if existing is not None:
                if not isinstance(existing.payload, NoteRefinedPayload):
                    raise RuntimeError("refinement operation points to another event type")
                payload = existing.payload
                if (
                    existing.investigation_id != investigation_id
                    or existing.document_id != resolved_document_id
                    or payload.note_id != note_node_id
                    or payload.new_text != new_text
                    or payload.refinement_reason != reason
                    or payload.sequence != seq
                ):
                    raise RuntimeError("stored refinement operation conflicts with retry")
                outcome_event = existing
                result = _result_from_outcome(payload)
            else:
                last_seq = int(meta.get("last_update_seq", -1))
                wins = seq > last_seq
                payload = NoteRefinedPayload(
                    note_id=note_node_id,
                    origin_note_id=membership.origin_note_id,
                    previous_text=prev_text,
                    new_text=new_text,
                    refinement_reason=reason,
                    sequence=seq,
                    previous_sequence=last_seq,
                    outcome="applied" if wins else "superseded",
                )
                if wins:
                    meta["last_update_seq"] = seq
                    meta.setdefault("refinement_count", 0)
                    meta["refinement_count"] += 1
                    c.execute(
                        "UPDATE nodes SET canonical_label = ?, metadata = ? "
                        "WHERE node_id = ?",
                        [new_text, json.dumps(meta, default=str), note_node_id],
                    )
                if _checkpoint:
                    _checkpoint("after_decision_before_enqueue")
                digest = operation_id.rsplit(":", 1)[-1]
                outcome_event = build_typed_envelope(
                    investigation_id,
                    payload,
                    role="note_taker",
                    document_id=resolved_document_id,
                    event_id=f"evt-note-refinement-{digest[:24]}",
                )
                enqueue_event(
                    c,
                    operation_id=operation_id,
                    aggregate_kind="living_note",
                    aggregate_id=aggregate_id,
                    event=outcome_event,
                )
                result = _result_from_outcome(payload)
                if _checkpoint:
                    _checkpoint("after_enqueue_before_commit")
        if outcome_event is not None:
            if _checkpoint:
                _checkpoint("after_commit_before_delivery")
            dispatch_aggregate_pending(
                c,
                investigation_id,
                aggregate_kind="living_note",
                aggregate_id=aggregate_id,
                events_dir=events_dir,
            )
        return result
    finally:
        if owned:
            c.close()


def challenge_note(
    note_node_id: str,
    challenge_text: str,
    *,
    resolver: Resolver,
    seq: int,
    investigation_id: str,
    document_id: str | None = None,
    embedding_provider: Any = None,
    events_dir: str | None = None,
    con: Any = None,
    idempotency_key: str | None = None,
    unavailable_errors: tuple[type[BaseException], ...] = (),
    _checkpoint: Callable[[str], None] | None = None,
) -> ChallengeResult:
    """Resolve a challenge against a note. If the resolver produces refined
    text, update the note in place (seq rule). If not, escalate: ensure a
    question node exists for the challenge and emit
    ``question.escalated_to_research`` with a reserved (un-launched) child
    investigation id."""
    owned = con is None
    c = _open(con)
    try:
        prev_text, _meta = _read_node(c, note_node_id)
        if prev_text is None:
            return ChallengeResult(note_node_id, applied=False)
        _assert_note_scope(c, note_node_id, investigation_id)
        document_id = document_id or _meta.get("source_document_id")
        decision: dict[str, Any] | None = None
        if idempotency_key is not None:
            request_sha256 = _challenge_request_digest(
                investigation_id, note_node_id, challenge_text
            )
            row = c.execute(
                "SELECT request_sha256, sequence, state, decision_json, response_json "
                "FROM challenge_request_journal WHERE idempotency_key = ?",
                [idempotency_key],
            ).fetchone()
            if row is not None:
                if row[0] != request_sha256:
                    raise ChallengeRequestConflict("idempotency key belongs to another challenge")
                seq = int(row[1])
                if row[2] == "completed":
                    return _result_from_json(row[4])
                if row[2] == "unavailable":
                    if unavailable_errors:
                        raise unavailable_errors[0]("challenge resolver unavailable")
                    raise RuntimeError("challenge resolver unavailable")
                if row[2] == "resolving":
                    raise ChallengeRequestInProgress("challenge resolution is still indeterminate")
                decision = json.loads(row[3])
            else:
                c.execute(
                    "INSERT INTO challenge_request_journal "
                    "(idempotency_key, request_sha256, investigation_id, note_node_id, sequence, state) "
                    "VALUES (?, ?, ?, ?, ?, 'resolving')",
                    [idempotency_key, request_sha256, investigation_id, note_node_id, seq],
                )
                if _checkpoint:
                    _checkpoint("after_challenge_claim_before_resolver")

        if decision is None:
            try:
                resolved_text = resolver(prev_text, challenge_text)
            except unavailable_errors:
                if idempotency_key is not None:
                    c.execute(
                        "UPDATE challenge_request_journal SET state = 'unavailable', "
                        "updated_at = CURRENT_TIMESTAMP WHERE idempotency_key = ?",
                        [idempotency_key],
                    )
                raise
            if _checkpoint:
                _checkpoint("after_challenge_resolver_before_decision")
            decision = (
                {"kind": "refine", "text": resolved_text.strip()}
                if resolved_text is not None and resolved_text.strip()
                else {"kind": "escalate"}
            )
            if idempotency_key is not None:
                c.execute(
                    "UPDATE challenge_request_journal SET state = 'decided', decision_json = ?, "
                    "updated_at = CURRENT_TIMESTAMP WHERE idempotency_key = ?",
                    [json.dumps(decision, sort_keys=True, separators=(",", ":")), idempotency_key],
                )
                if _checkpoint:
                    _checkpoint("after_challenge_decision_before_apply")

        resolved_text = decision.get("text") if decision.get("kind") == "refine" else None
        if resolved_text is not None and resolved_text.strip():
            result = apply_refinement(
                note_node_id, resolved_text.strip(), seq=seq,
                investigation_id=investigation_id, reason="challenge_resolved",
                document_id=document_id, events_dir=events_dir, con=c,
                _checkpoint=_checkpoint,
            )
            if idempotency_key is not None:
                if _checkpoint:
                    _checkpoint("after_challenge_apply_before_complete")
                c.execute(
                    "UPDATE challenge_request_journal SET state = 'completed', response_json = ?, "
                    "updated_at = CURRENT_TIMESTAMP WHERE idempotency_key = ?",
                    [_result_json(result), idempotency_key],
                )
            return result
        operation_id = _escalation_operation_id(
            investigation_id=investigation_id,
            note_node_id=note_node_id,
            challenge_text=challenge_text,
            seq=seq,
            document_id=document_id,
        )
        digest = operation_id.rsplit(":", 1)[-1]
        identity_scope = f"challenge:{investigation_id}:{note_node_id}"
        expected_question_id = question_node_id(
            challenge_text, identity_scope=identity_scope
        )
        expected_child_id = "inv-" + digest[:16]
        aggregate_id = note_node_id
        graph_payloads: list[Any] = []
        escalation_event = None
        result = ChallengeResult(note_node_id, applied=False)
        with eventful_transaction(c, investigation_id, events_dir=events_dir):
            existing = event_for_operation(c, operation_id)
            if existing is not None:
                if not isinstance(
                    existing.payload, QuestionEscalatedToResearchPayload
                ):
                    raise RuntimeError("escalation operation points to another event type")
                payload = existing.payload
                if (
                    existing.investigation_id != investigation_id
                    or existing.document_id != document_id
                    or payload.question_id != expected_question_id
                    or payload.child_investigation_id != expected_child_id
                ):
                    raise RuntimeError("stored challenge escalation conflicts with retry")
                escalation_event = existing
                result = _escalation_result(note_node_id, payload)
            else:
                qid = promote_question(
                    text=challenge_text,
                    investigation_id=investigation_id,
                    asks_about=[note_node_id] if _is_node_target(note_node_id) else [],
                    metadata={
                        "raised_by_challenge_of": note_node_id,
                        "challenge_document_context": document_id,
                    },
                    embedding_provider=embedding_provider,
                    con=c,
                    identity_scope=identity_scope,
                    event_sink=graph_payloads.append,
                )
                if qid != expected_question_id:
                    raise RuntimeError("promoted challenge question identity conflicts")
                for index, graph_payload in enumerate(graph_payloads):
                    graph_event = build_typed_envelope(
                        investigation_id,
                        graph_payload,
                        role="connector",
                        event_id=f"evt-note-escalation-{digest[:20]}-g{index}",
                    )
                    enqueue_event(
                        c,
                        operation_id=f"{operation_id}:graph:{index}",
                        aggregate_kind="living_note",
                        aggregate_id=aggregate_id,
                        event=graph_event,
                    )
                escalation_payload = QuestionEscalatedToResearchPayload(
                    question_id=qid,
                    child_investigation_id=expected_child_id,
                )
                escalation_event = build_typed_envelope(
                    investigation_id,
                    escalation_payload,
                    role="note_taker",
                    document_id=document_id,
                    event_id=f"evt-note-escalation-{digest[:24]}",
                )
                enqueue_event(
                    c,
                    operation_id=operation_id,
                    aggregate_kind="living_note",
                    aggregate_id=aggregate_id,
                    event=escalation_event,
                )
                result = _escalation_result(note_node_id, escalation_payload)
                if _checkpoint:
                    _checkpoint("after_escalation_enqueue_before_commit")
        if escalation_event is not None:
            if _checkpoint:
                _checkpoint("after_escalation_commit_before_delivery")
            dispatch_aggregate_pending(
                c,
                investigation_id,
                aggregate_kind="living_note",
                aggregate_id=aggregate_id,
                events_dir=events_dir,
            )
        if idempotency_key is not None:
            if _checkpoint:
                _checkpoint("after_challenge_apply_before_complete")
            c.execute(
                "UPDATE challenge_request_journal SET state = 'completed', response_json = ?, "
                "updated_at = CURRENT_TIMESTAMP WHERE idempotency_key = ?",
                [_result_json(result), idempotency_key],
            )
        return result
    finally:
        if owned:
            c.close()


def _is_node_target(node_id: str) -> bool:
    # asks_about may point at an insight node; the vocabulary allows
    # question --asks_about--> insight. Always true for our promoted notes.
    return bool(node_id)
