"""Fail-closed advisory interpretation of qualitative judge evidence."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from .anchors import AnchorCalibration, AnchorSet, calibrate_against_anchors
from .calibration import compare_position_swap
from .disagreement import DisagreementReport, compute_disagreement
from .journal import EvidenceRecord

SuppressionReason = Literal[
    "position_sensitive",
    "judge_disagreement",
    "missing_coverage",
    "self_judging",
    "mixed_rubric_versions",
    "equal_scores",
    "failed_swap",
    "condorcet_cycle",
    "uncalibrated",
]
SUPPRESSION_REASONS: tuple[SuppressionReason, ...] = (
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
VERDICT_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class VerdictPolicy:
    version: str
    maximum_axis_delta: int
    minimum_judges: int
    source: str
    reverser: str

    def __post_init__(self) -> None:
        if not self.version.strip() or not self.source.strip() or not self.reverser.strip():
            raise ValueError("policy version, source, and reverser are required")
        if (
            isinstance(self.maximum_axis_delta, bool)
            or isinstance(self.minimum_judges, bool)
            or self.maximum_axis_delta < 0
            or self.minimum_judges < 1
        ):
            raise ValueError("policy thresholds are invalid")


@dataclass(frozen=True)
class QualitativeVerdict:
    winner: str | None
    suppression_reasons: tuple[SuppressionReason, ...]
    calibrated: bool
    effective_sample_size: int
    policy_version: str
    advisory: bool = True
    schema_version: int = VERDICT_SCHEMA_VERSION


def build_qualitative_verdict(
    *,
    records: Iterable[EvidenceRecord],
    disagreement: DisagreementReport,
    swaps: Iterable[tuple[EvidenceRecord, EvidenceRecord]],
    calibration: AnchorCalibration,
    anchors: AnchorSet | None,
    candidate_models: Iterable[str],
    policy: VerdictPolicy,
) -> QualitativeVerdict:
    """Interpret evidence without acquiring dispatch, routing, or promotion authority."""
    rows = tuple(records)
    raw_swaps = tuple(swaps)
    swap_rows = tuple(
        compare_position_swap(first, reversed_row) for first, reversed_row in raw_swaps
    )
    reasons: set[SuppressionReason] = set()
    recomputed_disagreement = compute_disagreement(
        rows, expected_judges=disagreement.expected_judges
    )
    recomputed_calibration = calibrate_against_anchors(rows, anchors)
    if disagreement != recomputed_disagreement or calibration != recomputed_calibration:
        raise ValueError("derived views do not match verdict evidence")
    if any(swap.position_sensitive for swap in swap_rows):
        reasons.add("position_sensitive")
    if any(swap.failed_swap for swap in swap_rows):
        reasons.add("failed_swap")
    successful = {row.evidence_id: row for row in rows if row.status == "ok"}
    covered: set[str] = set()
    for (first, _), swap in zip(raw_swaps, swap_rows, strict=True):
        source = successful.get(swap.first_evidence_id)
        if (
            source is None
            or source != first
            or swap.first_evidence_id in covered
            or swap.judge_model.strip().casefold() != source.judge_model.strip().casefold()
            or swap.candidate_hashes != source.candidate_hashes
        ):
            raise ValueError("position swap does not match verdict evidence")
        covered.add(swap.first_evidence_id)
    if successful.keys() - covered:
        reasons.add("missing_coverage")
    maximum_delta = disagreement.maximum_axis_delta
    if disagreement.winner_disagreement or (
        maximum_delta is not None and maximum_delta > policy.maximum_axis_delta
    ):
        reasons.add("judge_disagreement")
    if (
        disagreement.effective_sample_size < policy.minimum_judges
        or disagreement.effective_sample_size < disagreement.expected_sample_size
        or disagreement.missing_judges
        or disagreement.failure_count
    ):
        reasons.add("missing_coverage")
    model_ids = {model.strip().casefold() for model in candidate_models}
    if any(row.judge_model.strip().casefold() in model_ids for row in rows):
        reasons.add("self_judging")
    if disagreement.mixed_rubric_versions:
        reasons.add("mixed_rubric_versions")
    if disagreement.condorcet_cycle:
        reasons.add("condorcet_cycle")
    decisive = {winner for _, winner in disagreement.judge_winners if winner is not None}
    if not decisive or any(winner is None for _, winner in disagreement.judge_winners):
        reasons.add("equal_scores")
    if not calibration.calibrated:
        reasons.add("uncalibrated")
    ordered = tuple(reason for reason in SUPPRESSION_REASONS if reason in reasons)
    winner = next(iter(decisive)) if len(decisive) == 1 and not ordered else None
    return QualitativeVerdict(
        winner=winner,
        suppression_reasons=ordered,
        calibrated=calibration.calibrated,
        effective_sample_size=disagreement.effective_sample_size,
        policy_version=policy.version,
    )
