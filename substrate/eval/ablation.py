"""Pure ablation primitive — the bug-finding complement to the eval ladder.

When a flywheel surface regresses, vary one factor, name the noise, and return
one of three verdicts. ``run_ablation`` is PURE: deterministic, no I/O, no
randomness — the same inputs produce a byte-identical report every run. The
CLI (``python -m substrate.eval.ablation``) is a thin YAML-loading wrapper.

Load-bearing honesty rule: a ``factor_related`` / ``noise`` verdict is
FORBIDDEN without a real noise estimate. When noise cannot be determined
(no replicate samples AND no operator override) the verdict is
``inconclusive`` — never a confident guess.
"""

from __future__ import annotations

import json
import math
import statistics
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from substrate.constants import (
    ABLATION_INCONCLUSIVE_NOISE_FLOOR,
    ABLATION_MIN_SAMPLES_FOR_NOISE,
    ABLATION_VERDICT_SIGMA,
    ANTIEK_PARAM_VERSION,
)

__all__ = [
    "Measurement",
    "AblationHypothesis",
    "AblationReport",
    "Verdict",
    "run_ablation",
    "load_hypothesis",
    "load_measurements",
    "main",
]

# Three verdicts, mapping to Yao's three-causes test:
#   factor_related — the ablated factor plausibly caused the change (|Δ| > σ·noise)
#   noise          — the effect is within the run-to-run noise band
#   inconclusive   — noise cannot be estimated; no verdict is defensible
Verdict = str
FACTOR_RELATED = "factor_related"
NOISE = "noise"
INCONCLUSIVE = "inconclusive"
_VERDICTS = (FACTOR_RELATED, NOISE, INCONCLUSIVE)

# Recognised expected-effect directions. ``None`` means "no direction asserted".
_DIRECTIONS = ("increase", "decrease")

# Noise provenance labels stamped on every report that has an estimate.
_NOISE_POOLED = "pooled"
_NOISE_OVERRIDE = "override"
_NOISE_NONE = "none"


@dataclass(frozen=True)
class Measurement:
    """A single metric observation: a point value + replicate samples.

    ``name`` is the metric identity (what is being measured); baseline and
    treatment must share it and it must match the hypothesis ``metric_name``.
    ``samples`` are the replicate observations used to estimate run-to-run
    noise (empty when no replicates were captured).
    """

    name: str
    value: float
    samples: Sequence[float] = field(default_factory=tuple)


@dataclass(frozen=True)
class AblationHypothesis:
    """What factor is being ablated and the expected shape of its effect."""

    name: str
    factor: str
    baseline_label: str
    treatment_label: str
    metric_name: str
    expected_direction: str | None
    noise_estimate: float | None
    origin: str


@dataclass(frozen=True)
class AblationReport:
    """The verdict + every number that justifies it."""

    verdict: Verdict
    metric_name: str
    factor: str
    delta: float
    effect_size: float
    noise: float | None
    threshold: float | None
    sigma: float
    noise_origin: str
    direction_reversal: bool
    verdict_reason: str
    param_version: str

    def to_json(self) -> str:
        # Deterministic serialisation — same report ⇒ byte-identical output.
        return json.dumps(
            {
                "verdict": self.verdict,
                "metric_name": self.metric_name,
                "factor": self.factor,
                "delta": self.delta,
                "effect_size": self.effect_size,
                "noise": self.noise,
                "threshold": self.threshold,
                "sigma": self.sigma,
                "noise_origin": self.noise_origin,
                "direction_reversal": self.direction_reversal,
                "verdict_reason": self.verdict_reason,
                "param_version": self.param_version,
            },
            sort_keys=True,
            separators=(",", ":"),
        )

    def to_markdown(self) -> str:
        lines = [
            f"## Ablation verdict: `{self.verdict}`",
            f"- **factor**: {self.factor}",
            f"- **metric**: {self.metric_name}",
            f"- **delta (treatment − baseline)**: {self.delta}",
            f"- **effect size |Δ|**: {self.effect_size}",
            f"- **noise estimate**: {self.noise} (origin: `{self.noise_origin}`)",
            f"- **threshold (σ·noise)**: {self.threshold}  (σ = {self.sigma})",
            f"- **direction reversal**: {self.direction_reversal}",
            f"- **reason**: {self.verdict_reason}",
            f"- **param_version**: {self.param_version}",
        ]
        return "\n".join(lines)


