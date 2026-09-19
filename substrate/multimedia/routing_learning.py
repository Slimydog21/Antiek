"""Immutable evidence and recommendations for multimedia cost-quality routing."""

from __future__ import annotations

import hashlib
import hmac
import json
import math
from collections import defaultdict
from collections.abc import Iterable
from datetime import datetime
from typing import Literal, TypeVar, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

from substrate.contracts.multimedia import RoutePolicy
from substrate.multimedia.provider_router import GenerationKind, ProviderRoute

CostBasis = Literal[
    "ledger_actual",
    "ledger_ceiling_settlement",
    "ledger_hold_open",
    "zero_non_billable",
]
TerminalStatus = Literal["succeeded", "failed", "cancelled"]
RegenerationReason = Literal[
    "quality_rejection", "provider_failure", "operator_preference_change", "unrelated_edit"
]
RecommendationAction = Literal[
    "retain", "consider_promote", "consider_demote", "insufficient_evidence"
]
ConfidenceStatus = Literal["insufficient", "reportable", "replacement_ready"]

_MIN_ELIGIBLE = 10
_MIN_PASSING = 5
_MIN_REPLACEMENT = 30
_MATERIAL_IMPROVEMENT = 1.10
_MAX_ROWS = 10_000
_MAX_POLICIES = 512
_MAX_COHORTS = 512
_MIN_ACCOUNTING_KEY_BYTES = 32


class RoutingLearningError(ValueError):
    """Routing evidence is incomplete, conflicting, or gameable."""


class _EvidenceModel(BaseModel):  # type: ignore[misc]
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        allow_inf_nan=False,
        revalidate_instances="always",
    )


EvidenceT = TypeVar("EvidenceT", bound=_EvidenceModel)


class RoutePolicySnapshot(_EvidenceModel):
    policy_version_id: str
    route_policy: RoutePolicy
    provider: str = Field(min_length=1, max_length=128)
    model: str = Field(min_length=1, max_length=128)
    endpoint_capability: str = Field(min_length=1, max_length=128)
    generation_kind: GenerationKind
    catalog_version: str = Field(min_length=1, max_length=128)
    catalog_digest: str = Field(pattern="^[0-9a-f]{64}$")
    quality_knobs: tuple[tuple[str, str], ...] = Field(max_length=64)
    fallback_policy_version_ids: tuple[str, ...] = Field(default=(), max_length=32)
    estimator_version: str = Field(min_length=1, max_length=128)
    created_reason: Literal["manual_initial", "operator_override", "learned_recommendation"]
    supersedes_policy_version_id: str | None = None
    evidence_report_id: str | None = None

    @model_validator(mode="after")  # type: ignore[untyped-decorator]
    def identity_and_lineage_are_bound(self) -> RoutePolicySnapshot:
        _unique((key for key, _ in self.quality_knobs), "quality knob names")
        _unique(self.fallback_policy_version_ids, "fallback policy ids")
        if tuple(sorted(self.quality_knobs)) != self.quality_knobs:
            raise RoutingLearningError("quality knobs must be canonical and sorted")
        if any(not key or len(key) > 128 or len(value) > 512 for key, value in self.quality_knobs):
            raise RoutingLearningError("quality knobs exceed their string boundary")
        if any(not value or len(value) > 128 for value in self.fallback_policy_version_ids):
            raise RoutingLearningError("fallback policy ids exceed their string boundary")
        if self.policy_version_id in self.fallback_policy_version_ids:
            raise RoutingLearningError("a policy cannot fall back to itself")
        if self.created_reason == "learned_recommendation" and not self.evidence_report_id:
            raise RoutingLearningError("learned policies require an evidence report")
        expected = _content_id("policy", _policy_content(self))
        if self.policy_version_id != expected:
            raise RoutingLearningError("policy version id does not match canonical content")
        return self


class ProjectedRouteCost(_EvidenceModel):
    projection_id: str
    policy_version_id: str
    asset_id: str = Field(min_length=1, max_length=128)
    revision_id: str = Field(min_length=1, max_length=128)
    steering_event_id: str | None = None
    target_ids: tuple[str, ...] = Field(min_length=1, max_length=512)
    generation_kind: GenerationKind
    provider_route_digest: str = Field(pattern="^[0-9a-f]{64}$")
    estimated_microdollars: int = Field(ge=0)
    estimate_basis: Literal["router_projection"] = "router_projection"
    estimator_version: str = Field(min_length=1, max_length=128)
    estimated_at: datetime

    @model_validator(mode="after")  # type: ignore[untyped-decorator]
    def projection_is_canonical(self) -> ProjectedRouteCost:
        _aware(self.estimated_at, "estimated_at")
        _unique(self.target_ids, "projection target ids")
        expected = _content_id("projection", _projection_content(self))
        if self.projection_id != expected:
            raise RoutingLearningError("projection id does not match canonical content")
        return self


