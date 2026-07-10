"""Independent-judge disagreement views over immutable evidence."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from .journal import EvidenceRecord


@dataclass(frozen=True)
class AxisDisagreement:
    axis: str
    minimum: int
    maximum: int
    delta: int
    effective_sample_size: int


@dataclass(frozen=True)
class DisagreementReport:
    evidence_ids: tuple[str, ...]
    expected_judges: tuple[str, ...]
    axes: tuple[AxisDisagreement, ...]
    judge_winners: tuple[tuple[str, str | None], ...]
    winner_disagreement: bool
    failure_count: int
    effective_sample_size: int
    expected_sample_size: int
    missing_judges: tuple[str, ...]
    mixed_rubric_versions: bool
    condorcet_cycle: bool

    @property
    def maximum_axis_delta(self) -> int | None:
        return max((axis.delta for axis in self.axes), default=None)


def evidence_winner(record: EvidenceRecord) -> str | None:
    """Return the candidate hash favored by one successful evidence row."""
    if record.status != "ok":
        return None
    values = tuple(score for _, score in record.scores)
    if values and all(score >= 3 for score in values) and any(score > 3 for score in values):
        return record.candidate_hashes[0]
    if values and all(score <= 3 for score in values) and any(score < 3 for score in values):
        return record.candidate_hashes[1]
    return None


def compute_disagreement(
    records: Iterable[EvidenceRecord], *, expected_judges: Iterable[str] = ()
) -> DisagreementReport:
    """Summarize observed judge variance without imputing missing rows as zero."""
    rows = tuple(records)
    if rows and len(
        {(row.week_id, row.suite_version, row.item_id_hash, row.task_class) for row in rows}
    ) != 1:
        raise ValueError("disagreement evidence must share week, suite, item, and task")
    seen: set[tuple[tuple[str, str], str]] = set()
    for row in rows:
        ordered = sorted(row.candidate_hashes)
        canonical = (ordered[0], ordered[1])
        key = (canonical, row.judge_model.strip().casefold())
        if key in seen:
            raise ValueError("duplicate judge evidence for candidate pair")
        seen.add(key)
    successful = tuple(row for row in rows if row.status == "ok")
    pair_scores: dict[tuple[tuple[str, str], str], list[int]] = defaultdict(list)
    for row in successful:
        ordered = sorted(row.candidate_hashes)
        canonical = (ordered[0], ordered[1])
        reversed_order = row.candidate_hashes != canonical
        for axis, score in row.scores:
            pair_scores[(canonical, axis)].append(6 - score if reversed_order else score)
    axis_deltas: dict[str, list[int]] = defaultdict(list)
    axis_values: dict[str, list[int]] = defaultdict(list)
    for (_, axis), values in pair_scores.items():
        axis_deltas[axis].append(max(values) - min(values))
        axis_values[axis].extend(values)
    axes = tuple(
        AxisDisagreement(
            axis,
            min(axis_values[axis]),
            max(axis_values[axis]),
            max(deltas),
            len(axis_values[axis]),
        )
        for axis, deltas in sorted(axis_deltas.items())
    )
    winners = tuple((row.judge_model, evidence_winner(row)) for row in successful)
    decisive = {winner for _, winner in winners if winner is not None}
    indeterminate = any(winner is None for _, winner in winners)
    expected = {judge.strip().casefold(): judge.strip() for judge in expected_judges}
    observed = {row.judge_model.strip().casefold() for row in rows}
    missing = tuple(expected[key] for key in sorted(expected.keys() - observed))
    expected_size = len(expected) if expected else len(rows)
    return DisagreementReport(
        evidence_ids=tuple(sorted(row.evidence_id for row in rows)),
        expected_judges=tuple(expected[key] for key in sorted(expected)),
        axes=axes,
        judge_winners=winners,
        winner_disagreement=len(decisive) > 1 or bool(decisive and indeterminate),
        failure_count=len(rows) - len(successful),
        effective_sample_size=len(successful),
        expected_sample_size=expected_size,
        missing_judges=missing,
        mixed_rubric_versions=len({row.rubric_version for row in rows}) > 1,
        condorcet_cycle=_has_condorcet_cycle(successful),
    )


def _has_condorcet_cycle(records: tuple[EvidenceRecord, ...]) -> bool:
    votes: dict[tuple[str, str], int] = defaultdict(int)
    candidates: set[str] = set()
    for row in records:
        winner = evidence_winner(row)
        if winner is None:
            continue
        loser = row.candidate_hashes[1] if winner == row.candidate_hashes[0] else row.candidate_hashes[0]
        votes[(winner, loser)] += 1
        candidates.update(row.candidate_hashes)
    beats = {
        (left, right)
        for left in candidates
        for right in candidates
        if left != right and votes[(left, right)] > votes[(right, left)]
    }
    return any(
        (a, b) in beats and (b, c) in beats and (c, a) in beats
        for a in candidates
        for b in candidates
        for c in candidates
        if len({a, b, c}) == 3
    )
