from __future__ import annotations

import hashlib
import json
from dataclasses import replace

import pytest

from substrate.multimedia.bedrock_batch_adapter import (
    BedrockBatchRecoveryAdapter,
    BedrockBatchRequest,
)
from substrate.research_spend import (
    IdempotencyConflict,
    LaunchExecutionIntent,
    LaunchOperationIntent,
    LaunchOperationState,
    PaidHoldState,
    ProviderSubmissionState,
    ResearchSpendLedger,
    RunBinding,
)


class StatefulBedrock:
    def __init__(self, account: str, region: str) -> None:
        self.account = account
        self.region = region
        self.jobs: dict[str, tuple[dict[str, object], str]] = {}
        self.create_attempts = 0
        self.lose_next_response = True
        self.status = "InProgress"

    def create_model_invocation_job(self, **request: object) -> dict[str, object]:
        self.create_attempts += 1
        token = str(request["clientRequestToken"])
        existing = self.jobs.get(token)
        if existing is not None and existing[0] != request:
            raise ValueError("idempotency token reused with changed terms")
        arn = f"arn:aws:bedrock:{self.region}:{self.account}:model-invocation-job/job-1"
        self.jobs.setdefault(token, (request, arn))
        if self.lose_next_response:
            self.lose_next_response = False
            raise TimeoutError("response lost after acceptance")
        return {"jobArn": arn}

    def get_model_invocation_job(self, *, jobIdentifier: str) -> dict[str, object]:
        request, arn = next(iter(self.jobs.values()))
        assert jobIdentifier == arn
        return {
            "jobArn": arn,
            "status": self.status,
            **request,
        }


def _authority(tmp_path):
    ledger = ResearchSpendLedger(tmp_path / "spend.sqlite3")
    ledger.ensure_schema()
    binding = RunBinding("run-1", "owner-1", "session-1", "plan-digest", 1)
    ledger.create_or_reopen_run("create", binding, 500)
    execution = LaunchExecutionIntent(
        "execution-1", "multimedia_research_v1", "reservation-1", "manifest-digest",
        "integrity-digest", "aws-bedrock", "batch-model", "route-digest",
        "pricing-digest", "workload-digest", 1, "request-digest",
    )
    operation = LaunchOperationIntent(
        "operation-1", 0, "leaf-1", "private question", "payload-digest",
        "aws-bedrock", "batch-model", "logical-1", LaunchOperationState.PENDING,
    )
    ledger.materialize_launch_execution("materialize", binding, execution, (operation,))
    return ledger, binding


def _request(account: str = "123456789012") -> BedrockBatchRequest:
    return BedrockBatchRequest(
        job_name="job-name", model_id="provider-model",
        role_arn=f"arn:aws:iam::{account}:role/AntiekBedrockBatch",
        input_s3_uri="s3://input-bucket/prefix/manifest.jsonl",
        output_s3_uri="s3://output-bucket/prefix/", timeout_hours=24,
        account_digest=hashlib.sha256(account.encode()).hexdigest(), region="us-east-1",
    )


def test_lost_create_response_replays_exact_request_and_binds_one_job(tmp_path) -> None:
    ledger, binding = _authority(tmp_path)
    service = StatefulBedrock("123456789012", "us-east-1")
    adapter = BedrockBatchRecoveryAdapter(ledger, service)
    submission = adapter.prepare(
        command_key="prepare", binding=binding, operation_id="operation-1",
        model="batch-model", request=_request(), projected_max_cents=200,
        projection_digest="projection-digest", rate_snapshot="unresolved-bedrock-billing",
    )
    assert submission.state is ProviderSubmissionState.PREPARED
    assert ledger.balance("run-1").held_cents == 200
    request = json.loads(submission.intent.create_request_json)
    assert set(request) == {
        "clientRequestToken", "inputDataConfig", "jobName", "modelId",
        "outputDataConfig", "roleArn", "timeoutDurationInHours",
    }
    assert request["roleArn"] == "arn:aws:iam::123456789012:role/AntiekBedrockBatch"
    assert ledger.launch_execution_for_run("run-1", "owner-1").operations[0].intent.state is LaunchOperationState.CLAIMED

    submission = adapter.advance(command_key="mark", submission_id=submission.intent.submission_id, owner_id="owner-1")
    assert submission.state is ProviderSubmissionState.SUBMIT_POSSIBLE
    assert ledger.launch_execution_for_run("run-1", "owner-1").operations[0].intent.state is LaunchOperationState.DISPATCH_POSSIBLE
    submission = adapter.advance(command_key="lost", submission_id=submission.intent.submission_id, owner_id="owner-1")
    assert submission.state is ProviderSubmissionState.CREATE_OUTCOME_UNKNOWN
    assert ledger.launch_execution_for_run("run-1", "owner-1").operations[0].intent.state is LaunchOperationState.UNKNOWN

    restarted = BedrockBatchRecoveryAdapter(ResearchSpendLedger(tmp_path / "spend.sqlite3"), service)
    submission = restarted.advance(command_key="replay", submission_id=submission.intent.submission_id, owner_id="owner-1")
    assert submission.state is ProviderSubmissionState.IDENTITY_BOUND
    assert submission.attempt_count == 2
    assert service.create_attempts == 2
    assert len(service.jobs) == 1
    assert ledger.hold(submission.hold_id).state is PaidHoldState.UNKNOWN
    assert len(ledger.provider_observations(submission.intent.submission_id, "owner-1")) == 3

    submission = restarted.advance(command_key="get-running", submission_id=submission.intent.submission_id, owner_id="owner-1")
    assert submission.state is ProviderSubmissionState.RUNNING
    service.status = "Completed"
    submission = restarted.advance(command_key="get-terminal", submission_id=submission.intent.submission_id, owner_id="owner-1")
    assert submission.state is ProviderSubmissionState.BILLING_PENDING
    assert ledger.balance("run-1").held_cents == 200
    assert ledger.hold(submission.hold_id).state is PaidHoldState.UNKNOWN
    assert len(ledger.provider_observations(submission.intent.submission_id, "owner-1")) == 5


