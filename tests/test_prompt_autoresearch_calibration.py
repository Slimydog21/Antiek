"""No-op variance calibration tests for prompt-autoresearch Wedge 1."""

from __future__ import annotations

from decimal import Decimal

from tools.prompt_autoresearch import (
    CompositeScore,
    PromptMutationOutcome,
    calibrate_epsilon,
    render_calibration_markdown,
    write_outcomes_json,
)


def _outcome(mutation_id: str, delta: float) -> PromptMutationOutcome:
    return PromptMutationOutcome(
        mutation_id=mutation_id,
        accepted=False,
        baseline_score=0.70,
        candidate_score=0.70 + delta,
        delta=delta,
        epsilon_required=0.05,
        composite_breakdown=CompositeScore(
            rubric=0.80,
            voice_style=0.90,
            sector_vocab=0.90,
            grounding=0.90,
            total=0.70 + delta,
        ),
        cost_usd=Decimal("0.01"),
    )


def test_calibration_keeps_floor_when_noop_variance_is_low():
    outcomes = [_outcome(f"noop-{i}", 0.001) for i in range(10)]

    report = calibrate_epsilon("synthesizer", outcomes, floor_epsilon=0.05)

    assert report.iteration_count == 10
    assert report.sigma == 0.0
    assert report.recommended_epsilon == 0.05


def test_calibration_raises_epsilon_above_floor_for_noisy_noop_runs():
    outcomes = [
        _outcome("noop-low", -0.10),
        _outcome("noop-mid", 0.00),
        _outcome("noop-high", 0.10),
    ]

    report = calibrate_epsilon("synthesizer", outcomes, floor_epsilon=0.05)

    assert report.two_sigma > 0.05
    assert report.recommended_epsilon == report.two_sigma


def test_calibration_markdown_records_recommended_epsilon():
    report = calibrate_epsilon(
        "synthesizer",
        [_outcome("noop-a", -0.10), _outcome("noop-b", 0.10)],
        floor_epsilon=0.05,
    )

    md = render_calibration_markdown(report)

    assert "# Prompt autoresearch calibration — `synthesizer`" in md
    assert "Recommended epsilon" in md


def test_calibration_cli_writes_markdown_from_outcome_json(tmp_path):
    from tools.prompt_autoresearch.calibration_cli import main

    outcomes_path = tmp_path / "noop-outcomes.json"
    output_path = tmp_path / "calibration.md"
    write_outcomes_json(
        outcomes_path,
        role="synthesizer",
        outcomes=[_outcome(f"noop-{i}", 0.0) for i in range(5)],
    )

    rc = main(["--outcomes", str(outcomes_path), "--output", str(output_path)])

    assert rc == 0
    md = output_path.read_text(encoding="utf-8")
    assert "Prompt autoresearch calibration" in md
    assert "Recommended epsilon" in md
