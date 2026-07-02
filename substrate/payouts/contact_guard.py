"""No-email-to-unclaimed contact guard (SPR-09 M3).

**HONEST FRAMING.** There is today no arXiv-author outreach product flow in
Antiek: ``EnrichedAuthor`` (``substrate/schemas/documents.py``) carries only
``orcid`` / ``author_position`` / ``display_name`` — no email, no ``claimed``
field — and the payouts ledger (``substrate/payouts/ledger.py``) states in its
own docstring that it "NEVER ... contacts an author". This guard therefore
stays **deny-by-default** unless a caller supplies a real write/read connection
containing an explicit ``author_contact_claims`` row with ``contact_opt_in``.

The point of building the guard NOW, before the path exists, is that it makes
the path impossible to add UNGUARDED later. The single sanctioned author-email
entry point is :func:`guarded_send_to_author`; the companion AST scanner
``tools/lint/contact_guard_check.py`` reds CI if any NEW ``provider.send(`` or
``OutboundEmail(`` construction appears outside the small allowlist (the operator
magic-link route, the email-provider module itself, and this guard). Together
they guarantee: a future SPR-07 author-outreach feature MUST route through this
guard, and the guard blocks every author send until the claim table says the
author both claimed authorship and opted into contact.

The operator magic-link sign-in (``interfaces/research/api/auth.py``) is NOT
author-directed — it mails the operator their own sign-in link, gated to
``ANTIEK_OPERATOR_EMAIL``. It is explicitly allowed and does NOT route through
this guard; the scanner allowlists it.

The SPR-07 plug point
---------------------
:func:`is_author_claimed` is the single seam author outreach consults. Without a
claim-store connection it returns ``False``. With one, it reads
``author_contact_claims`` and only admits rows whose ``contact_opt_in`` is true
and whose claim has not been revoked.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Optional

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


@dataclass(frozen=True)
class AuthorContactClaim:
    """An explicit author-contact claim row.

    ``contact_opt_in`` is deliberately separate from "claimed": a verified author
    claim alone does not permit outreach. The guard admits only active rows with
    explicit contact opt-in.
    """

    author_ref: str
    contact_opt_in: bool
    claimed_at: str | None
    contact_opted_in_at: str | None
    revoked_at: str | None
    evidence: dict[str, Any]


def _normalize_author_ref(author_ref: str) -> str:
    ref = author_ref.strip()
    if not ref:
        raise ValueError("author_ref must be non-empty")
    return ref


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def ensure_author_contact_claims_table(con: Any) -> None:
    """Create the explicit author-contact claim table if needed.

    This mirrors the repo's defensive module-level ``ensure_tables`` idiom while
    the canonical idempotent DDL also lives in ``substrate.graph.schema``.
    """
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS author_contact_claims (
            author_ref            TEXT PRIMARY KEY,
            contact_opt_in        BOOLEAN NOT NULL DEFAULT FALSE,
            claimed_at            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            contact_opted_in_at   TIMESTAMP,
            revoked_at            TIMESTAMP,
            evidence_json         TEXT NOT NULL DEFAULT '{}',
            updated_at            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    con.execute(
        "CREATE INDEX IF NOT EXISTS idx_author_contact_claims_active "
        "ON author_contact_claims(author_ref, contact_opt_in, revoked_at)"
    )


def record_author_contact_claim(
    con: Any,
    *,
    author_ref: str,
    contact_opt_in: bool = False,
    evidence: dict[str, Any] | None = None,
) -> AuthorContactClaim:
    """Record or update an author's verified claim state.

    A claim does not imply outreach permission. Callers must pass
    ``contact_opt_in=True`` only after the author has explicitly opted into
    contact.
    """
    ref = _normalize_author_ref(author_ref)
    evidence_json = json.dumps(evidence or {}, sort_keys=True, separators=(",", ":"))
    now = _now_iso()
    opted_in_at = now if contact_opt_in else None
    ensure_author_contact_claims_table(con)
    con.execute(
        """
        INSERT INTO author_contact_claims (
            author_ref, contact_opt_in, contact_opted_in_at, revoked_at,
            evidence_json, updated_at
        ) VALUES (?, ?, ?, NULL, ?, ?)
        ON CONFLICT(author_ref) DO UPDATE SET
            contact_opt_in = excluded.contact_opt_in,
            contact_opted_in_at = CASE
                WHEN excluded.contact_opt_in THEN COALESCE(
                    author_contact_claims.contact_opted_in_at,
                    excluded.contact_opted_in_at
                )
                ELSE NULL
            END,
            revoked_at = NULL,
            evidence_json = excluded.evidence_json,
            updated_at = excluded.updated_at
        """,
        [ref, bool(contact_opt_in), opted_in_at, evidence_json, now],
    )
    claim = get_author_contact_claim(con, ref)
    if claim is None:  # pragma: no cover - defensive; INSERT above should win.
        raise RuntimeError(f"author contact claim was not persisted for {ref!r}")
    return claim


def revoke_author_contact_claim(con: Any, *, author_ref: str) -> None:
    """Revoke an author's contact claim/opt-in without deleting the audit row."""
    ref = _normalize_author_ref(author_ref)
    now = _now_iso()
    ensure_author_contact_claims_table(con)
    con.execute(
        """
        UPDATE author_contact_claims
        SET contact_opt_in = FALSE,
            revoked_at = ?,
            updated_at = ?
        WHERE author_ref = ?
        """,
        [now, now, ref],
    )