def test_prepare_replay_is_exact_and_changed_terms_conflict(tmp_path) -> None:
    ledger, binding = _authority(tmp_path)
    adapter = BedrockBatchRecoveryAdapter(ledger, StatefulBedrock("123456789012", "us-east-1"))
    kwargs = dict(
        command_key="prepare", binding=binding, operation_id="operation-1", model="batch-model",
        request=_request(), projected_max_cents=200, projection_digest="projection-digest",
        rate_snapshot="unresolved-bedrock-billing",
    )
    first = adapter.prepare(**kwargs)
    assert adapter.prepare(**kwargs) == first
    with pytest.raises(IdempotencyConflict):
        adapter.prepare(**{**kwargs, "request": replace(_request(), output_s3_uri="s3://other/prefix/")})
    assert ledger.balance("run-1").held_cents == 200


def test_bad_arn_freezes_submission_without_releasing_hold(tmp_path) -> None:
    ledger, binding = _authority(tmp_path)
    service = StatefulBedrock("999999999999", "us-east-1")
    service.lose_next_response = False
    adapter = BedrockBatchRecoveryAdapter(ledger, service)
    submission = adapter.prepare(
        command_key="prepare", binding=binding, operation_id="operation-1", model="batch-model",
        request=_request(), projected_max_cents=200, projection_digest="projection-digest",
        rate_snapshot="unresolved-bedrock-billing",
    )
    adapter.advance(command_key="mark", submission_id=submission.intent.submission_id, owner_id="owner-1")
    submission = adapter.advance(command_key="create-job", submission_id=submission.intent.submission_id, owner_id="owner-1")
    assert submission.state is ProviderSubmissionState.INTEGRITY_CONFLICT
    assert submission.job_arn is None
    assert ledger.balance("run-1").held_cents == 200


def test_bad_poll_arn_is_recorded_as_integrity_conflict(tmp_path) -> None:
    ledger, binding = _authority(tmp_path)
    service = StatefulBedrock("123456789012", "us-east-1")
    service.lose_next_response = False
    adapter = BedrockBatchRecoveryAdapter(ledger, service)
    submission = adapter.prepare(
        command_key="prepare", binding=binding, operation_id="operation-1",
        model="batch-model", request=_request(), projected_max_cents=200,
        projection_digest="projection-digest", rate_snapshot="unresolved-bedrock-billing",
    )
    adapter.advance(command_key="mark", submission_id=submission.intent.submission_id, owner_id="owner-1")
    submission = adapter.advance(command_key="create-job", submission_id=submission.intent.submission_id, owner_id="owner-1")
    service.get_model_invocation_job = lambda **_: {
        "jobArn": "arn:aws:bedrock:us-east-1:999999999999:model-invocation-job/job-1"
    }
    submission = adapter.advance(command_key="bad-poll", submission_id=submission.intent.submission_id, owner_id="owner-1")
    assert submission.state is ProviderSubmissionState.INTEGRITY_CONFLICT
    assert ledger.balance("run-1").held_cents == 200


def test_timeout_must_satisfy_bedrock_minimum() -> None:
    with pytest.raises(ValueError, match="24 and 168"):
        replace(_request(), timeout_hours=23)


def test_nonempty_tags_are_canonicalized_without_recursion() -> None:
    request = replace(_request(), tags_json='[{"key":"team","value":"antiek"}]')
    assert request.create_request("a" * 64)["tags"] == [
        {"key": "team", "value": "antiek"}
    ]


def test_definitive_pre_acceptance_failure_releases_authority(tmp_path) -> None:
    ledger, binding = _authority(tmp_path)
    adapter = BedrockBatchRecoveryAdapter(
        ledger, StatefulBedrock("123456789012", "us-east-1")
    )
    submission = adapter.prepare(
        command_key="prepare", binding=binding, operation_id="operation-1",
        model="batch-model", request=_request(), projected_max_cents=200,
        projection_digest="projection-digest", rate_snapshot="unresolved-bedrock-billing",
    )
    submission = adapter.advance(
        command_key="mark", submission_id=submission.intent.submission_id,
        owner_id="owner-1",
    )
    submission = ledger.transition_provider_submission(
        "rejected", submission.intent.submission_id, "owner-1",
        ProviderSubmissionState.FAILED_PRE_ACCEPTANCE,
        source="typed_pre_acceptance_rejection", evidence_json="{}",
        raw_digest=hashlib.sha256(b"{}").hexdigest(),
    )
    assert submission.state is ProviderSubmissionState.FAILED_PRE_ACCEPTANCE
    assert ledger.hold(submission.hold_id).state is PaidHoldState.RELEASED
    assert ledger.balance("run-1").held_cents == 0
    operation = ledger.launch_execution_for_run("run-1", "owner-1").operations[0]
    assert operation.intent.state is LaunchOperationState.FAILED_TERMINAL