class LedgerCostEvidence(_EvidenceModel):
    receipt_id: str = Field(min_length=1, max_length=128)
    receipt_digest: str = Field(pattern="^[0-9a-f]{64}$")
    cost_basis: CostBasis
    reconciled_cost_microdollars: int | None = Field(default=None, ge=0)
    binding_digest: str = Field(pattern="^[0-9a-f]{64}$")
    authority_mac: str = Field(pattern="^[0-9a-f]{64}$")

    @model_validator(mode="after")  # type: ignore[untyped-decorator]
    def amount_matches_basis(self) -> LedgerCostEvidence:
        has_cost = self.reconciled_cost_microdollars is not None
        if self.cost_basis in {"ledger_actual", "ledger_ceiling_settlement"} and not has_cost:
            raise RoutingLearningError("reconciled cost basis requires a ledger amount")
        if self.cost_basis in {"ledger_hold_open", "zero_non_billable"} and has_cost:
            raise RoutingLearningError("non-reconciled cost basis cannot claim realized cost")
        return self


class RouteOutcomeObservation(_EvidenceModel):
    observation_id: str
    policy_version_id: str
    execution_id: str = Field(min_length=1, max_length=128)
    authorization_id: str = Field(min_length=1, max_length=128)
    asset_id: str = Field(min_length=1, max_length=128)
    revision_id: str = Field(min_length=1, max_length=128)
    provider: str = Field(min_length=1, max_length=128)
    model: str = Field(min_length=1, max_length=128)
    endpoint_capability: str = Field(min_length=1, max_length=128)
    generation_kind: GenerationKind
    route_policy: RoutePolicy
    duration_seconds: float | None = Field(default=None, ge=0, le=2700)
    width_px: int = Field(ge=1, le=7680)
    height_px: int = Field(ge=1, le=4320)
    request_body_digest: str = Field(pattern="^[0-9a-f]{64}$")
    terminal_status: TerminalStatus
    started_at: datetime
    terminal_at: datetime
    accounting: LedgerCostEvidence
    output_file_sha256s: tuple[str, ...] = Field(default=(), max_length=128)

    @model_validator(mode="after")  # type: ignore[untyped-decorator]
    def terminal_evidence_is_coherent(self) -> RouteOutcomeObservation:
        _aware(self.started_at, "started_at")
        _aware(self.terminal_at, "terminal_at")
        if self.terminal_at < self.started_at:
            raise RoutingLearningError("terminal time precedes trusted start time")
        _unique(self.output_file_sha256s, "output hashes")
        if any(
            len(value) != 64 or set(value) - set("0123456789abcdef")
            for value in self.output_file_sha256s
        ):
            raise RoutingLearningError("output hashes must be lowercase sha256")
        if self.terminal_status == "succeeded" and not self.output_file_sha256s:
            raise RoutingLearningError("successful outcomes require output hashes")
        expected = _content_id("outcome", _outcome_content(self))
        if self.observation_id != expected:
            raise RoutingLearningError("observation id does not match canonical content")
        return self

    @property
    def latency_ms(self) -> int:
        return round((self.terminal_at - self.started_at).total_seconds() * 1000)


class VerifierResult(_EvidenceModel):
    verifier_id: str = Field(min_length=1, max_length=128)
    verifier_version: str = Field(pattern=r"^[1-9][0-9]*\.[0-9]+$")
    criterion: str = Field(min_length=1, max_length=256)
    score: float = Field(ge=0, le=1)
    threshold: float = Field(ge=0, le=1)
    passed: bool
    evidence_digest: str = Field(pattern="^[0-9a-f]{64}$")

    @model_validator(mode="after")  # type: ignore[untyped-decorator]
    def pass_matches_score(self) -> VerifierResult:
        if self.passed != (self.score >= self.threshold):
            raise RoutingLearningError("verifier pass conflicts with score threshold")
        return self


