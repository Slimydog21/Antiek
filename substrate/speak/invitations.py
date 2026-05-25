"""Speak SPR-03 — the invitation system.

The operator creates a project and sends invite links to all of a
subject's friends and family. Each link lands on consent + interview.
This module:

  • generates a unique invite TOKEN per stakeholder (the
    ``interview.antiek.ai/{interview_id}?token=`` link), reusing the
    existing ``interviews`` row for lifecycle (invited / in_progress /
    completed / declined / incomplete);
  • captures the consent scopes the invite must collect, matched to the
    project's publish intent (M4);
  • dedupes a stakeholder invited twice (same email, same project);
  • keeps the PUBLIC open-contribution ecosystem feature-flagged off and
    gated on G7 (M3) — it is inherently multi-user.

Invite-link contributors are SOURCES, not accounts. They get no
account-like state — that is exactly what G7 unlocks. Giving invitees
account state is the temptation that trips G7; we don't.
"""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from typing import Any, Optional

from .consent import ConsentScope
from .events import SPEAK_INTERVIEW_INVITED, record_speak_event
from .ids import new_invite_id
from .schema import ensure_speak_schema

# The invite-link host (the existing per-interview token-link pattern).
INVITE_HOST = "interview.antiek.ai"


class PublicEcosystemGated(RuntimeError):
    """Raised when the public open-contribution ecosystem is requested
    while G7 is open. v1 is private invitations only."""


@dataclass(frozen=True)
class Invite:
    invite_id: str
    interview_id: str
    project_id: str
    token: str
    required_consent_scopes: tuple[ConsentScope, ...]
    informant_email: Optional[str]
    status: str

    @property
    def link(self) -> str:
        return f"https://{INVITE_HOST}/{self.interview_id}?token={self.token}"


def public_ecosystem_enabled() -> bool:
    """Whether the public open-contribution ecosystem is enabled. Gated
    on G7 (~Sprint 22); deny-by-default until the operator flips
    ``ANTIEK_SPEAK_PUBLIC_ECOSYSTEM`` post-G7."""
    return os.environ.get("ANTIEK_SPEAK_PUBLIC_ECOSYSTEM", "").strip().lower() in (
        "1", "true", "yes",
    )


def _required_scopes_for_intent(publish_intent: str) -> tuple[ConsentScope, ...]:
    """The consent scopes an invite must capture, matched to publish
    intent (M4). A will-be-public project needs publish-scope at invite;
    a private project needs only record (attribute optional in both)."""
    if publish_intent == "will_be_public":
        return (ConsentScope.RECORD, ConsentScope.ATTRIBUTE, ConsentScope.PUBLISH)
    return (ConsentScope.RECORD,)


def invite_stakeholder(
    con: Any,
    *,
    project_id: str,
    informant_email: Optional[str] = None,
    informant_handle: Optional[str] = None,
    required_scopes: Optional[tuple[ConsentScope, ...]] = None,
) -> Invite:
    """Invite one stakeholder by link. Idempotent per (project, email):
    inviting the same email twice returns the existing invite rather
    than creating a duplicate interview."""
    ensure_speak_schema(con)

    # Dedupe: same email, same project → existing invite.
    if informant_email:
        existing = con.execute(
            "SELECT s.invite_id FROM speak_invites s "
            "JOIN interviews i ON i.interview_id = s.interview_id "
            "WHERE s.project_id = ? AND i.informant_email = ? LIMIT 1",
            [project_id, informant_email],
        ).fetchone()
        if existing:
            return get_invite(con, existing[0])

    # Required scopes from the project's publish intent (M4) unless
    # explicitly overridden.
    if required_scopes is None:
        row = con.execute(
            "SELECT publish_intent FROM speak_projects WHERE project_id = ?",
            [project_id],
        ).fetchone()
        publish_intent = row[0] if row else "private_never_published"
        required_scopes = _required_scopes_for_intent(publish_intent)

    interview_id = f"interview-{secrets.token_hex(6)}"
    con.execute(
        "INSERT INTO interviews "
        "(interview_id, project_id, informant_handle, informant_email, status) "
        "VALUES (?, ?, ?, ?, 'invited')",
        [interview_id, project_id, informant_handle, informant_email],
    )
    invite_id = new_invite_id()
    token = secrets.token_urlsafe(24)
    import json
    con.execute(
        "INSERT INTO speak_invites "
        "(invite_id, interview_id, project_id, token, required_consent_scopes) "
        "VALUES (?, ?, ?, ?, ?)",
        [invite_id, interview_id, project_id, token,
         json.dumps([s.value for s in required_scopes])],
    )
    record_speak_event(
        SPEAK_INTERVIEW_INVITED,
        {"interview_id": interview_id, "informant_email": informant_email,
         "required_scopes": [s.value for s in required_scopes]},
        project_id=project_id,
    )
    return get_invite(con, invite_id)


