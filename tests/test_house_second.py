"""SPR-05 M5 — the house-second rule.

When a second's frame has NO eligible asset (Speak with no IP context, a frame
of only private uploads, an empty window), the second's ad value is a HOUSE
SECOND — the platform pockets it, nothing accrues to any contributor. House
seconds are recorded EXPLICITLY (never silently dropped) so the window
reconciles: Σ contributor + Σ house = total.
"""

from __future__ import annotations

import os
import tempfile
from decimal import Decimal

import pytest

from runtime.db_lock import connect_write
from substrate import ip_holders
from substrate.ad_inventory.frame_attention import (
    FrameAttentionSample,
    FrameSecond,
    WindowFrameBatch,
)
from substrate.ad_inventory.frame_attention_accrual import (
    accrue_window,
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
    tmpdir = tempfile.mkdtemp(prefix="antiek-house-")
    db_path = os.path.join(tmpdir, "test.duckdb")
    c = connect_write(db_path, purpose="house_second_test")
    c.execute(_IP_HOLDERS_DDL)
    yield c
    c.close()


def _sample(asset_id, *, cc="public_domain"):
    return FrameAttentionSample(
        asset_id=asset_id, viewport_area_fraction=0.5, prominence=0.5,
        focused_dwell_ms=500, content_class=cc,
    )


def _window(window_id, seconds, ad_value_cents):
    return WindowFrameBatch(
        window_id=window_id, seconds=tuple(seconds), ad_value_usd_cents=ad_value_cents,
    )


def test_zero_eligible_frame_is_all_house(con):
    """Every second has only private uploads → the whole window is house; no
    contributor accrual; the platform pockets the full ad value."""
    secs = [
        FrameSecond(i, "speak", (_sample("priv", cc="user_owned"),))
        for i in range(10)
    ]
    result = accrue_window(con, _window("w-house", secs, 1000))
    assert result.asset_lines == ()
    assert result.house.amount_cents == 1000
    assert result.house.n_seconds == 10
    assert result.reconciles()


def test_private_uploads_only_frame_is_house(con):
    """Acceptance: a private-uploads-only frame is a house second (tested)."""
    secs = [
        FrameSecond(0, "read", (
            _sample("p1", cc="user_owned"), _sample("p2", cc="user_owned"),
        )),
    ]
    result = accrue_window(con, _window("w-priv", secs, 100))
    assert result.house.amount_cents == 100
    assert "no_eligible_asset_in_frame" in result.house.reason


def test_empty_window_is_house(con):
    secs = [FrameSecond(i, "write", ()) for i in range(5)]
    result = accrue_window(con, _window("w-empty", secs, 500))
    assert result.house.amount_cents == 500
    assert "empty_or_no_assets_in_frame" in result.house.reason


def test_zero_second_window_is_house(con):
    """A window with no seconds at all: entire ad value is house, recorded."""
    result = accrue_window(con, _window("w-none", [], 250))
    assert result.house.amount_cents == 250
    assert result.house.reason == "empty_window_no_seconds"
    assert result.reconciles()


def test_house_seconds_persisted_explicitly(con):
    secs = [FrameSecond(0, "speak", (_sample("priv", cc="user_owned"),))]
    accrue_window(con, _window("w-explicit", secs, 100))
    row = con.execute(
        "SELECT window_id, n_seconds, amount_cents, reason FROM house_seconds "
        "WHERE window_id = 'w-explicit'"
    ).fetchone()
    assert row is not None  # never silently dropped
    assert row[2] == 100


def test_nothing_accrues_to_contributors_on_house_window(con):
    h = ip_holders.create_pre_onboarded(con, display_name="Bystander Press")
    secs = [FrameSecond(0, "speak", (_sample("priv", cc="user_owned"),))]
    # even though we pass a mapping, the asset is ineligible so it earns nothing
    accrue_window(con, _window("w-bystander", secs, 100),
                  asset_to_ip_holder={"priv": h})
    assert ip_holders.get(con, h).escrow_balance_usd == Decimal(0)


def test_mixed_window_splits_eligible_and_house(con):
    """Some seconds eligible, some house — both tallies present, reconciles."""
    h = ip_holders.create_pre_onboarded(con, display_name="Mixed Press")
    secs = [
        FrameSecond(0, "read", (_sample("doc-a"),)),               # eligible
        FrameSecond(1, "read", (_sample("doc-a"),)),               # eligible
        FrameSecond(2, "read", (_sample("priv", cc="user_owned"),)),  # house
        FrameSecond(3, "read", ()),                                # house
    ]
    result = accrue_window(con, _window("w-mixed", secs, 400),
                           asset_to_ip_holder={"doc-a": h})
    assert result.house.n_seconds == 2
    assert len(result.asset_lines) == 1
    # 400c / 4s = 100c/sec; 2 eligible secs → 200c eligible; AFA-S5 70/30 at
    # pool boundary → 140c to doc-a, 60c platform cut into house; 2 house secs
    # → 200c house. Total house = 260c. Conservation exact.
    assert result.asset_lines[0].amount_cents == 140
    assert result.house.amount_cents == 260
    assert result.reconciles()
    rec = window_reconciliation(con, "w-mixed")
    assert rec["contributor_cents"] == 140
    assert rec["house_cents"] == 260
    assert rec["total_cents"] == 400
