"""SPR-05 M6 — conservation + load characterization.

Property tests over random frames: per-second eligible weights sum to 1 (or
house); window reconciliation Σ contributor + Σ house == total ad value EXACTLY.
Plus the enumerated edge-case fixture and a read-only load-characterization note.

LOAD CHARACTERIZATION (read-only — flagged for the SPR-11 Hetzner load check):
Under the batching rule, ONE window flush writes at most
(#eligible-assets-in-window + 1 house row) accrual rows — independent of how many
SECONDS the window lasted. Worst realistic Read window: ~600s (10 min) showing
~8 distinct eligible assets ⇒ ≤ 9 rows per window. If 100 concurrent windows each
flush once per 10 min, that is ≤ 900 rows / 600 s ≈ 1.5 INSERTs/s funneled
through the single DuckDB writer — trivially within a serialized writer's
headroom. Contrast the NAIVE per-second-per-asset shape: 600 × 8 × 100 / 600 ≈
800 INSERTs/s, which WOULD pressure the single writer. The aggregation is what
makes the per-second economic unit affordable on one writer. SPR-11 should
confirm the real flush cadence + concurrent-window count against this estimate.

A scratch proof that the conservation gate BITES (a deliberate weighting tweak
breaks it) was run during development and reverted; see the handoff packet's
"scratch proof" note. It is NOT left in the tree.
"""

from __future__ import annotations

import json
import os
import random
import tempfile
from decimal import Decimal
from pathlib import Path

import pytest

from runtime.db_lock import connect_write
from substrate.ad_inventory.frame_attention import (
    FrameAttentionSample,
    FrameSecond,
    WindowFrameBatch,
    weigh_second,
)
from substrate.ad_inventory.frame_attention_accrual import (
    accrue_window,
    aggregate_window,
    window_reconciliation,
)

_FIXTURE = Path(__file__).parent / "fixtures" / "frame_attention" / "edge_cases.json"

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

_ELIGIBLE_CLASSES = [
    "public_domain", "opt_in_licensed", "source_declared_open",
    "user_public_contribution", "restricted_pending_opt_in",
]
_INELIGIBLE_CLASSES = ["user_owned", None, "garbage_class"]


@pytest.fixture
def con():
    tmpdir = tempfile.mkdtemp(prefix="antiek-frame-cons-")
    db_path = os.path.join(tmpdir, "test.duckdb")
    c = connect_write(db_path, purpose="frame_conservation_test")
    c.execute(_IP_HOLDERS_DDL)
    yield c
    c.close()


def _random_second(rng, idx):
    n = rng.randint(0, 5)
    samples = []
    for k in range(n):
        eligible = rng.random() < 0.6
        cc = rng.choice(_ELIGIBLE_CLASSES if eligible else _INELIGIBLE_CLASSES)
        samples.append(FrameAttentionSample(
            asset_id=f"doc-{rng.randint(0, 6)}-{k}",
            viewport_area_fraction=round(rng.random(), 4),
            prominence=round(rng.random(), 4),
            focused_dwell_ms=rng.randint(0, 1000),
            content_class=cc,
            chunk_id=(None if rng.random() < 0.2 else f"ch-{k}"),
        ))
    return FrameSecond(second_index=idx, lens=rng.choice(
        ["read", "research", "write", "speak"]), samples=tuple(samples))


def test_every_second_sums_to_one_or_house():
    rng = random.Random(20260529)
    for _ in range(2000):
        sec = _random_second(rng, 0)
        w = weigh_second(sec)
        total = sum((aw.weight for aw in w.eligible_weights), Decimal(0))
        if w.is_house_second:
            assert total == Decimal(0)
            assert w.eligible_weights == ()
        else:
            assert total == Decimal(1), (
                f"eligible weights summed to {total}, not 1, for {sec}"
            )


