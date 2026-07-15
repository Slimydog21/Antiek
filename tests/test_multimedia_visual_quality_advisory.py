from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest

import substrate.multimedia.visual_quality_advisory as visual_quality_advisory
from runtime.db_lock import connect_read, connect_write
from substrate.multimedia.read_model import (
    ApplySteeringPreviewRequest,
    SteeringPreviewRequest,
)
from substrate.multimedia.visual_quality_advisory import (
    RUBRIC_VERSION,
    VisualQualityAdvisoryError,
    VisualQualityAdvisoryIntegrityError,
    VisualQualityAdvisoryRegistry,
    VisualQualityAssessmentRequest,
    VisualRoutingCohortKey,
    _CohortAccumulator,
    _finalize_cohort,
    _wilson_lower_bound,
)
from tests.test_multimedia_visual_authorization import KEY
from tests.test_multimedia_visual_candidate_materialization import NOW
from tests.test_multimedia_visual_candidate_review import _candidate


def _request(
    revision_id: str,
    *,
    request_id: str = "quality-request-1",
    disposition: str = "accepted",
    production_usable: str = "pass",
) -> VisualQualityAssessmentRequest:
    return VisualQualityAssessmentRequest(
        request_id=request_id,
        expected_revision_id=revision_id,
        disposition=disposition,
        prompt_fidelity="pass",
        technical_acceptability="pass",
        visual_coherence="fail",
        production_usable=production_usable,
        reason_codes=("visual_incoherence",),
    )


def test_assessment_is_server_bound_scored_and_exactly_idempotent(tmp_path) -> None:
    store, ready, db, candidate_id = _candidate(tmp_path)
    registry = VisualQualityAdvisoryRegistry(db_path=db, signing_key=KEY)
    kwargs = dict(
        asset_id=ready.asset.asset_id,
        candidate_id=candidate_id,
        request=_request(ready.asset.revision_id),
        owner_id="owner-1",
        store=store,
    )
    first = registry.assess(**kwargs, now=NOW + timedelta(seconds=10))
    replay = registry.assess(**kwargs, now=NOW + timedelta(hours=1))
    assert replay == first
    assert first.quality_score == 0.75
    assert first.rubric_version == RUBRIC_VERSION
    assert first.execution_id.startswith("mmexec_")
    assert len(first.artifact_sha256) == 64
    assert not hasattr(first, "charged_cents")

    steering = SteeringPreviewRequest(
        expected_parent_revision_id=ready.asset.revision_id,
        prompt="go deeper on chapter 2",
    )
    preview = store.preview_steering(
        ready.asset.asset_id, steering, owner_id="owner-1"
    )
    store.apply_steering_preview(
        ready.asset.asset_id,
        ApplySteeringPreviewRequest(
            **steering.model_dump(), preview_token=preview.preview_token
        ),
        owner_id="owner-1",
    )
    assert store.get(ready.asset.asset_id, owner_id="owner-1").asset.revision_id != (
        ready.asset.revision_id
    )
    assert registry.assess(**kwargs, now=NOW + timedelta(hours=2)) == first


def test_assessment_rejects_conflict_foreign_owner_stale_revision_and_bad_rubric(tmp_path) -> None:
    store, ready, db, candidate_id = _candidate(tmp_path)
    registry = VisualQualityAdvisoryRegistry(db_path=db, signing_key=KEY)
    registry.assess(
        asset_id=ready.asset.asset_id,
        candidate_id=candidate_id,
        request=_request(ready.asset.revision_id),
        owner_id="owner-1",
        store=store,
        now=NOW,
    )
    with pytest.raises(VisualQualityAdvisoryError, match="conflicts"):
        registry.assess(
            asset_id=ready.asset.asset_id,
            candidate_id=candidate_id,
            request=_request(
                ready.asset.revision_id,
                disposition="rejected",
                production_usable="fail",
            ),
            owner_id="owner-1",
            store=store,
            now=NOW,
        )
    with pytest.raises(VisualQualityAdvisoryError):
        registry.assess(
            asset_id=ready.asset.asset_id,
            candidate_id=candidate_id,
            request=_request(ready.asset.revision_id, request_id="foreign"),
            owner_id="owner-2",
            store=store,
            now=NOW,
        )
    with pytest.raises(VisualQualityAdvisoryError, match="stale"):
        registry.assess(
            asset_id=ready.asset.asset_id,
            candidate_id=candidate_id,
            request=_request("stale-revision", request_id="stale"),
            owner_id="owner-1",
            store=store,
            now=NOW,
        )
    with pytest.raises(VisualQualityAdvisoryError, match="production usability"):
        registry.assess(
            asset_id=ready.asset.asset_id,
            candidate_id=candidate_id,
            request=_request(
                ready.asset.revision_id,
                request_id="bad-rubric",
                production_usable="fail",
            ),
            owner_id="owner-1",
            store=store,
            now=NOW,
        )


