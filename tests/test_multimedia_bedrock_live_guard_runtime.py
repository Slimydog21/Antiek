from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from substrate.multimedia.bedrock_live_guard_acquisition import (
    LiveGuardAcquisitionAttempt,
    LiveGuardAcquisitionCoordinator,
)
from substrate.multimedia.bedrock_live_guard_journal import SqliteLiveGuardAcquisitionJournal
from substrate.multimedia.bedrock_live_guard_runtime import (
    BedrockLiveGuardRuntime,
    BedrockLiveGuardRuntimeError,
    LiveGuardRuntimeConfig,
    OrganizationsCapabilityManifest,
    VerifiedWorkloadIdentity,
    WorkloadIdentityObservation,
)
from tests.test_multimedia_bedrock_live_guard_acquisition import _command, _coordinator

NOW = datetime(2026, 7, 15, 1, tzinfo=UTC)


class IdentitySource:
    def __init__(self, observation: WorkloadIdentityObservation, calls: list[str]) -> None:
        self.observation = observation
        self.calls = calls

    def observe_identity(self, *, startup_challenge: str) -> str:
        self.calls.append("identity")
        assert startup_challenge == "7" * 32
        return self.observation.canonical_json


class IdentityVerifier:
    def __init__(self, config: LiveGuardRuntimeConfig, calls: list[str]) -> None:
        self.config = config
        self.calls = calls

    def verify(self, observation: WorkloadIdentityObservation) -> VerifiedWorkloadIdentity:
        self.calls.append("verify")
        return VerifiedWorkloadIdentity(
            observation_digest=observation.digest,
            verifier_digest=self.config.identity_verifier_digest,
            trust_root_digest=self.config.identity_trust_root_digest,
            startup_challenge=observation.startup_challenge,
        )


class CapabilityFactory:
    def __init__(self, config: LiveGuardRuntimeConfig, organizations: object, calls: list[str]) -> None:
        self.config = config
        self.organizations = organizations
        self.calls = calls

    def build(self, *, identity: WorkloadIdentityObservation):
        self.calls.append("factory")
        return (
            OrganizationsCapabilityManifest(
                identity_observation_digest=identity.digest,
                account_id=self.config.account_id,
                region=self.config.region,
                endpoint_digest=self.config.organizations_endpoint_digest,
                actions=self.config.allowed_actions,
            ),
            self.organizations,
        )


def _root(tmp_path: Path) -> Path:
    tmp_path.chmod(0o700)
    return tmp_path


def _config(**changes: object) -> LiveGuardRuntimeConfig:
    values = {
        "account_id": "123456789012",
        "role_arn": "arn:aws:iam::123456789012:role/antiek-live-guard",
        "session_issuer_digest": "1" * 64,
        "deployment_digest": "2" * 64,
        "region": "us-east-1",
        "credential_source": "container",
        "identity_verifier_digest": "3" * 64,
        "identity_trust_root_digest": "4" * 64,
        "organizations_endpoint_digest": "5" * 64,
    }
    values.update(changes)
    return LiveGuardRuntimeConfig(**values)


def _observation(config: LiveGuardRuntimeConfig, **changes: object) -> WorkloadIdentityObservation:
    values = {
        "account_id": config.account_id,
        "role_arn": config.role_arn,
        "session_issuer_digest": config.session_issuer_digest,
        "deployment_digest": config.deployment_digest,
        "credential_source": config.credential_source,
        "issued_at": "2026-07-15T00:59:00Z",
        "expires_at": "2026-07-15T02:00:00Z",
        "nonce": "6" * 32,
        "startup_challenge": "7" * 32,
    }
    values.update(changes)
    return WorkloadIdentityObservation(**values)


def _environment() -> dict[str, str]:
    return {
        "AWS_EC2_METADATA_DISABLED": "true",
        "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI": "/v2/credentials/antiek",
    }


