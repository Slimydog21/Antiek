"""AFA-S2 M5 — writer-level regressions for the two codex-BLOCKING findings.

These exercise accrue_window (the DB writer) + replay on a temp DuckDB, so they
catch bugs the pure aggregate_window tests cannot: replay faithfulness under the
now-order-sensitive filter, and the writer's return/reload carrying the
anti-gaming audit fields.
"""

from __future__ import annotations

import os
import tempfile

import pytest

from runtime.db_lock import connect_write
from substrate.ad_inventory.frame_attention import (
    FrameAttentionSample,
    FrameSecond,
    WindowFrameBatch,
)
from substrate.ad_inventory.frame_attention_accrual import (
    accrue_window,
    replay,
)
from substrate.anti_gaming.frame_ivt import REASON_DUPLICATE_INDEX

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
    tmpdir = tempfile.mkdtemp(prefix="antiek-frame-filter-writer-")
    c = connect_write(os.path.join(tmpdir, "test.duckdb"), purpose="filter_writer_test")
    c.execute(_IP_HOLDERS_DDL)
    yield c
    c.close()


def _sec(index, asset_id="pd-a"):
    return FrameSecond(
        second_index=index,
        lens="read",
        samples=(FrameAttentionSample(
            asset_id=asset_id, viewport_area_fraction=0.6, prominence=0.7,
            focused_dwell_ms=800, content_class="public_domain",
        ),),
    )


def _batch(seconds, *, window_id="win:read:w", cents=1000):
    return WindowFrameBatch(
        window_id=window_id, seconds=tuple(seconds), ad_value_usd_cents=cents,
    )


def test_reordered_batch_replay_matches_accrual(con):
    """BLOCKING #1 regression: the filter is order-sensitive, so the input
    snapshot must preserve second ORDER. An out-of-order batch (its middle
    seconds regress) is accrued one way; replay MUST reproduce that exact
    accrual — not re-sort the seconds into a clean, differently-filtered batch.
    Pre-fix _batch_inputs sorted by second_index and replay diverged."""
    # Indices [2, 0, 1]: position 1 (index 0) regresses below position 0 (index
    # 2) → filtered; the accrual is over the surviving positions.
    result = accrue_window(con, _batch([_sec(2, "pd-a"), _sec(0, "pd-b"), _sec(1, "pd-c")]))
    rep = replay(con, result.batch_ref)
    assert rep.identical, (rep.recorded, rep.recomputed)


def test_block_window_return_and_reload_carry_verdict(con):
    """BLOCKING #2 regression: accrue_window's return AND its idempotent reload
    must carry the real fraud_verdict + exclusion counts — not the pass/empty
    defaults. A BLOCK window ([0,0,0,0]) must report block on both paths."""
    batch = _batch([_sec(0), _sec(0), _sec(0), _sec(0)])
    fresh = accrue_window(con, batch)
    assert fresh.fraud_verdict == "block"
    assert fresh.house.amount_cents == 1000  # whole value to house
    assert fresh.asset_lines == ()

    # Idempotent re-post → reload from DB → SAME verdict (pre-fix reloaded "pass").
    reloaded = accrue_window(con, batch)
    assert reloaded.fraud_verdict == "block"
    assert reloaded.house.amount_cents == 1000


def test_partial_filter_return_carries_exclusion_counts(con):
    """A PASS window with one filtered second reports the exclusion count on
    both the fresh return and the reload."""
    batch = _batch([_sec(0), _sec(1), _sec(2), _sec(1)])  # last = duplicate
    fresh = accrue_window(con, batch)
    assert fresh.fraud_verdict == "pass"
    assert fresh.excluded_second_counts == ((REASON_DUPLICATE_INDEX, 1),)
    reloaded = accrue_window(con, batch)
    assert reloaded.excluded_second_counts == ((REASON_DUPLICATE_INDEX, 1),)
    assert reloaded.reconciles()