def test_assessment_tamper_is_detected_on_replay_and_report(tmp_path) -> None:
    store, ready, db, candidate_id = _candidate(tmp_path)
    registry = VisualQualityAdvisoryRegistry(db_path=db, signing_key=KEY)
    registry.assess(
        asset_id=ready.asset.asset_id,
        candidate_id=candidate_id,
        request=_request(ready.asset.revision_id),
        owner_id="owner-1",
        store=store,
        now=NOW,
    )
    with connect_write(db, purpose="test.visual_quality.tamper") as connection:
        connection.execute(
            "UPDATE multimedia_visual_quality_assessments SET visual_coherence=1"
        )
    with pytest.raises(VisualQualityAdvisoryIntegrityError, match="integrity"):
        registry.report(owner_id="owner-1", as_of=NOW + timedelta(hours=1))


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE multimedia_visual_quality_assessments SET owner_identity_digest='" + "0" * 64 + "'",
        "UPDATE multimedia_provider_executions SET operator_id='other-owner'",
        "UPDATE multimedia_provider_artifact_candidates SET execution_id='other-execution'",
        "UPDATE multimedia_artifact_quarantine_receipts "
        "SET candidate_id=candidate_id || '-tampered'",
    ],
)
def test_identity_tamper_cannot_hide_evidence_from_report(tmp_path, statement: str) -> None:
    store, ready, db, candidate_id = _candidate(tmp_path)
    registry = VisualQualityAdvisoryRegistry(db_path=db, signing_key=KEY)
    registry.assess(
        asset_id=ready.asset.asset_id,
        candidate_id=candidate_id,
        request=_request(ready.asset.revision_id),
        owner_id="owner-1",
        store=store,
        now=NOW,
    )
    with connect_write(db, purpose="test.visual_quality.identity_tamper") as connection:
        connection.execute(statement)
    with pytest.raises(VisualQualityAdvisoryIntegrityError):
        registry.report(owner_id="owner-1", as_of=NOW + timedelta(hours=1))


def test_revision_is_rechecked_after_authority_reopen_before_insert(
    tmp_path, monkeypatch
) -> None:
    store, ready, db, candidate_id = _candidate(tmp_path)
    registry = VisualQualityAdvisoryRegistry(db_path=db, signing_key=KEY)
    steering = SteeringPreviewRequest(
        expected_parent_revision_id=ready.asset.revision_id,
        prompt="go deeper on chapter 2",
    )
    preview = store.preview_steering(
        ready.asset.asset_id, steering, owner_id="owner-1"
    )
    original = registry._reopen_candidate_authority

    def reopen_then_advance(**kwargs):
        authority = original(**kwargs)
        store.apply_steering_preview(
            ready.asset.asset_id,
            ApplySteeringPreviewRequest(
                **steering.model_dump(), preview_token=preview.preview_token
            ),
            owner_id="owner-1",
        )
        return authority

    monkeypatch.setattr(registry, "_reopen_candidate_authority", reopen_then_advance)
    with pytest.raises(VisualQualityAdvisoryError, match="stale"):
        registry.assess(
            asset_id=ready.asset.asset_id,
            candidate_id=candidate_id,
            request=_request(ready.asset.revision_id),
            owner_id="owner-1",
            store=store,
            now=NOW,
        )
    with connect_read(db) as connection:
        assert connection.execute(
            "SELECT count(*) FROM multimedia_visual_quality_assessments"
        ).fetchone() == (0,)