def get_author_contact_claim(con: Any, author_ref: str) -> AuthorContactClaim | None:
    ref = _normalize_author_ref(author_ref)
    try:
        row = con.execute(
            """
            SELECT author_ref, contact_opt_in, claimed_at, contact_opted_in_at,
                   revoked_at, evidence_json
            FROM author_contact_claims
            WHERE author_ref = ?
            """,
            [ref],
        ).fetchone()
    except Exception as exc:
        msg = str(exc).lower()
        if "author_contact_claims" in msg and "does not exist" in msg:
            return None
        raise
    if row is None:
        return None
    evidence: dict[str, Any] = {}
    if row[5]:
        try:
            parsed = json.loads(row[5])
            if isinstance(parsed, dict):
                evidence = parsed
        except (TypeError, ValueError):
            evidence = {}
    return AuthorContactClaim(
        author_ref=str(row[0]),
        contact_opt_in=bool(row[1]),
        claimed_at=str(row[2]) if row[2] else None,
        contact_opted_in_at=str(row[3]) if row[3] else None,
        revoked_at=str(row[4]) if row[4] else None,
        evidence=evidence,
    )


def is_author_claimed(author_ref: str, *, con: Any | None = None) -> bool:
    """Return whether ``author_ref`` is claimed and explicitly opted into contact.

    Without ``con`` the function remains deny-by-default. With ``con`` it reads
    the canonical ``author_contact_claims`` table and returns true only for an
    active row with ``contact_opt_in``.
    """
    ref = _normalize_author_ref(author_ref)
    if con is None:
        return False
    claim = get_author_contact_claim(con, ref)
    return bool(claim and claim.contact_opt_in and claim.revoked_at is None)


def guarded_send_to_author(
    provider: EmailProvider,
    outbound: OutboundEmail,
    *,
    author_ref: str,
    claims_con: Any | None = None,
) -> AuthorContactResult:
    """The ONE sanctioned author-directed email path. Deny-by-default.

    Consults :func:`is_author_claimed`. If the author is NOT claimed and
    contact-opted-in, the send is BLOCKED and LOGGED, the underlying
    ``provider.send`` is NEVER called, and the function raises
    :class:`ContactBlocked`. A caller must pass ``claims_con`` for any author to
    be considered claimed; omitting it preserves deny-by-default.

    This is the only place in the codebase allowed to send author-directed mail;
    the contact_guard_check scanner reds CI on any ``provider.send(`` /
    ``OutboundEmail(`` outside the allowlist, forcing all future author-email
    paths through here. The operator magic-link route is NOT author-directed and
    does not go through this guard.
    """
    if not is_author_claimed(author_ref, con=claims_con):
        logger.warning(
            "BLOCKED author-directed email: author_ref=%s to=%s subject=%r — "
            "author is not claimed/contact-opted-in; deny-by-default. "
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
                "claimed their authorship and opted in to contact. This is "
                "deny-by-default — every author send is blocked until the "
                "author_contact_claims table says otherwise."
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
    "AuthorContactClaim",
    "AuthorContactResult",
    "ContactBlocked",
    "ensure_author_contact_claims_table",
    "get_author_contact_claim",
    "guarded_send_to_author",
    "is_author_claimed",
    "record_author_contact_claim",
    "revoke_author_contact_claim",
]
