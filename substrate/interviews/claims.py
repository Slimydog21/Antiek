"""Owner-qualified explicit claims grounded in completed interview answers."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from runtime.db_lock import LockedConnection
from substrate.investigation_tenancy import InvestigationAuthority
from substrate.legal_gate.read import read_document, readable_admission

from .authority import InterviewAccountAuthority
from .consent import consent_state


class ClaimConflict(RuntimeError):
    pass


@dataclass(frozen=True)
class CanonicalClaim:
    claim_id: str
    project_id: str
    interview_id: str
    question_id: str
    source_document_id: str
    text: str
    about_subject: bool
    is_third_party: bool
    subject_ref: str | None
    speaker_is_subject: bool
    independence_key: str | None
    verification: str
    confidence: float


def _require_locked(con: object) -> LockedConnection:
    if not isinstance(con, LockedConnection):
        raise TypeError("canonical interview claims require a LockedConnection")
    return con


def _begin_if_needed(con: LockedConnection) -> bool:
    if con.transaction_active:
        return False
    con.execute("BEGIN TRANSACTION")
    return True


def _claim_id(
    authority: InterviewAccountAuthority,
    *,
    interview_id: str,
    question_id: str,
    document_id: str,
    text_sha256: str,
    subject_ref: str | None,
    about_subject: bool,
    speaker_is_subject: bool,
) -> str:
    encoded = "\0".join(
        (
            authority.account_digest, interview_id, question_id, document_id,
            text_sha256, subject_ref or "", str(about_subject), str(speaker_is_subject),
        )
    )
    digest = hashlib.sha256(b"antiek-interview-claim-v1\0" + encoded.encode()).hexdigest()
    return f"ivcl-{digest[:32]}"


def _from_row(row: tuple[Any, ...]) -> CanonicalClaim:
    return CanonicalClaim(
        claim_id=str(row[0]), project_id=str(row[1]), interview_id=str(row[2]),
        question_id=str(row[3]), source_document_id=str(row[4]), text=str(row[5]),
        about_subject=bool(row[6]), is_third_party=bool(row[7]),
        subject_ref=None if row[8] is None else str(row[8]),
        speaker_is_subject=bool(row[9]),
        independence_key=None if row[10] is None else str(row[10]),
        verification=str(row[11]), confidence=float(row[12]),
    )


def record_claim(
    con: LockedConnection,
    authority: InterviewAccountAuthority,
    *,
    interview_id: str,
    question_id: str,
    source_document_id: str,
    text: str,
    about_subject: bool,
    subject_ref: str | None,
    speaker_is_subject: bool,
    independence_key: str | None = None,
    confidence: float,
) -> CanonicalClaim:
    """Record an operator-confirmed claim; never infer identity from its text."""
    con = _require_locked(con)
    if not text or text != text.strip():
        raise ValueError("claim text is invalid")
    if not 0.0 <= confidence <= 1.0:
        raise ValueError("claim confidence is invalid")
    if about_subject and not subject_ref:
        raise ValueError("about-subject claims require an explicit subject_ref")
    if subject_ref is not None and (not subject_ref or subject_ref != subject_ref.strip()):
        raise ValueError("claim subject_ref is invalid")
    if independence_key is not None and (
        not independence_key or independence_key != independence_key.strip()
    ):
        raise ValueError("claim independence_key is invalid")
    scopes = consent_state(con, authority, interview_id=interview_id)
    if "record" not in scopes:
        raise ClaimConflict("record consent is not currently granted")
    identifiable = bool(about_subject or subject_ref is not None)
    if identifiable and "attribute" not in scopes:
        raise ClaimConflict("attribute consent is not currently granted")
    derivation = con.execute(
        "SELECT d.project_id, d.investigation_id, d.investigation_digest, d.stream_key, "
        "d.admission_receipt_id FROM interview_answer_derivations d "
        "WHERE d.account_digest = ? AND d.owner_user_id = ? AND d.interview_id = ? "
        "AND d.question_id = ? AND d.document_id = ? AND d.delivery_state = 'completed'",
        [authority.account_digest, authority.account_id, interview_id,
         question_id, source_document_id],
    ).fetchone()
    if derivation is None:
        raise ValueError("completed interview answer document not found")
    project_id, investigation_id, investigation_digest, stream_key, receipt_id = derivation
    target = InvestigationAuthority(authority.account_id, str(investigation_id))
    if target.investigation_digest != investigation_digest or target.stream_key != stream_key:
        raise ClaimConflict("claim source authority is corrupt")
    admission = readable_admission(con, target, source_document_id)
    document = read_document(con, target, source_document_id)
    if (
        admission.receipt_id != receipt_id
        or document.get("owner_user_id") != authority.account_id
        or document.get("document_type") != "interview_answer"
        or document.get("investigation_id") != target.investigation_id
    ):
        raise ClaimConflict("claim source custody is corrupt")
    text_sha256 = hashlib.sha256(text.encode()).hexdigest()
    claim_id = _claim_id(
        authority, interview_id=interview_id, question_id=question_id,
        document_id=source_document_id, text_sha256=text_sha256,
        subject_ref=subject_ref, about_subject=about_subject,
        speaker_is_subject=speaker_is_subject,
    )
    is_third_party = identifiable and not speaker_is_subject
    expected = (
        str(project_id), interview_id, question_id, source_document_id,
        str(receipt_id), authority.account_id, text, text_sha256, about_subject,
        is_third_party, subject_ref, speaker_is_subject, float(confidence),
        independence_key,
    )
    owns_transaction = _begin_if_needed(con)
    try:
        existing = con.execute(
            "SELECT project_id, interview_id, question_id, source_document_id, "
            "source_receipt_id, owner_user_id, text, text_sha256, about_subject, "
            "is_third_party, subject_ref, speaker_is_subject, confidence "
            ", independence_key "
            "FROM interview_claims_authority WHERE account_digest = ? AND claim_id = ?",
            [authority.account_digest, claim_id],
        ).fetchone()
        if existing is None:
            con.execute(
                "INSERT INTO interview_claims_authority "
                "(account_digest, claim_id, project_id, interview_id, question_id, "
                "source_document_id, source_receipt_id, owner_user_id, text, text_sha256, "
                "about_subject, is_third_party, subject_ref, speaker_is_subject, confidence, "
                "independence_key) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [authority.account_digest, claim_id, *expected],
            )
        elif tuple(existing) != expected:
            raise ClaimConflict("canonical claim identity conflicts")
        if owns_transaction:
            con.execute("COMMIT")
    except BaseException:
        if owns_transaction:
            con.execute("ROLLBACK")
        raise
    return get_claim(con, authority, claim_id=claim_id)


def get_claim(
    con: Any, authority: InterviewAccountAuthority, *, claim_id: str
) -> CanonicalClaim:
    row = con.execute(
        "SELECT claim_id, project_id, interview_id, question_id, source_document_id, "
        "text, about_subject, is_third_party, subject_ref, speaker_is_subject, "
        "independence_key, verification, confidence FROM interview_claims_authority "
        "WHERE account_digest = ? AND owner_user_id = ? AND claim_id = ?",
        [authority.account_digest, authority.account_id, claim_id],
    ).fetchone()
    if row is None:
        raise ValueError("canonical claim not found")
    return _from_row(row)


def list_claims(
    con: Any,
    authority: InterviewAccountAuthority,
    *,
    project_id: str,
) -> list[CanonicalClaim]:
    rows = con.execute(
        "SELECT claim_id, project_id, interview_id, question_id, source_document_id, "
        "text, about_subject, is_third_party, subject_ref, speaker_is_subject, "
        "independence_key, verification, confidence FROM interview_claims_authority "
        "WHERE account_digest = ? AND owner_user_id = ? AND project_id = ? "
        "ORDER BY created_at, claim_id",
        [authority.account_digest, authority.account_id, project_id],
    ).fetchall()
    visible: list[CanonicalClaim] = []
    scopes_by_interview: dict[str, set[str]] = {}
    for row in rows:
        claim = _from_row(row)
        scopes = scopes_by_interview.get(claim.interview_id)
        if scopes is None:
            scopes = consent_state(con, authority, interview_id=claim.interview_id)
            scopes_by_interview[claim.interview_id] = scopes
        if "record" not in scopes:
            continue
        if (claim.about_subject or claim.subject_ref is not None) and "attribute" not in scopes:
            continue
        visible.append(claim)
    return visible


__all__ = ["CanonicalClaim", "ClaimConflict", "get_claim", "list_claims", "record_claim"]