class RegenerationEvidence(_EvidenceModel):
    execution_id: str = Field(min_length=1, max_length=128)
    originating_execution_id: str = Field(min_length=1, max_length=128)
    authorization_id: str = Field(min_length=1, max_length=128)
    target_ids: tuple[str, ...] = Field(min_length=1, max_length=512)
    reason: RegenerationReason
    accounting: LedgerCostEvidence
    latency_ms: int = Field(ge=0)

    @model_validator(mode="after")  # type: ignore[untyped-decorator]
    def targets_are_unique(self) -> RegenerationEvidence:
        _unique(self.target_ids, "regeneration target ids")
        return self


class OutcomeEvaluation(_EvidenceModel):
    evaluation_id: str
    observation_id: str
    verifier_suite_version: str = Field(pattern=r"^[1-9][0-9]*\.[0-9]+$")
    verifier_results: tuple[VerifierResult, ...] = Field(min_length=1, max_length=128)
    user_rating: int | None = Field(default=None, ge=1, le=5)
    rated_at: datetime | None = None
    regenerations: tuple[RegenerationEvidence, ...] = Field(default=(), max_length=128)
    evaluated_at: datetime

    @model_validator(mode="after")  # type: ignore[untyped-decorator]
    def evaluation_is_canonical(self) -> OutcomeEvaluation:
        _aware(self.evaluated_at, "evaluated_at")
        if (self.user_rating is None) != (self.rated_at is None):
            raise RoutingLearningError("rating and rating timestamp must be supplied together")
        if self.rated_at is not None:
            _aware(self.rated_at, "rated_at")
            if self.rated_at > self.evaluated_at:
                raise RoutingLearningError("rating occurs after evaluation cutoff")
        _unique((row.verifier_id for row in self.verifier_results), "verifier ids")
        suite_major = self.verifier_suite_version.split(".", 1)[0]
        if any(
            row.verifier_version.split(".", 1)[0] != suite_major for row in self.verifier_results
        ):
            raise RoutingLearningError("verifier result major version conflicts with its suite")
        _unique((row.execution_id for row in self.regenerations), "regeneration executions")
        expected = _content_id("evaluation", _evaluation_content(self))
        if self.evaluation_id != expected:
            raise RoutingLearningError("evaluation id does not match canonical content")
        return self

    @property
    def verifier_pass(self) -> bool:
        return all(row.passed for row in self.verifier_results)

    @property
    def verifier_score(self) -> float:
        return min(row.score for row in self.verifier_results)


class CohortKey(_EvidenceModel):
    generation_kind: GenerationKind
    endpoint_capability: str
    duration_bucket: str
    resolution_bucket: str
    route_policy: RoutePolicy
    verifier_suite_major: int = Field(ge=1)
    evaluation_mode: Literal["verifier_only", "user_rated"]


class LearningSample(_EvidenceModel):
    observation: RouteOutcomeObservation
    evaluation: OutcomeEvaluation
    cohort: CohortKey
    target_ids: tuple[str, ...] = ()

    @model_validator(mode="after")  # type: ignore[untyped-decorator]
    def regeneration_lineage_is_bound(self) -> LearningSample:
        _unique(self.target_ids, "learning target ids")
        targets = set(self.target_ids)
        for row in self.evaluation.regenerations:
            if _penalty_reason(row) and not targets.intersection(row.target_ids):
                raise RoutingLearningError(
                    "penalized regeneration does not overlap original targets"
                )
        return self


class ExcludedObservation(_EvidenceModel):
    observation_id: str
    reason: str


class PolicyEvidenceRow(_EvidenceModel):
    cohort: CohortKey
    policy_version_id: str
    eligible_sample_count: int = Field(ge=0)
    passing_sample_count: int = Field(ge=0)
    rated_sample_count: int = Field(ge=0)
    failure_count: int = Field(ge=0)
    penalized_regeneration_count: int = Field(ge=0)
    total_lifecycle_cost_microdollars: int = Field(ge=0)
    latency_p50_ms: int = Field(ge=0)
    latency_p95_ms: int = Field(ge=0)
    quality_point_estimate: float = Field(ge=0, le=1)
    quality_lower_bound: float = Field(ge=0, le=1)
    effective_cost_per_passing_output_microdollars: int | None = Field(default=None, ge=0)
    quality_per_dollar_lower_bound: float | None = Field(default=None, ge=0)
    confidence_status: ConfidenceStatus
    observation_ids: tuple[str, ...]


