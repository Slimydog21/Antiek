"""SPR-05 M3 — the attention-weighting function.

Real frames pushed through eligibility + weighting (NOT a hardcoded vector that
skips eligibility — that would be a fake gate, rigor #3):

* eligible weights sum to EXACTLY 1.0 (Decimal); house sums to 0;
* ineligible (private-upload-in-frame) get weight 0 and are EXCLUDED from the
  normalization base;
* deterministic / byte-identical on repeat;
* MONOTONIC in each feature holding others fixed (property-tested);
* the explain hook works.
"""

from __future__ import annotations

from decimal import Decimal

from substrate.ad_inventory.frame_attention import (
    FrameAttentionSample,
    FrameSecond,
    explain_second,
    weigh_second,
)


def _sample(asset_id, *, area=0.5, prom=0.5, dwell=500, cc="public_domain", chunk=None):
    return FrameAttentionSample(
        asset_id=asset_id, viewport_area_fraction=area, prominence=prom,
        focused_dwell_ms=dwell, content_class=cc, chunk_id=chunk,
    )


def test_eligible_weights_sum_to_exactly_one_decimal():
    sec = FrameSecond(second_index=0, lens="read", samples=(
        _sample("a", area=0.3, prom=0.2, dwell=400),
        _sample("b", area=0.6, prom=0.9, dwell=900),
        _sample("c", area=0.1, prom=0.5, dwell=100),
    ))
    w = weigh_second(sec)
    assert not w.is_house_second
    total = sum((aw.weight for aw in w.eligible_weights), Decimal(0))
    assert total == Decimal(1), f"eligible weights must sum to exactly 1, got {total}"


def test_house_second_weights_sum_to_zero():
    """A frame of only ineligible assets is a house second: no eligible weights
    (sum 0), flagged is_house_second."""
    sec = FrameSecond(second_index=0, lens="speak", samples=(
        _sample("priv-1", cc="user_owned"),
        _sample("priv-2", cc="user_owned"),
    ))
    w = weigh_second(sec)
    assert w.is_house_second
    assert w.eligible_weights == ()
    total = sum((aw.weight for aw in w.eligible_weights), Decimal(0))
    assert total == Decimal(0)


def test_empty_window_is_house_second():
    w = weigh_second(FrameSecond(second_index=0, lens="write", samples=()))
    assert w.is_house_second
    assert w.eligible_weights == ()


def test_private_upload_in_frame_excluded_from_normalization():
    """Gate 2: a private upload in frame gets weight 0 and is ABSENT from the
    normalization base — the eligible assets still sum to 1 among themselves
    (the private asset did not dilute them)."""
    sec = FrameSecond(second_index=0, lens="read", samples=(
        _sample("pub-a", area=0.5, prom=0.5, dwell=500),
        _sample("priv", area=0.9, prom=1.0, dwell=1000, cc="user_owned"),
        _sample("pub-b", area=0.5, prom=0.5, dwell=500),
    ))
    w = weigh_second(sec)
    eligible_ids = {aw.asset_id for aw in w.eligible_weights}
    assert eligible_ids == {"pub-a", "pub-b"}
    assert "priv" not in eligible_ids
    # the ineligible asset is recorded with a dispute reason, not silently gone
    inelig_ids = {aid for aid, _ in w.ineligible}
    assert inelig_ids == {"priv"}
    # eligible base still sums to exactly 1 (two equal assets → 0.5 each)
    total = sum((aw.weight for aw in w.eligible_weights), Decimal(0))
    assert total == Decimal(1)
    weights = {aw.asset_id: aw.weight for aw in w.eligible_weights}
    assert weights["pub-a"] == weights["pub-b"]


def test_null_and_unknown_content_class_are_ineligible():
    sec = FrameSecond(second_index=0, lens="read", samples=(
        _sample("a", cc="public_domain"),
        _sample("null", cc=None),
        _sample("weird", cc="something_unrecognised"),
    ))
    w = weigh_second(sec)
    assert {aw.asset_id for aw in w.eligible_weights} == {"a"}
    assert {aid for aid, _ in w.ineligible} == {"null", "weird"}


