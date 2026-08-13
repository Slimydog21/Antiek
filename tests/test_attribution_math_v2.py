"""AFA-S5 — published split order (attribution-math-v2).

Stage-by-stage unit tests + version stamp + e2e accrual wire-through.
Integer equalities only; no tolerances anywhere in money math.
"""

from __future__ import annotations

import os
import tempfile
from decimal import Decimal

import pytest

from runtime.db_lock import connect_write
from substrate import ip_holders
from substrate.ad_inventory.attribution_math import (
    ATTRIBUTION_MATH_VERSION,
    REASON_EMPTY_POOL,
    REASON_INELIGIBLE_CONTENT,
    REASON_NO_HOLDER,
    REASON_PLATFORM_CUT,
    REASON_T1_GATE,
    STAGE_VERSIONS,
    AssetCandidate,
    CarveOutEntry,
    PipelineParams,
    composed_version_id,
    params_fingerprint,
    run_pipeline,
    stage_carve_outs,
    stage_composition,
    stage_filtered_weights,
    stage_holder_gates,
    stage_platform_cut,
    stage_residuals,
)
from substrate.ad_inventory.frame_attention import (
    FrameAttentionSample,
    FrameSecond,
    WindowFrameBatch,
)
from substrate.ad_inventory.frame_attention_accrual import (
    accrue_window,
    aggregate_window,
)
from substrate.ad_inventory.payout import CREATOR_REV_SHARE, PLATFORM_CUT
from substrate.constants import UNATTRIBUTED_RIGHTS_BUCKET
from substrate.payouts.split import SPLIT_POLICY_VERSION

# ---------------------------------------------------------------------------
# Stage 1 — carve-outs
# ---------------------------------------------------------------------------


def test_carve_outs_empty_registry_is_passthrough():
    remaining, lines, trace = stage_carve_outs(1000, ())
    assert remaining == 1000
    assert lines == []
    assert trace.conserves()
    assert trace.routed_cents == 0


def test_carve_outs_deducts_fraction_to_the_cent():
    entries = [
        CarveOutEntry(document_id="doc-a", fraction=0.10, payee_ref="label:sony"),
    ]
    remaining, lines, trace = stage_carve_outs(1000, entries)
    assert trace.conserves()
    assert remaining + sum(line.amount_cents for line in lines) == 1000
    assert sum(line.amount_cents for line in lines) == 100  # 10% of 1000
    assert lines[0].payee_ref == "label:sony"
    assert lines[0].kind == "carve_out"


def test_carve_outs_precedence_before_platform_cut():
    """Carve-outs are stage 1: the 70/30 cut applies to the POST-carve pool.

    Counterfactual (carve after cut) would take 30% of 1000 = 300 platform,
    then carve 10% of remaining creator — different numbers. Shipped order:
    carve 100 first, then 70/30 of 900 → creator 630, platform 270.
    """
    result = run_pipeline(
        1000,
        candidates=[
            AssetCandidate(
                asset_id="a", weight=1.0, content_class="public_domain",
                ip_holder_id="h1",
            ),
        ],
        carve_outs=[
            CarveOutEntry(document_id="doc-a", fraction=0.10, payee_ref="label:x"),
        ],
    )
    assert result.conserves()
    assert result.carve_out_cents == 100
    assert result.creator_pool_cents == 630  # int(900 * 0.70)
    assert result.platform_cut_cents == 270  # 900 - 630
    # Counterfactual wrong number: platform cut of full 1000 would be 300.
    assert result.platform_cut_cents != 300


def test_carve_outs_cannot_exceed_window():
    entries = [
        CarveOutEntry(document_id="d1", fraction=0.8, payee_ref="p1"),
        CarveOutEntry(document_id="d2", fraction=0.8, payee_ref="p2"),
    ]
    remaining, lines, trace = stage_carve_outs(1000, entries)
    assert trace.conserves()
    assert remaining == 0
    assert sum(line.amount_cents for line in lines) == 1000


# ---------------------------------------------------------------------------
# Stage 2 — 70/30 platform cut
# ---------------------------------------------------------------------------


