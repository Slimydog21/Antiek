"""No-op variance calibration tests for prompt-autoresearch Wedge 1."""

from __future__ import annotations

from decimal import Decimal

from tools.prompt_autoresearch import (
    CalibrationReport,
    CompositeScore,
    PromptMutationOutcome,
    calibrate_epsilon,
    render_calibration_markdown,
    write_outcomes_json,
)


def _outcome(mutation_id: str, delta: float, *, accepted: bool = False) -> PromptMutationOutcome:
    return PromptMutationOutcome(
        mutation_id=mutation_id,
        accepted=accepted,
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


def test_calibration_rejects_invalid_floor_epsilon():
    outcomes = [_outcome("noop-a", 0.0)]

    try:
        calibrate_epsilon("synthesizer", outcomes, floor_epsilon=-0.01)
    except ValueError as exc:
        assert "floor_epsilon must be a non-negative finite number" in str(exc)
    else:  # pragma: no cover - defensive assertion path
        raise AssertionError("expected invalid floor epsilon to be rejected")


def test_calibration_rejects_accepted_noop_outcomes():
    outcomes = [
        _outcome("noop-a", 0.0),
        _outcome("accepted-not-noop", 0.10, accepted=True),
    ]

    try:
        calibrate_epsilon("synthesizer", outcomes)
    except ValueError as exc:
        assert "no-op calibration outcomes must all be rejected" in str(exc)
        assert "accepted-not-noop" in str(exc)
    else:  # pragma: no cover - defensive assertion path
        raise AssertionError("expected accepted no-op outcome to be rejected")


def test_calibration_markdown_records_recommended_epsilon():
    report = calibrate_epsilon(
        "synthesizer",
        [_outcome("noop-a", -0.10), _outcome("noop-b", 0.10)],
        floor_epsilon=0.05,
    )

    md = render_calibration_markdown(report)

    assert "# Prompt autoresearch calibration — `synthesizer`" in md
    assert "Recommended epsilon" in md


def test_calibration_markdown_rejects_inconsistent_report():
    report = CalibrationReport(
        role="synthesizer",
        iteration_count=5,
        mean_delta=0.0,
        sigma=0.01,
        two_sigma=0.02,
        floor_epsilon=0.05,
        recommended_epsilon=0.01,
        rationale="bad report",
    )

    try:
        render_calibration_markdown(report)
    except ValueError as exc:
        assert "recommended_epsilon must be at least floor_epsilon" in str(exc)
    else:  # pragma: no cover - defensive assertion path
        raise AssertionError("expected inconsistent calibration report to be rejected")


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


def test_calibration_cli_rejects_invalid_floor_epsilon(tmp_path, capsys):
    from tools.prompt_autoresearch.calibration_cli import main

    outcomes_path = tmp_path / "noop-outcomes.json"
    write_outcomes_json(
        outcomes_path,
        role="synthesizer",
        outcomes=[_outcome("noop-0", 0.0)],
    )

    rc = main([
        "--outcomes",
        str(outcomes_path),
        "--floor-epsilon",
        "-0.01",
    ])

    assert rc == 2
    assert "floor_epsilon must be a non-negative finite number" in capsys.readouterr().err


def test_calibration_cli_rejects_accepted_noop_outcome(tmp_path, capsys):
    from tools.prompt_autoresearch.calibration_cli import main

    outcomes_path = tmp_path / "noop-outcomes.json"
    write_outcomes_json(
        outcomes_path,
        role="synthesizer",
        outcomes=[
            _outcome("noop-0", 0.0),
            _outcome("accepted-not-noop", 0.10, accepted=True),
        ],
    )

    rc = main(["--outcomes", str(outcomes_path)])

    assert rc == 2
    err = capsys.readouterr().err
    assert "no-op calibration outcomes must all be rejected" in err
    assert "accepted-not-noop" in err