def _pooled_stdev(baseline: Measurement, treatment: Measurement) -> float | None:
    """Pooled WITHIN-GROUP sample standard deviation across replicates.

    This is the run-to-run noise estimate, computed the way ablation
    experiments demand: from the within-group variance of each condition's
    replicates, NOT the spread of the concatenated samples (which would fold
    in the between-group effect and make "factor_related" near-impossible).

    Only groups with >= 2 replicates contribute within-group variance — a
    group with 0 or 1 replicate has no internal spread, so including it would
    inject a negative degree of freedom (n-1) and distort the estimate (the
    asymmetric case: one group with replicates, the other with none, was
    inflated 2x). When only one condition has replicates, that condition's
    variance IS the noise estimate. Returns ``None`` when no group can
    contribute variance or total replicates < ABLATION_MIN_SAMPLES_FOR_NOISE.
    """
    groups = [
        [float(x) for x in g]
        for g in (baseline.samples, treatment.samples)
        if len(g) >= 2
    ]
    if not groups or sum(len(g) for g in groups) < ABLATION_MIN_SAMPLES_FOR_NOISE:
        return None
    num = sum((len(g) - 1) * statistics.variance(g) for g in groups)
    denom = sum((len(g) - 1) for g in groups)
    return math.sqrt(num / denom)


def run_ablation(
    hypothesis: AblationHypothesis,
    baseline: Measurement,
    treatment: Measurement,
) -> AblationReport:
    """Return the ablation verdict for one factor varied between two measurements.

    Pure: deterministic, no I/O, no randomness. Raises ``ValueError`` on a
    metric-name mismatch between the measurements and the hypothesis.
    """
    # ── Metric-identity guard ──────────────────────────────────────────────
    if baseline.name != treatment.name:
        raise ValueError(
            f"metric-name mismatch: baseline.name={baseline.name!r} "
            f"!= treatment.name={treatment.name!r}"
        )
    if baseline.name != hypothesis.metric_name:
        raise ValueError(
            f"metric-name mismatch: measurement name {baseline.name!r} "
            f"!= hypothesis.metric_name={hypothesis.metric_name!r}"
        )

    # ── Input integrity ───────────────────────────────────────────────────
    # Non-finite values (NaN/inf) would manufacture a silent wrong verdict
    # (NaN comparisons are always False ⇒ NOISE) and serialise to non-standard
    # JSON. Reject loudly, mirroring the strict YAML loaders. This also covers
    # the operator noise_estimate override — it reaches the verdict math
    # unchanged and would otherwise leak the failure mode above.
    for _label, _m in (("baseline", baseline), ("treatment", treatment)):
        if not all(math.isfinite(v) for v in (_m.value, *_m.samples)):
            raise ValueError(f"{_label} measurement has a non-finite value")
    if (
        hypothesis.noise_estimate is not None
        and not math.isfinite(hypothesis.noise_estimate)
    ):
        raise ValueError("hypothesis.noise_estimate must be finite")

    delta = float(treatment.value) - float(baseline.value)
    effect_size = abs(delta)

    # ── Noise estimation (precedence: pooled > operator override > absent) ─
    # Prefer MEASURED noise over an asserted override — calibrate to evidence.
    pooled = _pooled_stdev(baseline, treatment)
    if pooled is not None:
        noise: float | None = pooled
        noise_origin = _NOISE_POOLED
    elif hypothesis.noise_estimate is not None:
        noise = float(hypothesis.noise_estimate)
        noise_origin = _NOISE_OVERRIDE
    else:
        noise = None
        noise_origin = _NOISE_NONE

    # ── Direction-reversal flag (magnitude-based verdict is unchanged) ─────
    direction_reversal = (
        (hypothesis.expected_direction == "increase" and delta < 0)
        or (hypothesis.expected_direction == "decrease" and delta > 0)
    )

    # ── Verdict ────────────────────────────────────────────────────────────
    if noise is None:
        verdict = INCONCLUSIVE
        threshold = None
        reason = (
            "inconclusive: no replicate samples and no operator noise override — "
            "noise cannot be estimated, so no factor_related/noise verdict is "
            "defensible."
        )
    elif noise < ABLATION_INCONCLUSIVE_NOISE_FLOOR:
        # A sub-floor noise estimate (e.g. identical replicates ⇒ zero stdev)
        # would manufacture false certainty; refuse to verdict on it.
        verdict = INCONCLUSIVE
        threshold = ABLATION_VERDICT_SIGMA * noise
        reason = (
            f"inconclusive: estimated noise {noise} is below the "
            f"inconclusive floor {ABLATION_INCONCLUSIVE_NOISE_FLOOR} — too "
            f"small to support a confident verdict (likely an artefact of "
            f"identical replicates)."
        )
    else:
        threshold = ABLATION_VERDICT_SIGMA * noise
        if effect_size > threshold:
            verdict = FACTOR_RELATED
            reason = (
                f"factor_related: |Δ|={effect_size} exceeds the noise threshold "
                f"{threshold} (σ={ABLATION_VERDICT_SIGMA} × noise {noise}, "
                f"origin `{noise_origin}`); the ablated factor plausibly caused "
                f"the change."
            )
        else:
            verdict = NOISE
            reason = (
                f"noise: |Δ|={effect_size} is within the noise band "
                f"(threshold {threshold} = σ={ABLATION_VERDICT_SIGMA} × noise "
                f"{noise}, origin `{noise_origin}`); indistinguishable from "
                f"run-to-run variance."
            )

    if direction_reversal and verdict == FACTOR_RELATED:
        reason += (
            " NOTE: the effect direction REVERSES the hypothesis "
            f"({hypothesis.expected_direction}) — the factor moved the metric, "
            f"but the wrong way."
        )

    return AblationReport(
        verdict=verdict,
        metric_name=hypothesis.metric_name,
        factor=hypothesis.factor,
        delta=delta,
        effect_size=effect_size,
        noise=noise,
        threshold=threshold,
        sigma=ABLATION_VERDICT_SIGMA,
        noise_origin=noise_origin,
        direction_reversal=direction_reversal,
        verdict_reason=reason,
        param_version=ANTIEK_PARAM_VERSION,
    )


