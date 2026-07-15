from __future__ import annotations

import hashlib
import json
import sqlite3

import pytest

from substrate.multimedia.bedrock_batch_adapter import (
    BedrockBatchRecoveryAdapter,
    BedrockBatchRequest,
)
from substrate.research_spend import (
    BillingClassification,
    BillingEvidenceKind,
    BillingRefusalReason,
    BindingConflict,
    IdempotencyConflict,
    InvalidTransition,
    LaunchExecutionIntent,
    LaunchOperationIntent,
    LaunchOperationState,
    LedgerIntegrityError,
    PaidHoldState,
    ProviderSubmissionState,
    ResearchSpendLedger,
    RunBinding,
    RunNotFound,
)
from substrate.research_spend.ledger import _DDL, _MIGRATIONS, APPLICATION_ID


class TerminalBedrock:
    def __init__(self) -> None:
        self.request: dict[str, object] | None = None
        self.arn = "arn:aws:bedrock:us-east-1:123456789012:model-invocation-job/job-1"

    def create_model_invocation_job(self, **request: object) -> dict[str, object]:
        self.request = request
        return {"jobArn": self.arn}

    def get_model_invocation_job(self, *, jobIdentifier: str) -> dict[str, object]:
        assert self.request is not None and jobIdentifier == self.arn
        return {"jobArn": self.arn, "status": "Completed", **self.request}


def _billing_pending(tmp_path):
    db = tmp_path / "spend.sqlite3"
    ledger = ResearchSpendLedger(db)
    ledger.ensure_schema()
    binding = RunBinding("run-1", "owner-1", "session-1", "plan", 1)
    ledger.create_or_reopen_run("create", binding, 500)
    execution = LaunchExecutionIntent(
        "execution-1",
        "multimedia_research_v1",
        "reservation-1",
        "manifest",
        "integrity",
        "aws-bedrock",
        "batch-model",
        "route",
        "pricing",
        "workload",
        1,
        "request",
    )
    operation = LaunchOperationIntent(
        "operation-1",
        0,
        "leaf-1",
        "question",
        "payload",
        "aws-bedrock",
        "batch-model",
        "logical-1",
        LaunchOperationState.PENDING,
    )
    ledger.materialize_launch_execution("materialize", binding, execution, (operation,))
    account = "123456789012"
    request = BedrockBatchRequest(
        "job-1",
        "provider-model",
        f"arn:aws:iam::{account}:role/Antiek",
        "s3://in/x",
        "s3://out/x",
        24,
        hashlib.sha256(account.encode()).hexdigest(),
        "us-east-1",
    )
    adapter = BedrockBatchRecoveryAdapter(ledger, TerminalBedrock())
    submission = adapter.prepare(
        command_key="prepare",
        binding=binding,
        operation_id="operation-1",
        model="batch-model",
        request=request,
        projected_max_cents=200,
        projection_digest="projection",
        rate_snapshot="unresolved",
    )
    for key in ("mark", "create-job", "terminal"):
        submission = adapter.advance(
            command_key=key,
            submission_id=submission.intent.submission_id,
            owner_id="owner-1",
        )
    assert submission.state is ProviderSubmissionState.BILLING_PENDING
    return db, ledger, submission


def _evidence(submission, **extra):
    return {
        "account_digest": submission.intent.account_digest,
        "job_arn": submission.job_arn,
        "model": submission.intent.model,
        "owner_id": submission.owner_id,
        "provider": submission.intent.provider,
        "region": submission.intent.region,
        "run_id": submission.run_id,
        "submission_id": submission.intent.submission_id,
        **extra,
    }