class RouterRecommendation(_EvidenceModel):
    cohort: CohortKey
    current_policy_version_id: str
    proposed_policy_version_id: str | None
    action: RecommendationAction
    reason_codes: tuple[str, ...]
    supporting_observation_ids: tuple[str, ...]


class RouterRecommendationReport(_EvidenceModel):
    report_id: str
    schema_version: Literal["antiek.routing-learning.v1"] = "antiek.routing-learning.v1"
    algorithm_version: Literal["conservative-qpd-v1"] = "conservative-qpd-v1"
    generated_at: datetime
    policy_rows: tuple[PolicyEvidenceRow, ...]
    recommendations: tuple[RouterRecommendation, ...]
    excluded_observations: tuple[ExcludedObservation, ...]
    input_observation_ids: tuple[str, ...]

    @model_validator(mode="after")  # type: ignore[untyped-decorator]
    def report_is_canonical(self) -> RouterRecommendationReport:
        _aware(self.generated_at, "generated_at")
        expected = _content_id("report", _report_content(self))
        if self.report_id != expected:
            raise RoutingLearningError("report id does not match canonical content")
        return self


def create_policy_snapshot(
    *,
    route_policy: RoutePolicy,
    provider: str,
    model: str,
    endpoint_capability: str,
    generation_kind: GenerationKind,
    catalog_version: str,
    catalog_digest: str,
    quality_knobs: dict[str, str],
    estimator_version: str,
    created_reason: Literal["manual_initial", "operator_override", "learned_recommendation"],
    fallback_policy_version_ids: tuple[str, ...] = (),
    supersedes_policy_version_id: str | None = None,
    evidence_report_id: str | None = None,
) -> RoutePolicySnapshot:
    values = {
        "route_policy": route_policy,
        "provider": provider,
        "model": model,
        "endpoint_capability": endpoint_capability,
        "generation_kind": generation_kind,
        "catalog_version": catalog_version,
        "catalog_digest": catalog_digest,
        "quality_knobs": tuple(sorted(quality_knobs.items())),
        "fallback_policy_version_ids": fallback_policy_version_ids,
        "estimator_version": estimator_version,
        "created_reason": created_reason,
        "supersedes_policy_version_id": supersedes_policy_version_id,
        "evidence_report_id": evidence_report_id,
    }
    return cast(
        RoutePolicySnapshot,
        RoutePolicySnapshot.model_validate(
            {"policy_version_id": _content_id("policy", values), **values}
        ),
    )


def create_projected_route_cost(
    *,
    policy: RoutePolicySnapshot,
    asset_id: str,
    revision_id: str,
    target_ids: tuple[str, ...],
    generation_kind: GenerationKind,
    route: ProviderRoute,
    estimator_version: str,
    estimated_at: datetime,
    steering_event_id: str | None = None,
) -> ProjectedRouteCost:
    if (
        policy.generation_kind != generation_kind
        or policy.provider != route.provider
        or policy.model != route.model
        or policy.route_policy != route.route_policy
    ):
        raise RoutingLearningError("projected route conflicts with policy snapshot")
    route_digest = _digest(route.model_dump(mode="json"))
    values = {
        "policy_version_id": policy.policy_version_id,
        "asset_id": asset_id,
        "revision_id": revision_id,
        "steering_event_id": steering_event_id,
        "target_ids": target_ids,
        "generation_kind": generation_kind,
        "provider_route_digest": route_digest,
        "estimated_microdollars": round(route.estimated_cost_usd * 1_000_000),
        "estimate_basis": "router_projection",
        "estimator_version": estimator_version,
        "estimated_at": estimated_at,
    }
    return cast(
        ProjectedRouteCost,
        ProjectedRouteCost.model_validate(
            {"projection_id": _content_id("projection", values), **values}
        ),
    )


def create_ledger_cost_evidence(
    *,
    accounting_key: bytes,
    receipt_id: str,
    receipt_digest: str,
    cost_basis: CostBasis,
    reconciled_cost_microdollars: int | None,
    binding: dict[str, object],
) -> LedgerCostEvidence:
    values = {
        "receipt_id": receipt_id,
        "receipt_digest": receipt_digest,
        "cost_basis": cost_basis,
        "reconciled_cost_microdollars": reconciled_cost_microdollars,
        "binding_digest": _digest(binding),
    }
    return LedgerCostEvidence(
        **values,
        authority_mac=hmac.new(
            _accounting_key(accounting_key), _canonical(values), hashlib.sha256
        ).hexdigest(),
    )


