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


# Pre-M5 schema (house_seconds WITHOUT the AFA-S2 audit columns) — what a DB
# created by M5a would have. The migration must ADD the columns on DuckDB.
_PRE_M5_HOUSE_DDL = """
CREATE TABLE IF NOT EXISTS house_seconds (
    house_id           TEXT PRIMARY KEY,
    batch_ref          TEXT NOT NULL,
    window_id          TEXT NOT NULL,
    n_seconds          INTEGER NOT NULL DEFAULT 0,
    amount_cents       INTEGER NOT NULL DEFAULT 0,
    reason             TEXT NOT NULL,
    telemetry_version  TEXT NOT NULL,
    weighting_version  TEXT NOT NULL,
    inputs_json        TEXT NOT NULL,
    accrued_at         TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def test_pre_m5_db_migrates_and_accrues(con):
    """Regression (fresh-verifier MAJOR): a house_seconds created before the M5
    audit columns must be MIGRATED by ensure_tables (via nullable ADD COLUMN —
    DuckDB rejects ADD COLUMN with NOT NULL/DEFAULT constraints), so accrue_window
    does not raise BinderException on its INSERT. Pre-fix this failed silently
    (the constrained ALTER raised and was swallowed → missing column → Binder
    error)."""
    con.execute(_PRE_M5_HOUSE_DDL)  # old schema exists BEFORE accrue_window
    result = accrue_window(con, _batch([_sec(0), _sec(1)]))  # ensure_tables migrates
    assert result.reconciles()
    assert result.fraud_verdict == "pass"
    # The columns are now present and populated on the fresh row.
    row = con.execute(
        "SELECT fraud_verdict, excluded_counts_json FROM house_seconds "
        "WHERE batch_ref = ?",
        [result.batch_ref],
    ).fetchone()
    assert row[0] == "pass"
    assert row[1] == "[]"
# ── AFA-S2 (W2-S2): per-(user, asset, day) dwell saturation cap ─────────────


def _dwell_batch(dwells, *, window_id, asset_id="pd-a", cents=1000):
    """A clean monotonic window whose per-second dwell is ``dwells`` (each
    second shows the same asset)."""
    return _batch(
        [FrameSecond(
            second_index=i,
            lens="read",
            samples=(FrameAttentionSample(
                asset_id=asset_id, viewport_area_fraction=0.6, prominence=0.7,
                focused_dwell_ms=dwell, content_class="public_domain",
            ),),
        ) for i, dwell in enumerate(dwells)],
        window_id=window_id,
        cents=cents,
    )


def test_dwell_cap_clamps_second_window_and_routes_to_house(con):
    """Two windows for the same (user, asset, day), cap 1500 ms. Window A's
    2000 ms of countable dwell is partially counted (1500) — its 1000 cents are
    scaled to 750, the 250 clamped cents join house. Window B finds the day
    already saturated: NOTHING counts, the whole 1000 cents route to house.
    Conservation stays exact and every clamped ms/cent is reported."""
    cap = 1500
    a = accrue_window(
        con, _dwell_batch([1000, 1000], window_id="win:read:capA"),
        asset_to_ip_holder={"pd-a": None}, owner_user_id="u-1",
        dwell_cap_ms=cap, day_bucket="2026-08-13",
    )
    assert a.reconciles()
    assert a.clamped_dwell_ms == 500
    assert a.clamped_cents == 250
    assert a.asset_lines[0].amount_cents == 750
    assert a.house.amount_cents == 250
    assert "dwell_cap_clamped" in a.house.reason

    b = accrue_window(
        con, _dwell_batch([1000, 1000], window_id="win:read:capB"),
        asset_to_ip_holder={"pd-a": None}, owner_user_id="u-1",
        dwell_cap_ms=cap, day_bucket="2026-08-13",
    )
    assert b.reconciles()
    assert b.clamped_dwell_ms == 2000
    assert b.clamped_cents == 1000
    assert b.asset_lines[0].amount_cents == 0
    assert b.house.amount_cents == 1000


def test_dwell_cap_identity_and_day_scoped(con):
    """The cap keys on (user, asset, day): a DIFFERENT user on the same day, and
    the SAME user on a different day, both start from zero prior — nothing is
    clamped even though user u-1's day is saturated."""
    cap = 1500
    accrue_window(
        con, _dwell_batch([1000, 1000], window_id="win:read:capA"),
        asset_to_ip_holder={"pd-a": None}, owner_user_id="u-1",
        dwell_cap_ms=cap, day_bucket="2026-08-13",
    )
    other_user = accrue_window(
        con, _dwell_batch([1000, 1000], window_id="win:read:capU2"),
        asset_to_ip_holder={"pd-a": None}, owner_user_id="u-2",
        dwell_cap_ms=cap, day_bucket="2026-08-13",
    )
    assert other_user.clamped_dwell_ms == 500  # own prior only
    next_day = accrue_window(
        con, _dwell_batch([1000, 1000], window_id="win:read:capDay2"),
        asset_to_ip_holder={"pd-a": None}, owner_user_id="u-1",
        dwell_cap_ms=cap, day_bucket="2026-08-14",
    )
    assert next_day.clamped_dwell_ms == 500  # fresh day bucket


