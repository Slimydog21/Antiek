from __future__ import annotations

import ast
from dataclasses import replace
from pathlib import Path
from typing import Literal

import pytest

from substrate.antiek_bench.judged import (
    SUPPRESSION_REASONS,
    AnchorItem,
    AnchorSet,
    EvidenceRecord,
    QualitativeVerdict,
    VerdictPolicy,
    build_qualitative_verdict,
    calibrate_against_anchors,
    compare_position_swap,
    compute_disagreement,
)

AXES = ("fidelity", "compression", "clarity")
POLICY = VerdictPolicy("judge-policy-v1", 1, 2, "operator-reviewed", "operator")


def test_suppression_reasons_are_a_closed_public_literal_set() -> None:
    assert SUPPRESSION_REASONS == (
        "position_sensitive",
        "judge_disagreement",
        "missing_coverage",
        "self_judging",
        "mixed_rubric_versions",
        "equal_scores",
        "failed_swap",
        "condorcet_cycle",
        "uncalibrated",
    )


def evidence(
    judge: str,
    scores: tuple[int, int, int] = (4, 4, 4),
    *,
    candidates: tuple[str, str] = ("candidate-a", "candidate-b"),
    item: str = "item-1",
    status: Literal["pending", "ok", "failed"] = "ok",
    rubric: str = "qualitative-v1",
) -> EvidenceRecord:
    return EvidenceRecord(
        week_id="2026-W28",
        suite_version="suite-v3",
        item_id_hash=item,
        task_class="distill",
        rubric_version=rubric,
        judge_model=judge,
        candidate_hashes=candidates,
        blinded_order=("A", "B"),
        status=status,
        claimed_at_ms=100,
        scores=tuple(zip(AXES, scores, strict=True)) if status == "ok" else (),
        evidence_refs=(
            tuple((axis, ("A:line-1",)) for axis in AXES) if status == "ok" else ()
        ),
        failure_code="invalid_or_failed_response" if status == "failed" else "",
    )


def anchors(version: str = "anchors-v1") -> AnchorSet:
    return AnchorSet(
        version,
        "operator review 2026-07-10",
        "replace with a newly reviewed version",
        (
            AnchorItem(
                "item-1",
                "qualitative-v1",
                ("candidate-a", "candidate-b"),
                tuple((axis, 3) for axis in AXES),
            ),
        ),
    )


def verdict(
    rows: tuple[EvidenceRecord, ...],
    *,
    swaps: tuple[tuple[EvidenceRecord, EvidenceRecord], ...] = (),
    anchor_set: AnchorSet | None = None,
    expected_judges: tuple[str, ...] = ("judge-1", "judge-2"),
    candidate_models: tuple[str, ...] = ("model-a", "model-b"),
) -> QualitativeVerdict:
    disagreement = compute_disagreement(rows, expected_judges=expected_judges)
    calibration = calibrate_against_anchors(rows, anchor_set)
    return build_qualitative_verdict(
        records=rows,
        disagreement=disagreement,
        swaps=swaps,
        calibration=calibration,
        anchors=anchor_set,
        candidate_models=candidate_models,
        policy=POLICY,
    )


def test_position_swap_normalizes_order_and_suppresses_flip() -> None:
    original = evidence("judge-1", (5, 5, 5))
    stable_reverse = evidence(
        "judge-1", (1, 1, 1), candidates=("candidate-b", "candidate-a")
    )
    stable = compare_position_swap(original, stable_reverse)
    assert stable.axis_scores == tuple((axis, 5, 5) for axis in AXES)
    assert not stable.position_sensitive
    assert stable.qualitative_winner == "candidate-a"

    flipped_reverse = replace(stable_reverse, scores=tuple((axis, 5) for axis in AXES))
    flip = compare_position_swap(original, flipped_reverse)
    assert flip.position_sensitive
    assert flip.qualitative_winner is None
    result = verdict(
        (original, evidence("judge-2", (5, 5, 5))),
        swaps=((original, flipped_reverse),),
        anchor_set=anchors(),
    )
    assert result.winner is None and "position_sensitive" in result.suppression_reasons


def test_equal_scores_never_produce_a_winner() -> None:
    result = verdict(
        (evidence("judge-1", (3, 3, 3)), evidence("judge-2", (3, 3, 3))),
        anchor_set=anchors(),
    )
    assert result.winner is None
    assert "equal_scores" in result.suppression_reasons