def create_outcome_observation(**values: object) -> RouteOutcomeObservation:
    return cast(
        RouteOutcomeObservation,
        RouteOutcomeObservation.model_validate(
            {"observation_id": _content_id("outcome", values), **values}
        ),
    )


def create_outcome_evaluation(**values: object) -> OutcomeEvaluation:
    return cast(
        OutcomeEvaluation,
        OutcomeEvaluation.model_validate(
            {"evaluation_id": _content_id("evaluation", values), **values}
        ),
    )


def compile_recommendation_report(
    *,
    snapshots: tuple[RoutePolicySnapshot, ...],
    samples: tuple[LearningSample, ...],
    current_policy_by_cohort: dict[CohortKey, str],
    generated_at: datetime,
    accounting_verification_key: bytes,
) -> RouterRecommendationReport:
    """Compile deterministic review-only evidence without routing or accounting I/O."""
    if len(samples) > _MAX_ROWS:
        raise RoutingLearningError("learning sample ceiling exceeded")
    if len(snapshots) > _MAX_POLICIES:
        raise RoutingLearningError("policy snapshot ceiling exceeded")
    if len(current_policy_by_cohort) > _MAX_COHORTS:
        raise RoutingLearningError("current cohort ceiling exceeded")
    _aware(generated_at, "generated_at")
    key = _accounting_key(accounting_verification_key)
    validated_snapshots = tuple(_revalidate(RoutePolicySnapshot, row) for row in snapshots)
    validated_samples = tuple(_revalidate(LearningSample, row) for row in samples)
    policies = {row.policy_version_id: row for row in validated_snapshots}
    if len(policies) != len(snapshots):
        raise RoutingLearningError("policy version ids must be unique")
    seen_executions: set[str] = set()
    seen_authorizations: set[str] = set()
    seen_receipts: set[str] = set()
    seen_outputs: set[str] = set()
    seen_regenerations: set[str] = set()
    grouped: dict[tuple[CohortKey, str], list[LearningSample]] = defaultdict(list)
    excluded: list[ExcludedObservation] = []
    for sample in sorted(validated_samples, key=lambda row: row.observation.observation_id):
        observation = sample.observation
        if observation.execution_id in seen_executions:
            raise RoutingLearningError("one execution cannot inflate multiple learning samples")
        seen_executions.add(observation.execution_id)
        if observation.authorization_id in seen_authorizations:
            raise RoutingLearningError("one authorization cannot inflate multiple samples")
        seen_authorizations.add(observation.authorization_id)
        _verify_accounting(
            observation.accounting, key, _outcome_accounting_binding(observation)
        )
        if observation.accounting.receipt_id in seen_receipts:
            raise RoutingLearningError("one ledger receipt cannot inflate multiple samples")
        seen_receipts.add(observation.accounting.receipt_id)
        for output_hash in observation.output_file_sha256s:
            if output_hash in seen_outputs:
                raise RoutingLearningError("one output cannot inflate multiple samples")
            seen_outputs.add(output_hash)
        for regeneration in sample.evaluation.regenerations:
            if regeneration.originating_execution_id != observation.execution_id:
                raise RoutingLearningError("regeneration references a different origin execution")
            _verify_accounting(
                regeneration.accounting,
                key,
                _regeneration_accounting_binding(regeneration),
            )
            if regeneration.execution_id in seen_regenerations:
                raise RoutingLearningError("one regeneration cannot penalize multiple samples")
            if regeneration.accounting.receipt_id in seen_receipts:
                raise RoutingLearningError("one ledger receipt cannot be counted twice")
            seen_regenerations.add(regeneration.execution_id)
            seen_receipts.add(regeneration.accounting.receipt_id)
        policy = policies.get(observation.policy_version_id)
        if policy is None:
            raise RoutingLearningError("learning observation references an unknown policy")
        _verify_policy_binding(policy, observation)
        if sample.evaluation.observation_id != observation.observation_id:
            raise RoutingLearningError("evaluation references a different observation")
        if sample.evaluation.evaluated_at < observation.terminal_at:
            raise RoutingLearningError("evaluation predates terminal output evidence")
        if observation.terminal_at > generated_at or sample.evaluation.evaluated_at > generated_at:
            raise RoutingLearningError("report cutoff predates terminal or evaluation evidence")
        if (
            sample.evaluation.rated_at is not None
            and sample.evaluation.rated_at < observation.terminal_at
        ):
            raise RoutingLearningError("rating predates terminal output evidence")
        if sample.evaluation.rated_at is not None and sample.evaluation.rated_at > generated_at:
            raise RoutingLearningError("report cutoff predates rating evidence")
        suite_major = int(sample.evaluation.verifier_suite_version.split(".", 1)[0])
        expected_cohort = _cohort_for(observation, suite_major, sample.cohort.evaluation_mode)
        if sample.cohort != expected_cohort:
            raise RoutingLearningError("cohort conflicts with immutable outcome shape")
        if sample.cohort.evaluation_mode == "verifier_only" and sample.evaluation.user_rating:
            raise RoutingLearningError("verifier-only cohorts cannot selectively include ratings")
        if sample.cohort.evaluation_mode == "user_rated" and sample.evaluation.user_rating is None:
            raise RoutingLearningError("user-rated cohorts require every rating")
        reason = _exclusion_reason(observation)
        if reason:
            excluded.append(
                ExcludedObservation(observation_id=observation.observation_id, reason=reason)
            )
            continue
        grouped[(sample.cohort, policy.policy_version_id)].append(sample)

    rows = tuple(
        _policy_row(cohort, policy_id, cohort_samples)
        for (cohort, policy_id), cohort_samples in sorted(
            grouped.items(), key=lambda item: (_canonical(item[0][0]), item[0][1])
        )
    )
    row_index = {(row.cohort, row.policy_version_id): row for row in rows}
    recommendations: list[RouterRecommendation] = []
    cohorts = sorted({cohort for cohort, _ in grouped}, key=_canonical)
    if set(current_policy_by_cohort) != set(cohorts):
        raise RoutingLearningError("current policy map must exactly cover report cohorts")
    for cohort in cohorts:
        current_id = current_policy_by_cohort.get(cohort)
        if current_id is None or current_id not in policies:
            raise RoutingLearningError("every cohort requires one known current policy")
        candidates = [row_index[(key, policy_id)] for key, policy_id in grouped if key == cohort]
        current = row_index.get((cohort, current_id))
        recommendations.append(_recommend(cohort, current_id, current, candidates))

    partial = {
        "schema_version": "antiek.routing-learning.v1",
        "algorithm_version": "conservative-qpd-v1",
        "generated_at": generated_at,
        "policy_rows": rows,
        "recommendations": tuple(recommendations),
        "excluded_observations": tuple(sorted(excluded, key=lambda row: row.observation_id)),
        "input_observation_ids": tuple(
            sorted(sample.observation.observation_id for sample in validated_samples)
        ),
    }
    return cast(
        RouterRecommendationReport,
        RouterRecommendationReport.model_validate(
            {"report_id": _content_id("report", partial), **partial}
        ),
    )