def test_no_cap_when_undefined(con):
    """dwell_cap_ms=None (the default) means NO cap: nothing is clamped and the
    dwell ledger is untouched — pre-cap callers are unaffected."""
    result = accrue_window(
        con, _dwell_batch([1000, 1000], window_id="win:read:uncapped"),
        asset_to_ip_holder={"pd-a": None}, owner_user_id="u-1",
    )
    assert result.reconciles()
    assert result.clamped_dwell_ms == 0
    assert result.clamped_cents == 0
    assert result.asset_lines[0].amount_cents == 1000
    rows = con.execute("SELECT COUNT(*) FROM frame_daily_dwell").fetchone()
    assert rows[0] == 0


def test_dwell_ledger_rows_carry_prior_and_cap(con):
    """Each dwell ledger row records the PRIOR it was clamped against and the
    cap in force — the replay contract (re-derive the clamp exactly, regardless
    of later windows)."""
    cap = 1500
    accrue_window(
        con, _dwell_batch([1000, 1000], window_id="win:read:capA"),
        asset_to_ip_holder={"pd-a": None}, owner_user_id="u-1",
        dwell_cap_ms=cap, day_bucket="2026-08-13",
    )
    row = con.execute(
        "SELECT owner_user_id, asset_id, day_bucket, incremental_ms, "
        "prior_counted_ms, counted_ms, clamped_ms, clamped_cents, cap_ms "
        "FROM frame_daily_dwell"
    ).fetchone()
    assert row is not None
    assert row[0] == "u-1"
    assert row[1] == "pd-a"
    assert row[2] == "2026-08-13"
    assert int(row[3]) == 2000
    assert int(row[4]) == 0      # first window of the day: prior 0
    assert int(row[5]) == 1500   # counted up to the cap
    assert int(row[6]) == 500    # clamped excess
    assert int(row[7]) == 250    # the excess's cents
    assert int(row[8]) == cap


def test_capped_window_replay_is_identical(con):
    """Replay re-derives the clamp from the dwell ledger's stored prior — a
    capped window must replay IDENTICALLY, not as the uncapped aggregate."""
    cap = 1500
    a = accrue_window(
        con, _dwell_batch([1000, 1000], window_id="win:read:capR"),
        asset_to_ip_holder={"pd-a": None}, owner_user_id="u-1",
        dwell_cap_ms=cap, day_bucket="2026-08-13",
    )
    assert a.clamped_cents > 0
    rep = replay(con, a.batch_ref)
    assert rep.identical, (rep.recorded, rep.recomputed)


def test_uncapped_window_replay_still_identical(con):
    result = accrue_window(
        con, _dwell_batch([1000, 1000], window_id="win:read:noCapR"),
        asset_to_ip_holder={"pd-a": None}, owner_user_id="u-1",
    )
    rep = replay(con, result.batch_ref)
    assert rep.identical, (rep.recorded, rep.recomputed)


def test_clamped_dwell_reported_even_when_window_is_unpriced(con):
    """An unpriced window (0 cents — the production default until SPR-10) must
    still REPORT clamped dwell: the operator sees the cap withheld dwell even
    though 0 cents moved. Conservation is trivial (0 == 0 + 0)."""
    cap = 1500
    a = accrue_window(
        con, _dwell_batch([1000, 1000], window_id="win:read:cap0", cents=0),
        asset_to_ip_holder={"pd-a": None}, owner_user_id="u-1",
        dwell_cap_ms=cap, day_bucket="2026-08-13",
    )
    assert a.clamped_dwell_ms == 500
    assert a.clamped_cents == 0
    assert a.reconciles()
    accrue_window(
        con, _dwell_batch([1000, 1000], window_id="win:read:cap0b", cents=0),
        asset_to_ip_holder={"pd-a": None}, owner_user_id="u-1",
        dwell_cap_ms=cap, day_bucket="2026-08-13",
    )
    b = accrue_window(
        con, _dwell_batch([1000, 1000], window_id="win:read:cap0c", cents=0),
        asset_to_ip_holder={"pd-a": None}, owner_user_id="u-1",
        dwell_cap_ms=cap, day_bucket="2026-08-13",
    )
    assert b.clamped_dwell_ms == 2000  # saturated day, 0 cents
    assert b.clamped_cents == 0
    assert b.reconciles()
