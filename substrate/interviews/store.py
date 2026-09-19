"""Owner-qualified canonical interview/project mutations."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from substrate.graph.ops import new_random_id

from .authority import InterviewAccountAuthority

MAX_TRANSCRIPT_TURNS = 2_000


class InterviewStateConflict(ValueError):
    """The interview exists but its lifecycle forbids the mutation."""


def create_project(con: Any, authority: InterviewAccountAuthority, *, title: str,
                   topic_description: str | None, deliverable_id: str | None,
                   interview_guide: object, project_id: str | None = None) -> str:
    pid = project_id or new_random_id("ivp")
    con.execute(
        "INSERT INTO interview_projects_authority "
        "(account_digest, project_id, owner_user_id, title, topic_description, "
        "deliverable_id, interview_guide) VALUES (?, ?, ?, ?, ?, ?, ?)",
        [authority.account_digest, pid, authority.account_id, title, topic_description,
         deliverable_id, json.dumps(interview_guide)],
    )
    return pid


def create_interview(con: Any, authority: InterviewAccountAuthority, *, project_id: str,
                     informant_handle: str | None, informant_email: str | None,
                     interview_id: str | None = None) -> str:
    exists = con.execute(
        "SELECT 1 FROM interview_projects_authority WHERE account_digest = ? "
        "AND owner_user_id = ? AND project_id = ?",
        [authority.account_digest, authority.account_id, project_id],
    ).fetchone()
    if exists is None:
        raise ValueError("interview project not found")
    iid = interview_id or new_random_id("intv")
    con.execute(
        "INSERT INTO interviews_authority "
        "(account_digest, interview_id, project_id, owner_user_id, informant_handle, "
        "informant_email) VALUES (?, ?, ?, ?, ?, ?)",
        [authority.account_digest, iid, project_id, authority.account_id,
         informant_handle, informant_email],
    )
    return iid


def _append_turn(con: Any, authority: InterviewAccountAuthority, *, interview_id: str,
                 role: str, text: str, question_id: str | None = None,
                 duration_seconds: float | None = None,
                 actor_kind: str = "operator_transcription") -> tuple[int, str]:
    if role not in ("interviewer", "informant"):
        raise ValueError(f"unknown turn role: {role!r}")
    row = con.execute(
        "SELECT transcript_turns, status, consent_recorded FROM interviews_authority "
        "WHERE account_digest = ? AND owner_user_id = ? AND interview_id = ?",
        [authority.account_digest, authority.account_id, interview_id],
    ).fetchone()
    if row is None:
        raise ValueError("interview not found")
    if row[1] in {"completed", "declined", "incomplete"}:
        raise InterviewStateConflict(f"interview is {row[1]}")
    if actor_kind not in {"operator_transcription", "invitee_capability"}:
        raise ValueError("turn actor is invalid")
    from .consent import consent_state

    if role == "informant" and "record" not in consent_state(
        con, authority, interview_id=interview_id
    ):
        raise InterviewStateConflict("interview consent has not been recorded")
    try:
        turns = json.loads(row[0]) if row[0] else []
    except (TypeError, ValueError) as exc:
        raise InterviewStateConflict("interview transcript is corrupt") from exc
    if not isinstance(turns, list) or not all(isinstance(turn, dict) for turn in turns):
        raise InterviewStateConflict("interview transcript is corrupt")
    if len(turns) >= MAX_TRANSCRIPT_TURNS:
        raise InterviewStateConflict("interview transcript turn limit reached")
    if question_id is not None:
        if not isinstance(question_id, str) or not question_id.strip():
            raise ValueError("question_id is invalid")
        for existing in turns:
            if existing.get("role") == role and existing.get("question_id") == question_id:
                if existing.get("text") == text:
                    if role == "informant":
                        from .derivation import stage_answer_if_bound

                        stage_answer_if_bound(
                            con, authority, interview_id=interview_id,
                            question_id=question_id, answer_text=text,
                        )
                    return len(turns), str(row[1])
                raise InterviewStateConflict("question already has a different answer")
    turn: dict[str, object] = {
        "role": role, "text": text,
        "ts": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "actor_kind": actor_kind,
    }
    if question_id is not None:
        turn["question_id"] = question_id
    if duration_seconds is not None:
        turn["duration_seconds"] = duration_seconds
    turns.append(turn)
    status = "in_progress" if row[1] == "invited" else row[1]
    con.execute(
        "UPDATE interviews_authority SET transcript_turns = ?, status = ?, "
        "started_at = CASE WHEN started_at IS NULL THEN CURRENT_TIMESTAMP ELSE started_at END "
        "WHERE account_digest = ? AND owner_user_id = ? AND interview_id = ?",
        [json.dumps(turns), status, authority.account_digest, authority.account_id, interview_id],
    )
    if role == "informant" and question_id is not None:
        from .derivation import stage_answer_if_bound

        stage_answer_if_bound(
            con, authority, interview_id=interview_id,
            question_id=question_id, answer_text=text,
        )
    return len(turns), status


def append_turn(con: Any, authority: InterviewAccountAuthority, *, interview_id: str,
                role: str, text: str, question_id: str | None = None,
                duration_seconds: float | None = None,
                actor_kind: str = "operator_transcription") -> tuple[int, str]:
    """Commit transcript and any bound derivation intent as one unit."""
    con.execute("BEGIN TRANSACTION")
    try:
        result = _append_turn(
            con, authority, interview_id=interview_id, role=role, text=text,
            question_id=question_id, duration_seconds=duration_seconds,
            actor_kind=actor_kind,
        )
        con.execute("COMMIT")
        return result
    except BaseException:
        con.execute("ROLLBACK")
        raise


def record_consent(con: Any, authority: InterviewAccountAuthority, *, interview_id: str,
                   granted: bool) -> bool:
    row = con.execute(
        "SELECT status FROM interviews_authority WHERE account_digest = ? "
        "AND owner_user_id = ? AND interview_id = ?",
        [authority.account_digest, authority.account_id, interview_id],
    ).fetchone()
    if row is None:
        return False
    if row[0] in {"completed", "declined", "incomplete"}:
        raise InterviewStateConflict(f"interview is {row[0]}")
    from .consent import record_consent_events

    record_consent_events(
        con, authority, interview_id=interview_id, scopes={"record"}, granted=granted,
        actor_kind="operator_witness",
    )
    return True


def decline(con: Any, authority: InterviewAccountAuthority, *, interview_id: str) -> bool:
    row = con.execute(
        "SELECT status FROM interviews_authority WHERE account_digest = ? "
        "AND owner_user_id = ? AND interview_id = ?",
        [authority.account_digest, authority.account_id, interview_id],
    ).fetchone()
    if row is None:
        return False
    if row[0] in {"completed", "declined", "incomplete"}:
        raise InterviewStateConflict(f"interview is {row[0]}")
    con.execute(
        "UPDATE interviews_authority SET status = 'declined' WHERE account_digest = ? "
        "AND owner_user_id = ? AND interview_id = ?",
        [authority.account_digest, authority.account_id, interview_id],
    )
    return True


def complete(con: Any, authority: InterviewAccountAuthority, *, interview_id: str,
             transcript_document_id: str | None) -> bool:
    exists = con.execute(
        "SELECT consent_recorded, status FROM interviews_authority WHERE account_digest = ? "
        "AND owner_user_id = ? AND interview_id = ?",
        [authority.account_digest, authority.account_id, interview_id],
    ).fetchone()
    if exists is None:
        return False
    if exists[1] in {"completed", "declined", "incomplete"}:
        raise InterviewStateConflict(f"interview is {exists[1]}")
    from .consent import consent_state

    if "record" not in consent_state(con, authority, interview_id=interview_id):
        raise InterviewStateConflict("interview consent has not been recorded")
    con.execute(
        "UPDATE interviews_authority SET status = 'completed', completed_at = CURRENT_TIMESTAMP, "
        "transcript_document_id = ? WHERE account_digest = ? AND owner_user_id = ? "
        "AND interview_id = ?",
        [transcript_document_id, authority.account_digest, authority.account_id, interview_id],
    )
    return True


__all__ = [
    "MAX_TRANSCRIPT_TURNS", "InterviewStateConflict", "append_turn", "complete",
    "create_interview", "create_project", "decline", "record_consent",
]
