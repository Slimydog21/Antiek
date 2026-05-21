"""Stripe Connect account + operations-log scaffolding."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from .providers import StripeProvider


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class StripeAccountStatus(str, Enum):
    """The publisher-side Stripe account lifecycle status as observed
    by Antiek's substrate. Stripe's own status enum is richer; this
    maps the subset we act on."""

    PENDING = "pending"          # account created, KYC not complete
    ACTIVE = "active"            # KYC complete, can receive transfers
    RESTRICTED = "restricted"    # KYC partially valid; some xfers blocked
    DISABLED = "disabled"        # operator/legal initiated tear-down


@dataclass
class StripeConnectAccount:
    """Antiek's local mirror of a Stripe Connect account. We do NOT
    re-store KYC documents here (that lives in Stripe per their
    compliance posture); we store the connect_account_id + status +
    the link back to the substrate ip_holder_id or user_id."""

    connect_account_id: str
    account_kind: str  # "publisher" | "user_creator"
    substrate_ref: str  # ip_holder_id or user_id
    status: StripeAccountStatus = StripeAccountStatus.PENDING
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)


@dataclass
class StripeOperationsLog:
    """Idempotent append-only log of money-movement operations.

    Sprint 18-19 ships the log + idempotency machinery. Production
    activation gates per master-spec §9.10: 'no payout activates
    until at least one publisher has opted in.' The log records
    INTENTS as 'pending'; the actual transfer fires only when the
    receiving party's status='claimed'.

    Per §16.2 'No commingled escrow funds': operations log includes
    a segregated_account_ref so audit can verify cash is actually in
    a segregated regulated account before transfer_initiated.
    """

    log_entries: list[dict] = field(default_factory=list)

    def append_intent(
        self,
        *,
        op_type: str,  # "publisher_payout" | "user_creator_payout" | "consumer_token_charge"
        amount_usd_cents: int,
        substrate_ref: str,
        idempotency_key: str,
        segregated_account_ref: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> dict:
        """Record the intent to make a money movement. Returns the
        log entry. Re-appending the same idempotency_key returns the
        existing entry — operations are at-least-once-safe."""
        existing = self._find_by_idem(idempotency_key)
        if existing is not None:
            return existing
        entry = {
            "op_type": op_type,
            "amount_usd_cents": amount_usd_cents,
            "substrate_ref": substrate_ref,
            "idempotency_key": idempotency_key,
            "segregated_account_ref": segregated_account_ref,
            "metadata": metadata or {},
            "status": "intent_recorded",
            "created_at": _now_iso(),
            "completed_at": None,
            "provider_ref": None,
        }
        self.log_entries.append(entry)
        return entry

    def mark_complete(
        self,
        *,
        idempotency_key: str,
        provider_ref: str,
    ) -> None:
        """Mark an intent as completed by the provider. Provider_ref
        is the Stripe transfer/charge ID for downstream audit."""
        entry = self._find_by_idem(idempotency_key)
        if entry is None:
            return
        entry["status"] = "completed"
        entry["completed_at"] = _now_iso()
        entry["provider_ref"] = provider_ref

    def _find_by_idem(self, key: str) -> Optional[dict]:
        for e in self.log_entries:
            if e["idempotency_key"] == key:
                return e
        return None


# ---------------------------------------------------------------------------
# Account-creation helpers
# ---------------------------------------------------------------------------


def create_publisher_account(
    provider: StripeProvider,
    *,
    display_name: str,
    legal_contact_email: Optional[str],
    ip_holder_id: str,
) -> StripeConnectAccount:
    """Create a Stripe Connect account for a publisher. The substrate
    ip_holders.escrow_account_ref is updated once this returns; per
    master-spec §9.10, the actual KYC + first-payout flow runs only
    after the publisher transitions status='claimed'."""
    connect_account_id = provider.create_connect_account(
        display_name=display_name,
        legal_contact_email=legal_contact_email,
        account_kind="publisher",
    )
    return StripeConnectAccount(
        connect_account_id=connect_account_id,
        account_kind="publisher",
        substrate_ref=ip_holder_id,
        status=StripeAccountStatus.PENDING,
    )


def create_user_creator_account(
    provider: StripeProvider,
    *,
    user_id: str,
    legal_contact_email: Optional[str] = None,
    display_name: Optional[str] = None,
) -> StripeConnectAccount:
    """Create a Stripe Connect account for a user-creator (the
    user-as-IP-holder framing per §13.9). Same architecture as
    publisher accounts; only the population differs."""
    connect_account_id = provider.create_connect_account(
        display_name=display_name or user_id,
        legal_contact_email=legal_contact_email,
        account_kind="user_creator",
    )
    return StripeConnectAccount(
        connect_account_id=connect_account_id,
        account_kind="user_creator",
        substrate_ref=user_id,
        status=StripeAccountStatus.PENDING,
    )
