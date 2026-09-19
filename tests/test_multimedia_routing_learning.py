from __future__ import annotations

import ast
import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from substrate.multimedia.provider_router import MediaGenerationRequest, route_media_request
from substrate.multimedia.routing_learning import (
    CohortKey,
    LearningSample,
    RegenerationEvidence,
    RoutePolicySnapshot,
    RoutingLearningError,
    VerifierResult,
    compile_recommendation_report,
    create_ledger_cost_evidence,
    create_outcome_evaluation,
    create_outcome_observation,
    create_policy_snapshot,
    create_projected_route_cost,
)

NOW = datetime(2026, 7, 11, 9, tzinfo=UTC)
DIGEST = "a" * 64
KEY = b"routing-learning-accounting-key-32"
COHORT = CohortKey(
    generation_kind="image",
    endpoint_capability="image-generate",
    duration_bucket="none",
    resolution_bucket="1280x720",
    route_policy="balanced",
    verifier_suite_major=1,
    evaluation_mode="verifier_only",
)
RATED_COHORT = COHORT.model_copy(update={"evaluation_mode": "user_rated"})


def _hex(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _policy(*, model: str, knob: str = "standard") -> RoutePolicySnapshot:
    return create_policy_snapshot(
        route_policy="balanced",
        provider="krea",
        model=model,
        endpoint_capability="image-generate",
        generation_kind="image",
        catalog_version="catalog-1",
        catalog_digest=DIGEST,
        quality_knobs={"quality": knob, "resolution": "1280x720"},
        estimator_version="estimator-1",
        created_reason="manual_initial",
    )


def _sample(
    policy: RoutePolicySnapshot,
    index: int,
    *,
    cost: int = 200_000,
    terminal_status: str = "succeeded",
    verifier_score: float = 0.9,
    user_rating: int | None = None,
    cost_basis: str = "ledger_actual",
    regenerations: tuple[RegenerationEvidence, ...] = (),
    cohort: CohortKey = COHORT,
    authorization_id: str | None = None,
    output_hash: str | None = None,
) -> LearningSample:
    execution_id = f"execution-{policy.model}-{index}"
    authorization = authorization_id or f"authorization-{policy.model}-{index}"
    asset_id = f"asset-{index}"
    request_digest = _hex(f"request-{policy.model}-{index}")
    output_hashes = (
        (output_hash or _hex(f"output-{policy.model}-{index}"),)
        if terminal_status == "succeeded"
        else ()
    )
    reconciled = cost if cost_basis in {"ledger_actual", "ledger_ceiling_settlement"} else None
    accounting = create_ledger_cost_evidence(
        accounting_key=KEY,
        receipt_id=f"receipt-{policy.model}-{index}",
        receipt_digest=_hex(f"receipt-body-{policy.model}-{index}"),
        cost_basis=cost_basis,
        reconciled_cost_microdollars=reconciled,
        binding={
            "kind": "outcome",
            "execution_id": execution_id,
            "authorization_id": authorization,
            "asset_id": asset_id,
            "revision_id": "revision-1",
            "request_body_digest": request_digest,
        },
    )
    observation = create_outcome_observation(
        policy_version_id=policy.policy_version_id,
        execution_id=execution_id,
        authorization_id=authorization,
        asset_id=asset_id,
        revision_id="revision-1",
        provider=policy.provider,
        model=policy.model,
        endpoint_capability=policy.endpoint_capability,
        generation_kind=policy.generation_kind,
        route_policy=policy.route_policy,
        duration_seconds=None,
        width_px=1280,
        height_px=720,
        request_body_digest=request_digest,
        terminal_status=terminal_status,
        started_at=NOW + timedelta(minutes=index),
        terminal_at=NOW + timedelta(minutes=index, seconds=2),
        accounting=accounting,
        output_file_sha256s=output_hashes,
    )
    passed = verifier_score >= 0.7
    evaluation = create_outcome_evaluation(
        observation_id=observation.observation_id,
        verifier_suite_version="1.2",
        verifier_results=(
            VerifierResult(
                verifier_id="grounding",
                verifier_version="1.4",
                criterion="grounded and useful",
                score=verifier_score,
                threshold=0.7,
                passed=passed,
                evidence_digest="b" * 64,
            ),
        ),
        user_rating=user_rating,
        rated_at=observation.terminal_at + timedelta(seconds=1) if user_rating else None,
        regenerations=regenerations,
        evaluated_at=observation.terminal_at + timedelta(minutes=10),
    )
    return LearningSample(
        observation=observation,
        evaluation=evaluation,
        cohort=cohort,
        target_ids=(f"target-{index}",),
    )


def _report(
    current: RoutePolicySnapshot,
    candidate: RoutePolicySnapshot,
    samples: tuple[LearningSample, ...],
):
    cohort = samples[0].cohort
    return compile_recommendation_report(
        snapshots=(current, candidate),
        samples=samples,
        current_policy_by_cohort={cohort: current.policy_version_id},
        generated_at=NOW + timedelta(days=7),
        accounting_verification_key=KEY,
    )


def test_policy_and_projection_are_content_derived_and_estimate_only() -> None:
    first = _policy(model="krea-image-standard")
    assert first == _policy(model="krea-image-standard")
    changed = _policy(model="krea-image-standard", knob="high")
    assert changed.policy_version_id != first.policy_version_id
    with pytest.raises((RoutingLearningError, ValidationError), match="canonical content"):
        RoutePolicySnapshot.model_validate(
            {**first.model_dump(mode="python"), "model": "silently-mutated"}
        )

    route = route_media_request(
        MediaGenerationRequest(kind="image", prompt="diagram", route_policy="balanced")
    )
    projection = create_projected_route_cost(
        policy=first,
        asset_id="asset-1",
        revision_id="revision-1",
        target_ids=("scene-1", "scene-2"),
        generation_kind="image",
        route=route,
        estimator_version="estimator-1",
        estimated_at=NOW,
        steering_event_id="steer-1",
    )
    assert projection.estimate_basis == "router_projection"
    assert projection.estimated_microdollars == 20_000
    assert not hasattr(projection, "actual_cost_microdollars")
    with pytest.raises(ValidationError, match="unique"):
        type(projection).model_validate(
            {**projection.model_dump(mode="python"), "target_ids": ("scene-1", "scene-1")}
        )


def test_outcomes_require_coherent_ledger_basis_trusted_time_and_output() -> None:
    policy = _policy(model="krea-image-standard")
    with pytest.raises(ValidationError, match="ledger amount"):
        create_ledger_cost_evidence(
            accounting_key=KEY,
            receipt_id="receipt",
            receipt_digest=DIGEST,
            cost_basis="ledger_actual",
            reconciled_cost_microdollars=None,
        )
    accounting = create_ledger_cost_evidence(
        accounting_key=KEY,
        receipt_id="receipt",
        receipt_digest=DIGEST,
        cost_basis="ledger_ceiling_settlement",
        reconciled_cost_microdollars=200_000,
    )
    with pytest.raises(ValidationError, match="output hashes"):
        create_outcome_observation(
            policy_version_id=policy.policy_version_id,
            execution_id="execution",
            authorization_id="authorization",
            asset_id="asset",
            revision_id="revision",
            provider=policy.provider,
            model=policy.model,
            endpoint_capability=policy.endpoint_capability,
            generation_kind="image",
            route_policy="balanced",
            duration_seconds=None,
            width_px=1280,
            height_px=720,
            request_body_digest=DIGEST,
            terminal_status="succeeded",
            started_at=NOW,
            terminal_at=NOW + timedelta(seconds=1),
            accounting=accounting,
        )
    sample = _sample(policy, 1, cost_basis="ledger_ceiling_settlement")
    assert sample.observation.accounting.cost_basis == "ledger_ceiling_settlement"
    assert sample.observation.latency_ms == 2000


def test_sparse_evidence_and_non_billable_rows_are_reported_not_promoted() -> None:
    current = _policy(model="current")
    candidate = _policy(model="candidate")
    eligible = tuple(_sample(current, index) for index in range(9))
    excluded = _sample(candidate, 20, cost_basis="ledger_hold_open")
    report = _report(current, candidate, (*eligible, excluded))
    assert report.recommendations[0].action == "insufficient_evidence"
    assert report.excluded_observations[0].reason == "unreconciled_open_hold"
    assert excluded.observation.observation_id in report.input_observation_ids
    assert all(
        excluded.observation.observation_id not in row.observation_ids for row in report.policy_rows
    )


def test_report_is_order_stable_and_recommends_only_safe_material_improvement() -> None:
    current = _policy(model="current")
    candidate = _policy(model="candidate")
    current_samples = tuple(_sample(current, index, cost=240_000) for index in range(30))
    candidate_samples = tuple(_sample(candidate, index + 100, cost=100_000) for index in range(30))
    samples = (*current_samples, *candidate_samples)
    first = _report(current, candidate, samples)
    second = _report(current, candidate, tuple(reversed(samples)))
    assert first == second
    assert first.report_id == second.report_id
    recommendation = first.recommendations[0]
    assert recommendation.action == "consider_promote"
    assert recommendation.proposed_policy_version_id == candidate.policy_version_id
    assert len(recommendation.supporting_observation_ids) == 60


def test_low_rating_verifier_failure_and_regeneration_prevent_cheap_route_winner() -> None:
    current = _policy(model="current")
    cheap = _policy(model="cheap")
    current_samples = tuple(
        _sample(current, index, cost=200_000, user_rating=5, cohort=RATED_COHORT)
        for index in range(30)
    )
    cheap_samples = []
    for index in range(30):
        regeneration = RegenerationEvidence(
            execution_id=f"retry-{index}",
            originating_execution_id=f"execution-cheap-{index + 100}",
            authorization_id=f"retry-authorization-{index}",
            target_ids=(f"target-{index + 100}",),
            reason="quality_rejection",
            accounting=create_ledger_cost_evidence(
                accounting_key=KEY,
                receipt_id=f"retry-receipt-{index}",
                receipt_digest=_hex(f"retry-receipt-{index}"),
                cost_basis="ledger_actual",
                reconciled_cost_microdollars=250_000,
            ),
            latency_ms=5000,
        )
        cheap_samples.append(
            _sample(
                cheap,
                index + 100,
                cost=20_000,
                verifier_score=0.95,
                user_rating=1,
                regenerations=(regeneration,),
                cohort=RATED_COHORT,
            )
        )
    report = _report(current, cheap, (*current_samples, *cheap_samples))
    cheap_row = next(
        row for row in report.policy_rows if row.policy_version_id == cheap.policy_version_id
    )
    assert cheap_row.quality_point_estimate == 0
    assert cheap_row.penalized_regeneration_count == 30
    assert cheap_row.total_lifecycle_cost_microdollars == 8_100_000
    assert report.recommendations[0].action == "retain"


def test_unrelated_regeneration_is_not_a_quality_penalty() -> None:
    policy = _policy(model="current")
    unrelated = RegenerationEvidence(
        execution_id="tone-edit",
        originating_execution_id="execution-current-0",
        authorization_id="tone-authorization",
        target_ids=("target",),
        reason="operator_preference_change",
        accounting=create_ledger_cost_evidence(
            accounting_key=KEY,
            receipt_id="tone-receipt",
            receipt_digest=_hex("tone-receipt"),
            cost_basis="ledger_actual",
            reconciled_cost_microdollars=900_000,
        ),
        latency_ms=9000,
    )
    samples = (
        _sample(policy, 0, regenerations=(unrelated,)),
        *(tuple(_sample(policy, index) for index in range(1, 30))),
    )
    report = compile_recommendation_report(
        snapshots=(policy,),
        samples=samples,
        current_policy_by_cohort={COHORT: policy.policy_version_id},
        generated_at=NOW + timedelta(days=7),
        accounting_verification_key=KEY,
    )
    row = report.policy_rows[0]
    assert row.penalized_regeneration_count == 0
    assert row.total_lifecycle_cost_microdollars == 6_000_000


def test_binding_duplicates_and_verifier_major_mismatch_fail_closed() -> None:
    policy = _policy(model="current")
    candidate = _policy(model="candidate")
    sample = _sample(policy, 1)
    with pytest.raises(RoutingLearningError, match="inflate"):
        _report(policy, candidate, (sample, sample))

    forged_observation = sample.observation.model_copy(update={"model": "other-model"})
    forged = sample.model_copy(update={"observation": forged_observation})
    with pytest.raises((RoutingLearningError, ValidationError), match="canonical content"):
        _report(policy, candidate, (forged,))

    mixed = sample.model_copy(
        update={"cohort": sample.cohort.model_copy(update={"verifier_suite_major": 2})}
    )
    with pytest.raises(RoutingLearningError, match="cohort conflicts"):
        _report(policy, candidate, (mixed,))


def test_forged_accounting_cohort_and_selective_ratings_fail_closed() -> None:
    policy = _policy(model="current")
    candidate = _policy(model="candidate")
    sample = _sample(policy, 1)
    forged_accounting = sample.observation.accounting.model_copy(
        update={"reconciled_cost_microdollars": 1}
    )
    observation_values = sample.observation.model_dump(mode="python", exclude={"observation_id"})
    forged_observation = create_outcome_observation(
        **{**observation_values, "accounting": forged_accounting}
    )
    evaluation_values = sample.evaluation.model_dump(mode="python", exclude={"evaluation_id"})
    forged_evaluation = create_outcome_evaluation(
        **{**evaluation_values, "observation_id": forged_observation.observation_id}
    )
    forged = sample.model_copy(
        update={"observation": forged_observation, "evaluation": forged_evaluation}
    )
    with pytest.raises(RoutingLearningError, match="accounting authority"):
        _report(policy, candidate, (forged,))

    reassigned = sample.model_copy(
        update={"cohort": sample.cohort.model_copy(update={"resolution_bucket": "8k"})}
    )
    with pytest.raises(RoutingLearningError, match="cohort conflicts"):
        _report(policy, candidate, (reassigned,))

    selectively_rated = _sample(policy, 2, user_rating=5, cohort=COHORT)
    with pytest.raises(RoutingLearningError, match="selectively include"):
        _report(policy, candidate, (selectively_rated,))
    missing_rating = _sample(policy, 3, cohort=RATED_COHORT)
    with pytest.raises(RoutingLearningError, match="require every rating"):
        _report(policy, candidate, (missing_rating,))


def test_duplicate_authority_output_regeneration_and_nested_ceiling_fail_closed() -> None:
    policy = _policy(model="current")
    candidate = _policy(model="candidate")
    shared_authorization = "same-authorization"
    first = _sample(policy, 1, authorization_id=shared_authorization)
    second = _sample(policy, 2, authorization_id=shared_authorization)
    with pytest.raises(RoutingLearningError, match="authorization"):
        _report(policy, candidate, (first, second))

    shared_output = _hex("same-output")
    first = _sample(policy, 3, output_hash=shared_output)
    second = _sample(policy, 4, output_hash=shared_output)
    with pytest.raises(RoutingLearningError, match="output"):
        _report(policy, candidate, (first, second))

    def regeneration(index: int, origin: str):
        return RegenerationEvidence(
            execution_id="same-regeneration",
            originating_execution_id=origin,
            authorization_id=f"regeneration-authorization-{index}",
            target_ids=(f"target-{index}",),
            reason="quality_rejection",
            accounting=create_ledger_cost_evidence(
                accounting_key=KEY,
                receipt_id=f"regeneration-receipt-{index}",
                receipt_digest=_hex(f"regeneration-receipt-{index}"),
                cost_basis="ledger_actual",
                reconciled_cost_microdollars=100_000,
            ),
            latency_ms=1000,
        )

    first = _sample(
        policy,
        5,
        regenerations=(regeneration(5, "execution-current-5"),),
    )
    second = _sample(
        policy,
        6,
        regenerations=(regeneration(6, "execution-current-6"),),
    )
    with pytest.raises(RoutingLearningError, match="regeneration"):
        _report(policy, candidate, (first, second))

    row = regeneration(7, "execution-current-7")
    evaluation = _sample(policy, 7).evaluation
    with pytest.raises(ValidationError, match="128"):
        type(evaluation).model_validate(
            {
                **evaluation.model_dump(mode="python"),
                "regenerations": tuple(
                    row.model_copy(update={"execution_id": f"regen-{index}"})
                    for index in range(129)
                ),
            }
        )


def test_learning_module_has_no_io_network_ledger_or_router_execution() -> None:
    path = Path("substrate/multimedia/routing_learning.py")
    tree = ast.parse(path.read_text())
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert not imports & {"os", "socket", "httpx", "requests", "urllib", "duckdb"}
    source = path.read_text()
    assert "BudgetLedger" not in source
    assert "route_media_request(" not in source
    assert "subprocess" not in source