def test_artifact_bytes_are_reopened_immediately_before_insert(tmp_path, monkeypatch) -> None:
    store, ready, db, candidate_id = _candidate(tmp_path)
    registry = VisualQualityAdvisoryRegistry(db_path=db, signing_key=KEY)
    with connect_read(db) as connection:
        quarantine_path = str(
            connection.execute(
                "SELECT quarantine_path FROM multimedia_artifact_quarantine_receipts "
                "WHERE candidate_id=?",
                [candidate_id],
            ).fetchone()[0]
        )
    original_verify = registry._verify_candidate_rows_in_context

    def verify_then_corrupt(*args, **kwargs) -> None:
        original_verify(*args, **kwargs)
        Path(quarantine_path).write_bytes(b"corrupt-after-authority-reopen")

    monkeypatch.setattr(registry, "_verify_candidate_rows_in_context", verify_then_corrupt)
    with pytest.raises(VisualQualityAdvisoryIntegrityError, match="commit-time"):
        registry.assess(
            asset_id=ready.asset.asset_id,
            candidate_id=candidate_id,
            request=_request(ready.asset.revision_id),
            owner_id="owner-1",
            store=store,
            now=NOW,
        )
    with connect_read(db) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM multimedia_visual_quality_assessments"
        ).fetchone()[0] == 0


def test_capacity_allows_exact_replay_but_rejects_a_new_assessment(
    tmp_path, monkeypatch
) -> None:
    store, ready, db, first_candidate = _candidate(tmp_path)
    with connect_read(db) as connection:
        candidate_ids = tuple(
            str(row[0])
            for row in connection.execute(
                "SELECT candidate_id FROM multimedia_provider_artifact_candidates "
                "ORDER BY ordinal"
            ).fetchall()
        )
    second_candidate = next(value for value in candidate_ids if value != first_candidate)
    monkeypatch.setattr(visual_quality_advisory, "_MAX_ASSESSMENTS", 1)
    registry = VisualQualityAdvisoryRegistry(db_path=db, signing_key=KEY)
    first_request = _request(ready.asset.revision_id, request_id="capacity-first")
    first = registry.assess(
        asset_id=ready.asset.asset_id,
        candidate_id=first_candidate,
        request=first_request,
        owner_id="owner-1",
        store=store,
        now=NOW,
    )
    assert registry.assess(
        asset_id=ready.asset.asset_id,
        candidate_id=first_candidate,
        request=first_request,
        owner_id="owner-1",
        store=store,
        now=NOW + timedelta(seconds=1),
    ) == first
    with pytest.raises(VisualQualityAdvisoryError, match="capacity"):
        registry.assess(
            asset_id=ready.asset.asset_id,
            candidate_id=second_candidate,
            request=_request(ready.asset.revision_id, request_id="capacity-second"),
            owner_id="owner-1",
            store=store,
            now=NOW + timedelta(seconds=2),
        )


def test_report_counts_materialized_coverage_and_charge_once_per_execution(
    tmp_path, monkeypatch
) -> None:
    store, ready, db, candidate_id = _candidate(tmp_path)
    registry = VisualQualityAdvisoryRegistry(db_path=db, signing_key=KEY)
    registry.assess(
        asset_id=ready.asset.asset_id,
        candidate_id=candidate_id,
        request=_request(ready.asset.revision_id),
        owner_id="owner-1",
        store=store,
        now=NOW + timedelta(seconds=10),
    )

    def reject_second_receipt_connection(**kwargs):
        raise AssertionError("report must use its receipt snapshot")

    monkeypatch.setattr(
        visual_quality_advisory,
        "reopen_quarantined_artifact",
        reject_second_receipt_connection,
    )
    with connect_read(db) as connection:
        authority_before = (
            connection.execute("SELECT * FROM multimedia_provider_executions").fetchall(),
            connection.execute(
                "SELECT * FROM multimedia_execution_authorization_claims"
            ).fetchall(),
            connection.execute("SELECT * FROM midnight_oil_call_holds").fetchall(),
        )
    report = registry.report(owner_id="owner-1", as_of=NOW + timedelta(minutes=1))
    with connect_read(db) as connection:
        authority_after = (
            connection.execute("SELECT * FROM multimedia_provider_executions").fetchall(),
            connection.execute(
                "SELECT * FROM multimedia_execution_authorization_claims"
            ).fetchall(),
            connection.execute("SELECT * FROM midnight_oil_call_holds").fetchall(),
        )
    assert authority_after == authority_before
    assert report.recommendation is None
    assert len(report.cohorts) == 1
    cohort = report.cohorts[0]
    assert cohort.n_executions == 1
    assert cohort.n_materialized_candidates == 2
    assert cohort.n_assessed_candidates == 1
    assert cohort.assessment_coverage == 0.5
    assert cohort.charged_cents_total is not None
    assert cohort.charged_cents_total == cohort.charged_cents_per_assessed_candidate
    assert cohort.ineligibility_reasons == (
        "minimum_assessed_candidates",
        "minimum_distinct_executions",
        "minimum_distinct_assets",
        "minimum_assessment_coverage",
    )
    serialized = repr(report)
    assert "actual_cost" not in serialized


