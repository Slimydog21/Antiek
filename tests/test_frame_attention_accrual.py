"""SPR-05 M4 — the per-second accrual writer.

Proves: append-only through the single-writer lock; trace chain + version
stamps on each row; write count ≪ seconds × assets (aggregation, not a row per
second); accrual feeds escrow via the ONE sanctioned writer; replay reproduces
the accrual.
"""

from __future__ import annotations

import os
import tempfile
from decimal import Decimal

import pytest

from runtime.db_lock import connect_write
from substrate import ip_holders
from substrate.ad_inventory.frame_attention import (
    FRAME_TELEMETRY_SCHEMA_VERSION,
    FRAME_WEIGHTING_VERSION,
    FrameAttentionSample,
    FrameSecond,
    WindowFrameBatch,
)
from substrate.ad_inventory.frame_attention_accrual import (
    accrue_window,
    aggregate_window,
    record_client_hint,
    replay,
    window_reconciliation,
)

_IP_HOLDERS_DDL = """
CREATE TABLE IF NOT EXISTS ip_holders (
    ip_holder_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    legal_contact_email TEXT,
    status TEXT NOT NULL DEFAULT 'pre_onboarded',
    escrow_balance_usd DECIMAL(18, 6) NOT NULL DEFAULT 0,
    escrow_account_ref TEXT,
    notification_sent_at TIMESTAMP,
    claimed_at TIMESTAMP,
    opted_out_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    metadata TEXT
);
"""


@pytest.fixture
def con():
    tmpdir = tempfile.mkdtemp(prefix="antiek-frame-accrual-")
    db_path = os.path.join(tmpdir, "test.duckdb")
    c = connect_write(db_path, purpose="frame_accrual_test")
    c.execute(_IP_HOLDERS_DDL)
    yield c
    c.close()


def _sample(asset_id, *, area=0.5, prom=0.5, dwell=500, cc="public_domain", chunk=None):
    return FrameAttentionSample(
        asset_id=asset_id, viewport_area_fraction=area, prominence=prom,
        focused_dwell_ms=dwell, content_class=cc, chunk_id=chunk,
    )


def _window(window_id, n_seconds, samples_per_second, ad_value_cents):
    seconds = tuple(
        FrameSecond(second_index=i, lens="read", samples=samples_per_second)
        for i in range(n_seconds)
    )
    return WindowFrameBatch(
        window_id=window_id, seconds=seconds, ad_value_usd_cents=ad_value_cents,
    )


def test_accrual_is_append_only_and_traceable(con):
    holder = ip_holders.create_pre_onboarded(con, display_name="MIT Press")
    samples = (
        _sample("doc-a", area=0.6, prom=0.8, dwell=900, chunk="ch-a"),
        _sample("doc-b", area=0.3, prom=0.2, dwell=300, chunk="ch-b"),
    )
    batch = _window("w-1", 10, samples, 1000)
    result = accrue_window(con, batch, asset_to_ip_holder={"doc-a": holder})

    rows = con.execute(
        "SELECT window_id, asset_id, chunk_id, ip_holder_id, summed_weight, "
        "amount_cents, n_seconds, telemetry_version, weighting_version "
        "FROM frame_attention_accruals ORDER BY asset_id"
    ).fetchall()
    assert len(rows) == 2
    a = next(r for r in rows if r[1] == "doc-a")
    # trace chain: window → asset → chunk → ip_holder, version-stamped
    assert a[0] == "w-1"
    assert a[2] == "ch-a"
    assert a[3] == holder
    assert a[6] == 10  # n_seconds
    assert a[7] == FRAME_TELEMETRY_SCHEMA_VERSION
    assert a[8] == FRAME_WEIGHTING_VERSION
    assert result.reconciles()