def _policy_row(
    cohort: CohortKey, policy_id: str, samples: list[LearningSample]
) -> PolicyEvidenceRow:
    samples = sorted(samples, key=lambda row: row.observation.observation_id)
    qualities = [_quality(row) for row in samples]
    passing = sum(value > 0 for value in qualities)
    rated = sum(row.evaluation.user_rating is not None for row in samples)
    failures = sum(row.observation.terminal_status != "succeeded" for row in samples)
    penalized = [
        regen for row in samples for regen in row.evaluation.regenerations if _penalizes(row, regen)
    ]
    lifecycle_cost = sum(
        cast(int, row.observation.accounting.reconciled_cost_microdollars) for row in samples
    )
    lifecycle_cost += sum(
        cast(int, row.accounting.reconciled_cost_microdollars) for row in penalized
    )
    latencies = sorted(
        row.observation.latency_ms
        + sum(regen.latency_ms for regen in row.evaluation.regenerations if _penalizes(row, regen))
        for row in samples
    )
    mean_quality = sum(qualities) / len(qualities)
    lower = max(0.0, mean_quality - 1.0 / math.sqrt(len(qualities)))
    confidence: ConfidenceStatus = "insufficient"
    if len(samples) >= _MIN_ELIGIBLE and passing >= _MIN_PASSING:
        confidence = "reportable"
    if len(samples) >= _MIN_REPLACEMENT and passing >= _MIN_PASSING:
        confidence = "replacement_ready"
    effective = math.ceil(lifecycle_cost / passing) if passing else None
    qpd = lower * 1_000_000 / lifecycle_cost if lifecycle_cost and passing else None
    return PolicyEvidenceRow(
        cohort=cohort,
        policy_version_id=policy_id,
        eligible_sample_count=len(samples),
        passing_sample_count=passing,
        rated_sample_count=rated,
        failure_count=failures,
        penalized_regeneration_count=len(penalized),
        total_lifecycle_cost_microdollars=lifecycle_cost,
        latency_p50_ms=_percentile(latencies, 0.50),
        latency_p95_ms=_percentile(latencies, 0.95),
        quality_point_estimate=round(mean_quality, 9),
        quality_lower_bound=round(lower, 9),
        effective_cost_per_passing_output_microdollars=effective,
        quality_per_dollar_lower_bound=round(qpd, 9) if qpd is not None else None,
        confidence_status=confidence,
        observation_ids=tuple(row.observation.observation_id for row in samples),
    )