def test_as_of_excludes_later_assessment_deterministically(tmp_path) -> None:
    store, ready, db, first_candidate = _candidate(tmp_path)
    with connect_read(db) as connection:
        candidate_ids = tuple(
            row[0]
            for row in connection.execute(
                "SELECT candidate_id FROM multimedia_provider_artifact_candidates ORDER BY ordinal"
            ).fetchall()
        )
    second_candidate = next(value for value in candidate_ids if value != first_candidate)
    registry = VisualQualityAdvisoryRegistry(db_path=db, signing_key=KEY)
    historical = registry.report(owner_id="owner-1", as_of=NOW + timedelta(seconds=1))
    assert historical.cohorts == ()
    registry.assess(
        asset_id=ready.asset.asset_id,
        candidate_id=first_candidate,
        request=_request(ready.asset.revision_id, request_id="first"),
        owner_id="owner-1",
        store=store,
        now=NOW + timedelta(seconds=10),
    )
    cutoff = NOW + timedelta(seconds=15)
    before = registry.report(owner_id="owner-1", as_of=cutoff)
    registry.assess(
        asset_id=ready.asset.asset_id,
        candidate_id=second_candidate,
        request=_request(
            ready.asset.revision_id,
            request_id="second",
            disposition="rejected",
            production_usable="fail",
        ),
        owner_id="owner-1",
        store=store,
        now=NOW + timedelta(seconds=20),
    )
    replay = registry.report(owner_id="owner-1", as_of=cutoff)
    after = registry.report(owner_id="owner-1", as_of=NOW + timedelta(seconds=30))
    assert registry.report(
        owner_id="owner-1", as_of=NOW + timedelta(seconds=1)
    ) == historical
    assert replay == before
    assert before.cohorts[0].n_assessed_candidates == 1
    assert after.cohorts[0].n_assessed_candidates == 2
    assert after.cohorts[0].charged_cents_total == before.cohorts[0].charged_cents_total


def test_wilson_golden_cases_and_recommendation_threshold_boundaries() -> None:
    assert _wilson_lower_bound(0, 20) == 0.0
    assert _wilson_lower_bound(20, 20) == pytest.approx(0.83887484)
    key = VisualRoutingCohortKey(
        "image",
        "krea",
        "imagen-3",
        "balanced",
        "catalog-v1",
        "a" * 64,
        RUBRIC_VERSION,
    )
    acc = _CohortAccumulator(
        execution_ids={f"execution-{index}" for index in range(10)},
        asset_ids={"asset-a", "asset-b", "asset-c"},
        candidate_ids={f"candidate-{index}" for index in range(20)},
        assessment_ids={f"assessment-{index}" for index in range(20)},
        accepted=20,
        quality_total=80,
        charged_by_execution={f"execution-{index}": 100 for index in range(10)},
        unresolved_accounting=0,
    )
    cohort = _finalize_cohort(key, acc)
    assert cohort.eligible
    assert cohort.charged_cents_total == 1000
    assert cohort.charged_cents_per_assessed_candidate == 50.0
    assert cohort.efficiency_score == pytest.approx(1.67774968)
    acc.candidate_ids.add("unassessed-1")
    acc.candidate_ids.add("unassessed-2")
    acc.candidate_ids.add("unassessed-3")
    acc.candidate_ids.add("unassessed-4")
    acc.candidate_ids.add("unassessed-5")
    assert _finalize_cohort(key, acc).eligible  # 20 / 25 is exactly the 80% floor.
    acc.candidate_ids.add("unassessed-6")
    assert _finalize_cohort(key, acc).ineligibility_reasons == (
        "minimum_assessment_coverage",
    )
