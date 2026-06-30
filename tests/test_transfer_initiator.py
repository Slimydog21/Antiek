"""Stripe Connect transfer initiator tests."""

from __future__ import annotations

import os
import shutil
import tempfile
import uuid

import duckdb
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
    _record,
    ensure_table,
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


def test_decision_id_is_database_unique(isolated_db):
    from runtime.db_lock import connect_write

    with connect_write(isolated_db, purpose="test:xfer") as con:
        ensure_table(con)
        con.execute(
            """
            INSERT INTO payout_transfers (
                transfer_attempt_id, decision_id, stripe_transfer_id,
                recipient_account_id, amount_usd_cents, status, note
            ) VALUES (
                'xfer-a', 'decision-fixed', 'tr-a', 'acct_X', 700,
                'transferred', 'first'
            )
            """
        )
        with pytest.raises(duckdb.ConstraintException):
            con.execute(
                """
                INSERT INTO payout_transfers (
                    transfer_attempt_id, decision_id, stripe_transfer_id,
                    recipient_account_id, amount_usd_cents, status, note
                ) VALUES (
                    'xfer-b', 'decision-fixed', 'tr-b', 'acct_X', 700,
                    'transferred', 'duplicate'
                )
                """
            )


class _RaceRecordConn:
    def __init__(self):
        self.insert_attempts = 0
        self._row = None
        self._last_select_row = None

    def execute(self, sql: str, params: list | None = None):
        normalized = " ".join(sql.split())
        if normalized.startswith("CREATE TABLE"):
            return self
        if normalized.startswith("CREATE UNIQUE INDEX"):
            return self
        if normalized.startswith("SELECT transfer_attempt_id"):
            self._last_select_row = self._row
            return self
        if normalized.startswith("INSERT INTO payout_transfers"):
            self.insert_attempts += 1
            self._row = (
                "xfer-raced", "tr-raced", "acct_X", 700,
                STATUS_TRANSFERRED, "other worker won", "2026-06-30T12:00:00",
            )
            raise duckdb.ConstraintException("duplicate decision_id")
        raise AssertionError(f"unexpected SQL: {normalized}")

    def fetchone(self):
        return self._last_select_row


def test_record_duplicate_insert_race_returns_matching_existing_outcome():
    con = _RaceRecordConn()

    outcome = _record(
        con,
        decision_id="decision-raced",
        stripe_transfer_id="tr-raced",
        recipient_account_id="acct_X",
        amount_usd_cents=700,
        status=STATUS_TRANSFERRED,
        note="other worker won",
    )

    assert outcome.transfer_attempt_id == "xfer-raced"
    assert outcome.stripe_transfer_id == "tr-raced"
    assert outcome.note == "other worker won"
    assert con.insert_attempts == 1


def test_record_duplicate_insert_race_with_mismatch_raises():
    con = _RaceRecordConn()

    with pytest.raises(TransferInitiatorError, match="different transfer outcome"):
        _record(
            con,
            decision_id="decision-raced",
            stripe_transfer_id="tr-loser",
            recipient_account_id="acct_X",
            amount_usd_cents=700,
            status=STATUS_TRANSFERRED,
            note="loser",
        )


def test_record_existing_row_with_mismatch_raises():
    con = _RaceRecordConn()
    con._row = (
        "xfer-existing", "tr-existing", "acct_X", 700,
        STATUS_TRANSFERRED, "existing", "2026-06-30T12:00:00",
    )

    with pytest.raises(TransferInitiatorError, match="already has a different"):
        _record(
            con,
            decision_id="decision-existing",
            stripe_transfer_id="tr-new",
            recipient_account_id="acct_X",
            amount_usd_cents=700,
            status=STATUS_TRANSFERRED,
            note="new",
        )
    assert con.insert_attempts == 0


class _BrokenRecordConn(_RaceRecordConn):
    def execute(self, sql: str, params: list | None = None):
        normalized = " ".join(sql.split())
        if normalized.startswith("INSERT INTO payout_transfers"):
            self.insert_attempts += 1
            raise RuntimeError("disk full")
        return super().execute(sql, params)