def test_deterministic_byte_identical_on_repeat():
    samples = (
        _sample("z", area=0.7, prom=0.3, dwell=800),
        _sample("a", area=0.2, prom=0.9, dwell=200),
        _sample("m", area=0.5, prom=0.5, dwell=500),
    )
    sec = FrameSecond(second_index=3, lens="research", samples=samples)
    a = weigh_second(sec)
    b = weigh_second(sec)
    assert explain_second(a) == explain_second(b)
    assert [(w.asset_id, w.weight) for w in a.eligible_weights] == \
           [(w.asset_id, w.weight) for w in b.eligible_weights]


def test_sample_order_does_not_change_result():
    """Stable tie-break by asset_id: feeding samples in a different order
    yields identical weights (no float-ordering drift)."""
    s1, s2, s3 = (
        _sample("a", area=0.3, prom=0.4, dwell=300),
        _sample("b", area=0.6, prom=0.2, dwell=900),
        _sample("c", area=0.4, prom=0.8, dwell=500),
    )
    forward = weigh_second(FrameSecond(0, "read", (s1, s2, s3)))
    reverse = weigh_second(FrameSecond(0, "read", (s3, s2, s1)))
    assert {w.asset_id: w.weight for w in forward.eligible_weights} == \
           {w.asset_id: w.weight for w in reverse.eligible_weights}


def test_monotonic_in_area():
    """Holding prominence + dwell fixed, more viewport area ⇒ at least as much
    weight (the asset whose area grew must not lose share)."""
    base = FrameSecond(0, "read", (
        _sample("a", area=0.3, prom=0.5, dwell=500),
        _sample("b", area=0.5, prom=0.5, dwell=500),
    ))
    bigger = FrameSecond(0, "read", (
        _sample("a", area=0.6, prom=0.5, dwell=500),  # area up
        _sample("b", area=0.5, prom=0.5, dwell=500),
    ))
    wa_base = {w.asset_id: w.weight for w in weigh_second(base).eligible_weights}["a"]
    wa_big = {w.asset_id: w.weight for w in weigh_second(bigger).eligible_weights}["a"]
    assert wa_big > wa_base


def test_monotonic_in_prominence():
    base = FrameSecond(0, "read", (
        _sample("a", area=0.5, prom=0.2, dwell=500),
        _sample("b", area=0.5, prom=0.5, dwell=500),
    ))
    bigger = FrameSecond(0, "read", (
        _sample("a", area=0.5, prom=0.9, dwell=500),  # prominence up
        _sample("b", area=0.5, prom=0.5, dwell=500),
    ))
    wa_base = {w.asset_id: w.weight for w in weigh_second(base).eligible_weights}["a"]
    wa_big = {w.asset_id: w.weight for w in weigh_second(bigger).eligible_weights}["a"]
    assert wa_big > wa_base


def test_monotonic_in_dwell():
    base = FrameSecond(0, "read", (
        _sample("a", area=0.5, prom=0.5, dwell=100),
        _sample("b", area=0.5, prom=0.5, dwell=500),
    ))
    bigger = FrameSecond(0, "read", (
        _sample("a", area=0.5, prom=0.5, dwell=900),  # dwell up
        _sample("b", area=0.5, prom=0.5, dwell=500),
    ))
    wa_base = {w.asset_id: w.weight for w in weigh_second(base).eligible_weights}["a"]
    wa_big = {w.asset_id: w.weight for w in weigh_second(bigger).eligible_weights}["a"]
    assert wa_big > wa_base


def test_zero_area_eligible_falls_back_to_equal_split():
    """Eligible assets with zero visible area: documented equal-split tie-break
    so the second is still conserved to 1, never silently dropped."""
    sec = FrameSecond(0, "read", (
        _sample("a", area=0.0, prom=0.5, dwell=500),
        _sample("b", area=0.0, prom=0.9, dwell=900),
    ))
    w = weigh_second(sec)
    assert not w.is_house_second
    total = sum((aw.weight for aw in w.eligible_weights), Decimal(0))
    assert total == Decimal(1)
    weights = {aw.asset_id: aw.weight for aw in w.eligible_weights}
    assert weights["a"] == weights["b"]


def test_single_eligible_gets_full_weight():
    sec = FrameSecond(0, "read", (
        _sample("solo", area=0.4, prom=0.3, dwell=200),
        _sample("priv", cc="user_owned"),
    ))
    w = weigh_second(sec)
    assert len(w.eligible_weights) == 1
    assert w.eligible_weights[0].weight == Decimal(1)


