"""Pull-driven Bedrock batch identity recovery with no production client factory."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from urllib.parse import urlsplit

from substrate.multimedia.bedrock_workload_bound import (
    BedrockBatchModelProfile,
    BedrockBatchWorkloadBound,
)
from substrate.research_spend import (
    BindingConflict,
    PaidHoldIntent,
    ProviderSubmissionIntent,
    ProviderSubmissionSnapshot,
    ProviderSubmissionState,
    ResearchSpendLedger,
    RunBinding,
)

_ARN = re.compile(r"^arn:(aws(?:-[a-z]+)?):bedrock:([a-z0-9-]+):(\d{12}):model-invocation-job/([A-Za-z0-9._-]+)$")
_TERMINAL = frozenset({"Completed", "Failed", "Stopped", "PartiallyCompleted", "Expired"})
_RUNNING = frozenset({"Submitted", "Validating", "Scheduled", "InProgress", "Stopping"})


class BedrockControlPlaneClient(Protocol):
    def create_model_invocation_job(self, **request: object) -> Mapping[str, object]: ...
    def get_model_invocation_job(self, *, jobIdentifier: str) -> Mapping[str, object]: ...


class BedrockBatchError(RuntimeError):
    """Injected Bedrock evidence was ambiguous or contradicted durable intent."""


def _s3_key_has_segment(uri: object, segment: object) -> bool:
    if not isinstance(uri, str) or not isinstance(segment, str):
        return False
    parsed = urlsplit(uri)
    return (
        parsed.scheme == "s3"
        and bool(parsed.netloc)
        and parsed.username is None
        and parsed.password is None
        and parsed.port is None
        and not parsed.query
        and not parsed.fragment
        and segment in parsed.path.removeprefix("/").split("/")
    )


@dataclass(frozen=True)
class BedrockBatchRequest:
    job_name: str
    model_id: str
    role_arn: str
    input_s3_uri: str
    output_s3_uri: str
    timeout_hours: int
    account_digest: str
    region: str
    tags_json: str = "[]"
    vpc_config_json: str = "null"
    workload_bound_json: str | None = None
    workload_bound_digest: str | None = None

    def __post_init__(self) -> None:
        for name in ("job_name", "model_id", "role_arn", "input_s3_uri",
                     "output_s3_uri", "account_digest", "region"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be non-empty text")
        if not re.fullmatch(r"arn:aws(?:-[a-z]+)?:iam::\d{12}:role/[\w+=,.@/-]+", self.role_arn):
            raise ValueError("role_arn must be an AWS IAM role ARN")
        if not re.fullmatch(r"[0-9a-f]{64}", self.account_digest):
            raise ValueError("account_digest must be a lowercase SHA-256")
        if not self.input_s3_uri.startswith("s3://") or not self.output_s3_uri.startswith("s3://"):
            raise ValueError("input and output locations must be S3 URIs")
        if isinstance(self.timeout_hours, bool) or not 24 <= self.timeout_hours <= 168:
            raise ValueError("timeout_hours must be between 24 and 168")
        for name in ("tags_json", "vpc_config_json"):
            raw = getattr(self, name)
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{name} must be canonical JSON") from exc
            if _canonical(parsed) != raw:
                raise ValueError(f"{name} must be canonical JSON")
        if (self.workload_bound_json is None) != (self.workload_bound_digest is None):
            raise ValueError("workload bound JSON and digest must be supplied together")
        if self.workload_bound_json is not None:
            if not re.fullmatch(r"[0-9a-f]{64}", self.workload_bound_digest or ""):
                raise ValueError("workload_bound_digest must be a lowercase SHA-256")
            if hashlib.sha256(self.workload_bound_json.encode()).hexdigest() != self.workload_bound_digest:
                raise ValueError("workload bound digest mismatch")
            bound = BedrockBatchWorkloadBound.from_json(self.workload_bound_json)
            workload_digest = bound.workload_sha256
            if not _s3_key_has_segment(self.input_s3_uri, workload_digest):
                raise ValueError("input S3 URI must contain the workload SHA-256 path segment")

    @classmethod
    def from_workload_bound(
        cls, *, workload_bound: BedrockBatchWorkloadBound, **request: object,
    ) -> BedrockBatchRequest:
        """Construct the authority-bearing request from a validated redacted bound."""
        return cls(
            **request,
            workload_bound_json=workload_bound.canonical_json,
            workload_bound_digest=workload_bound.digest,
        )

    def create_request(self, token: str) -> dict[str, object]:
        request: dict[str, object] = {
            "clientRequestToken": token,
            "jobName": self.job_name,
            "modelId": self.model_id,
            "roleArn": self.role_arn,
            "inputDataConfig": {"s3InputDataConfig": {"s3Uri": self.input_s3_uri}},
            "outputDataConfig": {"s3OutputDataConfig": {"s3Uri": self.output_s3_uri}},
            "timeoutDurationInHours": self.timeout_hours,
        }
        tags = json.loads(self.tags_json)
        vpc_config = json.loads(self.vpc_config_json)
        if tags:
            request["tags"] = tags
        if vpc_config is not None:
            request["vpcConfig"] = vpc_config
        return request


def _canonical(value: object) -> str:
    def check(item: object) -> object:
        if item is None or isinstance(item, (str, int, bool)):
            return item
        if isinstance(item, list):
            return [check(element) for element in item]
        if isinstance(item, dict) and all(isinstance(key, str) for key in item):
            return {key: check(value) for key, value in item.items()}
        raise TypeError("Bedrock request accepts exact JSON scalars without floats")
    return json.dumps(check(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


class BedrockBatchRecoveryAdapter:
    """Test-authority adapter. A client must always be explicitly injected."""

    provider = "aws-bedrock"
    adapter_contract = "aws-bedrock-model-invocation-job-workload-bound-v1"
    recovery_strategy = "exact-create-replay-by-client-request-token"

    def __init__(self, ledger: ResearchSpendLedger, client: BedrockControlPlaneClient) -> None:
        self.ledger = ledger
        self.client = client

    def prepare(
        self, *, command_key: str, binding: RunBinding, operation_id: str,
        model: str, request: BedrockBatchRequest, workload_bytes: bytes,
    ) -> ProviderSubmissionSnapshot:
        if request.workload_bound_json is None or request.workload_bound_digest is None:
            raise BedrockBatchError("prepare requires a workload-bound request")
        bound_contract = BedrockBatchWorkloadBound.from_json(request.workload_bound_json)
        bound_contract.verify_workload_bytes(workload_bytes)
        if bound_contract.reservation_cents == 0:
            raise BedrockBatchError("paid Bedrock dispatch requires a positive reservation")
        profile = BedrockBatchModelProfile.from_json(bound_contract.profile_json)
        if (
            model != profile.antiek_model
            or request.model_id != profile.provider_model_id
            or request.region != profile.region
        ):
            raise BedrockBatchError("request route conflicts with workload bound")
        bound_contract.require_current(datetime.now(UTC))
        seed = {"operation_id": operation_id, "request": request.__dict__}
        token = _digest({"domain": "bedrock-batch-token-v1", **seed})
        submission_id = "rps_" + _digest({"domain": "provider-submission-v1", **seed})[:48]
        create_json = _canonical(request.create_request(token))
        hold = PaidHoldIntent(
            reservation_key="bedrock-reservation:" + submission_id,
            seam_id="multimedia.research.bedrock.batch",
            provider=self.provider, model=model, operation="create-model-invocation-job",
            operation_digest=_digest(seed), projection_digest=request.workload_bound_digest,
            rate_snapshot=request.workload_bound_json, provider_idempotency_key=token,
        )
        intent = ProviderSubmissionIntent(
            submission_id=submission_id, operation_id=operation_id, provider=self.provider,
            model=model, adapter_contract=self.adapter_contract, account_digest=request.account_digest,
            region=request.region, provider_model_id=request.model_id, client_request_token=token,
            create_request_json=create_json, recovery_strategy=self.recovery_strategy,
        )
        return self.ledger.prepare_provider_submission(
            command_key, binding, hold, bound_contract.reservation_cents, intent
        )

    def advance(self, *, command_key: str, submission_id: str, owner_id: str) -> ProviderSubmissionSnapshot:
        submission = self.ledger.provider_submission(submission_id, owner_id)
        if submission.intent.adapter_contract != self.adapter_contract:
            raise BedrockBatchError("unsupported Bedrock adapter contract")
        self._revalidate_bound_submission(
            submission,
            require_current=submission.state in {
                ProviderSubmissionState.SUBMIT_POSSIBLE,
                ProviderSubmissionState.CREATE_OUTCOME_UNKNOWN,
            },
        )
        if submission.state is ProviderSubmissionState.PREPARED:
            return self._transition(command_key, submission, ProviderSubmissionState.SUBMIT_POSSIBLE,
                                    "local_submit_marker", {"provider_call": False})
        if submission.state in {ProviderSubmissionState.SUBMIT_POSSIBLE, ProviderSubmissionState.CREATE_OUTCOME_UNKNOWN}:
            request = json.loads(submission.intent.create_request_json)
            try:
                response = self.client.create_model_invocation_job(**request)
            except Exception as exc:
                return self._transition(command_key, submission, ProviderSubmissionState.CREATE_OUTCOME_UNKNOWN,
                                        "create_exception", {"exception_type": type(exc).__name__}, attempt=True)
            try:
                arn = self._validated_arn(response, submission)
            except (BedrockBatchError, BindingConflict) as exc:
                return self._transition(command_key, submission, ProviderSubmissionState.INTEGRITY_CONFLICT,
                                        "create_integrity_conflict", {"reason": type(exc).__name__}, attempt=True)
            return self._transition(command_key, submission, ProviderSubmissionState.IDENTITY_BOUND,
                                    "create_response", {"jobArn": arn}, job_arn=arn, attempt=True)
        if submission.state in {ProviderSubmissionState.IDENTITY_BOUND, ProviderSubmissionState.RUNNING}:
            assert submission.job_arn is not None
            try:
                response = self.client.get_model_invocation_job(jobIdentifier=submission.job_arn)
            except Exception as exc:
                return self._transition(command_key, submission, submission.state,
                                        "get_exception", {"exception_type": type(exc).__name__})
            return self._observe(command_key, submission, response)
        return submission

    def _revalidate_bound_submission(
        self, submission: ProviderSubmissionSnapshot, *, require_current: bool,
    ) -> None:
        hold = self.ledger.hold(submission.hold_id)
        try:
            bound_contract = BedrockBatchWorkloadBound.from_json(hold.intent.rate_snapshot)
            bound = bound_contract.as_dict()
            canonical = bound_contract.canonical_json
            profile = BedrockBatchModelProfile.from_json(bound_contract.profile_json)
            request = json.loads(submission.intent.create_request_json)
            input_uri = request["inputDataConfig"]["s3InputDataConfig"]["s3Uri"]
            reopened = BedrockBatchRequest.from_workload_bound(
                workload_bound=bound_contract,
                job_name=request["jobName"],
                model_id=request["modelId"],
                role_arn=request["roleArn"],
                input_s3_uri=input_uri,
                output_s3_uri=request["outputDataConfig"]["s3OutputDataConfig"]["s3Uri"],
                timeout_hours=request["timeoutDurationInHours"],
                account_digest=submission.intent.account_digest,
                region=submission.intent.region,
                tags_json=_canonical(request.get("tags", [])),
                vpc_config_json=_canonical(request.get("vpcConfig")),
            )
            seed = {"operation_id": submission.intent.operation_id, "request": reopened.__dict__}
            expected_token = _digest({"domain": "bedrock-batch-token-v1", **seed})
            expected_submission_id = "rps_" + _digest(
                {"domain": "provider-submission-v1", **seed}
            )[:48]
            if require_current:
                bound_contract.require_current(datetime.now(UTC))
            valid = (
                canonical == hold.intent.rate_snapshot
                and hashlib.sha256(canonical.encode()).hexdigest() == hold.intent.projection_digest
                and hold.projected_max_cents == bound["reservation_cents"]
                and submission.intent.model == profile.antiek_model
                and submission.intent.provider_model_id == profile.provider_model_id
                and submission.intent.region == profile.region
                and _s3_key_has_segment(input_uri, bound["workload_sha256"])
                and request["modelId"] == profile.provider_model_id
                and request["clientRequestToken"] == expected_token
                and submission.intent.client_request_token == expected_token
                and submission.intent.submission_id == expected_submission_id
                and hold.intent.operation_digest == _digest(seed)
                and hold.intent.provider_idempotency_key == expected_token
                and submission.intent.create_request_json
                == _canonical(reopened.create_request(expected_token))
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            valid = False
        if not valid:
            raise BedrockBatchError("persisted workload bound failed recovery validation")

    def _observe(self, command_key: str, submission: ProviderSubmissionSnapshot,
                 response: Mapping[str, object]) -> ProviderSubmissionSnapshot:
        try:
            arn = self._validated_arn(response, submission)
        except BedrockBatchError:
            return self._transition(
                command_key, submission, ProviderSubmissionState.INTEGRITY_CONFLICT,
                "get_integrity_conflict", {"invalid_identity": True},
                job_arn=submission.job_arn,
            )
        expected = json.loads(submission.intent.create_request_json)
        comparisons = {
            "clientRequestToken": "clientRequestToken",
            "inputDataConfig": "inputDataConfig",
            "jobName": "jobName",
            "modelId": "modelId",
            "outputDataConfig": "outputDataConfig",
            "roleArn": "roleArn",
            "timeoutDurationInHours": "timeoutDurationInHours",
        }
        if "vpcConfig" in expected:
            comparisons["vpcConfig"] = "vpcConfig"
        if arn != submission.job_arn or any(response.get(out) != expected[inp] for out, inp in comparisons.items()):
            return self._transition(command_key, submission, ProviderSubmissionState.INTEGRITY_CONFLICT,
                                    "get_integrity_conflict", {"mismatch": True}, job_arn=submission.job_arn)
        status = response.get("status")
        if status in _RUNNING:
            target = ProviderSubmissionState.RUNNING
        elif status in _TERMINAL:
            target = ProviderSubmissionState.BILLING_PENDING
        else:
            target = ProviderSubmissionState.INTEGRITY_CONFLICT
        return self._transition(command_key, submission, target, "get_response",
                                {"jobArn": arn, "status": status}, job_arn=arn,
                                provider_status=status if isinstance(status, str) else None)

    @staticmethod
    def _validated_arn(response: Mapping[str, object], submission: ProviderSubmissionSnapshot) -> str:
        arn = response.get("jobArn")
        match = _ARN.fullmatch(arn) if isinstance(arn, str) else None
        if match is None or match.group(2) != submission.intent.region:
            raise BedrockBatchError("Bedrock job ARN is invalid")
        if hashlib.sha256(match.group(3).encode()).hexdigest() != submission.intent.account_digest:
            raise BedrockBatchError("Bedrock job ARN account conflicts")
        return arn

    def _transition(self, command_key: str, submission: ProviderSubmissionSnapshot,
                    target: ProviderSubmissionState, source: str, evidence: object, *,
                    job_arn: str | None = None, attempt: bool = False,
                    provider_status: str | None = None) -> ProviderSubmissionSnapshot:
        raw = _canonical(evidence)
        return self.ledger.transition_provider_submission(
            command_key, submission.intent.submission_id, submission.owner_id, target,
            job_arn=job_arn, source=source, evidence_json=raw, raw_digest=hashlib.sha256(raw.encode()).hexdigest(),
            provider_status=provider_status, increment_attempt=attempt,
        )


__all__ = ["BedrockBatchError", "BedrockBatchRecoveryAdapter", "BedrockBatchRequest", "BedrockControlPlaneClient"]