def test_platform_cut_70_30_conservation():
    creator, platform, lines, trace = stage_platform_cut(1000)
    assert creator == 700
    assert platform == 300
    assert creator + platform == 1000
    assert trace.conserves()
    assert lines[0].reason == REASON_PLATFORM_CUT
    assert lines[0].payee_ref == "__platform__"


def test_platform_cut_reads_payout_constants():
    """The ratio is the payout.py constant, never a local hardcode."""
    assert Decimal("0.70") == CREATOR_REV_SHARE
    assert Decimal("0.30") == PLATFORM_CUT
    creator, platform, _, _ = stage_platform_cut(
        1000, creator_rev_share=CREATOR_REV_SHARE,
    )
    assert creator == int(1000 * float(CREATOR_REV_SHARE))
    assert platform == 1000 - creator


def test_platform_cut_odd_cents_platform_gets_remainder():
    """int(total * 0.70) truncation — platform gets the remainder (matches
    payout.distribute_session_ad_revenue)."""
    creator, platform, _, trace = stage_platform_cut(1)
    assert creator + platform == 1
    assert trace.conserves()
    creator, platform, _, _ = stage_platform_cut(3)
    assert creator + platform == 3
    assert creator == int(3 * 0.70)  # 2
    assert platform == 1


# ---------------------------------------------------------------------------
# Stage 3 — filtered weights
# ---------------------------------------------------------------------------


def test_filtered_weights_renormalize_survivors():
    cands = [
        AssetCandidate(asset_id="a", weight=2.0),
        AssetCandidate(asset_id="b", weight=2.0),
        AssetCandidate(asset_id="c", weight=0.0),  # dropped
    ]
    weights, trace = stage_filtered_weights(cands)
    assert set(weights) == {"a", "b"}
    assert abs(sum(weights.values()) - 1.0) < 1e-12
    assert weights["a"] == pytest.approx(0.5)
    assert trace.detail["n_dropped"] == 1


def test_filtered_weights_empty_survivors():
    weights, trace = stage_filtered_weights([
        AssetCandidate(asset_id="x", weight=0.0),
    ])
    assert weights == {}
    assert trace.detail["n_survivors"] == 0


def test_filtered_weight_exclusion_from_both_sides():
    """An excluded (zero-weight) asset does not appear in numerator OR
    denominator — survivors re-normalize to 1.0 without it."""
    cands = [
        AssetCandidate(asset_id="kept", weight=3.0),
        AssetCandidate(asset_id="filtered", weight=0.0),
    ]
    weights, _ = stage_filtered_weights(cands)
    assert "filtered" not in weights
    assert weights["kept"] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Stage 4 — composition
# ---------------------------------------------------------------------------


def test_composition_identity_share_vector():
    """No synthesis shares → asset is the identity payee unit."""
    cands = [
        AssetCandidate(asset_id="a", weight=0.6),
        AssetCandidate(asset_id="b", weight=0.4),
    ]
    weights, _ = stage_filtered_weights(cands)
    units, residual, trace = stage_composition(700, weights, cands)
    assert trace.conserves()
    assert sum(units.values()) + sum(r.amount_cents for r in residual) == 700
    assert set(units) == {"a", "b"}


def test_composition_expands_synthesis_shares():
    cands = [
        AssetCandidate(
            asset_id="synth",
            weight=1.0,
            synthesis_shares={"c1": 0.5, "c2": 0.5},
        ),
    ]
    weights, _ = stage_filtered_weights(cands)
    units, residual, trace = stage_composition(100, weights, cands)
    assert trace.conserves()
    assert sum(units.values()) == 100
    assert len(units) == 2
    assert all(v == 50 for v in units.values())


# ---------------------------------------------------------------------------
# Stage 5 — rights / T1 / author gates
# ---------------------------------------------------------------------------


def test_holder_gate_ineligible_content_class():
    cands = [
        AssetCandidate(
            asset_id="priv", weight=1.0, content_class="user_owned",
            ip_holder_id="h1",
        ),
    ]
    units = {"priv": 700}
    creators, residuals, trace = stage_holder_gates(units, cands)
    assert trace.conserves()
    assert creators == []
    assert residuals[0].reason == REASON_INELIGIBLE_CONTENT
    assert residuals[0].payee_ref == UNATTRIBUTED_RIGHTS_BUCKET


