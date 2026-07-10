"""Position-order calibration derived from immutable judge evidence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .journal import EvidenceRecord

PairWinner = Literal["first", "second", "tie"]


@dataclass(frozen=True)
class PositionSwapReport:
    """A comparison of the same pair judged in both presentation orders."""

    first_evidence_id: str
    swapped_evidence_id: str
    judge_model: str
    candidate_hashes: tuple[str, str]
    axis_scores: tuple[tuple[str, int, int], ...]
    first_winner: PairWinner | None
    swapped_winner: PairWinner | None
    position_sensitive: bool
    failed_swap: bool

    @property
    def qualitative_winner(self) -> str | None:
        if self.failed_swap or self.position_sensitive or self.first_winner in {None, "tie"}:
            return None
        return self.candidate_hashes[0 if self.first_winner == "first" else 1]


def _winner(scores: tuple[int, ...]) -> PairWinner:
    """Require directional axis consensus; never invent a composite score."""
    if scores and all(score >= 3 for score in scores) and any(score > 3 for score in scores):
        return "first"
    if scores and all(score <= 3 for score in scores) and any(score < 3 for score in scores):
        return "second"
    return "tie"


def compare_position_swap(first: EvidenceRecord, swapped: EvidenceRecord) -> PositionSwapReport:
    """Normalize a reversed presentation and report order sensitivity.

    Rubric scores use the closed 1..5 pairwise scale: values above three favor
    the first presented candidate. Reversing a score therefore uses ``6-score``.
    The input records are frozen Sprint 1 evidence and are never rewritten.
    """
    if (
        first.week_id,
        first.suite_version,
        first.item_id_hash,
        first.task_class,
        first.rubric_version,
        first.judge_model.strip().casefold(),
        first.schema_version,
    ) != (
        swapped.week_id,
        swapped.suite_version,
        swapped.item_id_hash,
        swapped.task_class,
        swapped.rubric_version,
        swapped.judge_model.strip().casefold(),
        swapped.schema_version,
    ):
        raise ValueError("position swap identity does not match")
    if swapped.candidate_hashes != tuple(reversed(first.candidate_hashes)):
        raise ValueError("position swap must reverse the candidate order")
    if first.blinded_order != ("A", "B") or swapped.blinded_order != ("A", "B"):
        raise ValueError("position swap requires canonical blinded labels")

    failed = first.status != "ok" or swapped.status != "ok"
    if failed:
        axis_scores: tuple[tuple[str, int, int], ...] = ()
        first_winner = swapped_winner = None
    else:
        left = dict(first.scores)
        right = dict(swapped.scores)
        if left.keys() != right.keys():
            raise ValueError("position swap axis sets do not match")
        axis_scores = tuple((axis, score, 6 - right[axis]) for axis, score in first.scores)
        first_winner = _winner(tuple(left.values()))
        swapped_winner = _winner(tuple(normalized for _, _, normalized in axis_scores))
    return PositionSwapReport(
        first_evidence_id=first.evidence_id,
        swapped_evidence_id=swapped.evidence_id,
        judge_model=first.judge_model.strip(),
        candidate_hashes=first.candidate_hashes,
        axis_scores=axis_scores,
        first_winner=first_winner,
        swapped_winner=swapped_winner,
        position_sensitive=not failed and first_winner != swapped_winner,
        failed_swap=failed,
    )