def _runtime(tmp_path: Path, *, environment: dict[str, str] | None = None):
    config = _config()
    observation = _observation(config)
    cycle34, _, organizations, _, _, _, _, external_calls = _coordinator(NOW)
    calls: list[str] = []
    journal = SqliteLiveGuardAcquisitionJournal(_root(tmp_path))
    command = _command(cycle34)
    nonce = "c" * 32
    start = "2026-07-15T01:00:00Z"
    attempt = LiveGuardAcquisitionAttempt(
        command_digest=command.digest,
        attempt_id="lga_" + hashlib.sha256(
            f"{command.digest}:{start}:{nonce}".encode("ascii")
        ).hexdigest(),
        attempt_nonce=nonce,
        trusted_start=start,
    )
    journal.record_intent(command_json=command.canonical_json, attempt_json=attempt.canonical_json)
    runtime = BedrockLiveGuardRuntime(
        config=config,
        environment=_environment() if environment is None else environment,
        identity_source=IdentitySource(observation, calls),
        identity_verifier=IdentityVerifier(config, calls),
        capability_factory=CapabilityFactory(config, organizations, calls),
        journal=journal,
        clock=lambda: NOW,
        challenge_source=lambda: "7" * 32,
    )
    return runtime, journal, cycle34, command, attempt, calls, external_calls


def test_startup_binds_identity_capability_and_journal_without_evidence_calls(
    tmp_path: Path,
) -> None:
    runtime, _, _, _, _, calls, external_calls = _runtime(tmp_path)
    receipt = runtime.startup()
    assert calls == ["identity", "verify", "factory"]
    assert external_calls == []
    assert receipt.journal_attempt_count == 1
    assert receipt.journal_completion_count == 0
    assert receipt.environment_checked is True
    assert receipt.iam_policy_qualified is False
    assert receipt.production_eligible is False
    assert receipt.bedrock_read_observed is False
    assert "credential" not in receipt.canonical_json.lower()
    with pytest.raises(BedrockLiveGuardRuntimeError, match="single-use"):
        runtime.startup()


@pytest.mark.parametrize(
    "name",
    [
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "AWS_PROFILE",
        "AWS_SHARED_CREDENTIALS_FILE",
        "AWS_CREDENTIAL_PROCESS",
        "AWS_ENDPOINT_URL_ORGANIZATIONS",
        "AWS_CONTAINER_CREDENTIALS_FULL_URI",
    ],
)
def test_forbidden_ambient_channels_fail_before_identity(
    tmp_path: Path, name: str
) -> None:
    environment = _environment()
    environment[name] = "not-persisted"
    runtime, _, _, _, _, calls, _ = _runtime(tmp_path, environment=environment)
    with pytest.raises(BedrockLiveGuardRuntimeError, match="ambient"):
        runtime.startup()
    assert calls == []


@pytest.mark.parametrize(
    "environment",
    [
        {"AWS_CONTAINER_CREDENTIALS_RELATIVE_URI": "/v2/credentials/x"},
        {"AWS_EC2_METADATA_DISABLED": "false", "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI": "/x"},
        {"AWS_EC2_METADATA_DISABLED": "true"},
        {"AWS_EC2_METADATA_DISABLED": "true", "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI": "/../x"},
        {
            "AWS_EC2_METADATA_DISABLED": "true",
            "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI": "/x",
            "AWS_WEB_IDENTITY_TOKEN_FILE": "/var/run/secrets/token",
        },
    ],
)
def test_credential_source_shape_is_exact(
    tmp_path: Path, environment: dict[str, str]
) -> None:
    runtime, _, _, _, _, calls, _ = _runtime(tmp_path, environment=environment)
    with pytest.raises(BedrockLiveGuardRuntimeError):
        runtime.startup()
    assert calls == []


def test_environment_is_copied_at_construction(tmp_path: Path) -> None:
    environment = _environment()
    runtime, _, _, _, _, _, _ = _runtime(tmp_path, environment=environment)
    environment["AWS_ACCESS_KEY_ID"] = "later"
    assert runtime.startup().environment_checked is True