def test_random_windows_reconcile_in_memory():
    """Pure aggregation conserves the window to the cent across random frames."""
    rng = random.Random(424242)
    for w_i in range(500):
        n_sec = rng.randint(0, 30)
        seconds = tuple(_random_second(rng, i) for i in range(n_sec))
        ad_value = rng.randint(0, 100000)
        batch = WindowFrameBatch(
            window_id=f"w-{w_i}", seconds=seconds, ad_value_usd_cents=ad_value,
        )
        result = aggregate_window(batch)
        recon = sum(line.amount_cents for line in result.asset_lines) + result.house.amount_cents
        assert recon == ad_value, (
            f"window {w_i}: Σasset+house={recon} != ad_value={ad_value}"
        )
        assert result.reconciles()


def test_random_windows_reconcile_persisted(con):
    """Persisted-then-queried reconciliation matches the total exactly."""
    rng = random.Random(7)
    for w_i in range(50):
        n_sec = rng.randint(0, 20)
        seconds = tuple(_random_second(rng, i) for i in range(n_sec))
        ad_value = rng.randint(0, 50000)
        wid = f"wp-{w_i}"
        accrue_window(con, WindowFrameBatch(
            window_id=wid, seconds=seconds, ad_value_usd_cents=ad_value,
        ))
        rec = window_reconciliation(con, wid)
        assert rec["total_cents"] == ad_value
        assert rec["contributor_cents"] + rec["house_cents"] == ad_value


def test_no_negative_or_invented_cents():
    """No accrual line is negative; nothing is invented above the total."""
    rng = random.Random(99)
    for _ in range(300):
        n_sec = rng.randint(0, 15)
        seconds = tuple(_random_second(rng, i) for i in range(n_sec))
        ad_value = rng.randint(0, 10000)
        result = aggregate_window(WindowFrameBatch(
            window_id="w", seconds=seconds, ad_value_usd_cents=ad_value,
        ))
        for line in result.asset_lines:
            assert line.amount_cents >= 0
        assert result.house.amount_cents >= 0


# ---------------------------------------------------------------------------
# Enumerated edge cases (fixture-driven)
# ---------------------------------------------------------------------------


def _batch_from_fixture(window):
    seconds = tuple(
        FrameSecond(
            second_index=s["second_index"],
            lens=s["lens"],
            samples=tuple(
                FrameAttentionSample(
                    asset_id=sm["asset_id"],
                    viewport_area_fraction=sm["viewport_area_fraction"],
                    prominence=sm["prominence"],
                    focused_dwell_ms=sm["focused_dwell_ms"],
                    content_class=sm["content_class"],
                    chunk_id=sm["chunk_id"],
                )
                for sm in s["samples"]
            ),
        )
        for s in window["seconds"]
    )
    return WindowFrameBatch(
        window_id=window["name"], seconds=seconds,
        ad_value_usd_cents=window["ad_value_usd_cents"],
    )


def test_edge_case_fixtures_reconcile():
    data = json.loads(_FIXTURE.read_text())
    for window in data["windows"]:
        batch = _batch_from_fixture(window)
        result = aggregate_window(batch)
        assert result.reconciles(), f"{window['name']} did not reconcile"
        assert result.house.amount_cents == window["expect_house_cents"], (
            f"{window['name']}: house cents mismatch"
        )
        assert sorted(line.asset_id for line in result.asset_lines) == \
            sorted(window["expect_asset_ids"]), (
            f"{window['name']}: eligible asset set mismatch"
        )


def test_fixture_covers_required_edge_cases():
    """The fixture must enumerate: zero eligible, single eligible, ties, asset
    with no chunk, ineligible-only."""
    data = json.loads(_FIXTURE.read_text())
    names = {w["name"] for w in data["windows"]}
    assert "zero_eligible_all_private" in names
    assert "single_eligible" in names
    assert "ties_three_identical" in names
    assert "eligible_with_no_chunk" in names
    assert "ineligible_only_unknown_class" in names