def _contract_evidence(submission, kind):
    fields = {
        BillingEvidenceKind.PROVIDER_METERING: {
            "terminal_observation_digest": "terminal-sha",
            "manifest_object_identity": "s3://bucket/output.json.out",
            "manifest_object_version": "v1",
            "manifest_digest": "manifest-sha",
            "record_count": 2,
            "input_token_count": 3,
            "output_token_count": 4,
            "retrieved_at": "2026-07-15T00:00:00Z",
        },
        BillingEvidenceKind.DERIVED_LIST_PRICE: {
            "metering_digest": "metering-sha",
            "rate_provider": "aws-bedrock",
            "rate_model": "batch-model",
            "rate_region": "us-east-1",
            "rate_tier": "batch",
            "rate_snapshot_digest": "rate-sha",
            "input_rate_dec": "0.001",
            "output_rate_dec": "0.002",
            "input_token_count": 3,
            "output_token_count": 4,
            "calculated_cost_dec": "0.011",
        },
        BillingEvidenceKind.CUR_OPEN_PERIOD: {
            "report_identity": "cur-1",
            "billing_period": "2026-07",
            "product": "Amazon Bedrock",
            "operation": "BatchInference",
            "usage_type": "tokens",
            "resource_id": "",
            "line_item_type": "Usage",
            "usage_amount_dec": "7",
            "rate_dec": "0.001",
            "cost_dec": "0.01",
            "tags": {},
            "ingested_at": "2026-07-15T00:00:00Z",
            "report_status": "open",
        },
        BillingEvidenceKind.CUR_FINAL_UNATTRIBUTABLE: {
            "report_identity": "invoice-1",
            "billing_period": "2026-07",
            "product": "Amazon Bedrock",
            "operation": "BatchInference",
            "usage_type": "tokens",
            "resource_id": "",
            "line_item_type": "Usage",
            "usage_amount_dec": "7",
            "rate_dec": "0.001",
            "cost_dec": "0.01",
            "tags": {},
            "ingested_at": "2026-08-15T00:00:00Z",
            "report_status": "final",
        },
        BillingEvidenceKind.UNSUPPORTED: {},
    }[kind]
    return _evidence(submission, **fields)


def _linked_contract_evidence(db, ledger, submission, kind, raw_digest):
    evidence = _contract_evidence(submission, kind)
    if kind is BillingEvidenceKind.PROVIDER_METERING:
        with sqlite3.connect(db) as connection:
            evidence["terminal_observation_digest"] = connection.execute(
                "SELECT evidence_sha256 FROM research_provider_observations "
                "WHERE submission_id=? AND provider_status='Completed'",
                (submission.intent.submission_id,),
            ).fetchone()[0]
        evidence["manifest_digest"] = raw_digest
    elif kind is BillingEvidenceKind.DERIVED_LIST_PRICE:
        metering_evidence = _linked_contract_evidence(
            db, ledger, submission, BillingEvidenceKind.PROVIDER_METERING, raw_digest
        )
        metering = ledger.assess_provider_billing(
            "metering",
            submission.intent.submission_id,
            "owner-1",
            "metering",
            BillingEvidenceKind.PROVIDER_METERING,
            metering_evidence,
            raw_digest,
        )
        evidence["metering_digest"] = hashlib.sha256(metering.evidence_json.encode()).hexdigest()
    return evidence


CASES = (
    (
        BillingEvidenceKind.PROVIDER_METERING,
        BillingClassification.PROVIDER_METERING_ONLY,
        (BillingRefusalReason.METERING_NOT_USD,),
    ),
    (
        BillingEvidenceKind.DERIVED_LIST_PRICE,
        BillingClassification.DERIVED_LIST_PRICE,
        (BillingRefusalReason.DERIVED_NOT_INVOICED, BillingRefusalReason.ADJUSTMENTS_UNALLOCATED),
    ),
    (
        BillingEvidenceKind.CUR_OPEN_PERIOD,
        BillingClassification.CUR_AGGREGATE_OBSERVED,
        (BillingRefusalReason.PERIOD_NOT_FINAL, BillingRefusalReason.JOB_JOIN_UNPROVEN),
    ),
    (
        BillingEvidenceKind.CUR_FINAL_UNATTRIBUTABLE,
        BillingClassification.INVOICE_PERIOD_FINALIZED_UNATTRIBUTABLE,
        (BillingRefusalReason.JOB_JOIN_UNPROVEN, BillingRefusalReason.ADJUSTMENTS_UNALLOCATED),
    ),
    (
        BillingEvidenceKind.UNSUPPORTED,
        BillingClassification.EXACT_JOB_FINAL_COST_UNAVAILABLE,
        (BillingRefusalReason.EVIDENCE_UNSUPPORTED,),
    ),
)