def test_holder_gate_t1_only_with_license_uri():
    """A CC-BY-NC (T2) license_uri fails the ads_allowed gate."""
    cands = [
        AssetCandidate(
            asset_id="nc",
            weight=1.0,
            content_class="source_declared_open",
            license_uri="https://creativecommons.org/licenses/by-nc/4.0/",
            ip_holder_id="h1",
        ),
    ]
    units = {"nc": 500}
    creators, residuals, trace = stage_holder_gates(units, cands)
    assert trace.conserves()
    assert creators == []
    assert residuals[0].reason == REASON_T1_GATE


def test_holder_gate_t1_cc_by_passes():
    cands = [
        AssetCandidate(
            asset_id="open",
            weight=1.0,
            content_class="source_declared_open",
            license_uri="https://creativecommons.org/licenses/by/4.0/",
            ip_holder_id="h1",
        ),
    ]
    units = {"open": 500}
    creators, residuals, trace = stage_holder_gates(units, cands)
    assert trace.conserves()
    assert residuals == []
    assert creators[0].payee_ref == "h1"
    assert creators[0].amount_cents == 500


def test_holder_gate_author_split_equal_v1():
    cands = [
        AssetCandidate(
            asset_id="paper",
            weight=1.0,
            content_class="public_domain",
            ip_holder_id="h1",
            document_id="doc-1",
            n_authors=3,
        ),
    ]
    units = {"paper": 100}
    creators, residuals, trace = stage_holder_gates(units, cands)
    assert trace.conserves()
    assert residuals == []
    amounts = sorted(c.amount_cents for c in creators)
    assert amounts == [33, 33, 34] or amounts == [33, 34, 33] or sum(amounts) == 100
    assert sum(c.amount_cents for c in creators) == 100
    assert all(c.author_position is not None for c in creators)
    assert all(c.reason == SPLIT_POLICY_VERSION for c in creators)


def test_holder_gate_no_holder_routes_unattributed():
    cands = [
        AssetCandidate(
            asset_id="orphan", weight=1.0, content_class="public_domain",
            ip_holder_id=None,
        ),
    ]
    units = {"orphan": 200}
    creators, residuals, trace = stage_holder_gates(units, cands)
    assert trace.conserves()
    assert creators == []
    assert residuals[0].reason == REASON_NO_HOLDER


# ---------------------------------------------------------------------------
# Stage 6 — UNATTRIBUTED bucket
# ---------------------------------------------------------------------------


def test_residuals_coalesce_by_reason():
    from substrate.ad_inventory.attribution_math import PayeeLine

    residual_in = [
        PayeeLine(
            payee_ref=UNATTRIBUTED_RIGHTS_BUCKET, amount_cents=10,
            kind="unattributed", reason=REASON_NO_HOLDER, asset_id="a",
        ),
        PayeeLine(
            payee_ref=UNATTRIBUTED_RIGHTS_BUCKET, amount_cents=15,
            kind="unattributed", reason=REASON_NO_HOLDER, asset_id="b",
        ),
        PayeeLine(
            payee_ref=UNATTRIBUTED_RIGHTS_BUCKET, amount_cents=7,
            kind="unattributed", reason=REASON_T1_GATE, asset_id="c",
        ),
    ]
    lines, trace = stage_residuals(residual_in)
    assert sum(line.amount_cents for line in lines) == 32
    by_reason = {line.reason: line.amount_cents for line in lines}
    assert by_reason[REASON_NO_HOLDER] == 25
    assert by_reason[REASON_T1_GATE] == 7


def test_residuals_empty_pool():
    lines, trace = stage_residuals([], empty_pool_cents=700)
    assert len(lines) == 1
    assert lines[0].amount_cents == 700
    assert lines[0].reason == REASON_EMPTY_POOL
    assert lines[0].payee_ref == UNATTRIBUTED_RIGHTS_BUCKET


