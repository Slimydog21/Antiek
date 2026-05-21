"""Stripe Connect transfer initiator tests."""

from __future__ import annotations

import os
import shutil
import tempfile
import uuid

import pytest

from substrate.ad_inventory.payout import (
    RevShareDecision,
    RevShareKind,
)
from substrate.ad_inventory.transfer_initiator import (
    STATUS_FAILED,
    STATUS_SKIPPED_ESCROW,
    STATUS_SKIPPED_PLATFORM,
    STATUS_TRANSFERRED,
    TransferInitiatorError,
    initiate_transfer,
    load_transfers_for_recipient,
)
from tools.stripe_connect.providers import MockStripeProvider


@pytest.fixture()
def isolated_db():
    """Each test gets its own DuckDB so the writer lock can't collide."""
    tmpdir = tempfile.mkdtemp(prefix="antiek-xfer-")
    db_path = os.path.join(tmpdir, "antiek.duckdb")
    try:
        from substrate.graph import ensure_initialized
        ensure_initialized(db_path)
        yield db_path
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _decision(
    *,
    decision_id: str | None = None,
    kind: RevShareKind = RevShareKind.CREATOR,
    recipient_ref: str = "user-X",
    amount_usd_cents: int = 700,
    document_id: str | None = "doc-A",
    requires_escrow: bool = False,
    capped_to_daily_limit: bool = False,
) -> RevShareDecision:
    return RevShareDecision(
        decision_id=decision_id or f"rs-{uuid.uuid4().hex[:10]}",
        impression_id="imp-1",
        kind=kind,
        recipient_ref=recipient_ref,
        amount_usd_cents=amount_usd_cents,
        document_id=document_id,
        requires_escrow=requires_escrow,
        capped_to_daily_limit=capped_to_daily_limit,
    )


# ── Platform decisions skip without provider call ──────────────────


def test_platform_decision_skips(isolated_db):
    from runtime.db_lock import connect_write

    provider = MockStripeProvider()
    decision = _decision(
        kind=RevShareKind.PLATFORM,
        recipient_ref="__platform__",
        document_id=None,
    )
    with connect_write(isolated_db, purpose="test:xfer") as con:
        outcome = initiate_transfer(
            con=con, provider=provider, decision=decision,
            account_id_for_recipient=None,
        )
    assert outcome.status == STATUS_SKIPPED_PLATFORM
    assert outcome.stripe_transfer_id is None
    assert provider.transfers == {}


# ── Escrow-required publishers skip ───────────────────────────────


def test_escrow_required_publisher_skips(isolated_db):
    from runtime.db_lock import connect_write

    provider = MockStripeProvider()
    decision = _decision(
        kind=RevShareKind.PUBLISHER,
        recipient_ref="ip-holder-1",
        requires_escrow=True,
    )
    with connect_write(isolated_db, purpose="test:xfer") as con:
        outcome = initiate_transfer(
            con=con, provider=provider, decision=decision,
            account_id_for_recipient="acct_pre_onboarded",
        )
    assert outcome.status == STATUS_SKIPPED_ESCROW
    assert outcome.stripe_transfer_id is None
    assert provider.transfers == {}


# ── Creator transfer happy path ────────────────────────────────────


def test_creator_transfer_happy_path(isolated_db):
    from runtime.db_lock import connect_write

    provider = MockStripeProvider()
    decision = _decision()
    with connect_write(isolated_db, purpose="test:xfer") as con:
        outcome = initiate_transfer(
            con=con, provider=provider, decision=decision,
            account_id_for_recipient="acct_user_X",
        )
    assert outcome.status == STATUS_TRANSFERRED
    assert outcome.stripe_transfer_id is not None
    assert outcome.stripe_transfer_id.startswith("tr_mock_")
    assert len(provider.transfers) == 1
    tr = next(iter(provider.transfers.values()))
    assert tr["amount_usd_cents"] == 700
    assert tr["account_id"] == "acct_user_X"
    assert tr["metadata"]["decision_id"] == decision.decision_id


# ── Idempotent re-initiate ─────────────────────────────────────────


def test_reinitiate_same_decision_returns_existing_outcome(isolated_db):
    from runtime.db_lock import connect_write

    provider = MockStripeProvider()
    decision = _decision()
    with connect_write(isolated_db, purpose="test:xfer") as con:
        first = initiate_transfer(
            con=con, provider=provider, decision=decision,
            account_id_for_recipient="acct_user_X",
        )
        second = initiate_transfer(
            con=con, provider=provider, decision=decision,
            account_id_for_recipient="acct_user_X",
        )
    assert first.transfer_attempt_id == second.transfer_attempt_id
    assert first.stripe_transfer_id == second.stripe_transfer_id
    # Mock provider sees idempotency_key reused and returns same id.
    assert len(provider.transfers) == 1


# ── Missing recipient account raises ──────────────────────────────


def test_missing_account_for_creator_raises(isolated_db):
    from runtime.db_lock import connect_write

    provider = MockStripeProvider()
    decision = _decision()
    with connect_write(isolated_db, purpose="test:xfer") as con:
        with pytest.raises(TransferInitiatorError, match="Connect account"):
            initiate_transfer(
                con=con, provider=provider, decision=decision,
                account_id_for_recipient=None,
            )


# ── Provider failure recorded as failed ───────────────────────────


def test_provider_exception_recorded_as_failed(isolated_db):
    from runtime.db_lock import connect_write

    class _FailingProvider:
        def transfer_to_connect(self, **kwargs):
            raise RuntimeError("Stripe outage")

        # Stub-out unused protocol methods.
        def create_connect_account(self, **kwargs):
            raise NotImplementedError

        def create_customer(self, **kwargs):
            raise NotImplementedError

        def record_usage(self, **kwargs):
            raise NotImplementedError

    decision = _decision()
    with connect_write(isolated_db, purpose="test:xfer") as con:
        outcome = initiate_transfer(
            con=con, provider=_FailingProvider(),
            decision=decision,
            account_id_for_recipient="acct_user_X",
        )
    assert outcome.status == STATUS_FAILED
    assert "Stripe outage" in outcome.note


# ── Audit lookup ───────────────────────────────────────────────────


def test_load_transfers_for_recipient(isolated_db):
    from runtime.db_lock import connect_write

    provider = MockStripeProvider()
    with connect_write(isolated_db, purpose="test:xfer") as con:
        for _ in range(3):
            initiate_transfer(
                con=con, provider=provider,
                decision=_decision(),
                account_id_for_recipient="acct_X",
            )
        # One transfer to a different recipient.
        initiate_transfer(
            con=con, provider=provider,
            decision=_decision(recipient_ref="user-Y"),
            account_id_for_recipient="acct_Y",
        )
        rows = load_transfers_for_recipient(con, "acct_X")
    assert len(rows) == 3
    for r in rows:
        assert r.recipient_account_id == "acct_X"
        assert r.status == STATUS_TRANSFERRED


# ── Capped-to-zero decisions skip cleanly ──────────────────────────


def test_zero_amount_decision_skips(isolated_db):
    from runtime.db_lock import connect_write

    provider = MockStripeProvider()
    decision = _decision(amount_usd_cents=0)
    with connect_write(isolated_db, purpose="test:xfer") as con:
        outcome = initiate_transfer(
            con=con, provider=provider, decision=decision,
            account_id_for_recipient="acct_user_X",
        )
    assert outcome.status == STATUS_SKIPPED_PLATFORM
    assert outcome.stripe_transfer_id is None
    assert provider.transfers == {}