@pytest.mark.parametrize(("kind", "classification", "reasons"), CASES)
def test_every_evidence_class_is_append_only_and_leaves_all_authority_unchanged(
    tmp_path, kind, classification, reasons
) -> None:
    db, ledger, submission = _billing_pending(tmp_path)
    protected = (
        "research_provider_submissions",
        "research_spend_holds",
        "research_spend_runs",
        "research_launch_operations",
    )
    with sqlite3.connect(db) as connection:
        before = {
            table: connection.execute(f"SELECT * FROM {table}").fetchall() for table in protected
        }
        qualification_schema_before = connection.execute(
            "SELECT name,sql FROM sqlite_master WHERE name LIKE '%qualification%' ORDER BY name"
        ).fetchall()
    raw_digest = hashlib.sha256(b"raw").hexdigest()
    evidence = _linked_contract_evidence(db, ledger, submission, kind, raw_digest)
    assessment = ledger.assess_provider_billing(
        "assess",
        submission.intent.submission_id,
        "owner-1",
        "evidence-1",
        kind,
        evidence,
        raw_digest,
    )
    assert assessment.classification is classification
    assert assessment.reason_codes == reasons
    assert assessment.settlement_authorized is False
    assert (
        ledger.assess_provider_billing(
            "assess",
            submission.intent.submission_id,
            "owner-1",
            "evidence-1",
            kind,
            json.loads(assessment.evidence_json),
            raw_digest,
        )
        == assessment
    )
    assert ledger.provider_submission(submission.intent.submission_id, "owner-1") == submission
    assert (
        ledger.provider_billing_assessments(submission.intent.submission_id, "owner-1")[-1]
        == assessment
    )
    assert ledger.hold(submission.hold_id).state is PaidHoldState.UNKNOWN
    assert ledger.balance("run-1").held_cents == 200
    assert (
        ledger.launch_execution_for_run("run-1", "owner-1").operations[0].intent.state
        is LaunchOperationState.UNKNOWN
    )
    with sqlite3.connect(db) as connection:
        after = {
            table: connection.execute(f"SELECT * FROM {table}").fetchall() for table in protected
        }
        assert after == before
        assert (
            connection.execute(
                "SELECT name,sql FROM sqlite_master WHERE name LIKE '%qualification%' ORDER BY name"
            ).fetchall()
            == qualification_schema_before
            == []
        )
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute("UPDATE research_provider_billing_assessments SET raw_digest='x'")
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute("DELETE FROM research_provider_billing_assessments")


@pytest.mark.parametrize(
    ("attack", "reason"),
    [
        ({"tag_only": True}, BillingRefusalReason.TAG_JOIN_UNPROVEN),
        ({"caller_classification": "exact_final"}, BillingRefusalReason.CALLER_ASSERTION_UNTRUSTED),
        ({"line_item_type": "Credit"}, BillingRefusalReason.ADJUSTMENTS_UNALLOCATED),
        ({"line_item_type": "Refund"}, BillingRefusalReason.ADJUSTMENTS_UNALLOCATED),
        ({"line_item_type": "Tax"}, BillingRefusalReason.ADJUSTMENTS_UNALLOCATED),
        ({"matching_concurrent_jobs": 2}, BillingRefusalReason.JOB_JOIN_UNPROVEN),
        ({"rows": [{"id": "line-1"}, {"id": "line-1"}]}, BillingRefusalReason.DUPLICATE_EVIDENCE),
        (
            {"claims": [{"field": "cost", "value": "1"}, {"field": "cost", "value": "2"}]},
            BillingRefusalReason.CONTRADICTORY_EVIDENCE,
        ),
    ],
)
def test_unsupported_claims_always_refuse_settlement(tmp_path, attack, reason) -> None:
    _, ledger, submission = _billing_pending(tmp_path)
    result = ledger.assess_provider_billing(
        "assess",
        submission.intent.submission_id,
        "owner-1",
        "attack",
        BillingEvidenceKind.UNSUPPORTED,
        _evidence(submission, **attack),
        hashlib.sha256(b"attack").hexdigest(),
    )
    assert result.classification is BillingClassification.EXACT_JOB_FINAL_COST_UNAVAILABLE
    assert result.reason_codes == (reason,)
    assert result.settlement_authorized is False
    assert ledger.balance("run-1").held_cents == 200


