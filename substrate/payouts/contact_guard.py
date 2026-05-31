"""No-email-to-unclaimed contact guard (SPR-09 M3).

**HONEST FRAMING.** This guard defends a path that does NOT YET EXIST. There is
today no arXiv-author outreach in Antiek: ``EnrichedAuthor``
(``substrate/schemas/documents.py``) carries only ``orcid`` /
``author_position`` / ``display_name`` — no email, no ``claimed`` field — and
the payouts ledger (``substrate/payouts/ledger.py``) states in its own docstring
that it "NEVER ... contacts an author" because the SPR-07 claim flow is unbuilt.
A repo-wide grep for ``notify_author`` / ``email_author`` / ``send_to_author`` /
``claim_invite`` returns nothing. So M3 is correctly **deny-by-default**: with no
author ever claimed, ALL author-directed email is blocked.

The point of building the guard NOW, before the path exists, is that it makes
the path impossible to add UNGUARDED later. The single sanctioned author-email
entry point is :func:`guarded_send_to_author`; the companion AST scanner
``tools/lint/contact_guard_check.py`` reds CI if any NEW ``provider.send(`` or
``OutboundEmail(`` construction appears outside the small allowlist (the operator
magic-link route, the email-provider module itself, and this guard). Together
they guarantee: a future SPR-07 author-outreach feature MUST route through this
guard, and the guard blocks every author send until a real claim table says the
author opted in.

The operator magic-link sign-in (``interfaces/research/api/auth.py``) is NOT
author-directed — it mails the operator their own sign-in link, gated to
``ANTIEK_OPERATOR_EMAIL``. It is explicitly allowed and does NOT route through
this guard; the scanner allowlists it.

The SPR-07 plug point
---------------------
:func:`is_author_claimed` is the single seam a future SPR-07 claim table fills.
TODAY it is HARDWIRED to ``False`` — no claim flow exists, so no author is ever
claimed, so every author send is blocked. When SPR-07 lands a real claim store,
this predicate (and only this predicate) is updated to consult it; the guard's
block/allow logic and the scanner do not change. We do NOT invent a claim system
here — that is SPR-07's job.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from substrate.auth.email_provider import EmailProvider, EmailRecord, OutboundEmail

logger = logging.getLogger("antiek.payouts.contact_guard")


class ContactBlocked(Exception):
    """Raised when :func:`guarded_send_to_author` refuses to send because the
    target author is not claimed. Carries the author ref + recipient for the
    audit log. Today this is ALWAYS raised (no author is ever claimed)."""

    def __init__(self, *, author_ref: str, to: str, message: str) -> None:
        super().__init__(message)
        self.author_ref = author_ref
        self.to = to


@dataclass(frozen=True)
class AuthorContactResult:
    """The outcome of an author-contact attempt. ``blocked`` is the honest
    answer; ``record`` is populated ONLY when an actual send happened (never,
    today — there is no claimed author)."""

    blocked: bool
    author_ref: str
    to: str
    reason: str
    record: Optional[EmailRecord] = None


def is_author_claimed(author_ref: str) -> bool:
    """**SPR-07 PLUG POINT — deny-all today.**

    Return whether the arXiv author identified by ``author_ref`` (e.g. an ORCID,
    or an ``(arxiv_id, author_position)`` tuple rendered to a string) has CLAIMED
    their authorship and opted in to contact.

    There is no claim flow in the codebase yet (SPR-07 is unbuilt: see this
    module's docstring + ``substrate/payouts/ledger.py``), so there is no claim
    state to read. This predicate is therefore HARDWIRED to ``False`` — no
    author is ever claimed, so every author send is blocked. When SPR-07 lands a
    real claim table, THIS function is the single seam updated to consult it; the
    guard and scanner are untouched. We deliberately do NOT invent a claim
    system here."""
    return False


def guarded_send_to_author(
    provider: EmailProvider,
    outbound: OutboundEmail,
    *,
    author_ref: str,
) -> AuthorContactResult:
    """The ONE sanctioned author-directed email path. Deny-by-default.

    Consults :func:`is_author_claimed`. If the author is NOT claimed (always,
    today), the send is BLOCKED and LOGGED, the underlying ``provider.send`` is
    NEVER called, and the function raises :class:`ContactBlocked`. Only a future
    SPR-07-claimed author would reach the ``provider.send`` line — and even then
    the send is logged so author outreach is fully auditable.

    This is the only place in the codebase allowed to send author-directed mail;
    the contact_guard_check scanner reds CI on any ``provider.send(`` /
    ``OutboundEmail(`` outside the allowlist, forcing all future author-email
    paths through here. The operator magic-link route is NOT author-directed and
    does not go through this guard.
    """
    if not is_author_claimed(author_ref):
        logger.warning(
            "BLOCKED author-directed email: author_ref=%s to=%s subject=%r — "
            "author is not claimed (no SPR-07 claim flow exists; deny-by-default). "
            "provider.send was NOT called.",
            author_ref,
            outbound.to,
            outbound.subject,
        )
        raise ContactBlocked(
            author_ref=author_ref,
            to=outbound.to,
            message=(
                f"refusing to email author {author_ref!r}: the author has not "
                "claimed their authorship and opted in. No claim flow exists yet "
                "(SPR-07 unbuilt) so this is deny-by-default — every author send "
                "is blocked until a real claim table says otherwise."
            ),
        )

    # Only reachable once SPR-07 lands a real claim store AND that author opted
    # in. The send is logged so author outreach is auditable from day one.
    logger.info(
        "ALLOWED author-directed email: author_ref=%s to=%s subject=%r "
        "(author is claimed)",
        author_ref,
        outbound.to,
        outbound.subject,
    )
    record = provider.send(outbound)
    return AuthorContactResult(
        blocked=False,
        author_ref=author_ref,
        to=outbound.to,
        reason="author_claimed",
        record=record,
    )


__all__ = [
    "AuthorContactResult",
    "ContactBlocked",
    "guarded_send_to_author",
    "is_author_claimed",
]