def _recommend(
    cohort: CohortKey,
    current_id: str,
    current: PolicyEvidenceRow | None,
    candidates: list[PolicyEvidenceRow],
) -> RouterRecommendation:
    evidence = tuple(sorted({obs for row in candidates for obs in row.observation_ids}))
    if current is None or current.confidence_status != "replacement_ready":
        return RouterRecommendation(
            cohort=cohort,
            current_policy_version_id=current_id,
            proposed_policy_version_id=None,
            action="insufficient_evidence",
            reason_codes=("current_policy_not_replacement_ready",),
            supporting_observation_ids=evidence,
        )
    ranked = sorted(
        candidates,
        key=lambda row: (
            -(row.quality_per_dollar_lower_bound or 0),
            -row.quality_lower_bound,
            row.total_lifecycle_cost_microdollars,
            row.latency_p95_ms,
            row.policy_version_id,
        ),
    )
    best = ranked[0]
    current_qpd = current.quality_per_dollar_lower_bound or 0
    best_qpd = best.quality_per_dollar_lower_bound or 0
    safe = (
        best.confidence_status == "replacement_ready"
        and best.quality_lower_bound >= current.quality_lower_bound
        and best.failure_count / best.eligible_sample_count
        <= current.failure_count / current.eligible_sample_count
        and best.penalized_regeneration_count / best.eligible_sample_count
        <= current.penalized_regeneration_count / current.eligible_sample_count
    )
    if (
        best.policy_version_id != current_id
        and safe
        and best_qpd >= current_qpd * _MATERIAL_IMPROVEMENT
    ):
        return RouterRecommendation(
            cohort=cohort,
            current_policy_version_id=current_id,
            proposed_policy_version_id=best.policy_version_id,
            action="consider_promote",
            reason_codes=("quality_per_dollar_materially_higher", "quality_floor_preserved"),
            supporting_observation_ids=evidence,
        )
    return RouterRecommendation(
        cohort=cohort,
        current_policy_version_id=current_id,
        proposed_policy_version_id=current_id,
        action="retain",
        reason_codes=("no_safe_material_improvement",),
        supporting_observation_ids=evidence,
    )


def _quality(sample: LearningSample) -> float:
    if sample.observation.terminal_status != "succeeded" or not sample.evaluation.verifier_pass:
        return 0.0
    score = sample.evaluation.verifier_score
    if sample.evaluation.user_rating is not None:
        score = min(score, (sample.evaluation.user_rating - 1) / 4)
    return score


def _penalty_reason(row: RegenerationEvidence) -> bool:
    return row.reason in {"quality_rejection", "provider_failure"}


def _penalizes(sample: LearningSample, row: RegenerationEvidence) -> bool:
    return _penalty_reason(row) and bool(set(sample.target_ids).intersection(row.target_ids))


def _exclusion_reason(row: RouteOutcomeObservation) -> str | None:
    if row.accounting.cost_basis == "ledger_hold_open":
        return "unreconciled_open_hold"
    if row.accounting.cost_basis == "zero_non_billable" or row.provider == "local_placeholder":
        return "non_billable_placeholder"
    return None


def _verify_policy_binding(policy: RoutePolicySnapshot, row: RouteOutcomeObservation) -> None:
    if (
        policy.route_policy != row.route_policy
        or policy.provider != row.provider
        or policy.model != row.model
        or policy.endpoint_capability != row.endpoint_capability
        or policy.generation_kind != row.generation_kind
    ):
        raise RoutingLearningError("outcome bindings conflict with policy snapshot")


