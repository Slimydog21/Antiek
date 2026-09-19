"""Opaque, revocable, least-authority interview invite capabilities."""

from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import dataclass
from typing import Any

from .authority import InterviewAccountAuthority


def invite_token_digest(token: str) -> str:
    if not isinstance(token, str) or len(token) < 24 or token != token.strip():
        raise ValueError("invite token is invalid")
    return hashlib.sha256(f"antiek-interview-invite-v1\0{token}".encode()).hexdigest()


@dataclass(frozen=True)
class IssuedInvite:
    invite_id: str
    token: str


@dataclass(frozen=True)
class InviteCapability:
    invite_id: str
    authority: InterviewAccountAuthority
    interview_id: str
    project_id: str
    required_scopes: tuple[str, ...]


def issue_invite(con: Any, authority: InterviewAccountAuthority, *, interview_id: str,
                 required_scopes: tuple[str, ...] = ("record",)) -> IssuedInvite:
    allowed = {"record", "attribute", "publish"}
    if not required_scopes or any(scope not in allowed for scope in required_scopes):
        raise ValueError("required consent scopes are invalid")
    row = con.execute(
        "SELECT project_id FROM interviews_authority WHERE account_digest = ? "
        "AND owner_user_id = ? AND interview_id = ?",
        [authority.account_digest, authority.account_id, interview_id],
    ).fetchone()
    if row is None:
        raise ValueError("interview not found")
    invite_id = f"invite-{secrets.token_hex(12)}"
    token = secrets.token_urlsafe(32)
    con.execute(
        "INSERT INTO interview_invite_capabilities "
        "(token_digest, invite_id, account_digest, interview_id, project_id, owner_user_id, "
        "required_scopes_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
        [invite_token_digest(token), invite_id, authority.account_digest, interview_id,
         str(row[0]), authority.account_id, json.dumps(list(required_scopes))],
    )
    return IssuedInvite(invite_id, token)


def resolve_invite(con: Any, token: str) -> InviteCapability | None:
    try:
        digest = invite_token_digest(token)
    except ValueError:
        return None
    row = con.execute(
        "SELECT c.invite_id, c.owner_user_id, c.account_digest, c.interview_id, "
        "c.project_id, c.required_scopes_json "
        "FROM interview_invite_capabilities c "
        "JOIN interviews_authority i ON i.account_digest = c.account_digest "
        "AND i.owner_user_id = c.owner_user_id AND i.interview_id = c.interview_id "
        "AND i.project_id = c.project_id "
        "WHERE c.token_digest = ? AND c.revoked_at IS NULL "
        "AND (c.expires_at IS NULL OR c.expires_at > CURRENT_TIMESTAMP)",
        [digest],
    ).fetchone()
    if row is None:
        return None
    scopes = json.loads(row[5])
    if not isinstance(scopes, list) or not all(
        isinstance(scope, str) and scope in {"record", "attribute", "publish"}
        for scope in scopes
    ):
        return None
    authority = InterviewAccountAuthority(str(row[1]))
    if authority.account_digest != row[2]:
        return None
    return InviteCapability(str(row[0]), authority, str(row[3]), str(row[4]), tuple(scopes))


def revoke_invite(con: Any, authority: InterviewAccountAuthority, *, invite_id: str) -> bool:
    row = con.execute(
        "UPDATE interview_invite_capabilities SET revoked_at = CURRENT_TIMESTAMP "
        "WHERE account_digest = ? AND owner_user_id = ? AND invite_id = ? "
        "AND revoked_at IS NULL RETURNING 1",
        [authority.account_digest, authority.account_id, invite_id],
    ).fetchone()
    return row is not None


__all__ = [
    "InviteCapability", "IssuedInvite", "invite_token_digest", "issue_invite",
    "resolve_invite", "revoke_invite",
]