def test_replay_changed_evidence_or_assessment_identity_conflicts(tmp_path) -> None:
    _, ledger, submission = _billing_pending(tmp_path)
    args = (
        submission.intent.submission_id,
        "owner-1",
        "metering",
        BillingEvidenceKind.PROVIDER_METERING,
    )
    digest = hashlib.sha256(b"raw").hexdigest()
    ledger.assess_provider_billing("assess", *args, _evidence(submission, record_count=1), digest)
    with pytest.raises(IdempotencyConflict):
        ledger.assess_provider_billing(
            "assess", *args, _evidence(submission, record_count=2), digest
        )
    with pytest.raises(IdempotencyConflict):
        ledger.assess_provider_billing(
            "other-command", *args, _evidence(submission, record_count=1), digest
        )


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("evidence_json", "{}"),
        ("classification", "exact_job_final_cost_unavailable"),
        ("reason_codes_json", "[]"),
        ("hold_id", "substituted-hold"),
        ("owner_id", "substituted-owner"),
        ("raw_digest", "f" * 64),
        ("created_at", "2099-01-01T00:00:00Z"),
    ],
)
def test_persisted_canonical_scalar_and_cross_table_tampering_is_detected(
    tmp_path, column, value
) -> None:
    db, ledger, submission = _billing_pending(tmp_path)
    raw_digest = hashlib.sha256(b"raw").hexdigest()
    assessment = ledger.assess_provider_billing(
        "assess",
        submission.intent.submission_id,
        "owner-1",
        "evidence",
        BillingEvidenceKind.PROVIDER_METERING,
        _linked_contract_evidence(
            db, ledger, submission, BillingEvidenceKind.PROVIDER_METERING, raw_digest
        ),
        raw_digest,
    )
    with sqlite3.connect(db) as connection:
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute("DROP TRIGGER research_provider_billing_assessments_no_update")
        connection.execute(f"UPDATE research_provider_billing_assessments SET {column}=?", (value,))
    with pytest.raises((LedgerIntegrityError, RunNotFound)):
        ledger.provider_billing_assessments(submission.intent.submission_id, "owner-1")
    assert assessment.settlement_authorized is False


def test_coordinated_kind_classification_and_reason_tampering_is_detected(tmp_path) -> None:
    db, ledger, submission = _billing_pending(tmp_path)
    ledger.assess_provider_billing(
        "assess",
        submission.intent.submission_id,
        "owner-1",
        "evidence",
        BillingEvidenceKind.PROVIDER_METERING,
        _contract_evidence(submission, BillingEvidenceKind.PROVIDER_METERING),
        hashlib.sha256(b"raw").hexdigest(),
    )
    with sqlite3.connect(db) as connection:
        connection.execute("DROP TRIGGER research_provider_billing_assessments_no_update")
        connection.execute(
            "UPDATE research_provider_billing_assessments SET evidence_kind=?,"
            "classification=?,reason_codes_json=?",
            (
                "derived_list_price",
                "derived_list_price",
                '["derived_not_invoiced","adjustments_unallocated"]',
            ),
        )
    with pytest.raises(LedgerIntegrityError):
        ledger.provider_billing_assessments(submission.intent.submission_id, "owner-1")


@pytest.mark.parametrize(
    "kind",
    [
        BillingEvidenceKind.PROVIDER_METERING,
        BillingEvidenceKind.DERIVED_LIST_PRICE,
        BillingEvidenceKind.CUR_OPEN_PERIOD,
        BillingEvidenceKind.CUR_FINAL_UNATTRIBUTABLE,
    ],
)
def test_missing_required_contract_fields_downgrade_to_unavailable(tmp_path, kind) -> None:
    _, ledger, submission = _billing_pending(tmp_path)
    result = ledger.assess_provider_billing(
        "assess",
        submission.intent.submission_id,
        "owner-1",
        "missing",
        kind,
        _evidence(submission),
        hashlib.sha256(b"raw").hexdigest(),
    )
    assert result.classification is BillingClassification.EXACT_JOB_FINAL_COST_UNAVAILABLE
    assert result.reason_codes == (BillingRefusalReason.MISSING_REQUIRED_FIELD,)


