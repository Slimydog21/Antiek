"""IP holder escrow operations (master-spec §9.10, Sprint 18).

Pre-onboarded IP holder accounts with escrow accruing until publisher
opt-in. The architecture creates the row + accrues escrow; payouts
gate strictly on ``status='claimed'`` per §9.10 + §15.9 binding
Sprint 18 legal gate.

Implementation requirements (binding per master-spec §9.10):
- Notification email goes to publisher's LEGAL department, not marketing
- Account is claimable through documented process
- Escrow in segregated regulated accounts (Stripe Connect ACH path)
- Opt-out within 30 days triggers content removal
- Lawyer involved before first notification email sends
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from substrate.event_log import emit_typed

# Status state machine per master-spec §9.10.
VALID_STATUSES: frozenset[str] = frozenset({
    "pre_onboarded",  # account created; no notification yet
    "invited",        # notification email sent to legal dept
    "claimed",        # publisher opted in via documented claim flow
    "opted_out",      # publisher opted out; content removal scheduled
})

# First-cohort outreach per master-spec §9.10. Academic publishers
# whose institutional mission includes broad dissemination of
# knowledge and whose litigation budgets are smaller than the Big
# Five. Operator emails go here FIRST before any larger publisher
# notifications.
FIRST_COHORT_PUBLISHERS: tuple[str, ...] = (
    "MIT Press",
    "Cambridge University Press",
    "Princeton University Press",
)


@dataclass
class IpHolder:
    ip_holder_id: str
    display_name: str
    legal_contact_email: str | None
    status: str
    escrow_balance_usd: Decimal
    escrow_account_ref: str | None
    notification_sent_at: str | None
    claimed_at: str | None
    opted_out_at: str | None
    created_at: str
    metadata: dict = field(default_factory=dict)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def create_pre_onboarded(
    con: Any,
    *,
    display_name: str,
    legal_contact_email: str | None = None,
    metadata: dict | None = None,
) -> str:
    """Create a pre-onboarded IP holder account.

    Status starts at 'pre_onboarded'. No notification sent yet —
    that's a separate step gated on operator + lawyer review per
    master-spec §15.9 binding Sprint 18 legal gate.
    """
    ip_holder_id = f"ipholder-{uuid.uuid4().hex[:12]}"
    metadata_json = json.dumps(metadata or {})
    con.execute(
        """
        INSERT INTO ip_holders (
            ip_holder_id, display_name, legal_contact_email,
            status, escrow_balance_usd, metadata
        ) VALUES (?, ?, ?, 'pre_onboarded', 0, ?)
        """,
        [ip_holder_id, display_name, legal_contact_email, metadata_json],
    )
    return ip_holder_id


def mark_invited(con: Any, ip_holder_id: str) -> None:
    """Operator transitions pre_onboarded → invited AFTER notification
    email is sent to publisher's legal department. The lawyer-involved
    gate (master-spec §15.9) is the operator's responsibility BEFORE
    calling this function; the substrate does not enforce it because
    it's a process gate, not a runtime check."""
    con.execute(
        """
        UPDATE ip_holders
        SET status = 'invited',
            notification_sent_at = CURRENT_TIMESTAMP
        WHERE ip_holder_id = ? AND status = 'pre_onboarded'
        """,
        [ip_holder_id],
    )


def claim(
    con: Any,
    ip_holder_id: str,
    *,
    stripe_connect_account_id: str | None = None,
) -> None:
    """Publisher claims their account. Transitions invited → claimed.
    Unlocks the Stripe Connect payout path; the escrow balance can
    now flow.

    Per master-spec §9.10, this is the **only** transition that
    unlocks payouts. The substrate has no payouts-on-pre-onboarded
    code path; the data model alone enforces the gate."""
    con.execute(
        """
        UPDATE ip_holders
        SET status = 'claimed',
            claimed_at = CURRENT_TIMESTAMP,
            escrow_account_ref = ?
        WHERE ip_holder_id = ? AND status = 'invited'
        """,
        [stripe_connect_account_id, ip_holder_id],
    )


def opt_out(con: Any, ip_holder_id: str) -> None:
    """Publisher opts out. Transitions any status → opted_out. The
    content-removal SLA per master-spec §9.10 (30 days, ideally 7) is
    a separate background process that scans documents with
    ip_holder_id = this id and downgrades or removes them. The
    substrate just records the intent here.

    NOTE: opt-out from CLAIMED status returns the held escrow to the
    publisher; opt-out from PRE_ONBOARDED status does NOT generate a
    refund (no money was committed). The Stripe Connect refund flow
    handles the actual money movement; this function records the
    state transition."""
    con.execute(
        """
        UPDATE ip_holders
        SET status = 'opted_out',
            opted_out_at = CURRENT_TIMESTAMP
        WHERE ip_holder_id = ?
        """,
        [ip_holder_id],
    )