def test_wrong_verified_identity_fails_before_capability(tmp_path: Path) -> None:
    runtime, _, _, _, _, calls, _ = _runtime(tmp_path)
    class WrongVerifier:
        def verify(self, observation):
            return VerifiedWorkloadIdentity(
                observation_digest="f" * 64,
                verifier_digest=runtime.config.identity_verifier_digest,
                trust_root_digest=runtime.config.identity_trust_root_digest,
                startup_challenge=observation.startup_challenge,
            )

    runtime.identity_verifier = WrongVerifier()
    with pytest.raises(BedrockLiveGuardRuntimeError, match="identity conflicts"):
        runtime.startup()
    assert calls == ["identity"]


def test_expired_identity_fails_before_capability(tmp_path: Path) -> None:
    runtime, _, _, _, _, calls, _ = _runtime(tmp_path)
    runtime.identity_source.observation = _observation(  # type: ignore[attr-defined]
        runtime.config, expires_at="2026-07-15T01:00:00Z"
    )
    with pytest.raises(BedrockLiveGuardRuntimeError, match="validity"):
        runtime.startup()
    assert calls == ["identity", "verify"]


def test_replayed_identity_with_wrong_startup_challenge_fails(tmp_path: Path) -> None:
    runtime, _, _, _, _, calls, _ = _runtime(tmp_path)
    runtime.challenge_source = lambda: "8" * 32
    with pytest.raises(BedrockLiveGuardRuntimeError, match="identity verification"):
        runtime.startup()
    assert calls == ["identity"]


def test_manifest_substitution_fails_before_external_evidence(tmp_path: Path) -> None:
    runtime, _, _, _, _, calls, external_calls = _runtime(tmp_path)
    original = runtime.capability_factory

    class WrongManifestFactory:
        def build(self, *, identity):
            manifest, organizations = original.build(identity=identity)
            return replace(manifest, endpoint_digest="f" * 64), organizations

    runtime.capability_factory = WrongManifestFactory()
    with pytest.raises(BedrockLiveGuardRuntimeError, match="manifest conflicts"):
        runtime.startup()
    assert calls == ["identity", "verify", "factory"]
    assert external_calls == []


def test_corrupt_journal_fails_startup_after_manifest(tmp_path: Path) -> None:
    runtime, journal, _, _, _, calls, _ = _runtime(tmp_path)
    journal.path.chmod(0o644)
    with pytest.raises(BedrockLiveGuardRuntimeError, match="journal startup"):
        runtime.startup()
    assert calls == []


def test_recovery_reacquires_exact_in_progress_attempt(tmp_path: Path) -> None:
    runtime, journal, cycle34, _, attempt, _, external_calls = _runtime(tmp_path)
    runtime.startup()
    base = _coordinator(NOW)[1]

    def coordinator_factory(*, organizations, journal):
        return LiveGuardAcquisitionCoordinator(
            organizations=organizations,
            custody=base.custody,
            revocations=base.revocations,
            revocation_verifier=base.revocation_verifier,
            qualifier=base.qualifier,
            journal=journal,
            clock=lambda: NOW,
            approved_revocation_verifier_digest=base.approved_revocation_verifier_digest,
            approved_revocation_trust_root_digest=base.approved_revocation_trust_root_digest,
            approved_audit_source_digest=base.approved_audit_source_digest,
        )

    execution = runtime.recover(
        attempt_id=attempt.attempt_id,
        cycle34_receipt=cycle34,
        predecessor=None,
        coordinator_factory=coordinator_factory,
    )
    assert execution.attempt_id == attempt.attempt_id
    assert execution.production_eligible is False
    assert execution.iam_policy_qualified is False
    assert journal.read_attempt(attempt_id=attempt.attempt_id) == execution.acquisition_receipt_json
    assert len([call for call in external_calls if call.startswith("describe:")]) == 4


