"""Speak SPR-01 M2 — third-party-claim tagging.

A "third-party claim" is an assertion an interviewee makes about a
person *other than themselves* — the biography subject, or someone
else. In a biography almost every substantive claim is third-party
("my father was brave", "his brother cheated him"), and those are
exactly the claims that can defame a real person. They must be
corroborated (SPR-05) or operator-attested (SPR-01 M3) before they may
appear in a public output.

This module records claims and tags the third-party ones. The tag is
the input to the verification-before-publish gate (``publish_gate.py``):
a third-party claim whose ``verification`` is still ``unverified`` is
NOT publishable.

A claim is third-party when it is about an identifiable person who is
not the speaking interviewee. The caller signals this — we don't try to
infer identity from free text (that would be a confident guess about
exactly the kind of detail that gets people defamed). Default-safe: if a
claim is marked ``about_subject`` and the speaker isn't the subject, it
is third-party.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from .events import SPEAK_THIRD_PARTY_TAGGED, record_speak_event
from .ids import new_claim_id
from .schema import ensure_speak_schema


@dataclass(frozen=True)
class ClaimRecord:
    claim_id: str
    project_id: str
    interview_id: Optional[str]
    text: str
    about_subject: bool
    is_third_party: bool
    subject_ref: Optional[str]
    verification: str  # 'unverified' | 'multiply_attested' | 'operator_attested' | 'contradicted'
    confidence: float


def record_claim(
    con: Any,
    *,
    project_id: str,
    text: str,
    interview_id: Optional[str] = None,
    about_subject: bool = False,
    subject_ref: Optional[str] = None,
    speaker_is_subject: bool = False,
    confidence: float = 0.5,
    claim_id: Optional[str] = None,
) -> ClaimRecord:
    """Record one claim, tagging it third-party when warranted.

    third-party = the claim is about an identifiable person (the subject
    via ``about_subject``, or another person via ``subject_ref``) who is
    not the speaking interviewee (``speaker_is_subject=False``). A claim
    an interviewee makes purely about themselves is not third-party.
    """
    ensure_speak_schema(con)
    cid = claim_id or new_claim_id(project_id, text, interview_id)
    is_third_party = bool(
        (about_subject or subject_ref is not None) and not speaker_is_subject
    )
    con.execute(
        "INSERT INTO speak_claims "
        "(claim_id, project_id, interview_id, text, about_subject, "
        " is_third_party, subject_ref, verification, confidence) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, 'unverified', ?) "
        "ON CONFLICT (claim_id) DO NOTHING",
        [cid, project_id, interview_id, text, about_subject,
         is_third_party, subject_ref, confidence],
    )
    if is_third_party:
        record_speak_event(
            SPEAK_THIRD_PARTY_TAGGED,
            {"claim_id": cid, "subject_ref": subject_ref,
             "about_subject": about_subject},
            project_id=project_id,
        )
    return get_claim(con, cid)


def tag_third_party(con: Any, claim_id: str, *, subject_ref: Optional[str] = None) -> None:
    """Mark an existing claim as a third-party claim (requires
    verification before publish). Idempotent."""
    ensure_speak_schema(con)
    row = con.execute(
        "SELECT project_id FROM speak_claims WHERE claim_id = ?", [claim_id]
    ).fetchone()
    if row is None:
        raise ValueError(f"claim {claim_id!r} not found")
    con.execute(
        "UPDATE speak_claims SET is_third_party = TRUE, "
        "subject_ref = COALESCE(?, subject_ref), updated_at = CURRENT_TIMESTAMP "
        "WHERE claim_id = ?",
        [subject_ref, claim_id],
    )
    record_speak_event(
        SPEAK_THIRD_PARTY_TAGGED,
        {"claim_id": claim_id, "subject_ref": subject_ref, "retagged": True},
        project_id=row[0],
    )


def get_claim(con: Any, claim_id: str) -> ClaimRecord:
    row = con.execute(
        "SELECT claim_id, project_id, interview_id, text, about_subject, "
        "is_third_party, subject_ref, verification, confidence "
        "FROM speak_claims WHERE claim_id = ?",
        [claim_id],
    ).fetchone()
    if row is None:
        raise ValueError(f"claim {claim_id!r} not found")
    return ClaimRecord(
        claim_id=row[0], project_id=row[1], interview_id=row[2], text=row[3],
        about_subject=bool(row[4]), is_third_party=bool(row[5]),
        subject_ref=row[6], verification=row[7], confidence=float(row[8]),
    )


def list_claims(
    con: Any, project_id: str, *, third_party_only: bool = False
) -> list[ClaimRecord]:
    sql = (
        "SELECT claim_id FROM speak_claims WHERE project_id = ?"
        + (" AND is_third_party = TRUE" if third_party_only else "")
        + " ORDER BY created_at"
    )
    return [get_claim(con, r[0]) for r in con.execute(sql, [project_id]).fetchall()]
