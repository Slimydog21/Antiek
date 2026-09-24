"""Speak dual-push / continuous-ping helpers (Anti-Ek Speak remap).

Dogfoodable MVP — NO second notification stack, NO ML profile matching.
Email re-ping reuses substrate.auth get_email_provider (AgentMail/Resend/Mock):

  (a) Public opportunities — will_be_public projects ranked by a
      multi-signal heuristic (voice need + recency + subject/title
      specificity; optional interest-token overlap). Honest: not ML.
  (b) Private re-pings — invitees who are not declined, have a token,
      and still have pending questions (or can receive followups).
      ``prepare_reping`` runs ``next_followups`` (consent-scoped: skips
      declined) and returns the SpeakInvite door path.

Cite: docs/decisions/anti-ek-speak-deepblu-remap-2026-09-18.md §PUSHES.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from runtime.db_lock import DEFAULT_TIMEOUT_S
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
    rank_score: float = 0.0
    """Composite heuristic score (higher = listed first)."""


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


# --- ranking helpers (honest multi-signal heuristic, NOT ML) -----------------

_STOP = frozenset(
    {
        "a", "an", "the", "and", "or", "of", "for", "to", "in", "on", "at",
        "by", "with", "from", "his", "her", "their", "our", "my", "about",
        "story", "stories", "life", "biography", "remembrance", "memory",
        "memories", "project", "speak",
    }
)


def tokenize_interest(text: str | None) -> set[str]:
    """Lowercase alphanumeric tokens, stopwords dropped. Deterministic."""
    if not text:
        return set()
    raw: list[str] = []
    buf: list[str] = []
    for ch in text.lower():
        if ch.isalnum():
            buf.append(ch)
        else:
            if buf:
                raw.append("".join(buf))
                buf = []
    if buf:
        raw.append("".join(buf))
    return {t for t in raw if len(t) > 1 and t not in _STOP}


def _specificity_score(title: str, subject_ref: str | None) -> float:
    """More distinct content tokens → clearer contribution target (0..1)."""
    toks = tokenize_interest(f"{title} {subject_ref or ''}")
    if not toks:
        return 0.0
    return min(len(toks), 8) / 8.0


def _voice_need_score(voice_count: int) -> float:
    """Fewer voices → higher need. 0 voices = 1.0; decays toward 0."""
    return 1.0 / (1.0 + max(0, voice_count))


def _recency_score(created_at: Any, *, now_ts: float | None = None) -> float:
    """Newer projects score higher. Age > ~90 days → near floor."""
    import time
    from datetime import datetime

    now = now_ts if now_ts is not None else time.time()
    ts: float | None = None
    if created_at is None:
        return 0.5
    if isinstance(created_at, (int, float)):
        ts = float(created_at)
    elif isinstance(created_at, datetime):
        ts = created_at.timestamp()
    else:
        s = str(created_at).replace("Z", "")
        for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                ts = datetime.strptime(s[:26], fmt).timestamp()
                break
            except ValueError:
                continue
    if ts is None:
        return 0.5
    age_days = max(0.0, (now - ts) / 86400.0)
    return max(0.1, 1.0 - (age_days / 90.0) * 0.9)


def _overlap_score(title: str, subject_ref: str | None, interest: str | None) -> float:
    """Overlap of interest tokens with title+subject (0..1)."""
    q = tokenize_interest(interest)
    if not q:
        return 0.0
    doc = tokenize_interest(f"{title} {subject_ref or ''}")
    if not doc:
        return 0.0
    inter = q & doc
    if not inter:
        return 0.0
    return len(inter) / len(q | doc)


def _combine_scores(
    *,
    voice_need: float,
    recency: float,
    specificity: float,
    overlap: float,
    has_interest: bool,
) -> float:
    if has_interest:
        return (
            0.40 * voice_need
            + 0.20 * recency
            + 0.10 * specificity
            + 0.30 * overlap
        )
    return 0.55 * voice_need + 0.25 * recency + 0.20 * specificity


def _rank_reason(
    *,
    voice_count: int,
    recency: float,
    specificity: float,
    overlap: float,
    has_interest: bool,
) -> str:
    parts = [
        f"needs voices ({voice_count})",
        "newer first" if recency >= 0.6 else "older still open",
        "clearer subject" if specificity >= 0.4 else "thin subject labels",
    ]
    if has_interest:
        parts.append(
            f"title/subject overlap {overlap:.2f}"
            if overlap > 0
            else "no title/subject overlap with interest"
        )
    return "heuristic: " + "; ".join(parts) + " — not ML profile matching"


RANKING_HONESTY_ID = (
    "multi_signal_heuristic_voice_need_recency_specificity"
    "_optional_interest_overlap_not_ml"
)


def list_public_opportunities(
    con: Any,
    *,
    limit: int = 20,
    interest: str | None = None,
    ensure: bool = True,
) -> list[PublicOpportunity]:
    """Public push list with multi-signal heuristic ranking (NOT ML).

    Signals (documented in ``rank_reason`` / ``RANKING_HONESTY_ID``):
      • voice need — fewer non-declined voices score higher
      • recency — newer ``speak_projects.created_at`` scores higher
      • specificity — richer title/subject_ref token sets score higher
      • optional interest overlap — when ``interest`` is provided, Jaccard
        overlap with title+subject boosts the score (still token heuristic)

    Sort: descending composite score, then title.
    """
    if ensure:
        ensure_speak_schema(con)
    rows = con.execute(
        """
        SELECT p.project_id, ip.title, p.subject_ref,
               (SELECT COUNT(*) FROM interviews i
                WHERE i.project_id = p.project_id
                  AND i.status NOT IN ('declined')) AS voice_count,
               p.created_at
        FROM speak_projects p
        JOIN interview_projects ip ON ip.project_id = p.project_id
        WHERE p.publish_intent = 'will_be_public'
        """
    ).fetchall()
    has_interest = bool(tokenize_interest(interest))
    scored: list[PublicOpportunity] = []
    for r in rows:
        vc = int(r[3] or 0)
        title = r[1] or r[0]
        subject = r[2]
        voice_need = _voice_need_score(vc)
        recency = _recency_score(r[4])
        specificity = _specificity_score(title, subject)
        overlap = _overlap_score(title, subject, interest)
        score = _combine_scores(
            voice_need=voice_need,
            recency=recency,
            specificity=specificity,
            overlap=overlap,
            has_interest=has_interest,
        )
        scored.append(
            PublicOpportunity(
                project_id=r[0],
                title=title,
                subject_ref=subject,
                voice_count=vc,
                rank_reason=_rank_reason(
                    voice_count=vc,
                    recency=recency,
                    specificity=specificity,
                    overlap=overlap,
                    has_interest=has_interest,
                ),
                rank_score=score,
            )
        )
    scored.sort(key=lambda o: (-o.rank_score, o.title.lower()))
    return scored[:limit]


def list_private_repings_at(
    db_path: str, *, limit: int = 50, timeout_s: float = DEFAULT_TIMEOUT_S
) -> list[PrivateReping]:
    """Invitees still in flight; fills pending_question_count via resume().

    ``timeout_s`` bounds the write-lock wait (see ``async_interview``)."""
    from runtime.db_lock import connect_write

    with connect_write(
        db_path, purpose="speak/pushes.list_private", timeout_s=timeout_s
    ) as con:
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


def prepare_reping(
    db_path: str,
    *,
    interview_id: str,
    send_email: bool = False,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> RepingResult:
    """Consent-scoped continuous ping: generate followups + return invite door.

    Skips declined interviews. Reuses ``async_interview.next_followups``.
    Optionally delivers the invite door by email via ``reping_mail``
    (AgentMail/Resend/Mock) when ``send_email`` is True, consent allows,
    and ``ANTIEK_SPEAK_REPING_EMAIL`` is set. Never emails declined invitees.

    ``timeout_s`` bounds every write-lock wait here, including the one inside
    ``next_followups`` (see ``async_interview``).
    """
    from runtime.db_lock import connect_write

    with connect_write(
        db_path, purpose="speak/pushes.reping_gate", timeout_s=timeout_s
    ) as con:
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
    fus = async_interview.next_followups(
        db_path, interview_id=interview_id, timeout_s=timeout_s
    )
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
    "RANKING_HONESTY_ID",
    "list_public_opportunities",
    "list_private_repings_at",
    "prepare_reping",
    "tokenize_interest",
]