# ---------------------------------------------------------------------------
# End-to-end pipeline conservation
# ---------------------------------------------------------------------------


def test_run_pipeline_exact_cent_conservation():
    result = run_pipeline(
        1000,
        candidates=[
            AssetCandidate(
                asset_id="a", weight=0.6, content_class="public_domain",
                ip_holder_id="h-a",
            ),
            AssetCandidate(
                asset_id="b", weight=0.4, content_class="public_domain",
                ip_holder_id="h-b",
            ),
        ],
    )
    assert result.conserves()
    assert result.total_payee_cents() == 1000
    assert result.attribution_math_version == "attribution-math-v2"
    assert result.creator_pool_cents == 700
    assert result.platform_cut_cents == 300
    creator = sum(p.amount_cents for p in result.payee_lines if p.kind == "creator")
    assert creator == 700
    assert all(t.conserves() for t in result.stage_traces)


def test_run_pipeline_with_house_seconds():
    """House-seconds are not double-cut: 70/30 applies only to the eligible pool."""
    result = run_pipeline(
        1000,
        candidates=[
            AssetCandidate(
                asset_id="a", weight=1.0, content_class="public_domain",
                ip_holder_id="h1",
            ),
        ],
        house_seconds_cents=200,
    )
    assert result.conserves()
    assert result.total_payee_cents() == 1000
    # 70/30 of 800 eligible → creator 560, platform 240; + 200 house seconds.
    assert result.creator_pool_cents == 560
    assert result.platform_cut_cents == 240
    house = sum(
        p.amount_cents for p in result.payee_lines if p.kind in ("platform", "house")
    )
    assert house == 440  # 240 + 200


def test_run_pipeline_fully_filtered_routes_empty_pool():
    result = run_pipeline(
        500,
        candidates=[],  # no survivors
    )
    assert result.conserves()
    assert result.creator_pool_cents == 350  # int(500*0.70)
    # Empty weights → creator pool lands in unattributed (empty_pool).
    assert result.unattributed_cents == 350
    assert result.platform_cut_cents == 150


def test_run_pipeline_randomized_conservation():
    """Property: random windows always conserve exactly."""
    import random
    rng = random.Random(42)
    for _ in range(50):
        total = rng.randint(0, 10_000)
        n = rng.randint(0, 5)
        cands = [
            AssetCandidate(
                asset_id=f"a{i}",
                weight=rng.random() + 0.01,
                content_class="public_domain",
                ip_holder_id=f"h{i}" if rng.random() > 0.2 else None,
            )
            for i in range(n)
        ]
        house = rng.randint(0, total) if total else 0
        result = run_pipeline(total, candidates=cands, house_seconds_cents=house)
        assert result.conserves(), result
        assert result.total_payee_cents() == total


# ---------------------------------------------------------------------------
# Version id
# ---------------------------------------------------------------------------


def test_attribution_math_version_constant():
    assert ATTRIBUTION_MATH_VERSION == "attribution-math-v2"
    assert composed_version_id() == "attribution-math-v2"


def test_version_completeness_param_mutation_changes_fingerprint():
    """Mutate any stage param → fingerprint must differ (silent history
    rewrite is the defect this catches)."""
    base = PipelineParams()
    fp0 = params_fingerprint(base)

    mutated_share = PipelineParams(creator_rev_share=Decimal("0.80"))
    assert params_fingerprint(mutated_share) != fp0

    mutated_scope = PipelineParams(pool_scope="per-reader")
    assert params_fingerprint(mutated_scope) != fp0

    mutated_stages = PipelineParams(
        stage_versions={**STAGE_VERSIONS, "platform_cut": "platform-cut-80-20-v1"},
    )
    assert params_fingerprint(mutated_stages) != fp0

    mutated_split = PipelineParams(split_policy_version="author-split-first-v1")
    assert params_fingerprint(mutated_split) != fp0


# ---------------------------------------------------------------------------
# Accrual wire-through (frame_attention_accrual calls the math)
# ---------------------------------------------------------------------------


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
    tmpdir = tempfile.mkdtemp(prefix="antiek-attr-math-v2-")
    db_path = os.path.join(tmpdir, "test.duckdb")
    c = connect_write(db_path, purpose="attr_math_v2_test")
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