def test_missing_and_failed_judges_are_not_averaged_as_zero() -> None:
    rows = (evidence("judge-1", (5, 4, 3)), evidence("judge-2", status="failed"))
    report = compute_disagreement(rows, expected_judges=("judge-1", "judge-2", "judge-3"))
    assert report.effective_sample_size == 1
    assert report.expected_sample_size == 3
    assert report.failure_count == 1
    assert report.missing_judges == ("judge-3",)
    assert tuple(axis.minimum for axis in report.axes) == (3, 4, 5)
    result = verdict(
        rows,
        expected_judges=("judge-1", "judge-2", "judge-3"),
        anchor_set=anchors(),
    )
    assert result.winner is None and "missing_coverage" in result.suppression_reasons


def test_failed_swap_suppresses_even_with_other_successful_evidence() -> None:
    original = evidence("judge-1")
    failed = evidence(
        "judge-1", candidates=("candidate-b", "candidate-a"), status="failed"
    )
    swap = compare_position_swap(original, failed)
    assert swap.failed_swap and swap.qualitative_winner is None
    result = verdict(
        (original, evidence("judge-2")), swaps=((original, failed),), anchor_set=anchors()
    )
    assert result.winner is None and "failed_swap" in result.suppression_reasons


def test_mixed_rubric_versions_suppress() -> None:
    rows = (evidence("judge-1"), evidence("judge-2", rubric="qualitative-v2"))
    result = verdict(rows, anchor_set=anchors())
    assert result.winner is None
    assert "mixed_rubric_versions" in result.suppression_reasons


def test_adversarial_self_judging_suppresses_case_insensitively() -> None:
    rows = (evidence("MODEL-A"), evidence("judge-2"))
    result = verdict(rows, expected_judges=("MODEL-A", "judge-2"), anchor_set=anchors())
    assert result.winner is None and "self_judging" in result.suppression_reasons


def test_condorcet_cycle_is_observed_and_suppressed() -> None:
    rows = (
        evidence("judge-1", candidates=("a", "b")),
        evidence("judge-2", candidates=("b", "c")),
        evidence("judge-3", candidates=("c", "a")),
    )
    report = compute_disagreement(rows, expected_judges=("judge-1", "judge-2", "judge-3"))
    assert report.condorcet_cycle
    result = verdict(
        rows,
        expected_judges=("judge-1", "judge-2", "judge-3"),
        anchor_set=anchors(),
    )
    assert result.winner is None and "condorcet_cycle" in result.suppression_reasons


def test_anchor_calibration_is_versioned_signed_and_does_not_mutate_evidence() -> None:
    rows = (evidence("judge-1", (5, 3, 1)), evidence("judge-2", (3, 3, 3)))
    before = tuple(row.to_dict() for row in rows)
    first = calibrate_against_anchors(rows, anchors("anchors-v1"))
    changed = calibrate_against_anchors(rows, anchors("anchors-v2"))
    assert first.calibrated and first.anchor_version == "anchors-v1"
    assert first.signed_axis_errors == (("clarity", -1.0), ("compression", 0.0), ("fidelity", 1.0))
    assert changed.anchor_version == "anchors-v2"
    assert tuple(row.to_dict() for row in rows) == before


def test_absent_anchors_are_explicitly_uncalibrated_and_suppress() -> None:
    rows = (evidence("judge-1"), evidence("judge-2"))
    calibration = calibrate_against_anchors(rows, None)
    assert not calibration.calibrated and calibration.anchor_version is None
    result = verdict(rows)
    assert not result.calibrated and result.winner is None
    assert "uncalibrated" in result.suppression_reasons


def test_above_threshold_axis_disagreement_suppresses() -> None:
    rows = (evidence("judge-1", (5, 5, 5)), evidence("judge-2", (4, 2, 4)))
    report = compute_disagreement(rows, expected_judges=("judge-1", "judge-2"))
    assert report.maximum_axis_delta == 3
    result = verdict(rows, anchor_set=anchors())
    assert result.winner is None and "judge_disagreement" in result.suppression_reasons


def test_duplicate_judge_rows_cannot_inflate_effective_sample_size() -> None:
    duplicate = replace(evidence("judge-1"), claimed_at_ms=200)
    with pytest.raises(ValueError, match="duplicate judge"):
        compute_disagreement((evidence(" Judge-1 "), duplicate))


def test_reversed_rows_are_normalized_before_axis_disagreement() -> None:
    rows = (
        evidence("judge-1", (5, 5, 5)),
        evidence("judge-2", (1, 1, 1), candidates=("candidate-b", "candidate-a")),
    )
    report = compute_disagreement(rows)
    assert report.maximum_axis_delta == 0