# ── YAML loaders (strict — typos trip the loader, not a future operator) ────

_HYPOTHESIS_FIELDS = frozenset({
    "name", "factor", "baseline_label", "treatment_label", "metric_name",
    "expected_direction", "noise_estimate", "origin",
})
_MEASUREMENT_FIELDS = frozenset({"name", "value", "samples"})


def _reject_unknown(data: dict[str, Any], allowed: frozenset[str], kind: str) -> None:
    if not isinstance(data, dict):
        raise ValueError(f"{kind} must be a mapping, got {type(data).__name__}")
    extra = set(data) - allowed
    if extra:
        raise ValueError(
            f"unknown {kind} field(s): {sorted(extra)}; allowed: {sorted(allowed)}"
        )


def load_hypothesis(data: dict[str, Any]) -> AblationHypothesis:
    """Construct an ``AblationHypothesis`` from a parsed YAML mapping.

    Rejects unknown fields loudly so a typo fails here, not in a future run.
    """
    _reject_unknown(data, _HYPOTHESIS_FIELDS, "hypothesis")
    direction = data.get("expected_direction")
    if direction is not None and direction not in _DIRECTIONS:
        raise ValueError(
            f"expected_direction must be one of {_DIRECTIONS} or null, got {direction!r}"
        )
    return AblationHypothesis(
        name=data["name"],
        factor=data["factor"],
        baseline_label=data["baseline_label"],
        treatment_label=data["treatment_label"],
        metric_name=data["metric_name"],
        expected_direction=direction,
        noise_estimate=data.get("noise_estimate"),
        origin=data["origin"],
    )


def load_measurements(data: dict[str, Any]) -> tuple[Measurement, Measurement]:
    """Construct the (baseline, treatment) measurement pair from parsed YAML."""
    if not isinstance(data, dict) or set(data) != {"baseline", "treatment"}:
        raise ValueError(
            "measurements must be a mapping with exactly 'baseline' and 'treatment'"
        )
    parsed: list[Measurement] = []
    for key in ("baseline", "treatment"):
        m = data[key]
        _reject_unknown(m, _MEASUREMENT_FIELDS, f"measurement ({key})")
        parsed.append(
            Measurement(
                name=m["name"],
                value=float(m["value"]),
                samples=tuple(float(s) for s in m.get("samples", [])),
            )
        )
    return parsed[0], parsed[1]


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point. Emits JSON to stdout, markdown to stderr.

    Exit codes mirror the verdict: 0 for factor_related/noise, 2 for
    inconclusive. (Non-zero, non-2 for usage/loader errors.)
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m substrate.eval.ablation",
        description="Run a single-factor ablation and print the verdict report.",
    )
    parser.add_argument("--hypothesis", required=True, help="path to hypothesis YAML")
    parser.add_argument("--measurements", required=True, help="path to measurements YAML")
    args = parser.parse_args(argv)

    import yaml  # repo YAML lib (PyYAML) — no new dep

    with open(args.hypothesis, encoding="utf-8") as fh:
        hypothesis = load_hypothesis(yaml.safe_load(fh))
    with open(args.measurements, encoding="utf-8") as fh:
        baseline, treatment = load_measurements(yaml.safe_load(fh))

    report = run_ablation(hypothesis, baseline, treatment)
    sys.stdout.write(report.to_json() + "\n")
    sys.stderr.write(report.to_markdown() + "\n")

    return 0 if report.verdict in (FACTOR_RELATED, NOISE) else 2


if __name__ == "__main__":  # pragma: no cover — exercised via subprocess in tests
    raise SystemExit(main())