def test_recovery_uses_current_time_but_preserves_original_attempt(tmp_path: Path) -> None:
    runtime, journal, cycle34, _, attempt, _, _ = _runtime(tmp_path)
    runtime.startup()
    current = datetime(2026, 7, 15, 1, 0, 30, tzinfo=UTC)
    runtime.clock = lambda: current
    base = _coordinator(current)[1]
    base.revocations.watermark = "2026-07-15T01:00:00Z"

    def coordinator_factory(*, organizations, journal):
        return LiveGuardAcquisitionCoordinator(
            organizations=organizations,
            custody=base.custody,
            revocations=base.revocations,
            revocation_verifier=base.revocation_verifier,
            qualifier=base.qualifier,
            journal=journal,
            clock=lambda: current,
            approved_revocation_verifier_digest=base.approved_revocation_verifier_digest,
            approved_revocation_trust_root_digest=base.approved_revocation_trust_root_digest,
            approved_audit_source_digest=base.approved_audit_source_digest,
        )

    execution = runtime.recover(
        attempt_id=attempt.attempt_id,
        cycle34_receipt=cycle34,
        predecessor=None,
        coordinator_factory=coordinator_factory,
    )
    assert execution.attempt_id == attempt.attempt_id
    assert execution.completed_at == "2026-07-15T01:00:30Z"
    assert journal.inspect_attempt(attempt_id=attempt.attempt_id).status == "completed"
    with pytest.raises(ValueError, match="context binding"):
        replace(execution, startup_receipt_digest="f" * 64)


def test_identity_expiry_before_first_external_call_preserves_in_progress(tmp_path: Path) -> None:
    runtime, journal, cycle34, _, attempt, _, _ = _runtime(tmp_path)
    clock_values = iter([NOW, NOW, datetime(2026, 7, 15, 2, tzinfo=UTC)])
    runtime.clock = lambda: next(clock_values)
    runtime.startup()
    base = _coordinator(NOW)[1]

    def coordinator_factory(*, organizations, journal):
        base.organizations = organizations
        base.journal = journal
        return base

    with pytest.raises(BedrockLiveGuardRuntimeError, match="recovery failed"):
        runtime.recover(
            attempt_id=attempt.attempt_id,
            cycle34_receipt=cycle34,
            predecessor=None,
            coordinator_factory=coordinator_factory,
        )
    assert journal.inspect_attempt(attempt_id=attempt.attempt_id).status == "in_progress"


def test_runtime_clock_regression_fails_before_recovery_factory(tmp_path: Path) -> None:
    runtime, _, cycle34, _, attempt, _, _ = _runtime(tmp_path)
    runtime.startup()
    runtime.clock = lambda: datetime(2026, 7, 15, 0, 59, 30, tzinfo=UTC)
    factory_called = False

    def coordinator_factory(**_):
        nonlocal factory_called
        factory_called = True

    with pytest.raises(BedrockLiveGuardRuntimeError, match="trusted startup clock"):
        runtime.recover(
            attempt_id=attempt.attempt_id,
            cycle34_receipt=cycle34,
            predecessor=None,
            coordinator_factory=coordinator_factory,
        )
    assert factory_called is False


def test_completed_attempt_is_historical_not_recoverable(tmp_path: Path) -> None:
    runtime, journal, cycle34, _, attempt, _, _ = _runtime(tmp_path)
    runtime.startup()
    _, receipt = __import__(
        "tests.test_multimedia_bedrock_live_guard_journal", fromlist=["_complete_with_coordinator"]
    )._complete_with_coordinator(journal)
    assert receipt.attempt_id == attempt.attempt_id
    with pytest.raises(BedrockLiveGuardRuntimeError, match="historical"):
        runtime.recover(
            attempt_id=attempt.attempt_id,
            cycle34_receipt=cycle34,
            predecessor=None,
            coordinator_factory=lambda **_: None,
        )


def test_recovery_rejects_wrong_cycle34_before_external_calls(tmp_path: Path) -> None:
    runtime, _, _, _, attempt, _, external_calls = _runtime(tmp_path)
    runtime.startup()
    wrong_cycle34 = replace(_coordinator(NOW)[0], verifier_digest="f" * 64)
    with pytest.raises(BedrockLiveGuardRuntimeError, match="Cycle 34"):
        runtime.recover(
            attempt_id=attempt.attempt_id,
            cycle34_receipt=wrong_cycle34,
            predecessor=None,
            coordinator_factory=lambda **_: None,
        )
    assert external_calls == []
