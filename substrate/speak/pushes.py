"""Speak dual-push / continuous-ping helpers (Anti-Ek Speak remap).

Dogfoodable MVP — NO second notification stack, NO ML profile matching.
Email re-ping reuses substrate.auth get_email_provider (AgentMail/Resend/Mock):

  (a) Public opportunities — will_be_public projects ranked by fewest
      voices first ("what you'd add value to" heuristic). Honest: not
      profile-matched ML.
  (b) Private re-pings — invitees who are not declined, have a token,
      and still have pending questions (or can receive followups).
      ``prepare_reping`` runs ``next_followups`` (consent-scoped: skips
      declined) and returns the SpeakInvite door path.

Cite: docs/decisions/anti-ek-speak-deepblu-remap-2026-09-18.md §PUSHES.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.speak import async_interview
from substrate.speak.schema import ensure_speak_schema


@dataclass(frozen=True)
class PublicOpportunity:
    project_id: str
    title: str
    subject_ref: str | None
    voice_count: int
    """Honest ranking label — not ML."""
    rank_reason: str


@dataclass(frozen=True)
class PrivateReping:
    project_id: str
    project_title: str
    interview_id: str
    who: str
    status: str
    token: str
    pending_question_count: int
    invite_path: str


@dataclass(frozen=True)
class RepingResult:
    interview_id: str
    token: str
    invite_path: str
    followups_added: int
    pending_question_count: int
    skipped_reason: str | None = None
    email_status: str | None = None
    email_to: str | None = None
    email_provider: str | None = None
    email_message_id: str | None = None
    email_detail: str | None = None


def list_public_opportunities(con: Any, *, limit: int = 20) -> list[PublicOpportunity]:
    """Naive public push list: public-intent projects needing more voices.

    Ranking = ascending voice_count (fewest first). Explicitly NOT ML /
    profile matching — dogfood surface for dual-push (a).
    """
    ensure_speak_schema(con)
    rows = con.execute(
        """
        SELECT p.project_id, ip.title, p.subject_ref,
               (SELECT COUNT(*) FROM interviews i
                WHERE i.project_id = p.project_id
                  AND i.status NOT IN ('declined')) AS voice_count
        FROM speak_projects p
        JOIN interview_projects ip ON ip.project_id = p.project_id
        WHERE p.publish_intent = 'will_be_public'
        ORDER BY voice_count ASC, ip.title ASC
        LIMIT ?
        """,
        [limit],
    ).fetchall()
    out: list[PublicOpportunity] = []
    for r in rows:
        vc = int(r[3] or 0)
        out.append(
            PublicOpportunity(
                project_id=r[0],
                title=r[1] or r[0],
                subject_ref=r[2],
                voice_count=vc,
                rank_reason=(
                    "fewest voices first — heuristic, not profile matching"
                    if vc == 0
                    else f"{vc} voice(s) so far — heuristic, not profile matching"
                ),
            )
        )
    return out


def list_private_repings_at(db_path: str, *, limit: int = 50) -> list[PrivateReping]:
    """Invitees still in flight; fills pending_question_count via resume()."""
    from runtime.db_lock import connect_write

    with connect_write(db_path, purpose="speak/pushes.list_private") as con:
        ensure_speak_schema(con)
        rows = con.execute(
            """
            SELECT p.project_id, ip.title, i.interview_id,
                   COALESCE(i.informant_email, i.informant_handle, 'invitee'),
                   i.status, s.token
            FROM interviews i
            JOIN speak_projects p ON p.project_id = i.project_id
            JOIN interview_projects ip ON ip.project_id = p.project_id
            JOIN speak_invites s ON s.interview_id = i.interview_id
            WHERE i.status NOT IN ('declined', 'completed')
              AND s.token IS NOT NULL
            ORDER BY i.invited_at DESC
            LIMIT ?
            """,
            [limit],
        ).fetchall()

    out: list[PrivateReping] = []
    for r in rows:
        interview_id = r[2]
        token = r[5]
        try:
            session = async_interview.resume(db_path, interview_id)
            pending = len(session.pending_questions())
        except Exception:
            pending = 0
        # Surface invitees who still owe answers OR are merely invited
        # (pending may be 0 until followups are generated — still re-pingable).
        if pending == 0 and r[4] not in ("invited", "in_progress", "incomplete"):
            continue
        out.append(
            PrivateReping(
                project_id=r[0],
                project_title=r[1] or r[0],
                interview_id=interview_id,
                who=str(r[3]),
                status=str(r[4]),
                token=token,
                pending_question_count=pending,
                invite_path=f"/speak/invite/{token}",
            )
        )
    return out


def prepare_reping(db_path: str, *, interview_id: str, send_email: bool = False) -> RepingResult:
    """Consent-scoped continuous ping: generate followups + return invite door.

    Skips declined interviews. Reuses ``async_interview.next_followups``.
    Optionally delivers the invite door by email via ``reping_mail``
    (AgentMail/Resend/Mock) when ``send_email`` is True, consent allows,
    and ``ANTIEK_SPEAK_REPING_EMAIL`` is set. Never emails declined invitees.
    """
    from runtime.db_lock import connect_write

    with connect_write(db_path, purpose="speak/pushes.reping_gate") as con:
        ensure_speak_schema(con)
        row = con.execute(
            "SELECT i.status, s.token, "
            "COALESCE(i.informant_email, ''), "
            "COALESCE(ip.title, p.project_id) "
            "FROM interviews i "
            "LEFT JOIN speak_invites s ON s.interview_id = i.interview_id "
            "LEFT JOIN speak_projects p ON p.project_id = i.project_id "
            "LEFT JOIN interview_projects ip ON ip.project_id = i.project_id "
            "WHERE i.interview_id = ?",
            [interview_id],
        ).fetchone()
        if row is None:
            raise ValueError(f"interview {interview_id!r} not found")
        status, token, informant_email, project_title = (
            row[0], row[1], row[2], row[3],
        )
        if status == "declined":
            return RepingResult(
                interview_id=interview_id,
                token=token or "",
                invite_path=f"/speak/invite/{token}" if token else "",
                followups_added=0,
                pending_question_count=0,
                skipped_reason="declined — consent-scoped, no re-ping",
                email_status="skipped_declined",
                email_detail="consent-scoped: never email declined invitees",
            )
        if not token:
            return RepingResult(
                interview_id=interview_id,
                token="",
                invite_path="",
                followups_added=0,
                pending_question_count=0,
                skipped_reason="no invite token",
                email_status="skipped_no_invite_path",
            )

    before = async_interview.resume(db_path, interview_id)
    before_pending = {q["id"] for q in before.pending_questions()}
    fus = async_interview.next_followups(db_path, interview_id=interview_id)
    after = async_interview.resume(db_path, interview_id)
    after_pending = after.pending_questions()
    added = sum(1 for q in after_pending if q["id"] not in before_pending)
    # Count newly generated followups from return value when pending unchanged
    if added == 0 and fus:
        added = len(fus)
    invite_path = f"/speak/invite/{token}"
    from substrate.speak import reping_mail

    mail = reping_mail.try_send_reping_email(
        to=informant_email or None,
        invite_path=invite_path,
        project_title=str(project_title or ""),
        followups_added=added,
        pending_question_count=len(after_pending),
        send_requested=send_email,
    )
    return RepingResult(
        interview_id=interview_id,
        token=token,
        invite_path=invite_path,
        followups_added=added,
        pending_question_count=len(after_pending),
        skipped_reason=None,
        email_status=mail.status,
        email_to=mail.to,
        email_provider=mail.provider,
        email_message_id=mail.message_id,
        email_detail=mail.detail,
    )


__all__ = [
    "PublicOpportunity",
    "PrivateReping",
    "RepingResult",
    "list_public_opportunities",
    "list_private_repings_at",
    "prepare_reping",
]
