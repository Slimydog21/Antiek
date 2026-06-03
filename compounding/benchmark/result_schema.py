"""AFF SPR-09 M4 — the recorded-artifact schema.

Follows the ``benchmarks/baseline.json`` idiom (``seed`` / ``captured_at`` /
``git_sha`` + the metric fields) rather than inventing a result format. The
artifact is the defensible proof (rigor #5): a future skeptic re-runs from the
frozen set + seed and reproduces the deltas.

Per-metric the artifact carries a SIGNED ``delta`` (warm − cold; negative ⇒ warm
cheaper ⇒ flywheel works) with ``ci_low`` / ``ci_high``, never clamped or
abs()'d (M4). The top-level carries the frozen-set sha, the CI method + ``n``,
the validity verdict, and a truthful ``mock_run`` flag.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class MetricDelta:
    """One metric's signed warm−cold delta + its bootstrap/t CI over n paired
    runs. ``warm_mean`` / ``cold_mean`` are reported so the delta is auditable;
    ``delta = warm_mean − cold_mean`` is the headline number. Nothing here is
    clamped — a positive delta (warm more expensive) is emitted verbatim."""

    metric: str
    delta: float
    ci_low: float
    ci_high: float
    warm_mean: float
    cold_mean: float
    n: int

    @property
    def straddles_zero(self) -> bool:
        return self.ci_low <= 0.0 <= self.ci_high

    @property
    def ci_half_width(self) -> float:
        return (self.ci_high - self.ci_low) / 2.0


@dataclass(frozen=True)
class ArmComparison:
    """One pair of arms compared per metric (e.g. warm vs cold, or
    irrelevant vs cold). ``label`` names the comparison; ``metrics`` is the
    per-metric signed delta + CI."""

    label: str
    metrics: list[MetricDelta]

    def metric(self, name: str) -> MetricDelta | None:
        for m in self.metrics:
            if m.metric == name:
                return m
        return None


@dataclass
class BenchmarkResult:
    """The full recorded artifact. Serialized to
    ``compounding/benchmark/results/spr09_run.json`` (M6)."""

    frozen_sha: str
    seed: int
    n: int
    ci_method: str
    bootstrap_resamples: int
    mock_run: bool
    validity: str
    headline_interpretation: str
    git_sha: str
    captured_at: str
    # The headline comparison (warm vs cold over the high-overlap pooled cell).
    headline: ArmComparison
    # All comparisons, including the internal-probe (reported separately), the
    # partial dose-response cell, and the irrelevant-vs-cold validity control.
    comparisons: list[ArmComparison]
    control_tolerance: float
    material_floor: float
    notes: str = ""
    parameters_ratified: bool = False
    # ACV SPR-06 — the ratification PROVENANCE (M3 auditability). When the
    # operator passes ``--ratified``, this records WHAT was ratified (the
    # pilot-report artifact id / decision reference) so a reader can reconstruct
    # the ratified parameters, not just see a bare boolean. ``None`` when not
    # ratified (and the gate requires it non-null for a scored run).
    ratification_ref: str | None = None
    # ACV SPR-06 — which browse loop produced this artifact: ``"demo"`` (the
    # reuse-blind null) or ``"consuming"`` (the reuse-consuming real arm). Lets a
    # reader tell a genuine measurement from the keystone null at a glance.
    loop_kind: str = "demo"

    def to_dict(self) -> dict[str, Any]:
        return {
            "frozen_sha": self.frozen_sha,
            "seed": self.seed,
            "n": self.n,
            "ci_method": self.ci_method,
            "bootstrap_resamples": self.bootstrap_resamples,
            "mock_run": self.mock_run,
            "validity": self.validity,
            "headline_interpretation": self.headline_interpretation,
            "control_tolerance": self.control_tolerance,
            "material_floor": self.material_floor,
            "parameters_ratified": self.parameters_ratified,
            "ratification_ref": self.ratification_ref,
            "loop_kind": self.loop_kind,
            "git_sha": self.git_sha,
            "captured_at": self.captured_at,
            "headline": _comparison_to_dict(self.headline),
            "comparisons": [_comparison_to_dict(c) for c in self.comparisons],
            # Flat ``metrics`` mirror of the headline for the spec's jq gate
            # (``.metrics[].delta``).
            "metrics": [asdict(m) for m in self.headline.metrics],
            "notes": self.notes,
        }

    def write(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)
            f.write("\n")


def _comparison_to_dict(c: ArmComparison) -> dict[str, Any]:
    return {"label": c.label, "metrics": [asdict(m) for m in c.metrics]}
