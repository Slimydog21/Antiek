"""Speak SPR-01 M1 — scoped per-interviewee consent.

Antiek today has a single boolean: ``interviews.consent_recorded``,
checked by ``orchestration/interview/orchestrator.py`` (``ConsentRequired``)
before any substantive question. That boolean is necessary but not
sufficient for publishing real people's words: consent to *be recorded*
is not consent to *be named*, which is not consent to *be published*.

This module replaces the boolean with three independent scopes:

    record    — the interviewee agrees to be recorded + transcribed.
                Gates substantive questioning (the existing gate).
    attribute — the interviewee agrees to be NAMED as a source.
    publish   — the interviewee agrees their words may appear in a
                PUBLIC output.

Scopes are independent (an interviewee can grant ``record`` only). Each
action checks the scope it needs via ``require_consent``:

    no named attribution without ``attribute``
    no public output without ``publish``

To keep the existing orchestrator gate working unchanged, granting
``record`` also flips ``interviews.consent_recorded = TRUE`` — the old
boolean becomes a projection of the new scope.

Honest scope of this module: it enforces *what an interviewee agreed
to*. It does not make publishing legally safe — that is G2 counsel.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Any, Iterable, Optional

from .events import (
    SPEAK_CONSENT_RECORDED,
    SPEAK_CONSENT_REVOKED,
    record_speak_event,
)
from .schema import ensure_speak_schema


class ConsentScope(str, enum.Enum):
    """The three independent consent scopes. Values are stored in the
    ``speak_consent.scope`` column — stable strings."""

    RECORD = "record"
    ATTRIBUTE = "attribute"
    PUBLISH = "publish"


class ScopedConsentRequired(Exception):
    """Raised when an action needs a consent scope the interviewee has
    not granted (or has revoked). The Speak analog of the orchestrator's
    ``ConsentRequired`` — but scope-aware."""

    def __init__(self, interview_id: str, scope: ConsentScope, action: str):
        self.interview_id = interview_id
        self.scope = scope
        self.action = action
        super().__init__(
            f"action {action!r} on interview {interview_id!r} requires "
            f"consent scope {scope.value!r}, which is not granted"
        )


@dataclass(frozen=True)
class ConsentState:
    """The currently-granted (not-revoked) scopes for one interview."""

    interview_id: str
    granted: frozenset[ConsentScope]

    def has(self, scope: ConsentScope) -> bool:
        return scope in self.granted


def record_consent(
    con: Any,
    *,
    interview_id: str,
    scopes: Iterable[ConsentScope],
    project_id: Optional[str] = None,
) -> ConsentState:
    """Grant one or more consent scopes for an interview. Idempotent
    per scope (re-granting clears any prior revocation).

    Granting ``record`` also sets ``interviews.consent_recorded = TRUE``
    so the existing orchestrator gate is satisfied — the old boolean is
    a projection of the new ``record`` scope.
    """
    ensure_speak_schema(con)  # asserts LockedConnection (single-writer)
    granted_now: list[str] = []
    for scope in scopes:
        s = ConsentScope(scope)
        # Upsert: grant + clear revocation.
        con.execute(
            "DELETE FROM speak_consent WHERE interview_id = ? AND scope = ?",
            [interview_id, s.value],
        )
        con.execute(
            "INSERT INTO speak_consent (interview_id, scope, granted, revoked_at) "
            "VALUES (?, ?, TRUE, NULL)",
            [interview_id, s.value],
        )
        granted_now.append(s.value)

    if ConsentScope.RECORD.value in granted_now:
        # Bridge to the legacy boolean the orchestrator reads.
        con.execute(
            "UPDATE interviews SET consent_recorded = TRUE WHERE interview_id = ?",
            [interview_id],
        )

    record_speak_event(
        SPEAK_CONSENT_RECORDED,
        {"interview_id": interview_id, "scopes": granted_now},
        project_id=project_id,
    )
    return consent_state(con, interview_id)


def revoke_consent(
    con: Any,
    *,
    interview_id: str,
    scopes: Iterable[ConsentScope],
    project_id: Optional[str] = None,
) -> ConsentState:
    """Revoke one or more scopes. A revoked scope no longer satisfies
    ``require_consent``. Revoking ``record`` also clears the legacy
    boolean. (Takedown of already-published content is a separate,
    stronger action — see ``takedown.py``.)"""
    ensure_speak_schema(con)
    revoked_now: list[str] = []
    for scope in scopes:
        s = ConsentScope(scope)
        con.execute(
            "UPDATE speak_consent SET granted = FALSE, revoked_at = CURRENT_TIMESTAMP "
            "WHERE interview_id = ? AND scope = ?",
            [interview_id, s.value],
        )
        revoked_now.append(s.value)

    if ConsentScope.RECORD.value in revoked_now:
        con.execute(
            "UPDATE interviews SET consent_recorded = FALSE WHERE interview_id = ?",
            [interview_id],
        )

    record_speak_event(
        SPEAK_CONSENT_REVOKED,
        {"interview_id": interview_id, "scopes": revoked_now},
        project_id=project_id,
    )
    return consent_state(con, interview_id)


def consent_state(con: Any, interview_id: str) -> ConsentState:
    """Read the currently-granted scopes for an interview."""
    rows = con.execute(
        "SELECT scope FROM speak_consent "
        "WHERE interview_id = ? AND granted = TRUE",
        [interview_id],
    ).fetchall()
    granted = frozenset(ConsentScope(r[0]) for r in rows)
    return ConsentState(interview_id=interview_id, granted=granted)


def has_consent(con: Any, interview_id: str, scope: ConsentScope) -> bool:
    """Whether ``interview_id`` currently grants ``scope``."""
    return consent_state(con, interview_id).has(ConsentScope(scope))


def require_consent(
    con: Any, interview_id: str, scope: ConsentScope, *, action: str
) -> None:
    """Raise ``ScopedConsentRequired`` unless ``interview_id`` grants
    ``scope``. Call this at the top of any action that needs it:

        require_consent(con, iv, ConsentScope.ATTRIBUTE, action="attribute_by_name")
        require_consent(con, iv, ConsentScope.PUBLISH,   action="publish_public")
    """
    if not has_consent(con, interview_id, scope):
        raise ScopedConsentRequired(interview_id, ConsentScope(scope), action)
