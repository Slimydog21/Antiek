"""Speak SPR-01 M3 + M6 — verification-before-publish + the public gate.

This is the legal spine's enforcement point. It is enforced at the
DATA layer (not the UI) so no front-end mistake can publish something
it shouldn't — the tests bypass the UI entirely.

Two gates:

M3 — verification-before-publish (per-claim).
    A third-party claim (``third_party.py``) may be published only if it
    is corroborated (``verification='multiply_attested'``, SPR-05) or
    explicitly operator-attested (``verification='operator_attested'``).
    A ``contradicted`` claim is never publishable. A claim covered by an
    active takedown is never publishable. A claim an interviewee makes
    about themselves (not third-party) needs no corroboration here (it
    still needs that interviewee's publish-scope consent, enforced in
    ``consent.py``).

M6 — public-publishing gate (per-project).
    Public publishing is refused unless ALL hold: the legal gate
    (G2/G3) is open; the subject permits public publishing
    (``subject_consent.py``); no active takedown blocks the project; and
    every third-party claim destined for the public output is
    publishable under M3. Refusals carry the specific reason and are
    audited (``speak.publish.blocked``).

Honest scope: this REDUCES legal exposure; it does not make publishing
safe. G2 counsel is the binding gate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import gate_status
from . import subject_consent as subject_consent_mod
from . import takedown as takedown_mod
from .events import SPEAK_PUBLISH_BLOCKED, record_speak_event
from .schema import ensure_speak_schema
from .third_party import ClaimRecord, get_claim, list_claims

# Verification states that make a third-party claim publishable.
PUBLISHABLE_VERIFICATIONS = frozenset({"multiply_attested", "operator_attested"})


class PublishBlocked(Exception):
    """Raised when a claim or project cannot be published. ``reason`` is
    audit-grade free text."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class PublishDecision:
    allowed: bool
    reason: str
    blocked_claim_ids: tuple[str, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# M3 — per-claim verification gate
# ---------------------------------------------------------------------------


def check_claim_publishable(claim: ClaimRecord) -> tuple[bool, str]:
    """Pure decision for one claim (ignores takedown — see
    ``assert_claim_publishable`` for the full DB-aware check)."""
    if claim.verification == "contradicted":
        return False, f"claim {claim.claim_id} is contradicted; not publishable"
    if not claim.is_third_party:
        return True, "first-party claim (about the speaker); no corroboration required"
    if claim.verification in PUBLISHABLE_VERIFICATIONS:
        return True, f"third-party claim {claim.verification}"
    return (
        False,
        f"third-party claim {claim.claim_id} is {claim.verification}; a "
        "third-party claim must be corroborated (multiply-attested) or "
        "operator-attested before it may be published",
    )


def is_blocked_by_takedown(con: Any, claim: ClaimRecord) -> bool:
    """Whether an active takedown covers this claim, its source
    interview, or its subject."""
    if takedown_mod.is_taken_down(con, target_kind="claim", target_id=claim.claim_id):
        return True
    if claim.interview_id and takedown_mod.is_taken_down(
        con, target_kind="interview", target_id=claim.interview_id
    ):
        return True
    if claim.subject_ref and takedown_mod.is_taken_down(
        con, target_kind="subject", target_id=claim.subject_ref
    ):
        return True
    return False


def assert_claim_publishable(con: Any, claim_id: str) -> None:
    """Raise ``PublishBlocked`` unless ``claim_id`` may be published.
    The full DB-aware check: verification state AND takedown."""
    claim = get_claim(con, claim_id)
    if is_blocked_by_takedown(con, claim):
        raise PublishBlocked(f"claim {claim_id} is under an active takedown")
    ok, reason = check_claim_publishable(claim)
    if not ok:
        raise PublishBlocked(reason)


def operator_attest_claim(
    con: Any, claim_id: str, *, project_id: str | None = None
) -> None:
    """Explicit operator attestation of a third-party claim — the M3
    escape valve for a claim the operator vouches for without
    cross-interviewee corroboration. Distinct from corroboration so the
    audit log shows WHO made the call."""
    ensure_speak_schema(con)
    con.execute(
        "UPDATE speak_claims SET verification = 'operator_attested', "
        "updated_at = CURRENT_TIMESTAMP WHERE claim_id = ?",
        [claim_id],
    )


# ---------------------------------------------------------------------------
# M6 — per-project public-publishing gate
# ---------------------------------------------------------------------------


def _project_subject_ref(con: Any, project_id: str) -> str | None:
    row = con.execute(
        "SELECT subject_ref FROM speak_projects WHERE project_id = ?",
        [project_id],
    ).fetchone()
    return row[0] if row else None


def check_public_publish(
    con: Any, *, project_id: str, subject_ref: str | None = None
) -> PublishDecision:
    """The full public-publishing gate for a project. Deny-by-default;
    the FIRST failing condition wins so the reason is specific. Audits
    refusals."""
    ensure_speak_schema(con)

    def refuse(reason: str, blocked: tuple[str, ...] = ()) -> PublishDecision:
        record_speak_event(
            SPEAK_PUBLISH_BLOCKED,
            {"reason": reason, "blocked_claim_ids": list(blocked)},
            project_id=project_id,
        )
        return PublishDecision(False, reason, blocked)

    # 1. Legal gate G2/G3.
    legal = gate_status.public_publishing_allowed()
    if not legal.allowed:
        return refuse(legal.reason)

    # 2. Active takedown blocking the whole project.
    if takedown_mod.active_takedowns(con, project_id):
        return refuse("an active takedown blocks publishing for this project")

    # 3. Subject consent.
    subj = subject_ref or _project_subject_ref(con, project_id)
    if subj is not None:
        decision = subject_consent_mod.public_publish_allowed_for_subject(
            con, project_id=project_id, subject_ref=subj
        )
        if not decision.allowed:
            return refuse(decision.reason)

    # 4. Every third-party claim must be publishable (M3).
    blocked: list[str] = []
    for claim in list_claims(con, project_id, third_party_only=True):
        if is_blocked_by_takedown(con, claim):
            blocked.append(claim.claim_id)
            continue
        ok, _ = check_claim_publishable(claim)
        if not ok:
            blocked.append(claim.claim_id)
    if blocked:
        return refuse(
            f"{len(blocked)} third-party claim(s) are uncorroborated / "
            "un-attested / taken down and cannot be published",
            tuple(blocked),
        )

    return PublishDecision(True, "all public-publishing gates satisfied")
