"""Tests for the pure ablation primitive (substrate/eval/ablation.py).

Covers all three verdicts, both noise sources + the precedence rule, the
direction-reversal flag, the metric-identity guard, determinism (purity),
the noise-floor honesty guard, strict YAML loaders, and CLI exit codes.
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest
import yaml

from substrate.constants import (
    ABLATION_INCONCLUSIVE_NOISE_FLOOR,
    ANTIEK_PARAM_VERSION,
)
from substrate.eval.ablation import (
    FACTOR_RELATED,
    INCONCLUSIVE,
    NOISE,
    AblationHypothesis,
    Measurement,
    load_hypothesis,
    load_measurements,
    run_ablation,
)

HYP = AblationHypothesis(
    name="h1",
    factor="retrieval_top_k",
    baseline_label="k=5",
    treatment_label="k=10",
    metric_name="faithfulness",
    expected_direction="increase",
    noise_estimate=None,
    origin="drw-spr04",
)


def _hyp(**over: object) -> AblationHypothesis:
    defaults = dict(
        name="h1", factor="f", baseline_label="b", treatment_label="t",
        metric_name="m", expected_direction=None, noise_estimate=None, origin="o",
    )
    defaults.update(over)
    return AblationHypothesis(**defaults)  # type: ignore[arg-type]


# ── Three verdicts ──────────────────────────────────────────────────────────


def test_factor_related_large_effect_small_noise():
    # Within-group replicate noise is tiny (±0.05) while the means shift by 9.
    # Pooled WITHIN-group stdev ≈ 0.07 → threshold 2σ·0.07 ≈ 0.14; |Δ|=9 ≫ it.
    baseline = Measurement("m", 1.0, (0.95, 1.05))
    treatment = Measurement("m", 10.0, (9.95, 10.05))
    rep = run_ablation(_hyp(metric_name="m"), baseline, treatment)
    assert rep.verdict == FACTOR_RELATED
    assert rep.noise_origin == "pooled"
    assert rep.effect_size > rep.threshold  # type: ignore[operator]


def test_noise_verdict_effect_within_band():
    # Within-group noise (±0.2 → stdev ≈ 0.28) dwarfs the |Δ|=0.3 shift.
    baseline = Measurement("m", 1.0, (0.8, 1.2))
    treatment = Measurement("m", 1.3, (1.1, 1.5))
    rep = run_ablation(_hyp(metric_name="m"), baseline, treatment)
    assert rep.verdict == NOISE
    assert rep.effect_size <= rep.threshold  # type: ignore[operator]


def test_inconclusive_when_no_noise_estimate():
    baseline = Measurement("m", 1.0)
    treatment = Measurement("m", 2.0)
    rep = run_ablation(_hyp(metric_name="m"), baseline, treatment)
    assert rep.verdict == INCONCLUSIVE
    assert rep.noise is None
    assert rep.noise_origin == "none"
    # The honesty rule: a confident verdict without noise is forbidden.
    assert rep.verdict != FACTOR_RELATED
    assert rep.verdict != NOISE


# ── Noise precedence: pooled > override > absent ────────────────────────────


def test_pooled_takes_precedence_over_override():
    # Both samples AND an override are present → pooled wins (calibrate to
    # measured evidence, not an asserted number).
    baseline = Measurement("m", 1.0, (1.0, 1.0))
    treatment = Measurement("m", 6.0, (6.0, 6.0))
    rep = run_ablation(_hyp(metric_name="m", noise_estimate=0.001), baseline, treatment)
    assert rep.noise_origin == "pooled"
    assert rep.noise != 0.001


def test_override_used_when_insufficient_samples():
    # < MIN_SAMPLES_FOR_NOISE → fall back to the operator override.
    baseline = Measurement("m", 1.0, (1.0,))  # only 1 sample each → pooled=2 < 2? combined=2
    treatment = Measurement("m", 6.0, (6.0,))
    # combined samples = 2, which meets MIN=2, so pooled WOULD be used. To
    # force the override path, provide ONE sample total.
    baseline = Measurement("m", 1.0)
    treatment = Measurement("m", 6.0, (5.0,))  # combined=1 < 2 → override path
    rep = run_ablation(_hyp(metric_name="m", noise_estimate=0.5), baseline, treatment)
    assert rep.noise_origin == "override"
    assert rep.noise == 0.5
    assert rep.verdict == FACTOR_RELATED  # |5.0| > 2·0.5


def test_inconclusive_when_no_samples_and_no_override():
    baseline = Measurement("m", 1.0)
    treatment = Measurement("m", 6.0)
    rep = run_ablation(_hyp(metric_name="m"), baseline, treatment)
    assert rep.verdict == INCONCLUSIVE


# ── Noise-floor honesty guard ───────────────────────────────────────────────


def test_noise_floor_yields_inconclusive():
    # Identical replicates → pooled stdev = 0 < floor → inconclusive (refuse
    # to fabricate factor_related on zero noise).
    baseline = Measurement("m", 1.0, (1.0, 1.0))
    treatment = Measurement("m", 6.0, (6.0, 6.0))  # stdev of [1,1,6,6] ≈ 2.83 (not 0)
    # To get a sub-floor noise, make ALL replicates identical across both:
    baseline = Measurement("m", 1.0, (5.0, 5.0))
    treatment = Measurement("m", 6.0, (5.0, 5.0))
    rep = run_ablation(_hyp(metric_name="m"), baseline, treatment)
    # stdev of [5,5,5,5] = 0 < floor → inconclusive
    assert rep.verdict == INCONCLUSIVE
    assert rep.noise is not None and rep.noise < ABLATION_INCONCLUSIVE_NOISE_FLOOR


# ── Direction reversal ──────────────────────────────────────────────────────


def test_direction_reversal_flagged_on_factor_related():
    baseline = Measurement("m", 5.0, (4.95, 5.05))
    treatment = Measurement("m", 1.0, (0.95, 1.05))  # Δ = -4 (decrease)
    rep = run_ablation(
        _hyp(metric_name="m", expected_direction="increase"), baseline, treatment
    )
    assert rep.verdict == FACTOR_RELATED
    assert rep.direction_reversal is True
    assert "REVERSES" in rep.verdict_reason


def test_no_reversal_when_direction_matches():
    baseline = Measurement("m", 1.0, (1.0, 1.0))
    treatment = Measurement("m", 6.0, (6.0, 6.0))
    rep = run_ablation(
        _hyp(metric_name="m", expected_direction="increase"), baseline, treatment
    )
    assert rep.direction_reversal is False


# ── Metric-identity guard ───────────────────────────────────────────────────


def test_metric_mismatch_baseline_vs_treatment_raises():
    with pytest.raises(ValueError, match="metric-name mismatch"):
        run_ablation(_hyp(metric_name="m"), Measurement("m", 1.0), Measurement("x", 2.0))


def test_metric_mismatch_vs_hypothesis_raises():
    with pytest.raises(ValueError, match="metric-name mismatch"):
        run_ablation(
            _hyp(metric_name="other"),
            Measurement("m", 1.0, (1.0, 1.0)),
            Measurement("m", 2.0, (2.0, 2.0)),
        )


# ── Purity / determinism ────────────────────────────────────────────────────


def test_run_ablation_is_pure_byte_identical_json():
    b = Measurement("m", 1.0, (1.0, 1.0))
    t = Measurement("m", 6.0, (6.0, 6.0))
    r1 = run_ablation(_hyp(metric_name="m"), b, t)
    r2 = run_ablation(_hyp(metric_name="m"), b, t)
    assert r1 == r2
    assert r1.to_json() == r2.to_json()
    # JSON is sorted (deterministic keys).
    parsed = json.loads(r1.to_json())
    assert list(parsed) == sorted(parsed)


def test_param_version_stamped():
    rep = run_ablation(
        _hyp(metric_name="m"),
        Measurement("m", 1.0, (1.0, 1.0)),
        Measurement("m", 6.0, (6.0, 6.0)),
    )
    assert rep.param_version == ANTIEK_PARAM_VERSION
    assert rep.param_version == "0.2.0"


def test_to_markdown_contains_key_fields():
    rep = run_ablation(
        _hyp(factor="my_factor", metric_name="my_metric"),
        Measurement("my_metric", 1.0, (0.95, 1.05)),
        Measurement("my_metric", 10.0, (9.95, 10.05)),
    )
    md = rep.to_markdown()
    assert "my_factor" in md
    assert "my_metric" in md
    assert "factor_related" in md


# ── Strict YAML loaders ─────────────────────────────────────────────────────


def test_asymmetric_replicates_uses_single_group_variance():
    # Only baseline has replicates; treatment has none. The pooled noise must
    # be baseline's WITHIN-group stdev (≈0.1), NOT the 2×-inflated value the
    # negative-degree-of-freedom bug produced before the fix (≈0.141).
    baseline = Measurement("m", 1.0, (0.9, 1.0, 1.1))  # within-group stdev = 0.1
    treatment = Measurement("m", 10.0)  # no replicates
    rep = run_ablation(_hyp(metric_name="m"), baseline, treatment)
    assert rep.noise_origin == "pooled"
    assert rep.noise == pytest.approx(0.1)
    assert rep.verdict == FACTOR_RELATED  # |Δ|=9 ≫ 2·0.1


def test_non_finite_value_rejected():
    # NaN must not silently yield a wrong verdict; it is rejected loudly.
    with pytest.raises(ValueError, match="non-finite"):
        run_ablation(
            _hyp(metric_name="m"),
            Measurement("m", float("nan"), (1.0, 2.0)),
            Measurement("m", 6.0, (5.0, 7.0)),
        )


def test_non_finite_sample_rejected():
    with pytest.raises(ValueError, match="non-finite"):
        run_ablation(
            _hyp(metric_name="m"),
            Measurement("m", 1.0, (1.0, float("inf"))),
            Measurement("m", 6.0, (5.0, 7.0)),
        )


def test_non_finite_override_rejected():
    # An operator override of NaN/inf reaches the verdict math and would leak
    # a silent wrong verdict — it is rejected too (no replicates ⇒ override
    # is the active noise source here).
    with pytest.raises(ValueError, match="finite"):
        run_ablation(
            _hyp(metric_name="m", noise_estimate=float("inf")),
            Measurement("m", 1.0),
            Measurement("m", 6.0),
        )


def test_degenerate_pooled_with_override_is_inconclusive():
    # Deliberate decision (spec: "pooled > override"): identical replicates
    # ⇒ pooled = 0.0 < floor ⇒ inconclusive, EVEN when an operator override
    # is present. Pinned so the choice is explicit, not accidental. See the
    # PR description for the documented tradeoff.
    baseline = Measurement("m", 1.0, (1.0, 1.0))
    treatment = Measurement("m", 6.0, (6.0, 6.0))
    rep = run_ablation(_hyp(metric_name="m", noise_estimate=0.1), baseline, treatment)
    assert rep.noise_origin == "pooled"  # pooled still wins precedence
    assert rep.verdict == INCONCLUSIVE   # but is degenerate ⇒ no verdict


# ── Strict YAML loaders ─────────────────────────────────────────────────────


def test_load_hypothesis_rejects_unknown_field():
    with pytest.raises(ValueError, match="unknown hypothesis field"):
        load_hypothesis({
            "name": "h", "factor": "f", "baseline_label": "b",
            "treatment_label": "t", "metric_name": "m", "origin": "o",
            "typoo": 1,
        })


def test_load_measurements_rejects_unknown_field():
    with pytest.raises(ValueError, match="unknown measurement"):
        load_measurements({
            "baseline": {"name": "m", "value": 1.0, "extra": 9},
            "treatment": {"name": "m", "value": 2.0},
        })


def test_load_hypothesis_rejects_bad_direction():
    with pytest.raises(ValueError, match="expected_direction"):
        load_hypothesis({
            "name": "h", "factor": "f", "baseline_label": "b",
            "treatment_label": "t", "metric_name": "m", "origin": "o",
            "expected_direction": "sideways",
        })


def test_yaml_round_trip(tmp_path):
    hyp_data = {
        "name": "h", "factor": "f", "baseline_label": "b", "treatment_label": "t",
        "metric_name": "m", "expected_direction": "increase", "noise_estimate": None,
        "origin": "o",
    }
    meas_data = {
        "baseline": {"name": "m", "value": 1.0, "samples": [1.0, 1.0]},
        "treatment": {"name": "m", "value": 6.0, "samples": [6.0, 6.0]},
    }
    meas_data = {
        "baseline": {"name": "m", "value": 1.0, "samples": [0.95, 1.05]},
        "treatment": {"name": "m", "value": 10.0, "samples": [9.95, 10.05]},
    }
    h = load_hypothesis(yaml.safe_load(yaml.safe_dump(hyp_data)))
    b, t = load_measurements(yaml.safe_load(yaml.safe_dump(meas_data)))
    rep = run_ablation(h, b, t)
    assert rep.verdict == FACTOR_RELATED


# ── CLI ─────────────────────────────────────────────────────────────────────


def _write_yaml(path, data):
    path.write_text(yaml.safe_dump(data), encoding="utf-8")


def _run_cli(tmp_path, hyp_data, meas_data):
    hp = tmp_path / "hyp.yaml"
    mp = tmp_path / "meas.yaml"
    _write_yaml(hp, hyp_data)
    _write_yaml(mp, meas_data)
    return subprocess.run(
        [sys.executable, "-m", "substrate.eval.ablation",
         "--hypothesis", str(hp), "--measurements", str(mp)],
        capture_output=True, text=True,
    )


def test_cli_factor_related_exits_zero(tmp_path):
    r = _run_cli(tmp_path,
        {"name": "h", "factor": "f", "baseline_label": "b", "treatment_label": "t",
         "metric_name": "m", "expected_direction": "increase", "noise_estimate": None,
         "origin": "o"},
        {"baseline": {"name": "m", "value": 1.0, "samples": [0.95, 1.05]},
         "treatment": {"name": "m", "value": 10.0, "samples": [9.95, 10.05]}})
    assert r.returncode == 0
    parsed = json.loads(r.stdout)
    assert parsed["verdict"] == FACTOR_RELATED


def test_cli_inconclusive_exits_two(tmp_path):
    r = _run_cli(tmp_path,
        {"name": "h", "factor": "f", "baseline_label": "b", "treatment_label": "t",
         "metric_name": "m", "expected_direction": None, "noise_estimate": None,
         "origin": "o"},
        {"baseline": {"name": "m", "value": 1.0, "samples": []},
         "treatment": {"name": "m", "value": 6.0, "samples": []}})
    assert r.returncode == 2
    assert json.loads(r.stdout)["verdict"] == INCONCLUSIVE


def test_cli_unknown_field_exits_nonzero(tmp_path):
    r = _run_cli(tmp_path,
        {"name": "h", "factor": "f", "baseline_label": "b", "treatment_label": "t",
         "metric_name": "m", "noise_estimate": None, "origin": "o", "bogus": 1},
        {"baseline": {"name": "m", "value": 1.0},
         "treatment": {"name": "m", "value": 2.0}})
    assert r.returncode != 0
    assert r.returncode != 2  # a loader error, not an inconclusive verdict


def test_cli_help_exits_zero():
    r = subprocess.run(
        [sys.executable, "-m", "substrate.eval.ablation", "--help"],
        capture_output=True, text=True,
    )
    assert r.returncode == 0
    assert "--hypothesis" in r.stdout
