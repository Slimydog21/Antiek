"""Speak SPR-03 — the project container + project-scoped aggregation.

A Speak project (e.g. "Dad's biography") groups N interviews under one
subject and one publish intent. It sits ON TOP of the existing
``interview_projects`` table (title/topic/guide) via the ``speak_projects``
sidecar, which adds the two things Speak needs: the publish intent
(which drives consent scope + economics) and the subject (whose
living/deceased status gates public publishing, SPR-01).

Project-scoped aggregation (M5): every interviewee's claims land in
``speak_claims`` keyed by ``project_id`` AND ``interview_id`` — so the
project's knowledge is one queryable, per-interviewee-attributed set,
and one project's graph never bleeds into another's (the isolation
test). Voice-note nodes are project-scoped the same way via
``investigation_id = project_id`` in ``ingest_voice_note``.

Invite-link contributors are SOURCES, not accounts — the operator owns
the graph. That line is what keeps v1 inside the single-operator
constraint; the open public-contribution ecosystem is gated on G7
(``invitations.py``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.graph.ops import insert_interview_project

from .events import SPEAK_PROJECT_CREATED, record_speak_event
from .schema import ensure_speak_schema
from .third_party import ClaimRecord, list_claims

_PUBLISH_INTENTS = frozenset({"private_never_published", "will_be_public"})
_SUBJECT_STATUSES = frozenset({"living", "deceased", "non_identifiable", "unknown"})


@dataclass(frozen=True)
class SpeakProject:
    project_id: str
    title: str
    subject_ref: str | None
    subject_status: str
    publish_intent: str
    invitation_mode: str


def create_project(
    con: Any,
    *,
    title: str,
    subject_ref: str | None = None,
    subject_status: str = "unknown",
    publish_intent: str = "private_never_published",
    topic_description: str | None = None,
    interview_guide: Any | None = None,
    project_id: str | None = None,
    emit_event: bool = True,
) -> SpeakProject:
    """Create a Speak project: the base ``interview_projects`` row plus
    the ``speak_projects`` sidecar carrying publish intent + subject."""
    ensure_speak_schema(con)
    if publish_intent not in _PUBLISH_INTENTS:
        raise ValueError(f"unknown publish_intent: {publish_intent!r}")
    if subject_status not in _SUBJECT_STATUSES:
        raise ValueError(f"unknown subject_status: {subject_status!r}")
    pid = insert_interview_project(
        con,
        title=title,
        topic_description=topic_description,
        interview_guide=interview_guide,
        project_id=project_id,
    )
    con.execute(
        "INSERT INTO speak_projects "
        "(project_id, publish_intent, invitation_mode, subject_ref, subject_status) "
        "VALUES (?, ?, 'private', ?, ?) ON CONFLICT (project_id) DO NOTHING",
        [pid, publish_intent, subject_ref, subject_status],
    )
    if emit_event:
        record_speak_event(
            SPEAK_PROJECT_CREATED,
            {"title": title, "publish_intent": publish_intent,
             "subject_ref": subject_ref, "subject_status": subject_status},
            project_id=pid,
        )
    return get_project(con, pid)


def get_project(con: Any, project_id: str) -> SpeakProject:
    row = con.execute(
        "SELECT p.project_id, ip.title, p.subject_ref, p.subject_status, "
        "p.publish_intent, p.invitation_mode "
        "FROM speak_projects p "
        "JOIN interview_projects ip ON ip.project_id = p.project_id "
        "WHERE p.project_id = ?",
        [project_id],
    ).fetchone()
    if row is None:
        raise ValueError(f"speak project {project_id!r} not found")
    return SpeakProject(
        project_id=row[0], title=row[1], subject_ref=row[2],
        subject_status=row[3], publish_intent=row[4], invitation_mode=row[5],
    )


def set_publish_intent(con: Any, *, project_id: str, publish_intent: str) -> None:
    """Change a project's publish intent (used by the SPR-07 mode flip).
    Does NOT itself re-gate consent — the caller (economics_mode) does."""
    ensure_speak_schema(con)
    if publish_intent not in _PUBLISH_INTENTS:
        raise ValueError(f"unknown publish_intent: {publish_intent!r}")
    con.execute(
        "UPDATE speak_projects SET publish_intent = ?, updated_at = CURRENT_TIMESTAMP "
        "WHERE project_id = ?",
        [publish_intent, project_id],
    )


# ---------------------------------------------------------------------------
# M5 — project-scoped aggregation + isolation
# ---------------------------------------------------------------------------


def project_claims(con: Any, project_id: str) -> list[ClaimRecord]:
    """All claims aggregated for this project (only this project's —
    isolation). Each carries its source ``interview_id`` (attribution)."""
    return list_claims(con, project_id)


def contributions_by_interviewee(con: Any, project_id: str) -> dict[str, int]:
    """How many claims each interviewee contributed to the project.
    The raw input the SPR-06 economics refine into weighted shares."""
    rows = con.execute(
        "SELECT interview_id, count(*) FROM speak_claims "
        "WHERE project_id = ? AND interview_id IS NOT NULL "
        "GROUP BY interview_id",
        [project_id],
    ).fetchall()
    return {r[0]: int(r[1]) for r in rows}


def interview_ids(con: Any, project_id: str) -> list[str]:
    """The interviews belonging to a project (its supply side)."""
    rows = con.execute(
        "SELECT interview_id FROM interviews WHERE project_id = ? ORDER BY invited_at",
        [project_id],
    ).fetchall()
    return [r[0] for r in rows]
