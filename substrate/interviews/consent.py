"""Immutable per-scope consent evidence for canonical interviews."""

from __future__ import annotations

import uuid
from typing import Any

from .authority import InterviewAccountAuthority

SCOPES = frozenset({"record", "attribute", "publish"})
ACTORS = frozenset({"invitee_capability", "operator_witness", "legacy_projection"})


def record_consent_events(
    con: Any,
    authority: InterviewAccountAuthority,
    *,
    interview_id: str,
    scopes: set[str],
    granted: bool,
    actor_kind: str,
    invite_id: str | None = None,
) -> frozenset[str]:
    if not scopes or not scopes <= SCOPES or actor_kind not in ACTORS:
        raise ValueError("consent evidence is invalid")
    if actor_kind == "invitee_capability" and not invite_id:
        raise ValueError("invite-bound consent evidence is required")
    parent = con.execute(
        "SELECT 1 FROM interviews_authority WHERE account_digest = ? "
        "AND owner_user_id = ? AND interview_id = ?",
        [authority.account_digest, authority.account_id, interview_id],
    ).fetchone()
    if parent is None:
        raise ValueError("interview not found")
    for scope in sorted(scopes):
        con.execute(
            "INSERT INTO interview_consent_events "
            "(event_id, account_digest, interview_id, owner_user_id, invite_id, scope, "
            "granted, actor_kind) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [f"consent-{uuid.uuid4().hex}", authority.account_digest, interview_id,
             authority.account_id, invite_id, scope, granted, actor_kind],
        )
    current = consent_state(con, authority, interview_id=interview_id)
    con.execute(
        "UPDATE interviews_authority SET consent_recorded = ? WHERE account_digest = ? "
        "AND owner_user_id = ? AND interview_id = ?",
        ["record" in current, authority.account_digest, authority.account_id, interview_id],
    )
    return current


def consent_state(
    con: Any, authority: InterviewAccountAuthority, *, interview_id: str
) -> frozenset[str]:
    rows = con.execute(
        "SELECT scope, granted FROM (SELECT scope, granted, row_number() OVER "
        "(PARTITION BY scope ORDER BY recorded_at DESC, event_id DESC) AS ordinal "
        "FROM interview_consent_events WHERE account_digest = ? AND owner_user_id = ? "
        "AND interview_id = ?) ranked WHERE ordinal = 1",
        [authority.account_digest, authority.account_id, interview_id],
    ).fetchall()
    return frozenset(str(scope) for scope, granted in rows if granted)


__all__ = ["ACTORS", "SCOPES", "consent_state", "record_consent_events"]
