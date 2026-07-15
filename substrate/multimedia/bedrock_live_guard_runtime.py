"""Identity-bound composition for the read-only live guard coordinator."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from substrate.multimedia.bedrock_live_guard_acquisition import (
    LiveGuardAcquisitionCoordinator,
    LiveGuardAcquisitionReceipt,
    OrganizationsGuardEvidenceClient,
)
from substrate.multimedia.bedrock_live_guard_custody import LiveGuardCustodyReceipt
from substrate.multimedia.bedrock_live_guard_journal import (
    LiveGuardJournalIntegrityReport,
    SqliteLiveGuardAcquisitionJournal,
)
from substrate.multimedia.bedrock_s3_namespace import BedrockS3NamespaceLeaseReceipt

_DIGEST = re.compile(r"[0-9a-f]{64}")
_ACCOUNT = re.compile(r"\d{12}")
_ROLE_ARN = re.compile(r"arn:aws:iam::(\d{12}):role/[A-Za-z0-9+=,.@_/-]{1,512}")
_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
_ACTIONS = ("organizations:DescribePolicy", "organizations:ListTargetsForPolicy")
_SOURCES = {"container", "web_identity"}
_FORBIDDEN_ENVIRONMENT = {
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "AWS_PROFILE",
    "AWS_DEFAULT_PROFILE",
    "AWS_SHARED_CREDENTIALS_FILE",
    "AWS_CONFIG_FILE",
    "AWS_CREDENTIAL_PROCESS",
    "AWS_ENDPOINT_URL",
    "AWS_ENDPOINT_URL_ORGANIZATIONS",
    "AWS_CONTAINER_CREDENTIALS_FULL_URI",
    "AWS_CONTAINER_AUTHORIZATION_TOKEN",
    "AWS_CONTAINER_AUTHORIZATION_TOKEN_FILE",
}


class BedrockLiveGuardRuntimeError(RuntimeError):
    """Runtime identity, capability, or recovery authority failed closed."""


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("ascii")).hexdigest()


def _require_digest(name: str, value: object) -> None:
    if type(value) is not str or _DIGEST.fullmatch(value) is None:
        raise ValueError(f"{name} must be a lowercase SHA-256")


def _parse_time(value: object) -> datetime:
    if type(value) is not str or _TIMESTAMP.fullmatch(value) is None:
        raise ValueError("timestamp must be canonical whole-second UTC text")
    parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        raise ValueError("timestamp must be canonical whole-second UTC text")
    return parsed


def _time_text(value: object) -> str:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("trusted time must be UTC")
    utc = value.astimezone(UTC)
    if utc.microsecond:
        raise ValueError("trusted time must be whole-second UTC")
    return utc.strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class LiveGuardRuntimeConfig:
    account_id: str
    role_arn: str
    session_issuer_digest: str
    deployment_digest: str
    region: str
    credential_source: str
    identity_verifier_digest: str
    identity_trust_root_digest: str
    organizations_endpoint_digest: str
    allowed_actions: tuple[str, ...] = _ACTIONS

    def __post_init__(self) -> None:
        if type(self.account_id) is not str or _ACCOUNT.fullmatch(self.account_id) is None:
            raise ValueError("runtime account_id is invalid")
        match = _ROLE_ARN.fullmatch(self.role_arn) if type(self.role_arn) is str else None
        if match is None or match.group(1) != self.account_id:
            raise ValueError("runtime role_arn is invalid")
        for name in (
            "session_issuer_digest",
            "deployment_digest",
            "identity_verifier_digest",
            "identity_trust_root_digest",
            "organizations_endpoint_digest",
        ):
            _require_digest(name, getattr(self, name))
        if len({getattr(self, name) for name in (
            "session_issuer_digest", "deployment_digest", "identity_verifier_digest",
            "identity_trust_root_digest", "organizations_endpoint_digest"
        )}) != 5:
            raise ValueError("runtime authority digests must differ")
        if type(self.region) is not str or re.fullmatch(r"[a-z]{2}(?:-gov)?-[a-z]+-\d", self.region) is None:
            raise ValueError("runtime region is invalid")
        if self.credential_source not in _SOURCES:
            raise ValueError("runtime credential_source is invalid")
        if type(self.allowed_actions) is not tuple or self.allowed_actions != _ACTIONS:
            raise ValueError("runtime actions must be the exact read-only capability")

    @property
    def canonical_json(self) -> str:
        return _canonical({**self.__dict__, "allowed_actions": list(self.allowed_actions)})

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.canonical_json.encode("ascii")).hexdigest()


@dataclass(frozen=True)
class WorkloadIdentityObservation:
    account_id: str
    role_arn: str
    session_issuer_digest: str
    deployment_digest: str
    credential_source: str
    issued_at: str
    expires_at: str
    nonce: str
    startup_challenge: str

    def __post_init__(self) -> None:
        if type(self.account_id) is not str or _ACCOUNT.fullmatch(self.account_id) is None:
            raise ValueError("identity account_id is invalid")
        match = _ROLE_ARN.fullmatch(self.role_arn) if type(self.role_arn) is str else None
        if match is None or match.group(1) != self.account_id:
            raise ValueError("identity role_arn is invalid")
        _require_digest("session_issuer_digest", self.session_issuer_digest)
        _require_digest("deployment_digest", self.deployment_digest)
        if self.credential_source not in _SOURCES:
            raise ValueError("identity credential_source is invalid")
        if _parse_time(self.issued_at) >= _parse_time(self.expires_at):
            raise ValueError("identity validity interval is invalid")
        if type(self.nonce) is not str or re.fullmatch(r"[0-9a-f]{32}", self.nonce) is None:
            raise ValueError("identity nonce must be 128-bit lowercase hexadecimal")
        if type(self.startup_challenge) is not str or re.fullmatch(
            r"[0-9a-f]{32}", self.startup_challenge
        ) is None:
            raise ValueError("identity startup_challenge must be 128-bit lowercase hexadecimal")

    @property
    def canonical_json(self) -> str:
        return _canonical(self.__dict__)

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.canonical_json.encode("ascii")).hexdigest()

    @classmethod
    def from_json(cls, raw: str) -> WorkloadIdentityObservation:
        try:
            value = json.loads(raw)
        except (json.JSONDecodeError, TypeError) as exc:
            raise ValueError("identity must be canonical JSON") from exc
        if type(value) is not dict or _canonical(value) != raw or set(value) != set(cls.__dataclass_fields__):
            raise ValueError("identity must be canonical JSON")
        return cls(**value)


@dataclass(frozen=True)
class VerifiedWorkloadIdentity:
    observation_digest: str
    verifier_digest: str
    trust_root_digest: str
    startup_challenge: str

    def __post_init__(self) -> None:
        for name in ("observation_digest", "verifier_digest", "trust_root_digest"):
            _require_digest(name, getattr(self, name))
        if type(self.startup_challenge) is not str or re.fullmatch(
            r"[0-9a-f]{32}", self.startup_challenge
        ) is None:
            raise ValueError("verified startup challenge is invalid")


@dataclass(frozen=True)
class OrganizationsCapabilityManifest:
    identity_observation_digest: str
    account_id: str
    region: str
    endpoint_digest: str
    actions: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_digest("identity_observation_digest", self.identity_observation_digest)
        _require_digest("endpoint_digest", self.endpoint_digest)
        if type(self.account_id) is not str or _ACCOUNT.fullmatch(self.account_id) is None:
            raise ValueError("capability account_id is invalid")
        if type(self.region) is not str or not self.region:
            raise ValueError("capability region is invalid")
        if type(self.actions) is not tuple or self.actions != _ACTIONS:
            raise ValueError("capability actions are not exact")

    @property
    def digest(self) -> str:
        return _digest({**self.__dict__, "actions": list(self.actions)})


class WorkloadIdentitySource(Protocol):
    def observe_identity(self, *, startup_challenge: str) -> str: ...


class WorkloadIdentityVerifier(Protocol):
    def verify(self, observation: WorkloadIdentityObservation) -> VerifiedWorkloadIdentity: ...


class OrganizationsCapabilityFactory(Protocol):
    def build(
        self, *, identity: WorkloadIdentityObservation
    ) -> tuple[OrganizationsCapabilityManifest, OrganizationsGuardEvidenceClient]: ...


@dataclass(frozen=True)
class LiveGuardRuntimeStartupReceipt:
    config_digest: str
    identity_observation_digest: str
    identity_verifier_digest: str
    identity_trust_root_digest: str
    startup_challenge: str
    capability_manifest_digest: str
    journal_command_count: int
    journal_attempt_count: int
    journal_completion_count: int
    checked_at: str
    environment_checked: bool = True
    journal_integrity_verified: bool = True
    iam_policy_qualified: bool = False
    production_eligible: bool = False
    bedrock_version_selected: bool = False
    bedrock_read_observed: bool = False

    def __post_init__(self) -> None:
        for name in (
            "config_digest", "identity_observation_digest", "identity_verifier_digest",
            "identity_trust_root_digest", "capability_manifest_digest"
        ):
            _require_digest(name, getattr(self, name))
        for name in ("journal_command_count", "journal_attempt_count", "journal_completion_count"):
            if type(getattr(self, name)) is not int or getattr(self, name) < 0:
                raise ValueError("startup journal count is invalid")
        _parse_time(self.checked_at)
        if type(self.startup_challenge) is not str or re.fullmatch(
            r"[0-9a-f]{32}", self.startup_challenge
        ) is None:
            raise ValueError("startup receipt challenge is invalid")
        if self.environment_checked is not True or self.journal_integrity_verified is not True:
            raise ValueError("startup checks must be exact")
        if any(getattr(self, name) is not False for name in (
            "iam_policy_qualified", "production_eligible", "bedrock_version_selected",
            "bedrock_read_observed"
        )):
            raise ValueError("startup cannot grant production capability")

    @property
    def canonical_json(self) -> str:
        return _canonical(self.__dict__)

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.canonical_json.encode("ascii")).hexdigest()


@dataclass(frozen=True)
class LiveGuardRuntimeExecutionReceipt:
    startup_receipt_digest: str
    identity_observation_digest: str
    capability_manifest_digest: str
    context_digest: str
    command_digest: str
    attempt_id: str
    acquisition_receipt_digest: str
    acquisition_receipt_json: str
    completed_at: str
    identity_rechecked: bool = True
    iam_policy_qualified: bool = False
    production_eligible: bool = False

    def __post_init__(self) -> None:
        for name in (
            "startup_receipt_digest", "identity_observation_digest",
            "capability_manifest_digest", "context_digest", "command_digest",
            "acquisition_receipt_digest"
        ):
            _require_digest(name, getattr(self, name))
        if self.context_digest != _digest(
            {
                "capability_manifest_digest": self.capability_manifest_digest,
                "identity_observation_digest": self.identity_observation_digest,
                "startup_receipt_digest": self.startup_receipt_digest,
            }
        ):
            raise ValueError("runtime execution context binding conflicts")
        receipt = LiveGuardAcquisitionReceipt.from_json(self.acquisition_receipt_json)
        if (
            receipt.digest != self.acquisition_receipt_digest
            or receipt.command_digest != self.command_digest
            or receipt.attempt_id != self.attempt_id
            or receipt.completed_at != self.completed_at
        ):
            raise ValueError("runtime execution receipt conflicts with acquisition")
        if self.identity_rechecked is not True:
            raise ValueError("runtime execution identity must be rechecked")
        if self.iam_policy_qualified is not False or self.production_eligible is not False:
            raise ValueError("runtime execution cannot grant production capability")

    @property
    def canonical_json(self) -> str:
        return _canonical(self.__dict__)


class LiveGuardRuntimeCoordinatorFactory(Protocol):
    def __call__(
        self,
        *,
        organizations: OrganizationsGuardEvidenceClient,
        journal: SqliteLiveGuardAcquisitionJournal,
    ) -> LiveGuardAcquisitionCoordinator: ...


class BedrockLiveGuardRuntime:
    def __init__(
        self,
        *,
        config: LiveGuardRuntimeConfig,
        environment: Mapping[str, str],
        identity_source: WorkloadIdentitySource,
        identity_verifier: WorkloadIdentityVerifier,
        capability_factory: OrganizationsCapabilityFactory,
        journal: SqliteLiveGuardAcquisitionJournal,
        clock: Callable[[], datetime],
        challenge_source: Callable[[], str],
    ) -> None:
        if not isinstance(config, LiveGuardRuntimeConfig):
            raise TypeError("config must be LiveGuardRuntimeConfig")
        if type(environment) is not dict or any(type(k) is not str or type(v) is not str for k, v in environment.items()):
            raise ValueError("environment must be a plain string mapping")
        self.config = config
        self.environment = dict(environment)
        self.identity_source = identity_source
        self.identity_verifier = identity_verifier
        self.capability_factory = capability_factory
        self.journal = journal
        self.clock = clock
        self.challenge_source = challenge_source
        self._organizations: OrganizationsGuardEvidenceClient | None = None
        self._startup: LiveGuardRuntimeStartupReceipt | None = None
        self._observation: WorkloadIdentityObservation | None = None
        self._manifest: OrganizationsCapabilityManifest | None = None
        self._startup_attempted = False
        self._last_checked_at: datetime | None = None

    def startup(self) -> LiveGuardRuntimeStartupReceipt:
        if self._startup_attempted:
            raise BedrockLiveGuardRuntimeError("runtime startup is single-use")
        self._startup_attempted = True
        self._verify_environment()
        try:
            report = self.journal.verify_all()
        except Exception as exc:
            raise BedrockLiveGuardRuntimeError("live guard journal startup check failed") from exc
        try:
            challenge = self.challenge_source()
        except Exception as exc:
            raise BedrockLiveGuardRuntimeError("startup challenge source failed") from exc
        if type(challenge) is not str or re.fullmatch(r"[0-9a-f]{32}", challenge) is None:
            raise BedrockLiveGuardRuntimeError("startup challenge source failed")
        try:
            observation = WorkloadIdentityObservation.from_json(
                self.identity_source.observe_identity(startup_challenge=challenge)
            )
            verified = self.identity_verifier.verify(observation)
        except Exception as exc:
            raise BedrockLiveGuardRuntimeError("workload identity verification failed") from exc
        self._verify_identity(observation, verified, challenge)
        checked_at = self._read_clock()
        if not _parse_time(observation.issued_at) <= checked_at < _parse_time(observation.expires_at):
            raise BedrockLiveGuardRuntimeError("workload identity is outside its validity interval")
        try:
            manifest, organizations = self.capability_factory.build(identity=observation)
        except Exception as exc:
            raise BedrockLiveGuardRuntimeError("Organizations capability construction failed") from exc
        self._verify_manifest(manifest, observation)
        receipt = self._startup_receipt(observation, verified, manifest, report, checked_at)
        self._organizations = organizations
        self._startup = receipt
        self._observation = observation
        self._manifest = manifest
        return receipt

    def recover(
        self,
        *,
        attempt_id: str,
        cycle34_receipt: BedrockS3NamespaceLeaseReceipt,
        predecessor: LiveGuardCustodyReceipt | None,
        coordinator_factory: LiveGuardRuntimeCoordinatorFactory,
    ) -> LiveGuardRuntimeExecutionReceipt:
        if (
            self._startup is None
            or self._organizations is None
            or self._observation is None
            or self._manifest is None
        ):
            raise BedrockLiveGuardRuntimeError("runtime startup has not succeeded")
        self._require_current_identity()
        try:
            intent = self.journal.read_intent(attempt_id=attempt_id)
        except Exception as exc:
            raise BedrockLiveGuardRuntimeError("recovery intent is unavailable") from exc
        if intent.completed:
            raise BedrockLiveGuardRuntimeError("completed attempts are historical authority")
        command = intent.command
        attempt = intent.attempt
        if cycle34_receipt.digest != command.cycle34_receipt_digest:
            raise BedrockLiveGuardRuntimeError("Cycle 34 recovery authority conflicts")
        predecessor_digest = None if predecessor is None else predecessor.digest
        if predecessor_digest != command.predecessor_receipt_digest:
            raise BedrockLiveGuardRuntimeError("predecessor recovery authority conflicts")
        try:
            coordinator = coordinator_factory(
                organizations=self._organizations,
                journal=self.journal,
            )
            coordinator.runtime_guard = self._require_current_identity
            coordinator.clock = self._read_clock
            receipt = coordinator.acquire(
                command=command,
                cycle34_receipt=cycle34_receipt,
                attempt_nonce=attempt.attempt_nonce,
                predecessor=predecessor,
                attempt_started_at=attempt.trusted_start,
            )
        except Exception as exc:
            raise BedrockLiveGuardRuntimeError("live guard recovery failed") from exc
        if receipt.attempt_id != attempt_id:
            raise BedrockLiveGuardRuntimeError("recovery created a distinct attempt")
        try:
            reopened = self.journal.read_attempt(attempt_id=attempt_id)
        except Exception as exc:
            raise BedrockLiveGuardRuntimeError("recovery receipt readback failed") from exc
        if reopened != receipt.canonical_json:
            raise BedrockLiveGuardRuntimeError("recovery receipt readback conflicts")
        self._require_current_identity()
        return LiveGuardRuntimeExecutionReceipt(
            startup_receipt_digest=self._startup.digest,
            identity_observation_digest=self._observation.digest,
            capability_manifest_digest=self._manifest.digest,
            context_digest=_digest(
                {
                    "capability_manifest_digest": self._manifest.digest,
                    "identity_observation_digest": self._observation.digest,
                    "startup_receipt_digest": self._startup.digest,
                }
            ),
            command_digest=command.digest,
            attempt_id=attempt_id,
            acquisition_receipt_digest=receipt.digest,
            acquisition_receipt_json=receipt.canonical_json,
            completed_at=receipt.completed_at,
        )

    def _verify_environment(self) -> None:
        present = sorted(_FORBIDDEN_ENVIRONMENT.intersection(self.environment))
        if present:
            raise BedrockLiveGuardRuntimeError("ambient credential channel is configured")
        if self.environment.get("AWS_EC2_METADATA_DISABLED") != "true":
            raise BedrockLiveGuardRuntimeError("instance metadata must be explicitly disabled")
        container = "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI" in self.environment
        web_token = "AWS_WEB_IDENTITY_TOKEN_FILE" in self.environment
        web_role = self.environment.get("AWS_ROLE_ARN")
        if self.config.credential_source == "container":
            if not container or web_token or web_role is not None:
                raise BedrockLiveGuardRuntimeError("container identity environment conflicts")
            value = self.environment["AWS_CONTAINER_CREDENTIALS_RELATIVE_URI"]
            if re.fullmatch(r"/[A-Za-z0-9._/-]{1,512}", value) is None or ".." in value.split("/"):
                raise BedrockLiveGuardRuntimeError("container identity marker is unsafe")
        elif container or not web_token or web_role != self.config.role_arn:
            raise BedrockLiveGuardRuntimeError("web identity environment conflicts")
        elif not self.environment["AWS_WEB_IDENTITY_TOKEN_FILE"].startswith("/var/run/secrets/"):
            raise BedrockLiveGuardRuntimeError("web identity token path is outside the mounted secret root")

    def _verify_identity(
        self,
        observation: WorkloadIdentityObservation,
        verified: VerifiedWorkloadIdentity,
        challenge: str,
    ) -> None:
        if (
            observation.account_id != self.config.account_id
            or observation.role_arn != self.config.role_arn
            or observation.session_issuer_digest != self.config.session_issuer_digest
            or observation.deployment_digest != self.config.deployment_digest
            or observation.credential_source != self.config.credential_source
            or verified.observation_digest != observation.digest
            or verified.verifier_digest != self.config.identity_verifier_digest
            or verified.trust_root_digest != self.config.identity_trust_root_digest
            or observation.startup_challenge != challenge
            or verified.startup_challenge != challenge
        ):
            raise BedrockLiveGuardRuntimeError("workload identity conflicts with runtime config")

    def _verify_manifest(
        self, manifest: OrganizationsCapabilityManifest, observation: WorkloadIdentityObservation
    ) -> None:
        if (
            manifest.identity_observation_digest != observation.digest
            or manifest.account_id != self.config.account_id
            or manifest.region != self.config.region
            or manifest.endpoint_digest != self.config.organizations_endpoint_digest
            or manifest.actions != self.config.allowed_actions
        ):
            raise BedrockLiveGuardRuntimeError("Organizations capability manifest conflicts")

    def _read_clock(self) -> datetime:
        try:
            value = self.clock()
            _time_text(value)
            current = value.astimezone(UTC)
            if self._last_checked_at is not None and current < self._last_checked_at:
                raise ValueError("trusted runtime clock regressed")
            self._last_checked_at = current
            return current
        except Exception as exc:
            raise BedrockLiveGuardRuntimeError("trusted startup clock failed") from exc

    def _startup_receipt(
        self,
        observation: WorkloadIdentityObservation,
        verified: VerifiedWorkloadIdentity,
        manifest: OrganizationsCapabilityManifest,
        report: LiveGuardJournalIntegrityReport,
        checked_at: datetime,
    ) -> LiveGuardRuntimeStartupReceipt:
        return LiveGuardRuntimeStartupReceipt(
            config_digest=self.config.digest,
            identity_observation_digest=observation.digest,
            identity_verifier_digest=verified.verifier_digest,
            identity_trust_root_digest=verified.trust_root_digest,
            startup_challenge=observation.startup_challenge,
            capability_manifest_digest=manifest.digest,
            journal_command_count=report.command_count,
            journal_attempt_count=report.attempt_count,
            journal_completion_count=report.completion_count,
            checked_at=_time_text(checked_at),
        )

    def _require_current_identity(self) -> None:
        assert self._observation is not None
        current = self._read_clock()
        if not _parse_time(self._observation.issued_at) <= current < _parse_time(
            self._observation.expires_at
        ):
            raise BedrockLiveGuardRuntimeError("workload identity expired during runtime use")


__all__ = [
    "BedrockLiveGuardRuntime",
    "BedrockLiveGuardRuntimeError",
    "LiveGuardRuntimeConfig",
    "LiveGuardRuntimeStartupReceipt",
    "LiveGuardRuntimeExecutionReceipt",
    "OrganizationsCapabilityFactory",
    "OrganizationsCapabilityManifest",
    "VerifiedWorkloadIdentity",
    "WorkloadIdentityObservation",
    "WorkloadIdentitySource",
    "WorkloadIdentityVerifier",
]