def get_invite(con: Any, invite_id: str) -> Invite:
    return _row_to_invite(con, _invite_row(con, "invite_id", invite_id))


def resolve_token(con: Any, token: str) -> Optional[Invite]:
    """Resolve an invite link's token to its invite (the landing flow).
    Returns None for an unknown/expired token."""
    row = _invite_row(con, "token", token, optional=True)
    return _row_to_invite(con, row) if row else None


def lifecycle(con: Any, project_id: str) -> list[dict]:
    """Each invitee's lifecycle status for a project (the operator's
    invite-tracking view), with the invite link + the consent scopes the
    invite captures. LEFT JOIN so an interview without a speak_invite row
    (e.g. created directly via the async API) still appears."""
    import json
    rows = con.execute(
        "SELECT i.interview_id, i.informant_email, i.informant_handle, i.status, "
        "s.token, s.required_consent_scopes "
        "FROM interviews i "
        "LEFT JOIN speak_invites s ON s.interview_id = i.interview_id "
        "WHERE i.project_id = ? ORDER BY i.invited_at",
        [project_id],
    ).fetchall()
    out: list[dict] = []
    for r in rows:
        token = r[4]
        out.append({
            "interview_id": r[0],
            "informant_email": r[1],
            "informant_handle": r[2],
            "status": r[3],
            "link": (f"https://{INVITE_HOST}/{r[0]}?token={token}" if token else None),
            "required_consent_scopes": (json.loads(r[5]) if r[5] else []),
        })
    return out


def open_public_contribution(con: Any, project_id: str) -> None:
    """Open a project to the PUBLIC open-contribution ecosystem.

    Refused unless G7 is enabled (``public_ecosystem_enabled()``). v1
    ships private invitations only; this is the explicit gate, not a
    silent no-op."""
    if not public_ecosystem_enabled():
        raise PublicEcosystemGated(
            "the public open-contribution ecosystem is inherently multi-user "
            "and gated on G7 (~Sprint 22). v1 supports private invite-link "
            "contributors only (sources, not accounts)."
        )
    ensure_speak_schema(con)
    con.execute(
        "UPDATE speak_projects SET invitation_mode = 'public', "
        "updated_at = CURRENT_TIMESTAMP WHERE project_id = ?",
        [project_id],
    )


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _invite_row(con: Any, by_col: str, value: str, *, optional: bool = False):
    row = con.execute(
        f"SELECT s.invite_id, s.interview_id, s.project_id, s.token, "
        f"s.required_consent_scopes, i.informant_email, i.status "
        f"FROM speak_invites s JOIN interviews i ON i.interview_id = s.interview_id "
        f"WHERE s.{by_col} = ?",
        [value],
    ).fetchone()
    if row is None and not optional:
        raise ValueError(f"invite with {by_col}={value!r} not found")
    return row


def _row_to_invite(con: Any, row) -> Invite:
    import json
    scopes = tuple(ConsentScope(s) for s in json.loads(row[4]))
    return Invite(
        invite_id=row[0], interview_id=row[1], project_id=row[2], token=row[3],
        required_consent_scopes=scopes, informant_email=row[5], status=row[6],
    )
