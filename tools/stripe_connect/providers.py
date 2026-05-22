"""Stripe provider protocol + mock implementation + real implementation.

Three classes:

- ``StripeProvider`` — the Protocol. Used everywhere in the substrate
  so the call sites are decoupled from whether we're talking to the
  real Stripe API or a test stub.
- ``MockStripeProvider`` — in-memory, deterministic, used in tests
  and local dev.
- ``RealStripeProvider`` — wraps the ``stripe`` Python SDK. Loaded
  lazily so the substrate boots without the SDK installed; raises
  ``StripeUnavailable`` with an actionable error if the SDK is
  missing or ``STRIPE_SECRET_KEY`` is unset.

Operator activation is a single ``get_stripe_provider()`` factory
call that switches on ``ANTIEK_STRIPE_PROVIDER`` env var (``mock``
default, ``real`` once keys land + Sprint 18 legal gates G2 + G3
close).
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol


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


# ── Real Stripe provider ─────────────────────────────────────────────


class StripeUnavailable(RuntimeError):
    """Raised when RealStripeProvider can't be activated.

    Causes (in order checked):

    1. The ``stripe`` Python SDK is not installed
       (``pip install antiek[stripe]`` or add ``stripe>=8`` to the
       project dependencies).
    2. ``STRIPE_SECRET_KEY`` env var is unset or empty.
    3. ``ANTIEK_STRIPE_PROVIDER`` is ``mock`` (the safe default —
       operator must explicitly switch to ``real`` once legal gates
       G2 + G3 close per §9.0).
    """


@dataclass
class RealStripeProvider:
    """Production Stripe provider, wrapping the ``stripe`` SDK.

    Connect accounts created via this provider go through the
    Standard or Express onboarding flow per §9.6. The ``account_kind``
    parameter on ``create_connect_account`` is recorded in Stripe
    metadata so reporting can distinguish publisher escrow accounts
    (``publisher``) from user-creator rev-share accounts
    (``user_creator``).

    The SDK is loaded lazily so this module can be imported in
    environments without it; the import happens at the first call
    that needs the SDK (or at ``__post_init__`` when invoked
    explicitly via the factory).
    """

    api_key: str = ""
    api_version: str = "2024-12-18.acacia"  # Stripe API version pin
    _stripe_module: Any = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.api_key:
            self.api_key = os.environ.get("STRIPE_SECRET_KEY", "").strip()
        if not self.api_key:
            raise StripeUnavailable(
                "STRIPE_SECRET_KEY is not set. Add it to "
                "/etc/antiek/secrets.env and restart the service. The "
                "factory at get_stripe_provider() returns the mock "
                "provider until this is configured."
            )
        try:
            import stripe  # type: ignore[import-not-found]
        except ImportError as exc:
            raise StripeUnavailable(
                "The `stripe` Python SDK is not installed. Add it via "
                "`pip install stripe>=8` (or extend the antiek "
                "optional-dependencies in pyproject.toml) and "
                "re-deploy."
            ) from exc
        stripe.api_key = self.api_key
        stripe.api_version = self.api_version
        self._stripe_module = stripe

    @property
    def stripe(self) -> Any:
        """The configured stripe SDK module. Available after
        ``__post_init__`` succeeds."""
        return self._stripe_module

    def create_connect_account(
        self,
        *,
        display_name: str,
        legal_contact_email: str | None,
        account_kind: str,
    ) -> str:
        params: dict[str, Any] = {
            "type": "standard",
            "business_profile": {"name": display_name},
            "metadata": {
                "antiek_account_kind": account_kind,
                "antiek_display_name": display_name,
            },
        }
        if legal_contact_email:
            params["email"] = legal_contact_email
        acct = self._stripe_module.Account.create(**params)
        return acct["id"]

    def create_customer(
        self,
        *,
        email: str | None,
        metadata: dict,
    ) -> str:
        params: dict[str, Any] = {
            "metadata": {**metadata, "antiek_managed": "true"},
        }
        if email:
            params["email"] = email
        customer = self._stripe_module.Customer.create(**params)
        return customer["id"]

    def record_usage(
        self,
        *,
        customer_id: str,
        amount_usd_cents: int,
        idempotency_key: str,
        metadata: dict,
    ) -> str:
        """Records a usage-based charge for pay-as-you-go pricing
        per §13.5. Uses Stripe's PaymentIntent API directly so the
        operator's three-tier token model can charge arbitrary
        amounts without pre-creating a Price for every tier × cap
        combination."""
        intent = self._stripe_module.PaymentIntent.create(
            amount=amount_usd_cents,
            currency="usd",
            customer=customer_id,
            metadata={**metadata, "antiek_idempotency_key": idempotency_key},
            confirm=True,
            off_session=True,
            idempotency_key=idempotency_key,
        )
        return intent["id"]

    def transfer_to_connect(
        self,
        *,
        account_id: str,
        amount_usd_cents: int,
        idempotency_key: str,
        metadata: dict,
    ) -> str:
        """The §9.0 payout primitive. Routes from the platform's
        balance to a Connect account. Stripe enforces idempotency
        on the supplied key so retried calls don't duplicate."""
        transfer = self._stripe_module.Transfer.create(
            amount=amount_usd_cents,
            currency="usd",
            destination=account_id,
            metadata={**metadata, "antiek_idempotency_key": idempotency_key},
            idempotency_key=idempotency_key,
        )
        return transfer["id"]


# ── Factory ──────────────────────────────────────────────────────────


def get_stripe_provider() -> StripeProvider:
    """Resolve the configured Stripe provider.

    ``ANTIEK_STRIPE_PROVIDER`` env var:
    - ``mock`` (default): returns MockStripeProvider.
    - ``real``: returns RealStripeProvider; raises StripeUnavailable
      if the SDK is missing or STRIPE_SECRET_KEY is unset.

    Single decision point so the rest of the substrate doesn't know
    which provider is in play.
    """
    choice = os.environ.get("ANTIEK_STRIPE_PROVIDER", "mock").strip().lower()
    if choice == "real":
        return RealStripeProvider()
    return MockStripeProvider()
