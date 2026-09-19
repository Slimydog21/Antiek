"""Explicit owner binding and durable intents for interview answer derivation.

This module deliberately does not run the legacy answer-to-document bridge.  It
closes the authority seam first: an authenticated owner binds a project to one
account-qualified investigation, and answer commits stage an immutable intent
for that exact destination in the same database transaction.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from substrate.investigation_tenancy import InvestigationAuthority

from .authority import InterviewAccountAuthority


class DerivationConflict(RuntimeError):
    """Stored binding or answer identity disagrees with the proposed intent."""


@dataclass(frozen=True)
class DerivationIntent:
    interview_id: str
    question_id: str
    investigation_id: str
    answer_sha256: str
    delivery_state: str


def _bind_project(
    con: Any,
    authority: InterviewAccountAuthority,
    *,
    project_id: str,
    investigation: InvestigationAuthority,
) -> int:
    """Bind an owned interview project to an exact owned investigation."""
    if investigation.account_id != authority.account_id:
        raise ValueError("derivation target crosses account authority")
    parent = con.execute(
        "SELECT 1 FROM interview_projects_authority WHERE account_digest = ? "
        "AND owner_user_id = ? AND project_id = ?",
        [authority.account_digest, authority.account_id, project_id],
    ).fetchone()
    if parent is None:
        raise ValueError("interview project not found")
    existing = con.execute(
        "SELECT investigation_id, investigation_digest, stream_key, revision "
        "FROM interview_derivation_bindings WHERE account_digest = ? AND project_id = ?",
        [authority.account_digest, project_id],
    ).fetchone()
    proposed = (
        investigation.investigation_id,
        investigation.investigation_digest,
        investigation.stream_key,
    )
    if existing is not None and tuple(existing[:3]) == proposed:
        return int(existing[3])
    pending = con.execute(
        "SELECT count(*) FROM interview_answer_derivations WHERE account_digest = ? "
        "AND project_id = ? AND delivery_state IN ('pending', 'processing')",
        [authority.account_digest, project_id],
    ).fetchone()[0]
    if existing is not None and pending:
        raise DerivationConflict("derivation target has pending answer intents")
    revision = int(existing[3]) + 1 if existing is not None else 1
    con.execute(
        "INSERT INTO interview_derivation_bindings "
        "(account_digest, project_id, owner_user_id, investigation_id, "
        "investigation_digest, stream_key, revision) VALUES (?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT (account_digest, project_id) DO UPDATE SET "
        "owner_user_id = excluded.owner_user_id, investigation_id = excluded.investigation_id, "
        "investigation_digest = excluded.investigation_digest, stream_key = excluded.stream_key, "
        "revision = excluded.revision, updated_at = now()",
        [authority.account_digest, project_id, authority.account_id, *proposed, revision],
    )
    # Binding is also the admission point for answers recorded while the
    # project was intentionally unbound. Backfill them in this same transaction
    # so choosing a target cannot leave earlier research permanently stranded.
    interviews = con.execute(
        "SELECT interview_id, transcript_turns FROM interviews_authority "
        "WHERE account_digest = ? AND owner_user_id = ? AND project_id = ?",
        [authority.account_digest, authority.account_id, project_id],
    ).fetchall()
    for interview_id, raw_turns in interviews:
        try:
            turns = json.loads(raw_turns) if raw_turns else []
        except (TypeError, ValueError) as exc:
            raise DerivationConflict("interview transcript is corrupt") from exc
        if not isinstance(turns, list) or not all(isinstance(turn, dict) for turn in turns):
            raise DerivationConflict("interview transcript is corrupt")
        for turn in turns:
            question_id = turn.get("question_id")
            answer_text = turn.get("text")
            if turn.get("role") != "informant" or question_id is None:
                continue
            if not isinstance(question_id, str) or not question_id.strip():
                raise DerivationConflict("interview question identity is corrupt")
            if not isinstance(answer_text, str):
                raise DerivationConflict("interview answer is corrupt")
            stage_answer_if_bound(
                con, authority, interview_id=str(interview_id),
                question_id=question_id, answer_text=answer_text,
            )
    return revision


def bind_project(
    con: Any,
    authority: InterviewAccountAuthority,
    *,
    project_id: str,
    investigation: InvestigationAuthority,
) -> int:
    """Commit the authority binding and its revision atomically."""
    con.execute("BEGIN TRANSACTION")
    try:
        revision = _bind_project(
            con, authority, project_id=project_id, investigation=investigation
        )
        con.execute("COMMIT")
        return revision
    except BaseException:
        con.execute("ROLLBACK")
        raise


def stage_answer_if_bound(
    con: Any,
    authority: InterviewAccountAuthority,
    *,
    interview_id: str,
    question_id: str,
    answer_text: str,
) -> DerivationIntent | None:
    """Stage an immutable derivation intent; return None when no target is bound."""
    row = con.execute(
        "SELECT i.project_id, b.investigation_id, b.investigation_digest, b.stream_key, "
        "b.revision FROM interviews_authority i JOIN interview_derivation_bindings b "
        "ON b.account_digest = i.account_digest AND b.project_id = i.project_id "
        "WHERE i.account_digest = ? AND i.owner_user_id = ? AND i.interview_id = ?",
        [authority.account_digest, authority.account_id, interview_id],
    ).fetchone()
    if row is None:
        return None
    project_id, investigation_id, investigation_digest, stream_key, revision = row
    answer_sha256 = hashlib.sha256(answer_text.encode("utf-8")).hexdigest()
    existing = con.execute(
        "SELECT answer_sha256, investigation_id, investigation_digest, stream_key, "
        "binding_revision, delivery_state FROM interview_answer_derivations "
        "WHERE account_digest = ? AND interview_id = ? AND question_id = ?",
        [authority.account_digest, interview_id, question_id],
    ).fetchone()
    expected = (
        answer_sha256, investigation_id, investigation_digest, stream_key, int(revision)
    )
    if existing is None:
        con.execute(
            "INSERT INTO interview_answer_derivations "
            "(account_digest, interview_id, question_id, project_id, owner_user_id, "
            "answer_sha256, investigation_id, investigation_digest, stream_key, "
            "binding_revision) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [authority.account_digest, interview_id, question_id, project_id,
             authority.account_id, *expected],
        )
        state = "pending"
    else:
        if tuple(existing[:5]) != expected:
            raise DerivationConflict("answer derivation identity conflicts")
        state = str(existing[5])
    return DerivationIntent(
        interview_id, question_id, str(investigation_id), answer_sha256, state
    )


def intent_for(
    con: Any, authority: InterviewAccountAuthority, *, interview_id: str, question_id: str
) -> DerivationIntent | None:
    row = con.execute(
        "SELECT investigation_id, answer_sha256, delivery_state "
        "FROM interview_answer_derivations WHERE account_digest = ? "
        "AND owner_user_id = ? AND interview_id = ? AND question_id = ?",
        [authority.account_digest, authority.account_id, interview_id, question_id],
    ).fetchone()
    return None if row is None else DerivationIntent(
        interview_id, question_id, str(row[0]), str(row[1]), str(row[2])
    )


__all__ = [
    "DerivationConflict", "DerivationIntent", "bind_project", "intent_for",
    "stage_answer_if_bound",
]