def accrue_escrow(con: Any, ip_holder_id: str, amount_usd: Decimal) -> None:
    """Accrue a positive USD amount to the IP holder's escrow balance.
    Called by the attribution pipeline whenever ad revenue routes to
    a chunk this IP holder owns. Per master-spec §9.10:
    "Architecture ships Sprint 18 alongside the publisher dashboard.
    Payouts gate strictly on publisher opt-in. Escrow accrues from
    Sprint 19 first-cohort outreach but no money routes until first
    opt-in."

    The substrate INCREMENTS the escrow_balance_usd column atomically.
    Whether the publisher receives the money is a separate Stripe
    Connect transfer that runs only when status='claimed'."""
    if amount_usd <= 0:
        raise ValueError(f"accrue_escrow amount must be positive, got {amount_usd}")
    con.execute(
        """
        UPDATE ip_holders
        SET escrow_balance_usd = escrow_balance_usd + ?
        WHERE ip_holder_id = ?
        """,
        [str(amount_usd), ip_holder_id],
    )


def get(con: Any, ip_holder_id: str) -> IpHolder | None:
    """Read a single IP holder. Returns None if not found."""
    row = con.execute(
        """
        SELECT ip_holder_id, display_name, legal_contact_email,
               status, escrow_balance_usd, escrow_account_ref,
               notification_sent_at, claimed_at, opted_out_at,
               created_at, metadata
        FROM ip_holders WHERE ip_holder_id = ?
        """,
        [ip_holder_id],
    ).fetchone()
    if row is None:
        return None
    return _row_to_holder(row)


def list_all(con: Any, status: str | None = None) -> list[IpHolder]:
    """List IP holders, optionally filtered by status."""
    if status is not None:
        if status not in VALID_STATUSES:
            raise ValueError(f"status must be in {VALID_STATUSES}, got {status!r}")
        rows = con.execute(
            """
            SELECT ip_holder_id, display_name, legal_contact_email,
                   status, escrow_balance_usd, escrow_account_ref,
                   notification_sent_at, claimed_at, opted_out_at,
                   created_at, metadata
            FROM ip_holders WHERE status = ?
            ORDER BY created_at DESC
            """,
            [status],
        ).fetchall()
    else:
        rows = con.execute(
            """
            SELECT ip_holder_id, display_name, legal_contact_email,
                   status, escrow_balance_usd, escrow_account_ref,
                   notification_sent_at, claimed_at, opted_out_at,
                   created_at, metadata
            FROM ip_holders ORDER BY created_at DESC
            """
        ).fetchall()
    return [_row_to_holder(r) for r in rows]


def _row_to_holder(row: tuple) -> IpHolder:
    (
        ip_holder_id, display_name, legal_contact_email,
        status, escrow_balance_usd, escrow_account_ref,
        notification_sent_at, claimed_at, opted_out_at,
        created_at, metadata,
    ) = row
    md = {}
    if metadata:
        try:
            md = json.loads(metadata)
        except (TypeError, ValueError):
            md = {}
    return IpHolder(
        ip_holder_id=ip_holder_id,
        display_name=display_name,
        legal_contact_email=legal_contact_email,
        status=status,
        escrow_balance_usd=Decimal(str(escrow_balance_usd)),
        escrow_account_ref=escrow_account_ref,
        notification_sent_at=str(notification_sent_at) if notification_sent_at else None,
        claimed_at=str(claimed_at) if claimed_at else None,
        opted_out_at=str(opted_out_at) if opted_out_at else None,
        created_at=str(created_at),
        metadata=md,
    )


# ---------------------------------------------------------------------------
# Notification email template (master-spec §9.10)
# ---------------------------------------------------------------------------


NOTIFICATION_EMAIL_TEMPLATE = """\
Subject: Antiek platform — pre-onboarded account ready for {display_name}

Dear {display_name} Legal Department,

We are building Antiek, an AI-mediated research synthesis platform
that uses chunks of published works for attribution-bearing
synthesis and discussion in a manner we believe is transformative
under fair use, while routing revenue share to rights holders in
good faith from day one.

We have created a pre-onboarded account for {display_name} on our
platform. Since {created_at}, an escrow balance has been accruing
based on attribution events involving your published works. The
balance accrued to date is ${escrow_balance_usd}.

We are NOT republishing your books. We are NOT letting users read
your books cover-to-cover. We are using chunks of text for
attribution-bearing synthesis and discussion, with revenue share
routing back to rights holders.

We invite you to claim your account and accept payments accrued to
date. The claim process is documented at our publisher portal.
Until you claim, no payment routes — the funds remain in segregated
escrow.

You may also opt out at any time by replying to this email. Upon
opt-out, we will remove your content from our platform within 30
days and refund any accrued escrow.

If you have questions, our legal contact is available at
legal@antiek.ai.

Sincerely,
The Antiek team
"""


def render_notification_email(holder: IpHolder) -> str:
    """Render the §9.10 notification email for the given pre-onboarded
    IP holder. Per master-spec §9.10 binding implementation
    requirements: this email goes to the publisher's LEGAL department
    (not marketing); record of delivery is required; lawyer-involved
    BEFORE first notification email sends.

    The operator is responsible for actually sending the email; this
    function only renders the canonical template. Email-send mechanics
    + record-of-delivery tracking live in the publisher dashboard
    REST endpoints, not in this module."""
    return NOTIFICATION_EMAIL_TEMPLATE.format(
        display_name=holder.display_name,
        created_at=holder.created_at,
        escrow_balance_usd=holder.escrow_balance_usd,
    )
