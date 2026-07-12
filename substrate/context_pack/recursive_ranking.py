"""Bounded advisory ranking and blinded replay for recursive context."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from html import escape

from .recursive_feedback import (
    FEEDBACK_POLICY_VERSION,
    RecursiveOutcomeReceipt,
    RecursiveTaskClass,
)
from .recursive_notes import RecursiveNotesPack, account_scope_digest

RANKING_POLICY_VERSION = "recursive-ranking-v1"
MIN_SAMPLES_PER_UNIT_TASK = 3
HALF_LIFE_DAYS = 28.0
MAX_POSITION_SHIFT = 2.0
MIN_REPLAY_SESSIONS = 10

_OUTCOME_WEIGHT = {
    "saved": 1.0,
    "cited": 1.0,
    "merged": 1.0,
    "followed_up": 0.75,
    "abandoned": -0.5,
    # Contradiction is valuable counterevidence, never a popularity failure.
    "contradicted": 0.5,
    "no_signal": 0.0,
}


@dataclass(frozen=True)
class AdvisoryFeature:
    unit_id: str
    text_digest: str
    task_class: RecursiveTaskClass
    score: float
    sample_count: int
    contradiction_count: int
    evidence_window_start_ms: int
    evidence_window_end_ms: int

    def __post_init__(self) -> None:
        if not self.unit_id.strip() or len(self.unit_id.encode("utf-8")) > 512:
            raise ValueError("advisory feature unit id is invalid")
        if len(self.text_digest) != 64 or any(
            character not in "0123456789abcdef" for character in self.text_digest
        ):
            raise ValueError("advisory feature text digest is invalid")
        if not math.isfinite(self.score) or not -1.0 <= self.score <= 1.0:
            raise ValueError("advisory feature score is invalid")
        if self.sample_count < MIN_SAMPLES_PER_UNIT_TASK:
            raise ValueError("advisory feature sample count is too small")
        if not 0 <= self.contradiction_count <= self.sample_count:
            raise ValueError("advisory contradiction count is invalid")
        if not 0 <= self.evidence_window_start_ms <= self.evidence_window_end_ms:
            raise ValueError("advisory evidence window is invalid")


@dataclass(frozen=True)
class RecursiveRankingSnapshot:
    owner_scope_digest: str
    task_class: RecursiveTaskClass
    generated_at_ms: int
    policy_version: str
    feedback_policy_version: str
    features: tuple[AdvisoryFeature, ...]

    def __post_init__(self) -> None:
        if len(self.owner_scope_digest) != 64:
            raise ValueError("ranking owner scope digest is invalid")
        _validate_task_class(self.task_class)
        if self.generated_at_ms < 0:
            raise ValueError("ranking generated time is invalid")
        if self.policy_version != RANKING_POLICY_VERSION:
            raise ValueError("ranking policy version is invalid")
        if self.feedback_policy_version != FEEDBACK_POLICY_VERSION:
            raise ValueError("ranking feedback policy version is invalid")
        if len({feature.unit_id for feature in self.features}) != len(self.features):
            raise ValueError("ranking snapshot contains duplicate unit features")


def _validate_task_class(task_class: str) -> None:
    if task_class not in {"distill", "synthesize", "wrestle", "book_qa", "research_reasoning"}:
        raise ValueError("recursive ranking task class is invalid")


def build_ranking_snapshot(
    *,
    owner_user_id: str,
    task_class: RecursiveTaskClass,
    receipts: Sequence[RecursiveOutcomeReceipt],
    now_ms: int,
) -> RecursiveRankingSnapshot:
    scope = account_scope_digest(owner_user_id)
    _validate_task_class(task_class)
    if now_ms < 0:
        raise ValueError("ranking snapshot time is invalid")
    aggregates: dict[str, tuple[str, list[tuple[float, int, bool]]]] = {}
    for receipt in receipts:
        if receipt.owner_scope_digest != scope:
            raise PermissionError("foreign feedback cannot enter ranking snapshot")
        if receipt.task_class != task_class or receipt.outcome == "no_signal":
            continue
        if receipt.observed_at_ms > now_ms + 300_000:
            raise ValueError("future feedback cannot enter ranking snapshot")
        age_ms = max(0, now_ms - receipt.observed_at_ms)
        decay = 0.5 ** (age_ms / (HALF_LIFE_DAYS * 86_400_000))
        weighted = max(-1.0, min(1.0, _OUTCOME_WEIGHT[receipt.outcome])) * decay
        for unit in receipt.units:
            prior = aggregates.get(unit.unit_id)
            if prior is not None and prior[0] != unit.text_digest:
                raise ValueError("ranking feedback contains conflicting unit digests")
            samples = prior[1] if prior is not None else []
            samples.append((weighted, receipt.observed_at_ms, receipt.outcome == "contradicted"))
            aggregates[unit.unit_id] = (unit.text_digest, samples)
    features: list[AdvisoryFeature] = []
    for unit_id, (text_digest, samples) in sorted(aggregates.items()):
        if len(samples) < MIN_SAMPLES_PER_UNIT_TASK:
            continue
        denominator = sum(
            0.5 ** (max(0, now_ms - observed_at) / (HALF_LIFE_DAYS * 86_400_000))
            for _, observed_at, _ in samples
        )
        score = sum(value for value, _, _ in samples) / max(denominator, 1e-12)
        features.append(
            AdvisoryFeature(
                unit_id=unit_id,
                text_digest=text_digest,
                task_class=task_class,
                score=max(-1.0, min(1.0, score)),
                sample_count=len(samples),
                contradiction_count=sum(1 for _, _, value in samples if value),
                evidence_window_start_ms=min(value for _, value, _ in samples),
                evidence_window_end_ms=max(value for _, value, _ in samples),
            )
        )
    return RecursiveRankingSnapshot(
        owner_scope_digest=scope,
        task_class=task_class,
        generated_at_ms=now_ms,
        policy_version=RANKING_POLICY_VERSION,
        feedback_policy_version=FEEDBACK_POLICY_VERSION,
        features=tuple(features),
    )


def apply_advisory_ranking(
    pack: RecursiveNotesPack,
    *,
    owner_user_id: str,
    snapshot: RecursiveRankingSnapshot,
) -> RecursiveNotesPack:
    if snapshot.owner_scope_digest != account_scope_digest(owner_user_id):
        raise PermissionError("ranking snapshot owner scope does not match")
    current_digests = {unit.unit_id: unit.text_digest for unit in pack.units}
    scores = {
        feature.unit_id: feature.score
        for feature in snapshot.features
        if current_digests.get(feature.unit_id) == feature.text_digest
    }
    baseline = {unit.unit_id: index for index, unit in enumerate(pack.units)}
    remaining = list(pack.units)
    ranked = []
    recent_assets: list[str] = []
    while remaining:
        ordered = sorted(
            remaining,
            key=lambda unit: (
                baseline[unit.unit_id] - scores.get(unit.unit_id, 0.0) * MAX_POSITION_SHIFT,
                baseline[unit.unit_id],
                unit.unit_id,
            ),
        )
        choice = ordered[0]
        if len(recent_assets) >= 2 and recent_assets[-2:] == [choice.asset_id] * 2:
            alternative = next(
                (unit for unit in ordered if unit.asset_id != choice.asset_id),
                None,
            )
            if alternative is not None:
                choice = alternative
        ranked.append(choice)
        recent_assets.append(choice.asset_id)
        remaining.remove(choice)
    return RecursiveNotesPack(
        units=tuple(ranked),
        exclusions=pack.exclusions,
        token_estimate=pack.token_estimate,
        token_budget=pack.token_budget,
        candidate_count=pack.candidate_count,
        advisory_previews=pack.advisory_previews,
        advisory_token_estimate=pack.advisory_token_estimate,
    )


@dataclass(frozen=True)
class ReplaySession:
    session_id: str
    task_class: RecursiveTaskClass
    baseline_unit_ids: tuple[str, ...]
    baseline_text_digests: tuple[str, ...]
    relevant_unit_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _validate_task_class(self.task_class)
        if not self.session_id.strip() or len(self.session_id.encode("utf-8")) > 512:
            raise ValueError("replay session id is invalid")
        if len(self.baseline_unit_ids) > 256 or len(self.relevant_unit_ids) > 256:
            raise ValueError("replay session unit bound exceeded")
        if len(set(self.baseline_unit_ids)) != len(self.baseline_unit_ids):
            raise ValueError("replay baseline contains duplicate units")
        if len(self.baseline_text_digests) != len(self.baseline_unit_ids) or any(
            len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest)
            for digest in self.baseline_text_digests
        ):
            raise ValueError("replay baseline text digests are invalid")
        if not set(self.relevant_unit_ids).issubset(self.baseline_unit_ids):
            raise ValueError("replay relevance must reference baseline units")


@dataclass(frozen=True)
class WeeklyReplayReport:
    week_id: str
    task_class: RecursiveTaskClass
    blinded_session_count: int
    baseline_mean_reciprocal_rank: float
    advisory_mean_reciprocal_rank: float
    delta_mean: float
    confidence_low: float
    confidence_high: float
    wins: int
    losses: int
    ties: int
    minimum_samples_met: bool
    auto_promoted: bool = False
    policy_version: str = RANKING_POLICY_VERSION


def _advisory_ids(unit_ids: Sequence[str], scores: Mapping[str, float]) -> tuple[str, ...]:
    baseline = {unit_id: index for index, unit_id in enumerate(unit_ids)}
    return tuple(
        sorted(
            unit_ids,
            key=lambda unit_id: (
                baseline[unit_id] - scores.get(unit_id, 0.0) * MAX_POSITION_SHIFT,
                baseline[unit_id],
                unit_id,
            ),
        )
    )


def _reciprocal_rank(order: Sequence[str], relevant: set[str]) -> float:
    for index, unit_id in enumerate(order, 1):
        if unit_id in relevant:
            return 1.0 / index
    return 0.0


def weekly_replay(
    *,
    week_id: str,
    task_class: RecursiveTaskClass,
    sessions: Sequence[ReplaySession],
    snapshot: RecursiveRankingSnapshot,
) -> WeeklyReplayReport:
    _validate_task_class(task_class)
    if not week_id.strip() or len(week_id.encode("utf-8")) > 64:
        raise ValueError("replay week id is invalid")
    if snapshot.task_class != task_class:
        raise ValueError("replay task class conflicts with ranking snapshot")
    deltas: list[float] = []
    baseline_values: list[float] = []
    advisory_values: list[float] = []
    features = {feature.unit_id: feature for feature in snapshot.features}
    blinded: set[str] = set()
    for session in sessions:
        if session.task_class != task_class:
            continue
        blinded_id = hashlib.sha256(
            f"recursive-replay-v1:{session.session_id}".encode()
        ).hexdigest()
        if blinded_id in blinded:
            continue
        blinded.add(blinded_id)
        relevant = set(session.relevant_unit_ids)
        current_digests = dict(
            zip(
                session.baseline_unit_ids,
                session.baseline_text_digests,
                strict=True,
            )
        )
        scores = {
            unit_id: feature.score
            for unit_id, feature in features.items()
            if current_digests.get(unit_id) == feature.text_digest
        }
        baseline_value = _reciprocal_rank(session.baseline_unit_ids, relevant)
        advisory_value = _reciprocal_rank(
            _advisory_ids(session.baseline_unit_ids, scores), relevant
        )
        baseline_values.append(baseline_value)
        advisory_values.append(advisory_value)
        deltas.append(advisory_value - baseline_value)
    count = len(deltas)
    mean = sum(deltas) / count if count else 0.0
    if count > 1:
        variance = sum((value - mean) ** 2 for value in deltas) / (count - 1)
        margin = 1.96 * math.sqrt(variance / count)
    else:
        margin = 0.0
    return WeeklyReplayReport(
        week_id=week_id,
        task_class=task_class,
        blinded_session_count=len(blinded),
        baseline_mean_reciprocal_rank=(sum(baseline_values) / count if count else 0.0),
        advisory_mean_reciprocal_rank=(sum(advisory_values) / count if count else 0.0),
        delta_mean=mean,
        confidence_low=mean - margin,
        confidence_high=mean + margin,
        wins=sum(value > 0 for value in deltas),
        losses=sum(value < 0 for value in deltas),
        ties=sum(value == 0 for value in deltas),
        minimum_samples_met=count >= MIN_REPLAY_SESSIONS,
        auto_promoted=False,
    )


def replay_report_html(report: WeeklyReplayReport) -> str:
    """Render the human audit as HTML without session or unit identifiers."""

    verdict = (
        "eligible for operator review" if report.minimum_samples_met else "sparse; no decision"
    )
    return (
        '<!doctype html><html><head><meta charset="utf-8"><title>'
        f"Recursive context replay {escape(report.week_id)}</title></head><body>"
        f"<main><h1>Recursive context weekly replay</h1><p>Task: {escape(report.task_class)}</p>"
        f"<p>Blinded sessions: {report.blinded_session_count}</p>"
        f"<p>Baseline MRR: {report.baseline_mean_reciprocal_rank:.4f}</p>"
        f"<p>Advisory MRR: {report.advisory_mean_reciprocal_rank:.4f}</p>"
        f"<p>Delta: {report.delta_mean:.4f} "
        f"(95% CI {report.confidence_low:.4f} to {report.confidence_high:.4f})</p>"
        f"<p>Wins/losses/ties: {report.wins}/{report.losses}/{report.ties}</p>"
        f"<p>Decision: {verdict}; auto_promoted=false.</p></main></body></html>"
    )
