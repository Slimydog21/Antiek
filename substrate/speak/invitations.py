"""Speak SPR-03 — the invitation system.

The operator creates a project and sends invite links to all of a
subject's friends and family. Each link lands on consent + interview.
This module:

  • generates a unique invite TOKEN per stakeholder (the
    ``antiek.ai/speak/invite/{token}`` link — token IS the credential on
    the unauth SpeakInvite route), reusing the
    existing ``interviews`` row for lifecycle (invited / in_progress /
    completed / declined / incomplete);
  • captures the consent scopes the invite must collect, matched to the
    project's publish intent (M4);
  • dedupes a stakeholder invited twice (same email, same project);
  • keeps the PUBLIC open-contribution ecosystem gated on G7 (M3) via
    ``ANTIEK_SPEAK_PUBLIC_ECOSYSTEM``; ``mint_open_contribution`` is the
    stranger self-serve door for will_be_public projects only.

Invite-link contributors are SOURCES, not accounts. They get no
account-like state — that is exactly what G7 unlocks. Giving invitees
account state is the temptation that trips G7; we don't.
"""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from typing import Any

from .consent import ConsentScope
from .events import SPEAK_INTERVIEW_INVITED, record_speak_event
from .ids import new_invite_id
from .schema import ensure_speak_schema
from .takedown import NO_ACTIVE_TAKEDOWN_SQL

# The handle ``mint_open_contribution`` stamps on the interview it creates
# (with no email). It is the durable marker of an anonymously minted door:
# ``speak_invites`` has no origin column, and tokens minted before this
# predicate existed must close too, so the marker is read from the row the
# mint already wrote rather than from a new column.
OPEN_CONTRIBUTOR_HANDLE = "open contributor"

# SQL predicate: is this invite-token door open? Every token-keyed surface
# resolves through it — ``resolve_token`` (so all six ``/speak/invite/{token}``
# routes and ``/speak/invites/resolve``) and the operator re-ping list/email
# in ``pushes.py``. Expects ``speak_invites`` aliased ``s`` and ``interviews``
# aliased ``i``. A door is closed while an active takedown
#   • targets the door's own interview (the landing replays its transcript
#     and the write routes would keep adding to it); or
#   • sits anywhere on the project AND the door was minted anonymously via
#     open contribution — the same project-wide predicate
#     (``NO_ACTIVE_TAKEDOWN_SQL``) that hides the project from the public
#     lists and refuses a fresh mint, since a token nobody vetted is just a
#     public list entry the caller saved earlier.
# It is a predicate over ACTIVE takedowns, not a revocation: reversing the
# takedown reopens exactly the doors the reopened public lists would mint.
INVITE_DOOR_OPEN_SQL = (
    "NOT EXISTS (SELECT 1 FROM speak_takedowns t WHERE t.status = 'active' "
    "AND ((t.target_kind = 'interview' AND t.target_id = s.interview_id) "
    "OR (t.project_id = s.project_id AND i.informant_email IS NULL "
    f"AND i.informant_handle = '{OPEN_CONTRIBUTOR_HANDLE}')))"
)


class PublicEcosystemGated(RuntimeError):
    """Raised when the public open-contribution ecosystem is requested
    while G7 is open. v1 is private invitations only."""


class InviteDoorClosed(ValueError):
    """Raised by ``require_open_door`` when a token no longer opens the
    interview being written. A ``ValueError`` so the Speak routes answer it
    with the same 404 as an unknown token."""


@dataclass(frozen=True)
class Invite:
    invite_id: str
    interview_id: str
    project_id: str
    token: str
    required_consent_scopes: tuple[ConsentScope, ...]
    informant_email: str | None
    status: str

    @property
    def link(self) -> str:
        # Antiek SpeakInvite door — token IS the credential (unauth route
        # /speak/invite/:token). Prefer this over the legacy interview-host
        # query form so PublicLane / share links never dead-end into the
        # authed operator console (speak-private-public-spine SPR-03).
        return f"https://antiek.ai/speak/invite/{self.token}"


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
    informant_email: str | None = None,
    informant_handle: str | None = None,
    required_scopes: tuple[ConsentScope, ...] | None = None,
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


def resolve_token(con: Any, token: str) -> Invite | None:
    """Resolve an invite link's token to its invite (the landing flow).
    Returns None for an unknown/expired token, and for a door an active
    takedown has closed (``INVITE_DOOR_OPEN_SQL``) — indistinguishable from
    unknown, so a closed door discloses neither the subject nor that a
    takedown exists."""
    row = _invite_row(con, "token", token, optional=True, only_open=True)
    return _row_to_invite(con, row) if row else None