@pytest.mark.parametrize(
    ("kind", "changes"),
    [
        (BillingEvidenceKind.PROVIDER_METERING, {"record_count": True}),
        (BillingEvidenceKind.PROVIDER_METERING, {"input_token_count": "3"}),
        (BillingEvidenceKind.PROVIDER_METERING, {"manifest_digest": ""}),
        (BillingEvidenceKind.CUR_OPEN_PERIOD, {"report_status": "final"}),
        (BillingEvidenceKind.CUR_FINAL_UNATTRIBUTABLE, {"report_status": "open"}),
        (BillingEvidenceKind.DERIVED_LIST_PRICE, {"rate_provider": "other"}),
        (BillingEvidenceKind.DERIVED_LIST_PRICE, {"rate_model": "other"}),
        (BillingEvidenceKind.DERIVED_LIST_PRICE, {"rate_region": "eu-west-1"}),
    ],
)
def test_semantically_invalid_contracts_downgrade_to_unavailable(tmp_path, kind, changes) -> None:
    _, ledger, submission = _billing_pending(tmp_path)
    evidence = _contract_evidence(submission, kind)
    evidence.update(changes)
    result = ledger.assess_provider_billing(
        "assess",
        submission.intent.submission_id,
        "owner-1",
        "invalid",
        kind,
        evidence,
        hashlib.sha256(b"raw").hexdigest(),
    )
    assert result.classification is BillingClassification.EXACT_JOB_FINAL_COST_UNAVAILABLE
    assert result.reason_codes == (BillingRefusalReason.EVIDENCE_INVARIANT_FAILED,)


def test_derived_counts_must_match_linked_metering_assessment(tmp_path) -> None:
    db, ledger, submission = _billing_pending(tmp_path)
    raw_digest = hashlib.sha256(b"raw").hexdigest()
    evidence = _linked_contract_evidence(
        db, ledger, submission, BillingEvidenceKind.DERIVED_LIST_PRICE, raw_digest
    )
    evidence.update(input_token_count=4, calculated_cost_dec="0.012")
    result = ledger.assess_provider_billing(
        "derived-mismatch",
        submission.intent.submission_id,
        "owner-1",
        "derived-mismatch",
        BillingEvidenceKind.DERIVED_LIST_PRICE,
        evidence,
        raw_digest,
    )
    assert result.classification is BillingClassification.EXACT_JOB_FINAL_COST_UNAVAILABLE
    assert result.reason_codes == (BillingRefusalReason.EVIDENCE_INVARIANT_FAILED,)


@pytest.mark.parametrize(
    "field",
    [
        "account_digest",
        "job_arn",
        "model",
        "owner_id",
        "provider",
        "region",
        "run_id",
        "submission_id",
    ],
)
def test_cross_identity_substitution_fails_closed(tmp_path, field) -> None:
    _, ledger, submission = _billing_pending(tmp_path)
    evidence = _evidence(submission)
    evidence[field] = "wrong"
    with pytest.raises(BindingConflict):
        ledger.assess_provider_billing(
            "assess",
            submission.intent.submission_id,
            "owner-1",
            field,
            BillingEvidenceKind.UNSUPPORTED,
            evidence,
            hashlib.sha256(b"raw").hexdigest(),
        )
    assert ledger.balance("run-1").held_cents == 200


@pytest.mark.parametrize("bad", [1.2, {"record_count": -1}, {"cost_dec": "01.0"}])
def test_malformed_exact_values_fail_closed(tmp_path, bad) -> None:
    _, ledger, submission = _billing_pending(tmp_path)
    evidence = _evidence(submission)
    if isinstance(bad, dict):
        evidence.update(bad)
    else:
        evidence["usage"] = bad
    with pytest.raises((TypeError, ValueError)):
        ledger.assess_provider_billing(
            "assess",
            submission.intent.submission_id,
            "owner-1",
            "bad",
            BillingEvidenceKind.UNSUPPORTED,
            evidence,
            hashlib.sha256(b"raw").hexdigest(),
        )


