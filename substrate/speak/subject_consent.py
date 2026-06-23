"""Speak SPR-01 M4 — subject consent for public publishing.

The interviewees consent to their own participation. But a biography is
*about* someone — the subject — and a living, identifiable subject has
their own right-of-publicity and defamation interest. Publishing a
biography about a living person publicly without their consent is a core
Speak liability.

The rule, deny-by-default:

    living + identifiable   → public publishing REQUIRES recorded
                              subject consent.
    deceased                → no living-person right-of-publicity in
                              most jurisdictions; allowed WITH a
                              documented rationale (not silent).
    non_identifiable        → no identifiable subject to consent;
                              allowed WITH a documented rationale.
    unknown                 → treated as living (the safe default):
                              consent required.

This is not legal advice; the living/deceased/identifiability line and
its jurisdictional nuance are exactly what G2 counsel reviews. The code
encodes a defensible default and records the basis for audit.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .events import SPEAK_SUBJECT_CONSENT_RECORDED, record_speak_event
from .schema import ensure_speak_schema

# Subject statuses that do NOT require living-subject consent, but DO
# require a documented rationale recorded alongside.
_DOCUMENTED_RULE_STATUSES = frozenset({"deceased", "non_identifiable"})


@dataclass(frozen=True)
class SubjectConsentDecision:
    allowed: bool
    reason: str


def record_subject_consent(
    con: Any,
    *,
    project_id: str,
    subject_ref: str,
    subject_status: str,
    consent_granted: bool,
    rationale: str | None = None,
) -> None:
    """Record the subject's consent (or the documented rule applied for a
    deceased / non-identifiable subject). Idempotent per (project,
    subject)."""
    ensure_speak_schema(con)
    if subject_status not in ("living", "deceased", "non_identifiable", "unknown"):
        raise ValueError(f"unknown subject_status: {subject_status!r}")
    con.execute(
        "DELETE FROM speak_subject_consent WHERE project_id = ? AND subject_ref = ?",
        [project_id, subject_ref],
    )
    con.execute(
        "INSERT INTO speak_subject_consent "
        "(project_id, subject_ref, subject_status, consent_granted, rationale) "
        "VALUES (?, ?, ?, ?, ?)",
        [project_id, subject_ref, subject_status, consent_granted, rationale],
    )
    record_speak_event(
        SPEAK_SUBJECT_CONSENT_RECORDED,
        {"subject_ref": subject_ref, "subject_status": subject_status,
         "consent_granted": consent_granted, "has_rationale": bool(rationale)},
        project_id=project_id,
    )


def public_publish_allowed_for_subject(
    con: Any, *, project_id: str, subject_ref: str
) -> SubjectConsentDecision:
    """Whether the subject permits PUBLIC publishing, per the rule above.
    Deny-by-default: an unrecorded subject is treated as living."""
    row = con.execute(
        "SELECT subject_status, consent_granted, rationale "
        "FROM speak_subject_consent WHERE project_id = ? AND subject_ref = ?",
        [project_id, subject_ref],
    ).fetchone()
    if row is None:
        return SubjectConsentDecision(
            False,
            f"no subject-consent record for {subject_ref!r}; a living, "
            "identifiable subject must consent before public publishing "
            "(treated as living by default).",
        )
    status, granted, rationale = row[0], bool(row[1]), row[2]
    if status in _DOCUMENTED_RULE_STATUSES:
        if not rationale:
            return SubjectConsentDecision(
                False,
                f"subject is {status}, which follows a documented different "
                "rule, but no rationale was recorded; record the basis "
                "before public publishing.",
            )
        return SubjectConsentDecision(
            True, f"subject is {status}; documented rule applied: {rationale}"
        )
    # living or unknown → consent required
    if granted:
        return SubjectConsentDecision(True, "living subject consented")
    return SubjectConsentDecision(
        False,
        "living/identifiable subject has not consented to public publishing; "
        "the project stays private.",
    )
