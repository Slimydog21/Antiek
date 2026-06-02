"""1099 reporting stub tests (Sprint 23-24 phase 4 — §9.5)."""

from __future__ import annotations

import os
import tempfile

import pytest

from runtime.db_lock import connect_write
from substrate.billing.tax_reports import (
    IRS_1099_NEC_THRESHOLD_USD_CENTS,
    AnnualPayoutAggregate,
    aggregate_annual_payouts,
    load_emissions,
    record_emission,
    render_csv,
    write_csv,
)
from substrate.graph.schema import init_database


@pytest.fixture
def db():
    tmpdir = tempfile.mkdtemp(prefix="antiek-tax-test-")
    db_path = os.path.join(tmpdir, "test.duckdb")
    con = connect_write(db_path, purpose="tax_test")
    init_database(con)
    yield con, tmpdir
    con.close()


def _seed_transfer(
    con, *, recipient_account_id: str, amount_usd_cents: int,
    initiated_at: str, status: str = "transferred",
) -> None:
    import uuid
    con.execute(
        """
        INSERT INTO payout_transfers (
            transfer_attempt_id, decision_id, stripe_transfer_id,
            recipient_account_id, amount_usd_cents, status, note,
            initiated_at
        ) VALUES (?, ?, ?, ?, ?, ?, '', ?::TIMESTAMP)
        """,
        [
            f"xfer-{uuid.uuid4().hex[:8]}",
            f"rs-{uuid.uuid4().hex[:8]}",
            f"tr_{uuid.uuid4().hex[:8]}",
            recipient_account_id, amount_usd_cents, status,
            initiated_at,
        ],
    )


# ── Aggregation ────────────────────────────────────────────────────


def test_aggregate_groups_by_recipient(db):
    con, _ = db
    _seed_transfer(
        con, recipient_account_id="acct_a",
        amount_usd_cents=100_00, initiated_at="2026-03-01 00:00:00",
    )
    _seed_transfer(
        con, recipient_account_id="acct_a",
        amount_usd_cents=200_00, initiated_at="2026-06-15 00:00:00",
    )
    _seed_transfer(
        con, recipient_account_id="acct_b",
        amount_usd_cents=500_00, initiated_at="2026-09-01 00:00:00",
    )
    aggs = aggregate_annual_payouts(con, tax_year=2026)
    by_recipient = {a.recipient_ref: a for a in aggs}
    assert by_recipient["acct_a"].total_usd_cents == 300_00
    assert by_recipient["acct_a"].transfer_count == 2
    assert by_recipient["acct_b"].total_usd_cents == 500_00


def test_aggregate_excludes_skipped_or_failed(db):
    con, _ = db
    _seed_transfer(
        con, recipient_account_id="acct_a",
        amount_usd_cents=100_00, initiated_at="2026-03-01 00:00:00",
        status="transferred",
    )
    _seed_transfer(
        con, recipient_account_id="acct_a",
        amount_usd_cents=999_00, initiated_at="2026-04-01 00:00:00",
        status="skipped_escrow",
    )
    _seed_transfer(
        con, recipient_account_id="acct_a",
        amount_usd_cents=999_00, initiated_at="2026-05-01 00:00:00",
        status="failed",
    )
    aggs = aggregate_annual_payouts(con, tax_year=2026)
    assert len(aggs) == 1
    assert aggs[0].total_usd_cents == 100_00


def test_aggregate_window_is_calendar_year(db):
    con, _ = db
    # 2025 transfer — out of window.
    _seed_transfer(
        con, recipient_account_id="acct_a",
        amount_usd_cents=100_00, initiated_at="2025-12-31 23:59:59",
    )
    # 2026 transfer — in window.
    _seed_transfer(
        con, recipient_account_id="acct_a",
        amount_usd_cents=200_00, initiated_at="2026-01-01 00:00:00",
    )
    # 2027 transfer — out of window.
    _seed_transfer(
        con, recipient_account_id="acct_a",
        amount_usd_cents=300_00, initiated_at="2027-01-01 00:00:00",
    )
    aggs = aggregate_annual_payouts(con, tax_year=2026)
    assert len(aggs) == 1
    assert aggs[0].total_usd_cents == 200_00


# ── Threshold flagging ────────────────────────────────────────────


def test_above_threshold_flag():
    above = AnnualPayoutAggregate(
        recipient_ref="x", tax_year=2026,
        total_usd_cents=IRS_1099_NEC_THRESHOLD_USD_CENTS,
        transfer_count=1,
    )
    below = AnnualPayoutAggregate(
        recipient_ref="x", tax_year=2026,
        total_usd_cents=IRS_1099_NEC_THRESHOLD_USD_CENTS - 1,
        transfer_count=1,
    )
    assert above.above_1099_threshold is True
    assert below.above_1099_threshold is False


# ── CSV rendering ──────────────────────────────────────────────────


def test_csv_header_and_rows():
    aggs = [
        AnnualPayoutAggregate(
            recipient_ref="acct_b", tax_year=2026,
            total_usd_cents=800_00, transfer_count=4,
        ),
        AnnualPayoutAggregate(
            recipient_ref="acct_a", tax_year=2026,
            total_usd_cents=500_00, transfer_count=2,
        ),
    ]
    csv_text = render_csv(aggs)
    lines = csv_text.strip().split("\n")
    assert lines[0] == (
        "recipient_ref,tax_year,total_payout_usd,"
        "transfer_count,above_1099_threshold"
    )
    # Sorted ascending by recipient_ref.
    assert lines[1].startswith("acct_a,2026,500.00,2,false")
    assert lines[2].startswith("acct_b,2026,800.00,4,true")


def test_write_csv_creates_file(db):
    _, tmpdir = db
    path = os.path.join(tmpdir, "out.csv")
    written = write_csv(
        [
            AnnualPayoutAggregate(
                recipient_ref="acct_a", tax_year=2026,
                total_usd_cents=100_00, transfer_count=1,
            ),
        ],
        path,
    )
    assert os.path.exists(written)
    with open(written, encoding="utf-8") as fh:
        contents = fh.read()
    assert "acct_a,2026,100.00,1,false" in contents


# ── Emission audit log ────────────────────────────────────────────


def test_record_then_load_emissions(db):
    con, _ = db
    aggs = [
        AnnualPayoutAggregate(
            recipient_ref="acct_a", tax_year=2026,
            total_usd_cents=800_00, transfer_count=2,
        ),
    ]
    record_emission(con, aggregates=aggs, csv_export_path="/tmp/1099.csv")
    emissions = load_emissions(con, tax_year=2026)
    assert len(emissions) == 1
    assert emissions[0].recipient_ref == "acct_a"
    assert emissions[0].above_1099_threshold is True
    assert emissions[0].csv_export_path == "/tmp/1099.csv"