def test_write_count_is_bounded_by_assets_not_seconds(con):
    """The load-bearing aggregation claim: 600 seconds × 5 assets must NOT
    produce 3,000 rows — at most (5 asset rows + 1 house row)."""
    samples = tuple(
        _sample(f"doc-{k}", area=0.3, prom=0.4, dwell=400) for k in range(5)
    )
    batch = _window("w-big", 600, samples, 6000)
    accrue_window(con, batch)
    n_accrual = con.execute(
        "SELECT COUNT(*) FROM frame_attention_accruals WHERE window_id = 'w-big'"
    ).fetchone()[0]
    n_house = con.execute(
        "SELECT COUNT(*) FROM house_seconds WHERE window_id = 'w-big'"
    ).fetchone()[0]
    total_rows = n_accrual + n_house
    seconds_times_assets = 600 * 5
    assert total_rows == 6  # 5 assets + 1 house row
    # The batching win: rows are bounded by (eligible assets + 1 house), NOT by
    # seconds×assets. 6 rows for a 600s × 5-asset window, not 3000 — two orders
    # of magnitude under, which is what keeps the single DuckDB writer alive.
    assert total_rows < seconds_times_assets
    assert total_rows * 100 < seconds_times_assets  # ≪, not merely <
    assert total_rows <= len(samples) + 1


def test_accrual_feeds_escrow_via_sanctioned_writer(con):
    h1 = ip_holders.create_pre_onboarded(con, display_name="Holder One")
    h2 = ip_holders.create_pre_onboarded(con, display_name="Holder Two")
    samples = (
        _sample("doc-a", area=0.5, prom=0.5, dwell=500),
        _sample("doc-b", area=0.5, prom=0.5, dwell=500),
    )
    batch = _window("w-esc", 4, samples, 800)  # 800c over 4s = 200c/sec
    result = accrue_window(
        con, batch, asset_to_ip_holder={"doc-a": h1, "doc-b": h2},
    )
    bal1 = ip_holders.get(con, h1).escrow_balance_usd
    bal2 = ip_holders.get(con, h2).escrow_balance_usd
    # AFA-S5: 70/30 at pool boundary. Equal assets over 800c → creator pool
    # 560c, each holder 280c = $2.80 (was 400c pre-S5; sanctioned pin edit).
    assert bal1 == Decimal("2.800000")
    assert bal2 == Decimal("2.800000")
    assert result.creator_pool_cents == 560
    assert result.platform_cut_cents == 240
    # escrow total equals contributor accrual total (creator pool only)
    cents_total = sum(line.amount_cents for line in result.asset_lines)
    assert (bal1 + bal2) == Decimal(cents_total) / Decimal(100)
    assert result.reconciles()


def test_preonboarded_holder_accrues(con):
    """Pre-onboarded (shadow) holders accrue too — no payout until claimed,
    but the balance is real."""
    h = ip_holders.create_pre_onboarded(con, display_name="Shadow Publisher")
    assert ip_holders.get(con, h).status == "pre_onboarded"
    batch = _window("w-shadow", 5, (_sample("doc-a"),), 500)
    accrue_window(con, batch, asset_to_ip_holder={"doc-a": h})
    holder = ip_holders.get(con, h)
    assert holder.status == "pre_onboarded"  # still shadow
    # AFA-S5: 70% of 500c = 350c = $3.50 (was $5.00 pre-S5; sanctioned pin).
    assert holder.escrow_balance_usd == Decimal("3.500000")  # but accrued


def test_idempotent_no_double_escrow(con):
    h = ip_holders.create_pre_onboarded(con, display_name="Idem Press")
    batch = _window("w-idem", 5, (_sample("doc-a"),), 500)
    accrue_window(con, batch, asset_to_ip_holder={"doc-a": h})
    first = ip_holders.get(con, h).escrow_balance_usd
    # re-accrue the SAME batch — must be a no-op, not a double accrual
    accrue_window(con, batch, asset_to_ip_holder={"doc-a": h})
    second = ip_holders.get(con, h).escrow_balance_usd
    assert first == second
    n_rows = con.execute(
        "SELECT COUNT(*) FROM frame_attention_accruals WHERE window_id = 'w-idem'"
    ).fetchone()[0]
    assert n_rows == 1  # not 2