def test_verdict_rejects_derived_views_from_different_evidence() -> None:
    rows = (evidence("judge-1"), evidence("judge-2"))
    report = compute_disagreement(rows)
    calibration = calibrate_against_anchors(rows[:1], anchors())
    with pytest.raises(ValueError, match="derived views"):
        build_qualitative_verdict(
            records=rows,
            disagreement=report,
            swaps=(),
            calibration=calibration,
            anchors=anchors(),
            candidate_models=("model-a", "model-b"),
            policy=POLICY,
        )


def test_missing_position_swap_coverage_suppresses() -> None:
    rows = (evidence("judge-1"), evidence("judge-2"))
    result = verdict(rows, anchor_set=anchors())
    assert result.winner is None and "missing_coverage" in result.suppression_reasons


def test_complete_stable_calibrated_panel_can_return_advisory_winner() -> None:
    rows = (evidence("judge-1"), evidence("judge-2"))
    swaps = tuple(
        (
            row,
            evidence(row.judge_model, (2, 2, 2), candidates=tuple(reversed(row.candidate_hashes))),
        )
        for row in rows
    )
    result = verdict(rows, swaps=swaps, anchor_set=anchors())
    assert result.winner == "candidate-a" and not result.suppression_reasons


def test_one_tie_among_decisive_judges_suppresses_winner() -> None:
    rows = (evidence("judge-1"), evidence("judge-2", (3, 3, 3)))
    swaps = (
        (
            rows[0],
            evidence("judge-1", (2, 2, 2), candidates=("candidate-b", "candidate-a")),
        ),
        (
            rows[1],
            evidence("judge-2", (3, 3, 3), candidates=("candidate-b", "candidate-a")),
        ),
    )
    result = verdict(rows, swaps=swaps, anchor_set=anchors())
    assert result.winner is None
    assert {"judge_disagreement", "equal_scores"} <= set(result.suppression_reasons)


def test_unrelated_swap_cannot_forge_position_coverage() -> None:
    rows = (evidence("judge-1"), evidence("judge-2"))
    unrelated = tuple(
        (
            evidence(row.judge_model, candidates=("c", "d")),
            evidence(row.judge_model, (2, 2, 2), candidates=("d", "c")),
        )
        for row in rows
    )
    with pytest.raises(ValueError, match="position swap"):
        verdict(rows, swaps=unrelated, anchor_set=anchors())


def test_swap_source_must_equal_the_immutable_panel_record() -> None:
    rows = (evidence("judge-1", (5, 5, 5)), evidence("judge-2", (5, 5, 5)))
    forged = tuple(
        (
            replace(row, scores=tuple((axis, 1) for axis in AXES), claimed_at_ms=999),
            evidence(row.judge_model, (5, 5, 5), candidates=("candidate-b", "candidate-a")),
        )
        for row in rows
    )
    with pytest.raises(ValueError, match="position swap"):
        verdict(rows, swaps=forged, anchor_set=anchors())


def test_reversed_evidence_is_normalized_against_pair_bound_anchor() -> None:
    anchor_set = anchors()
    reversed_row = evidence(
        "judge-1", (2, 2, 2), candidates=("candidate-b", "candidate-a")
    )
    calibration = calibrate_against_anchors((reversed_row,), anchor_set)
    assert calibration.calibrated
    assert calibration.signed_axis_errors == tuple((axis, 1.0) for axis in sorted(AXES))
    unrelated = evidence("judge-1", candidates=("candidate-c", "candidate-d"))
    assert not calibrate_against_anchors((unrelated,), anchor_set).calibrated


def test_forged_derived_report_is_rejected_even_with_matching_ids() -> None:
    rows = (evidence("judge-1"), evidence("judge-2"))
    report = compute_disagreement(rows)
    forged = replace(report, failure_count=99)
    calibration = calibrate_against_anchors(rows, anchors())
    with pytest.raises(ValueError, match="derived views"):
        build_qualitative_verdict(
            records=rows,
            disagreement=forged,
            swaps=(),
            calibration=calibration,
            anchors=anchors(),
            candidate_models=("model-a", "model-b"),
            policy=POLICY,
        )


def test_judged_calibration_modules_have_no_dispatch_or_router_authority() -> None:
    forbidden_modules = ("substrate.dispatch", "substrate.router")
    forbidden_callables = {"dispatch", "install", "select_driver", "as_dispatch_kwargs"}
    for path in (
        Path("substrate/antiek_bench/judged/calibration.py"),
        Path("substrate/antiek_bench/judged/disagreement.py"),
        Path("substrate/antiek_bench/judged/anchors.py"),
        Path("substrate/antiek_bench/judged/verdict.py"),
    ):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert all(
                    not alias.name.startswith(forbidden_modules)
                    and ".router" not in alias.name
                    for alias in node.names
                )
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                assert not module.startswith(forbidden_modules) and ".router" not in module
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                assert node.name not in forbidden_callables