def test_explain_hook_returns_feature_contributions():
    sec = FrameSecond(0, "read", (
        _sample("a", area=0.3, prom=0.4, dwell=300, chunk="ch-a"),
        _sample("priv", cc="user_owned"),
    ))
    exp = explain_second(weigh_second(sec))
    assert exp["lens"] == "read"
    assert exp["is_house_second"] is False
    assert len(exp["eligible"]) == 1
    e = exp["eligible"][0]
    assert e["asset_id"] == "a"
    assert e["chunk_id"] == "ch-a"
    assert e["features"] == {
        "viewport_area_fraction": 0.3, "prominence": 0.4, "focused_dwell_ms": 300,
    }
    assert len(exp["ineligible"]) == 1
    assert exp["ineligible"][0]["asset_id"] == "priv"
    assert "user_owned" in exp["ineligible"][0]["reason"]


def test_golden_weights_pin_the_blend_math():
    """GOLDEN / mutation gate (rigor #3, M6 acceptance criterion).

    Conservation tests cannot detect a blend-coefficient change: ANY blend
    normalizes to sum 1, so doubling prominence's influence shifts every
    publisher's per-second share while leaving the sum invariant. This test
    pins the EXACT normalized weights for a fixed asymmetric three-asset
    second, frozen as literals. A change to the blend in ``_raw_weight`` (a
    new term, a different coefficient, a different tie-break) moves these
    values and trips this test — and MUST be accompanied by a
    ``FRAME_WEIGHTING_VERSION`` bump, since a moved payout split is a disputed
    payout split. Snapshot minted from the v1 blend
    ``area * (1 + prominence) * (1 + dwell_ms/1000)``.

    Verified to bite: the mutation ``(1 + 2*prominence)`` yields
    a=0.147 b=0.798 c=0.055 — distinct from the golden below while the sum
    stays exactly 1, which the conservation suite alone would wave through.
    """
    sec = FrameSecond(second_index=0, lens="read", samples=(
        _sample("a", area=0.3, prom=0.2, dwell=400, chunk="ch-a"),
        _sample("b", area=0.6, prom=0.9, dwell=900, chunk="ch-b"),
        _sample("c", area=0.1, prom=0.5, dwell=100, chunk="ch-c"),
    ))
    w = weigh_second(sec)
    weights = {aw.asset_id: aw.weight for aw in w.eligible_weights}
    assert weights == {
        "a": Decimal("0.177777778"),
        "b": Decimal("0.764021164"),
        "c": Decimal("0.058201058"),
    }
    # The split is genuinely asymmetric (not an equal third) — the golden is
    # pinning real blend output, not a degenerate symmetric case.
    assert weights["b"] > weights["a"] > weights["c"]
    # Still conserved (the golden literals were minted by the conserving path).
    assert sum(weights.values()) == Decimal(1)
    # The version stamp travels with the weighting so a dispute can isolate a
    # changed split. It is frame-weight-v3 as of AFA-S2 W2-S2: the blend math
    # here is UNCHANGED (the golden literals above are identical), but the bump
    # marks the era in which aggregate_window runs the anti-gaming filter before
    # apportioning AND REVIEW windows are held + the dwell saturation cap can
    # reroute cents — payout-affecting changes to WHICH seconds contribute.
    assert w.weighting_version == "frame-weight-v3"


def test_ties_resolve_deterministically():
    """Two assets with identical features get identical weight (no arbitrary
    winner from float ordering)."""
    sec = FrameSecond(0, "read", (
        _sample("a", area=0.5, prom=0.5, dwell=500),
        _sample("b", area=0.5, prom=0.5, dwell=500),
        _sample("c", area=0.5, prom=0.5, dwell=500),
    ))
    w = weigh_second(sec)
    # 1/3 each, conserved by largest-remainder to sum exactly to 1.
    total = sum((aw.weight for aw in w.eligible_weights), Decimal(0))
    assert total == Decimal(1)
    # weights differ by at most one nano-unit (the remainder cent of weight)
    vals = sorted(aw.weight for aw in w.eligible_weights)
    assert vals[-1] - vals[0] <= Decimal("0.000000001")
