"""Crash-safe delivery of canonical interview answers into Research documents."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from runtime.db_lock import LockedConnection
from substrate.event_log import (
    append_event_once_authorized,
    prepare_typed_event,
    require_event_persistence,
)
from substrate.graph.ops import insert_chunk_admitted, insert_document_admitted
from substrate.graph.tenancy import initialize_graph_authority
from substrate.investigation_streams import resolve_investigation_stream
from substrate.investigation_tenancy import InvestigationAuthority
from substrate.legal_gate.admission import admit_staged_document
from substrate.legal_gate.policy_store import account_policy_authority
from substrate.schemas.events import DocumentLoadedPayload, Event

from .authority import InterviewAccountAuthority
from .derivation import DerivationConflict


@dataclass(frozen=True)
class ReconcileResult:
    attempted: int
    completed: int
    pending: int
    failed: int


class DerivationConsentBlocked(RuntimeError):
    """Current consent does not permit delivery; the intent remains retryable."""


def _require_locked(con: object) -> LockedConnection:
    if not isinstance(con, LockedConnection):
        raise TypeError("interview derivation reconciliation requires a LockedConnection")
    return con


def _document_id(
    authority: InterviewAccountAuthority,
    *,
    interview_id: str,
    question_id: str,
    answer_sha256: str,
    stream_key: str,
) -> str:
    digest = hashlib.sha256(
        b"antiek-interview-answer-document-v1\0"
        + authority.account_digest.encode()
        + b"\0"
        + interview_id.encode()
        + b"\0"
        + question_id.encode()
        + b"\0"
        + answer_sha256.encode()
        + b"\0"
        + stream_key.encode()
    ).hexdigest()
    return f"ivad-{digest[:32]}"


def _answer_text(raw_turns: object, *, question_id: str, answer_sha256: str) -> str:
    try:
        turns = json.loads(raw_turns) if raw_turns else []
    except (TypeError, ValueError) as exc:
        raise DerivationConflict("interview transcript is corrupt") from exc
    if not isinstance(turns, list) or not all(isinstance(turn, dict) for turn in turns):
        raise DerivationConflict("interview transcript is corrupt")
    matches = [
        turn.get("text")
        for turn in turns
        if turn.get("role") == "informant" and turn.get("question_id") == question_id
    ]
    if len(matches) != 1 or not isinstance(matches[0], str):
        raise DerivationConflict("interview answer identity is corrupt")
    if hashlib.sha256(matches[0].encode()).hexdigest() != answer_sha256:
        raise DerivationConflict("interview answer bytes conflict with intent")
    return matches[0]


def _event_fingerprint(event_json: str) -> str:
    return hashlib.sha256(event_json.encode()).hexdigest()


def _materialize(
    con: LockedConnection,
    interview_authority: InterviewAccountAuthority,
    row: tuple[Any, ...],
) -> tuple[InvestigationAuthority, Event]:
    (
        interview_id, question_id, answer_sha256, investigation_id,
        investigation_digest, stream_key, raw_turns,
    ) = row
    target = InvestigationAuthority(interview_authority.account_id, str(investigation_id))
    if (
        target.investigation_digest != investigation_digest
        or target.stream_key != stream_key
    ):
        raise DerivationConflict("derivation target authority is corrupt")
    resolve_investigation_stream(target)
    require_event_persistence()
    answer = _answer_text(
        raw_turns, question_id=str(question_id), answer_sha256=str(answer_sha256)
    )
    document_id = _document_id(
        interview_authority,
        interview_id=str(interview_id),
        question_id=str(question_id),
        answer_sha256=str(answer_sha256),
        stream_key=str(stream_key),
    )
    content_sha256 = hashlib.sha256(answer.encode()).hexdigest()
    title = f"Interview {interview_id} — answer to {question_id}"
    event = prepare_typed_event(
        target.investigation_id,
        DocumentLoadedPayload(
            media_type="pasted_text",
            content_hash=f"sha256:{content_sha256}",
            size_bytes=len(answer.encode("utf-8")),
            title=title,
            page_count=None,
            source_uri=None,
        ),
        event_id=f"evt-{hashlib.sha256(document_id.encode()).hexdigest()[:32]}",
        role="acquisition",
        policy_id="interviews/canonical-answer-v1",
        document_id=document_id,
    )
    event_json = json.dumps(
        event.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    )

    con.execute("BEGIN TRANSACTION")
    try:
        initialize_graph_authority(con, target)
        receipt = admit_staged_document(
            con,
            account_policy_authority(target),
            investigation_digest=target.investigation_digest,
            document_id=document_id,
            provenance_class="user_authored",
            title=title,
            author="interview informant",
            source_corpus="canonical_interview",
            content_sha256=content_sha256,
            at=event.emitted_at,
        )
        if receipt.decision != "allow":
            raise DerivationConflict("user-authored interview answer was denied")
        insert_document_admitted(
            con,
            target,
            admission_receipt_id=receipt.receipt_id,
            admitted_content_sha256=content_sha256,
            document_id=document_id,
            source_tier=1,
            document_type="interview_answer",
            title=title,
            author="interview informant",
            published_at=event.emitted_at,
            investigation_id=target.investigation_id,
            raw_text=answer,
            metadata={
                "source": "canonical_interview",
                "interview_id": str(interview_id),
                "question_id": str(question_id),
                "answer_sha256": str(answer_sha256),
            },
            content_class="user_owned",
            owner_user_id=interview_authority.account_id,
            on_conflict="error",
        )
        insert_chunk_admitted(
            con,
            target,
            admission_receipt_id=receipt.receipt_id,
            admitted_content_sha256=content_sha256,
            document_id=document_id,
            chunk_index=0,
            section_path=f"Interview/{interview_id}/{question_id}",
            text=answer,
            token_count=len(answer.split()),
        )
        changed = con.execute(
            "UPDATE interview_answer_derivations SET delivery_state = 'processing', "
            "document_id = ?, admission_receipt_id = ?, event_id = ?, event_json = ?, "
            "event_fingerprint = ?, attempt_count = attempt_count + 1, "
            "last_error_code = NULL, updated_at = CURRENT_TIMESTAMP "
            "WHERE account_digest = ? AND owner_user_id = ? AND interview_id = ? "
            "AND question_id = ? AND delivery_state = 'pending' RETURNING question_id",
            [
                document_id, receipt.receipt_id, event.event_id, event_json,
                _event_fingerprint(event_json), interview_authority.account_digest,
                interview_authority.account_id, str(interview_id), str(question_id),
            ],
        ).fetchall()
        if changed != [(str(question_id),)]:
            raise DerivationConflict("derivation intent state changed")
        con.execute("COMMIT")
    except BaseException:
        con.execute("ROLLBACK")
        raise
    return target, event


def _load_processing(
    con: LockedConnection,
    row: tuple[Any, ...],
    authority: InterviewAccountAuthority,
) -> tuple[InvestigationAuthority, Event]:
    (
        investigation_id, investigation_digest, stream_key, event_id, event_json,
        fingerprint, document_id, answer_sha256, admission_receipt_id,
    ) = row
    target = InvestigationAuthority(authority.account_id, str(investigation_id))
    if target.investigation_digest != investigation_digest or target.stream_key != stream_key:
        raise DerivationConflict("derivation target authority is corrupt")
    if (
        not isinstance(event_json, str)
        or not isinstance(fingerprint, str)
        or _event_fingerprint(event_json) != fingerprint
    ):
        raise DerivationConflict("derivation event envelope is corrupt")
    event = Event.model_validate_json(event_json)
    expected_event_id = f"evt-{hashlib.sha256(str(document_id).encode()).hexdigest()[:32]}"
    if (
        event.event_id != event_id
        or event.event_id != expected_event_id
        or event.investigation_id != target.investigation_id
        or event.document_id != document_id
        or event.role != "acquisition"
        or event.policy_id != "interviews/canonical-answer-v1"
        or not isinstance(event.payload, DocumentLoadedPayload)
        or event.payload.content_hash != f"sha256:{answer_sha256}"
    ):
        raise DerivationConflict("derivation event identity is corrupt")
    from substrate.legal_gate.read import read_document, readable_admission

    admission = readable_admission(con, target, str(document_id))
    document = read_document(con, target, str(document_id))
    if (
        document.get("owner_user_id") != authority.account_id
        or document.get("investigation_id") != target.investigation_id
        or document.get("document_type") != "interview_answer"
        or not isinstance(document.get("raw_text"), str)
        or hashlib.sha256(document["raw_text"].encode()).hexdigest() != answer_sha256
        or admission.receipt_id != admission_receipt_id
    ):
        raise DerivationConflict("derivation document custody is corrupt")
    return target, event


def _record_failure(
    con: LockedConnection,
    authority: InterviewAccountAuthority,
    *,
    interview_id: str,
    question_id: str,
    code: str,
    terminal: bool,
    increment_attempt: bool,
) -> None:
    con.execute("BEGIN TRANSACTION")
    try:
        con.execute(
            "UPDATE interview_answer_derivations SET delivery_state = "
            "CASE WHEN ? THEN 'failed' ELSE delivery_state END, "
            "attempt_count = attempt_count + CASE WHEN ? THEN 1 ELSE 0 END, "
            "last_error_code = ?, "
            "updated_at = CURRENT_TIMESTAMP WHERE account_digest = ? AND owner_user_id = ? "
            "AND interview_id = ? AND question_id = ? AND delivery_state IN ('pending','processing')",
            [terminal, increment_attempt, code, authority.account_digest,
             authority.account_id, interview_id, question_id],
        )
        con.execute("COMMIT")
    except BaseException:
        con.execute("ROLLBACK")
        raise


def reconcile_answer_derivations(
    con: LockedConnection,
    authority: InterviewAccountAuthority,
    *,
    interview_id: str,
    limit: int = 25,
) -> ReconcileResult:
    """Deliver pending answers and acknowledge only after authorized event append."""
    con = _require_locked(con)
    if not 1 <= limit <= 100:
        raise ValueError("derivation reconcile limit is invalid")
    parent = con.execute(
        "SELECT 1 FROM interviews_authority WHERE account_digest = ? AND owner_user_id = ? "
        "AND interview_id = ?",
        [authority.account_digest, authority.account_id, interview_id],
    ).fetchone()
    if parent is None:
        raise ValueError("interview not found")
    keys = con.execute(
        "SELECT question_id FROM interview_answer_derivations WHERE account_digest = ? "
        "AND owner_user_id = ? AND interview_id = ? "
        "AND delivery_state IN ('pending','processing') ORDER BY created_at, question_id LIMIT ?",
        [authority.account_digest, authority.account_id, interview_id, limit],
    ).fetchall()
    completed = 0
    failed = 0
    for (question_id,) in keys:
        state = con.execute(
            "SELECT delivery_state FROM interview_answer_derivations WHERE account_digest = ? "
            "AND owner_user_id = ? AND interview_id = ? AND question_id = ?",
            [authority.account_digest, authority.account_id, interview_id, question_id],
        ).fetchone()[0]
        attempt_counted = False
        try:
            from .consent import consent_state

            if "record" not in consent_state(
                con, authority, interview_id=interview_id
            ):
                raise DerivationConsentBlocked("record consent is not currently granted")
            if state == "pending":
                materialize_row = con.execute(
                    "SELECT d.interview_id, d.question_id, d.answer_sha256, "
                    "d.investigation_id, d.investigation_digest, d.stream_key, i.transcript_turns "
                    "FROM interview_answer_derivations d JOIN interviews_authority i "
                    "ON i.account_digest = d.account_digest AND i.interview_id = d.interview_id "
                    "WHERE d.account_digest = ? AND d.owner_user_id = ? "
                    "AND d.interview_id = ? AND d.question_id = ? AND d.delivery_state = 'pending'",
                    [authority.account_digest, authority.account_id, interview_id, question_id],
                ).fetchone()
                if materialize_row is None:
                    continue
                target, event = _materialize(con, authority, materialize_row)
                attempt_counted = True
            else:
                processing_row = con.execute(
                    "SELECT investigation_id, investigation_digest, stream_key, event_id, "
                    "event_json, event_fingerprint, document_id, answer_sha256, "
                    "admission_receipt_id FROM interview_answer_derivations "
                    "WHERE account_digest = ? AND owner_user_id = ? AND interview_id = ? "
                    "AND question_id = ? AND delivery_state = 'processing'",
                    [authority.account_digest, authority.account_id, interview_id, question_id],
                ).fetchone()
                if processing_row is None:
                    continue
                target, event = _load_processing(con, processing_row, authority)
            append_event_once_authorized(target, event)
            con.execute("BEGIN TRANSACTION")
            try:
                changed = con.execute(
                    "UPDATE interview_answer_derivations SET delivery_state = 'completed', "
                    "attempt_count = attempt_count + ?, "
                    "last_error_code = NULL, updated_at = CURRENT_TIMESTAMP "
                    "WHERE account_digest = ? AND owner_user_id = ? AND interview_id = ? "
                    "AND question_id = ? AND delivery_state = 'processing' "
                    "AND event_id = ? RETURNING question_id",
                    [0 if attempt_counted else 1, authority.account_digest,
                     authority.account_id, interview_id,
                     question_id, event.event_id],
                ).fetchall()
                if changed != [(str(question_id),)]:
                    raise DerivationConflict("derivation completion state changed")
                con.execute("COMMIT")
            except BaseException:
                con.execute("ROLLBACK")
                raise
            completed += 1
        except (DerivationConflict, ValueError, TypeError) as exc:
            _record_failure(
                con, authority, interview_id=interview_id, question_id=str(question_id),
                code=type(exc).__name__, terminal=True,
                increment_attempt=not attempt_counted,
            )
            failed += 1
        except Exception as exc:
            _record_failure(
                con, authority, interview_id=interview_id, question_id=str(question_id),
                code=type(exc).__name__, terminal=False,
                increment_attempt=not attempt_counted,
            )
    counts = dict(
        con.execute(
            "SELECT delivery_state, count(*) FROM interview_answer_derivations "
            "WHERE account_digest = ? AND owner_user_id = ? AND interview_id = ? "
            "GROUP BY delivery_state",
            [authority.account_digest, authority.account_id, interview_id],
        ).fetchall()
    )
    return ReconcileResult(
        attempted=len(keys), completed=completed,
        pending=int(counts.get("pending", 0)) + int(counts.get("processing", 0)),
        failed=failed,
    )


__all__ = ["ReconcileResult", "reconcile_answer_derivations"]
