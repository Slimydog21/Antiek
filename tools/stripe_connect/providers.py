"""Stripe provider protocol + mock implementation."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class StripeProvider(Protocol):
    """The substrate operations against Stripe. Production wires
    RealStripeProvider via the `stripe` SDK once keys land in env."""

    def create_connect_account(
        self,
        *,
        display_name: str,
        legal_contact_email: str | None,
        account_kind: str,  # "publisher" | "user_creator"
    ) -> str: ...

    def create_customer(
        self,
        *,
        email: str | None,
        metadata: dict,
    ) -> str: ...

    def record_usage(
        self,
        *,
        customer_id: str,
        amount_usd_cents: int,
        idempotency_key: str,
        metadata: dict,
    ) -> str: ...

    def transfer_to_connect(
        self,
        *,
        account_id: str,
        amount_usd_cents: int,
        idempotency_key: str,
        metadata: dict,
    ) -> str: ...


@dataclass
class MockStripeProvider:
    """In-memory test stub. Records every operation; never makes a
    network call. Operations are idempotent by key — re-submitting
    the same idempotency_key returns the original id."""

    accounts: dict[str, dict] = field(default_factory=dict)
    customers: dict[str, dict] = field(default_factory=dict)
    usage_records: dict[str, dict] = field(default_factory=dict)
    transfers: dict[str, dict] = field(default_factory=dict)
    _idem_index: dict[str, str] = field(default_factory=dict)

    def create_connect_account(
        self,
        *,
        display_name: str,
        legal_contact_email: str | None,
        account_kind: str,
    ) -> str:
        acct_id = f"acct_mock_{uuid.uuid4().hex[:12]}"
        self.accounts[acct_id] = {
            "id": acct_id,
            "display_name": display_name,
            "legal_contact_email": legal_contact_email,
            "account_kind": account_kind,
            "created_at": _now_iso(),
        }
        return acct_id

    def create_customer(
        self,
        *,
        email: str | None,
        metadata: dict,
    ) -> str:
        cus_id = f"cus_mock_{uuid.uuid4().hex[:12]}"
        self.customers[cus_id] = {
            "id": cus_id,
            "email": email,
            "metadata": metadata,
            "created_at": _now_iso(),
        }
        return cus_id

    def record_usage(
        self,
        *,
        customer_id: str,
        amount_usd_cents: int,
        idempotency_key: str,
        metadata: dict,
    ) -> str:
        if idempotency_key in self._idem_index:
            return self._idem_index[idempotency_key]
        rec_id = f"mbur_mock_{uuid.uuid4().hex[:12]}"
        self.usage_records[rec_id] = {
            "id": rec_id,
            "customer_id": customer_id,
            "amount_usd_cents": amount_usd_cents,
            "idempotency_key": idempotency_key,
            "metadata": metadata,
            "created_at": _now_iso(),
        }
        self._idem_index[idempotency_key] = rec_id
        return rec_id

    def transfer_to_connect(
        self,
        *,
        account_id: str,
        amount_usd_cents: int,
        idempotency_key: str,
        metadata: dict,
    ) -> str:
        if idempotency_key in self._idem_index:
            return self._idem_index[idempotency_key]
        tr_id = f"tr_mock_{uuid.uuid4().hex[:12]}"
        self.transfers[tr_id] = {
            "id": tr_id,
            "account_id": account_id,
            "amount_usd_cents": amount_usd_cents,
            "idempotency_key": idempotency_key,
            "metadata": metadata,
            "created_at": _now_iso(),
        }
        self._idem_index[idempotency_key] = tr_id
        return tr_id
