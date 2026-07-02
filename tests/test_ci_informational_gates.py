"""Informational CI gates must stay explicit and non-claimable as proof."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CI_POLICY = ROOT / "docs" / "decisions" / "ci-informational-gates.md"
CI = ROOT / ".github" / "workflows" / "ci.yml"
VISUALTEST = ROOT / ".github" / "workflows" / "visualtest.yml"
PROD_PARITY = ROOT / ".github" / "workflows" / "prod_parity.yml"


def test_ci_informational_policy_names_the_three_warn_only_gates() -> None:
    text = CI_POLICY.read_text(encoding="utf-8")
    compact = " ".join(text.split())

    assert "CI policy — three gates made informational on shared runners" in text
    assert "Inline-rubric latency" in text
    assert "axe-core — Storybook test-runner a11y job" in text
    assert "lostpixel — visual regression" in text
    assert "it still runs and surfaces a `::warning::`, but does not fail the gate" in compact
    assert "hard-blocking and green" in compact
    assert "Reconsider-if" in text


def test_ci_latency_warning_remains_informational_not_silent() -> None:
    text = CI.read_text(encoding="utf-8")
    compact = " ".join(text.split())

    assert "Inline-rubric latency (craft signature — informational on CI)" in text
    assert "benchmarks.rubric_latency --check-regression" in text
    assert "|| echo \"::warning title=Latency check is informational on CI" in text
    assert "enforced operator-side per CLAUDE.md" in text
    assert "microsecond benchmark, runner ~2x slower than baseline hardware" in compact


def test_visualtest_warn_only_steps_explain_their_operator_boundaries() -> None:
    text = VISUALTEST.read_text(encoding="utf-8")

    assert "Run Lost-Pixel against committed baselines (informational)" in text
    assert "|| echo \"::warning title=Lost-Pixel informational" in text
    assert "visual baselines not yet established" in text
    assert "approve them in the Lost Pixel dashboard to make this gate blocking" in text

    assert "Run axe-core against the a11y-audit stories (informational)" in text
    assert "|| echo \"::warning title=axe-core informational" in text
    assert "Storybook test-runner could not load the story index on CI" in text
    assert "a11y still checked via scripts/a11y_audit.ts" in text


def test_prod_parity_probe_is_scheduled_informational_only() -> None:
    text = PROD_PARITY.read_text(encoding="utf-8")

    assert "name: prod-parity (informational)" in text
    assert "schedule:" in text
    assert "continue-on-error: true" in text
    assert "Probe prod parity (informational)" in text
    assert "|| echo \"::warning title=prod-parity drift (informational)" in text
    assert "The BLOCKING parity surface is the post-deploy task in deploy.yml" in text
    assert "docs/decisions/ci-informational-gates.md" in text