def test_replay_reproduces_accrual(con):
    h = ip_holders.create_pre_onboarded(con, display_name="Replay Press")
    samples = (
        _sample("doc-a", area=0.6, prom=0.7, dwell=800),
        _sample("doc-b", area=0.4, prom=0.3, dwell=200),
    )
    batch = _window("w-replay", 12, samples, 1234)
    result = accrue_window(con, batch, asset_to_ip_holder={"doc-a": h})
    rr = replay(con, result.batch_ref)
    assert rr.identical, (
        f"replay diverged:\n recorded={rr.recorded}\n recomputed={rr.recomputed}"
    )


def test_aggregate_window_is_pure_and_reconciles():
    """Pure aggregation (no DB) conserves the window to the cent across many
    random-ish frames."""
    samples = (
        _sample("doc-a", area=0.7, prom=0.9, dwell=950),
        _sample("doc-b", area=0.2, prom=0.1, dwell=120),
        _sample("priv", cc="user_owned"),
    )
    batch = _window("w-pure", 37, samples, 9999)
    result = aggregate_window(batch)
    assert result.reconciles()
    # the private asset never appears in an accrual line
    assert "priv" not in {line.asset_id for line in result.asset_lines}


def test_reconciliation_query_matches_total(con):
    samples = (_sample("doc-a"), _sample("doc-b"))
    batch = _window("w-rec", 9, samples, 1000)
    accrue_window(con, batch)
    rec = window_reconciliation(con, "w-rec")
    assert rec["total_cents"] == 1000
    assert rec["contributor_cents"] + rec["house_cents"] == 1000


# ── ad-pipeline gap S1: the client-hint ledger ──────────────────────────────


def test_record_client_hint_is_append_only_and_idempotent(con):
    """An exact retry collapses to one row; a CHANGED claim appends — the
    ledger records every claim the client made, without any economic effect."""
    h1 = record_client_hint(
        con, window_id="w-hint", batch_ref="ref-1",
        client_hint_ad_value_usd_cents=1000,
        telemetry_version=FRAME_TELEMETRY_SCHEMA_VERSION,
    )
    h2 = record_client_hint(
        con, window_id="w-hint", batch_ref="ref-1",
        client_hint_ad_value_usd_cents=1000,
        telemetry_version=FRAME_TELEMETRY_SCHEMA_VERSION,
    )
    assert h1 == h2  # exact retry → same row, no duplicate
    record_client_hint(
        con, window_id="w-hint", batch_ref="ref-1",
        client_hint_ad_value_usd_cents=5000,  # revised claim
        telemetry_version=FRAME_TELEMETRY_SCHEMA_VERSION,
    )
    rows = con.execute(
        "SELECT client_hint_ad_value_usd_cents FROM "
        "frame_telemetry_client_hints WHERE window_id = 'w-hint'"
    ).fetchall()
    assert sorted(r[0] for r in rows) == [1000, 5000]


def test_record_client_hint_has_no_economic_effect(con):
    """The hint ledger NEVER touches money: recording a hint changes neither
    the accrual tables nor any escrow balance."""
    holder = ip_holders.create_pre_onboarded(con, display_name="Hint Press")
    batch = _window("w-hint-econ", 4, (_sample("doc-a"),), 400)
    accrue_window(con, batch, asset_to_ip_holder={"doc-a": holder})
    before_acc = con.execute(
        "SELECT COUNT(*) FROM frame_attention_accruals"
    ).fetchone()[0]
    before_escrow = ip_holders.get(con, holder).escrow_balance_usd

    record_client_hint(
        con, window_id="w-hint-econ", batch_ref="whatever-ref",
        client_hint_ad_value_usd_cents=999_999_999,
        telemetry_version=FRAME_TELEMETRY_SCHEMA_VERSION,
    )
    after_acc = con.execute(
        "SELECT COUNT(*) FROM frame_attention_accruals"
    ).fetchone()[0]
    assert after_acc == before_acc
    assert ip_holders.get(con, holder).escrow_balance_usd == before_escrow