def test_record_non_duplicate_insert_failure_still_raises():
    con = _BrokenRecordConn()

    with pytest.raises(RuntimeError, match="disk full"):
        _record(
            con,
            decision_id="decision-broken",
            stripe_transfer_id="tr-loser",
            recipient_account_id="acct_X",
            amount_usd_cents=700,
            status=STATUS_TRANSFERRED,
            note="loser",
        )


def test_provider_failure_returns_existing_concurrent_outcome():
    class _FailingProvider:
        def transfer_to_connect(self, **kwargs):
            raise RuntimeError("Stripe outage")

    con = _RaceRecordConn()
    con._row = (
        "xfer-existing", "tr-existing", "acct_X", 700,
        STATUS_TRANSFERRED, "transferred via Stripe Connect",
        "2026-06-30T12:00:00",
    )
    decision = _decision(decision_id="decision-existing")

    outcome = initiate_transfer(
        con=con,
        provider=_FailingProvider(),  # type: ignore[arg-type]
        decision=decision,
        account_id_for_recipient="acct_X",
    )

    assert outcome.status == STATUS_TRANSFERRED
    assert outcome.stripe_transfer_id == "tr-existing"
    assert con.insert_attempts == 0


# ── Missing recipient account raises ──────────────────────────────


def test_missing_account_for_creator_raises(isolated_db):
    from runtime.db_lock import connect_write

    provider = MockStripeProvider()
    decision = _decision()
    with (
        connect_write(isolated_db, purpose="test:xfer") as con,
        pytest.raises(TransferInitiatorError, match="Connect account"),
    ):
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


def test_failed_transfer_can_be_retried_to_success(isolated_db):
    from runtime.db_lock import connect_write

    class _FailingProvider:
        def transfer_to_connect(self, **kwargs):
            raise RuntimeError("Stripe outage")

    decision = _decision(decision_id="rs-retry")
    with connect_write(isolated_db, purpose="test:xfer") as con:
        failed = initiate_transfer(
            con=con,
            provider=_FailingProvider(),  # type: ignore[arg-type]
            decision=decision,
            account_id_for_recipient="acct_user_X",
        )
        assert failed.status == STATUS_FAILED

        retried = initiate_transfer(
            con=con,
            provider=MockStripeProvider(),
            decision=decision,
            account_id_for_recipient="acct_user_X",
        )
        assert retried.transfer_attempt_id == failed.transfer_attempt_id
        assert retried.status == STATUS_TRANSFERRED
        assert retried.stripe_transfer_id is not None

        rows = con.execute(
            "SELECT status, stripe_transfer_id FROM payout_transfers "
            "WHERE decision_id = ?",
            [decision.decision_id],
        ).fetchall()
    assert rows == [(STATUS_TRANSFERRED, retried.stripe_transfer_id)]


def test_failed_transfer_retry_with_different_account_raises(isolated_db):
    from runtime.db_lock import connect_write

    class _FailingProvider:
        def transfer_to_connect(self, **kwargs):
            raise RuntimeError("Stripe outage")

    decision = _decision(decision_id="rs-retry-mismatch")
    with connect_write(isolated_db, purpose="test:xfer") as con:
        failed = initiate_transfer(
            con=con,
            provider=_FailingProvider(),  # type: ignore[arg-type]
            decision=decision,
            account_id_for_recipient="acct_original",
        )
        assert failed.status == STATUS_FAILED

        with pytest.raises(TransferInitiatorError, match="different transfer outcome"):
            initiate_transfer(
                con=con,
                provider=MockStripeProvider(),
                decision=decision,
                account_id_for_recipient="acct_other",
            )

        rows = con.execute(
            "SELECT status, recipient_account_id FROM payout_transfers "
            "WHERE decision_id = ?",
            [decision.decision_id],
        ).fetchall()
    assert rows == [(STATUS_FAILED, "acct_original")]


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