def require_open_door(con: Any, token: str, interview_id: str) -> None:
    """Raise ``InviteDoorClosed`` unless ``token`` is an open door onto
    ``interview_id``. Token-driven writes call this under the SAME lock as
    the write: the routes resolve the token first and then write under
    later, separate locks (the voice route transcribes for seconds in
    between), so a takedown landing in that gap is only caught here."""
    iv = resolve_token(con, token)
    if iv is None or iv.interview_id != interview_id:
        raise InviteDoorClosed("unknown or expired invite link")


def lifecycle(con: Any, project_id: str) -> list[dict[str, Any]]:
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
    out: list[dict[str, Any]] = []
    for r in rows:
        token = r[4]
        out.append({
            "interview_id": r[0],
            "informant_email": r[1],
            "informant_handle": r[2],
            "status": r[3],
            "link": (f"https://antiek.ai/speak/invite/{token}" if token else None),
            "token": token,
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




def mint_open_contribution(con: Any, project_id: str) -> Invite:
    """Self-serve open contribution door for a *public-intent* project (G7).

    Cite: docs/decisions/speak-private-public-spine.md (SPR-03 / G7);
    docs/decisions/anti-ek-speak-deepblu-remap-2026-09-18.md §PUSHES / public.

    Hard rules:
      • Refused unless ``public_ecosystem_enabled()`` (ANTIEK_SPEAK_PUBLIC_ECOSYSTEM).
      • Refused unless ``publish_intent == will_be_public`` — private stays
        invite-only (operator-minted invites); no silent cross-over.
      • Refused while the project has an active takedown. The minted token's
        landing page (``GET /speak/invite/{token}``) is unauthenticated and
        returns ``subject_ref``, so this door shares the predicate that hides
        the project from ``/speak/feed``, ``/speak/opportunities`` and
        ``/speak/pushes``. Doors minted BEFORE the takedown close with it:
        ``resolve_token`` applies ``INVITE_DOOR_OPEN_SQL`` to every token
        route, keyed on the ``OPEN_CONTRIBUTOR_HANDLE`` stamped here.
      • Mints a fresh invite TOKEN (source, not an account) — stranger does
        not need a pre-shared family invite; the token remains the credential.
      • Marks ``invitation_mode=public`` (same flip as ``open_public_contribution``).
      • Economics unchanged: public may accrue escrow; G2/G3 still gate
        publish/disburse. Private no-earnings UX untouched.
    """
    if not public_ecosystem_enabled():
        raise PublicEcosystemGated(
            "open contribution without a pre-minted invite is gated on G7 "
            "(ANTIEK_SPEAK_PUBLIC_ECOSYSTEM). Private projects stay invite-only."
        )
    ensure_speak_schema(con)
    row = con.execute(
        "SELECT p.publish_intent, p.invitation_mode, "
        f"{NO_ACTIVE_TAKEDOWN_SQL} AS open_to_public "
        "FROM speak_projects p WHERE p.project_id = ?",
        [project_id],
    ).fetchone()
    if row is None:
        raise ValueError(f"project {project_id!r} not found")
    publish_intent, invitation_mode, open_to_public = row[0], row[1], row[2]
    if publish_intent != "will_be_public":
        raise PublicEcosystemGated(
            "private Speak projects stay invite-only — open contribution "
            "applies only to will_be_public projects (spine private↔public)."
        )
    if not open_to_public:
        raise PublicEcosystemGated(
            "this project is under an active takedown, so it is closed to "
            "open contribution until the takedown is reversed."
        )
    if invitation_mode != "public":
        con.execute(
            "UPDATE speak_projects SET invitation_mode = 'public', "
            "updated_at = CURRENT_TIMESTAMP WHERE project_id = ?",
            [project_id],
        )
    return invite_stakeholder(
        con,
        project_id=project_id,
        informant_handle=OPEN_CONTRIBUTOR_HANDLE,
        informant_email=None,
    )


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _invite_row(
    con: Any, by_col: str, value: str, *, optional: bool = False,
    only_open: bool = False,
) -> Any:
    door = f" AND {INVITE_DOOR_OPEN_SQL}" if only_open else ""
    row = con.execute(
        f"SELECT s.invite_id, s.interview_id, s.project_id, s.token, "
        f"s.required_consent_scopes, i.informant_email, i.status "
        f"FROM speak_invites s JOIN interviews i ON i.interview_id = s.interview_id "
        f"WHERE s.{by_col} = ?{door}",
        [value],
    ).fetchone()
    if row is None and not optional:
        raise ValueError(f"invite with {by_col}={value!r} not found")
    return row


def _row_to_invite(con: Any, row: Any) -> Invite:
    import json
    scopes = tuple(ConsentScope(s) for s in json.loads(row[4]))
    return Invite(
        invite_id=row[0], interview_id=row[1], project_id=row[2], token=row[3],
        required_consent_scopes=scopes, informant_email=row[5], status=row[6],
    )
