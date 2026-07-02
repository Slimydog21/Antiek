"""Contract-shaped Speak interviewer result boundary.

``InterviewerResultContract`` is the cross-product shape Write consumes from
Speak: one interview, the claims extracted from it, its contributor payee if
known, and the honest corroboration ceiling. The live source of truth is the
Speak claim ledger, not the role prompt parser.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

CorroborationStatus = Literal["uncorroborated", "multiply_attested"]


@dataclass(frozen=True)
class InterviewerResultState:
    """Live Speak state that structurally conforms to
    ``InterviewerResultContract``."""

    interview_id: str
    project_id: str
    contributor_ip_holder_id: str | None
    extracted_claim_ids: tuple[str, ...]
    corroboration: CorroborationStatus


def interviewer_result_for_interview(
    con: Any,
    interview_id: str,
) -> InterviewerResultState:
    """Project one persisted interview into the shared interviewer contract.

    Corroboration is intentionally binary at this boundary: if any extracted
    claim from the interview has been cross-interviewee corroborated, the
    interview result is ``multiply_attested``. Operator attestation is a publish
    review decision, not corroboration, so it does not raise this field.
    """
    from .contributor import get_payee
    from .schema import ensure_speak_schema

    ensure_speak_schema(con)
    project_row = con.execute(
        "SELECT project_id FROM interviews WHERE interview_id = ?",
        [interview_id],
    ).fetchone()
    if project_row is None:
        raise ValueError(f"interview {interview_id!r} not found")

    claim_rows = con.execute(
        "SELECT claim_id, verification FROM speak_claims "
        "WHERE interview_id = ? ORDER BY created_at, claim_id",
        [interview_id],
    ).fetchall()
    claim_ids = tuple(str(row[0]) for row in claim_rows)
    corroboration: CorroborationStatus = (
        "multiply_attested"
        if any(row[1] == "multiply_attested" for row in claim_rows)
        else "uncorroborated"
    )
    payee = get_payee(con, interview_id)

    return InterviewerResultState(
        interview_id=interview_id,
        project_id=str(project_row[0]),
        contributor_ip_holder_id=(payee.ip_holder_id if payee is not None else None),
        extracted_claim_ids=claim_ids,
        corroboration=corroboration,
    )