def _cohort_for(
    row: RouteOutcomeObservation,
    verifier_suite_major: int,
    evaluation_mode: Literal["verifier_only", "user_rated"],
) -> CohortKey:
    duration = "none" if row.duration_seconds is None else f"{row.duration_seconds:.3f}s"
    return CohortKey(
        generation_kind=row.generation_kind,
        endpoint_capability=row.endpoint_capability,
        duration_bucket=duration,
        resolution_bucket=f"{row.width_px}x{row.height_px}",
        route_policy=row.route_policy,
        verifier_suite_major=verifier_suite_major,
        evaluation_mode=evaluation_mode,
    )


def _outcome_accounting_binding(row: RouteOutcomeObservation) -> dict[str, object]:
    return {
        "kind": "outcome",
        "execution_id": row.execution_id,
        "authorization_id": row.authorization_id,
        "asset_id": row.asset_id,
        "revision_id": row.revision_id,
        "request_body_digest": row.request_body_digest,
    }


def _regeneration_accounting_binding(row: RegenerationEvidence) -> dict[str, object]:
    return {
        "kind": "regeneration",
        "execution_id": row.execution_id,
        "originating_execution_id": row.originating_execution_id,
        "authorization_id": row.authorization_id,
        "target_ids": row.target_ids,
        "reason": row.reason,
    }


def _verify_accounting(
    row: LedgerCostEvidence, key: bytes, expected_binding: dict[str, object]
) -> None:
    if not hmac.compare_digest(row.binding_digest, _digest(expected_binding)):
        raise RoutingLearningError("ledger accounting binding conflicts")
    values = row.model_dump(mode="json", exclude={"authority_mac"})
    expected = hmac.new(key, _canonical(values), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(row.authority_mac, expected):
        raise RoutingLearningError("ledger accounting authority is invalid")


def _accounting_key(value: bytes) -> bytes:
    if not isinstance(value, bytes) or len(value) < _MIN_ACCOUNTING_KEY_BYTES:
        raise RoutingLearningError("accounting key must contain at least 32 bytes")
    return value


def _revalidate(model: type[EvidenceT], row: EvidenceT) -> EvidenceT:  # noqa: UP047
    return cast(EvidenceT, model.model_validate(dict(row.__dict__)))


def _percentile(values: list[int], percentile: float) -> int:
    return values[max(0, math.ceil(len(values) * percentile) - 1)]


def _policy_content(row: RoutePolicySnapshot) -> dict[str, object]:
    return cast(dict[str, object], row.model_dump(mode="json", exclude={"policy_version_id"}))


def _projection_content(row: ProjectedRouteCost) -> dict[str, object]:
    return cast(dict[str, object], row.model_dump(mode="json", exclude={"projection_id"}))


def _outcome_content(row: RouteOutcomeObservation) -> dict[str, object]:
    return cast(dict[str, object], row.model_dump(mode="json", exclude={"observation_id"}))


def _evaluation_content(row: OutcomeEvaluation) -> dict[str, object]:
    return cast(dict[str, object], row.model_dump(mode="json", exclude={"evaluation_id"}))


def _report_content(row: RouterRecommendationReport) -> dict[str, object]:
    return cast(dict[str, object], row.model_dump(mode="json", exclude={"report_id"}))


def _content_id(prefix: str, value: object) -> str:
    return f"{prefix}_{_digest(value)[:24]}"


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _canonical(value: object) -> bytes:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=_json_default).encode()


def _json_default(value: object) -> object:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, datetime):
        encoded = value.isoformat()
        return encoded[:-6] + "Z" if encoded.endswith("+00:00") else encoded
    raise TypeError(f"unsupported canonical value: {type(value).__name__}")


def _aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise RoutingLearningError(f"{name} must be timezone-aware")


def _unique(values: Iterable[str], label: str) -> None:
    rows = tuple(values)
    if len(rows) != len(set(rows)):
        raise RoutingLearningError(f"{label} must be unique")


__all__ = [
    "CohortKey",
    "LedgerCostEvidence",
    "LearningSample",
    "OutcomeEvaluation",
    "ProjectedRouteCost",
    "RegenerationEvidence",
    "RouteOutcomeObservation",
    "RoutePolicySnapshot",
    "RouterRecommendationReport",
    "RoutingLearningError",
    "VerifierResult",
    "compile_recommendation_report",
    "create_ledger_cost_evidence",
    "create_outcome_evaluation",
    "create_outcome_observation",
    "create_policy_snapshot",
    "create_projected_route_cost",
]