def test_signed_cur_adjustment_is_exact_but_remains_unattributable(tmp_path) -> None:
    _, ledger, submission = _billing_pending(tmp_path)
    evidence = _contract_evidence(submission, BillingEvidenceKind.CUR_FINAL_UNATTRIBUTABLE)
    evidence.update(line_item_type="DiscountedUsage", cost_dec="-0.01")
    result = ledger.assess_provider_billing(
        "assess",
        submission.intent.submission_id,
        "owner-1",
        "discount",
        BillingEvidenceKind.CUR_FINAL_UNATTRIBUTABLE,
        evidence,
        hashlib.sha256(b"raw").hexdigest(),
    )
    assert result.classification is BillingClassification.INVOICE_PERIOD_FINALIZED_UNATTRIBUTABLE
    assert result.settlement_authorized is False


def test_integrity_check_traverses_billing_assessments(tmp_path) -> None:
    db, ledger, submission = _billing_pending(tmp_path)
    ledger.assess_provider_billing(
        "assess",
        submission.intent.submission_id,
        "owner-1",
        "evidence",
        BillingEvidenceKind.UNSUPPORTED,
        _evidence(submission),
        hashlib.sha256(b"raw").hexdigest(),
    )
    with sqlite3.connect(db) as connection:
        connection.execute("DROP TRIGGER research_provider_billing_assessments_no_update")
        connection.execute(
            "UPDATE research_provider_billing_assessments SET evidence_sha256='corrupt'"
        )
    with pytest.raises(LedgerIntegrityError):
        ledger.integrity_check()


def test_only_billing_pending_bound_submission_accepts_assessment(tmp_path) -> None:
    _, ledger, submission = _billing_pending(tmp_path)
    with sqlite3.connect(ledger._db_path) as connection:
        connection.execute("DROP TRIGGER research_provider_submissions_guard_transition")
        connection.execute("UPDATE research_provider_submissions SET state='running'")
    with pytest.raises(InvalidTransition):
        ledger.assess_provider_billing(
            "assess",
            submission.intent.submission_id,
            "owner-1",
            "early",
            BillingEvidenceKind.UNSUPPORTED,
            _evidence(submission),
            hashlib.sha256(b"raw").hexdigest(),
        )


@pytest.mark.parametrize("statement_index", range(1, len(_MIGRATIONS[4]) + 1))
def test_schema_v4_to_v5_failure_rolls_back_every_statement(tmp_path, statement_index) -> None:
    db = tmp_path / f"v4-{statement_index}.sqlite3"
    with sqlite3.connect(db) as connection:
        for statement in (*_DDL, *_MIGRATIONS[2], *_MIGRATIONS[3]):
            connection.execute(statement)
        connection.execute(f"PRAGMA application_id={APPLICATION_ID}")
        connection.execute("PRAGMA user_version=4")
        before = "\n".join(connection.iterdump()).encode()

    def fail(name: str) -> None:
        if name == f"schema:4:after_migration:{statement_index}":
            raise RuntimeError("injected v5 migration failure")

    with pytest.raises(RuntimeError, match="injected"):
        ResearchSpendLedger(db, failure_injector=fail).ensure_schema()
    with sqlite3.connect(db) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 4
        assert "\n".join(connection.iterdump()).encode() == before
    ResearchSpendLedger(db).ensure_schema()


def test_schema_v4_to_v5_before_commit_failure_rolls_back_version(tmp_path) -> None:
    db = tmp_path / "v4-before-commit.sqlite3"
    with sqlite3.connect(db) as connection:
        for statement in (*_DDL, *_MIGRATIONS[2], *_MIGRATIONS[3]):
            connection.execute(statement)
        connection.execute(f"PRAGMA application_id={APPLICATION_ID}")
        connection.execute("PRAGMA user_version=4")
        before = "\n".join(connection.iterdump()).encode()

    def fail(name: str) -> None:
        if name == "schema:before_commit":
            raise RuntimeError("injected before commit")

    with pytest.raises(RuntimeError, match="before commit"):
        ResearchSpendLedger(db, failure_injector=fail).ensure_schema()
    with sqlite3.connect(db) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 4
        assert "\n".join(connection.iterdump()).encode() == before