def test_aggregate_window_applies_70_30_and_stamps_version():
    samples = (
        _sample("doc-a", area=0.5, prom=0.5, dwell=500),
        _sample("doc-b", area=0.5, prom=0.5, dwell=500),
    )
    batch = _window("w-split", 10, samples, 1000)
    result = aggregate_window(batch)
    assert result.reconciles()
    assert result.attribution_math_version == ATTRIBUTION_MATH_VERSION
    # Full eligible window (no house seconds) → creator pool = 70% of 1000.
    assert result.creator_pool_cents == 700
    assert result.platform_cut_cents == 300
    assert sum(line.amount_cents for line in result.asset_lines) == 700
    assert result.house.amount_cents == 300
    assert "platform_cut_30" in result.house.reason


def test_accrue_window_stamps_version_and_conserves(con):
    """E2E through accrue_window with a monkeypatched nonzero server-minted
    value (here: the batch's ad_value_usd_cents field, the server-minted
    surface after AFA-S1)."""
    h1 = ip_holders.create_pre_onboarded(con, display_name="Holder A")
    h2 = ip_holders.create_pre_onboarded(con, display_name="Holder B")
    samples = (
        _sample("doc-a", area=0.5, prom=0.5, dwell=500),
        _sample("doc-b", area=0.5, prom=0.5, dwell=500),
    )
    # Nonzero server-minted window value (mirrors e2e harness).
    batch = _window("w-e2e", 4, samples, 800)
    result = accrue_window(
        con, batch, asset_to_ip_holder={"doc-a": h1, "doc-b": h2},
    )
    assert result.reconciles()
    assert result.attribution_math_version == "attribution-math-v2"
    assert result.creator_pool_cents == 560  # int(800 * 0.70)
    assert result.platform_cut_cents == 240

    # Version stamped on persisted rows.
    rows = con.execute(
        "SELECT attribution_math_version, amount_cents FROM frame_attention_accruals "
        "WHERE window_id = 'w-e2e'"
    ).fetchall()
    assert rows
    assert all(r[0] == "attribution-math-v2" for r in rows)
    assert sum(r[1] for r in rows) == 560

    hrow = con.execute(
        "SELECT attribution_math_version, amount_cents, reason FROM house_seconds "
        "WHERE window_id = 'w-e2e'"
    ).fetchone()
    assert hrow[0] == "attribution-math-v2"
    assert hrow[1] == 240
    assert "platform_cut_30" in hrow[2]

    # Escrow received creator-pool share only (not the platform cut).
    bal1 = ip_holders.get(con, h1).escrow_balance_usd
    bal2 = ip_holders.get(con, h2).escrow_balance_usd
    assert bal1 + bal2 == Decimal("5.600000")  # 560c


def test_accrue_window_idempotent_under_v2(con):
    h = ip_holders.create_pre_onboarded(con, display_name="Idem")
    batch = _window("w-idem-v2", 5, (_sample("doc-a"),), 500)
    r1 = accrue_window(con, batch, asset_to_ip_holder={"doc-a": h})
    r2 = accrue_window(con, batch, asset_to_ip_holder={"doc-a": h})
    assert r1.batch_ref == r2.batch_ref
    assert ip_holders.get(con, h).escrow_balance_usd == (
        Decimal(r1.creator_pool_cents) / Decimal(100)
    ).quantize(Decimal("0.000001"))


def test_private_asset_still_excluded_from_creator_pool():
    samples = (
        _sample("doc-a", area=0.7, prom=0.9, dwell=950),
        _sample("priv", cc="user_owned"),
    )
    batch = _window("w-priv", 10, samples, 1000)
    result = aggregate_window(batch)
    assert result.reconciles()
    assert "priv" not in {line.asset_id for line in result.asset_lines}
    # Only doc-a is eligible → its pre-cut amount is 1000, post-cut 700.
    assert sum(line.amount_cents for line in result.asset_lines) == 700
