"""Credentialless read orchestration for Cycle 35 live guard custody evidence."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol, TypeVar

from substrate.multimedia.bedrock_live_guard_custody import (
    IndependentCustodyAttestation,
    LiveGuardCustodyQualifier,
    LiveGuardCustodyReceipt,
    OrganizationGuardSnapshot,
)
from substrate.multimedia.bedrock_s3_namespace import BedrockS3NamespaceLeaseReceipt

_SHA256 = re.compile(r"[0-9a-f]{64}")
_COMMAND_ID = re.compile(r"lgc_[0-9a-f]{32}")
_ATTEMPT_ID = re.compile(r"lga_[0-9a-f]{64}")
_ORG_ID = re.compile(r"o-[a-z0-9]{10,32}")
_POLICY_ID = re.compile(r"p-[a-z0-9]{8,128}")
_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")


class BedrockLiveGuardAcquisitionError(RuntimeError):
    """Live acquisition evidence was absent, stale, revoked, or contradictory."""


class OrganizationsGuardEvidenceClient(Protocol):
    def describe_policy(self, **request: object) -> Mapping[str, object]: ...
    def list_targets_for_policy(self, **request: object) -> Mapping[str, object]: ...


class CustodyAttestationClient(Protocol):
    def acquire_attestation(self, *, request_json: str, idempotency_key: str) -> str: ...


class RevocationEvidenceClient(Protocol):
    def observe_revocation(self, *, request_json: str) -> str: ...


class RevocationEvidenceVerifier(Protocol):
    @property
    def verifier_digest(self) -> str: ...

    @property
    def trust_root_digest(self) -> str: ...

    def verify(self, observation: RevocationObservation) -> VerifiedRevocationResult: ...


class LiveGuardAcquisitionJournal(Protocol):
    def record_intent(self, *, command_json: str, attempt_json: str) -> None: ...
    def commit_attempt(self, *, attempt_id: str, receipt_json: str) -> None: ...
    def read_attempt(self, *, attempt_id: str) -> str | None: ...


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("ascii")).hexdigest()


def _require_digest(name: str, value: object) -> None:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{name} must be a lowercase SHA-256")


def _parse_time(value: object) -> datetime:
    if type(value) is not str or _TIMESTAMP.fullmatch(value) is None:
        raise ValueError("timestamp must be canonical whole-second UTC text")
    parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        raise ValueError("timestamp must be canonical whole-second UTC text")
    return parsed


def _time_text(value: object) -> str:
    if (
        type(value) is not datetime
        or value.tzinfo is None
        or value.utcoffset() != timedelta(0)
        or value.microsecond
    ):
        raise ValueError("trusted time must be a whole-second UTC datetime")
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


T = TypeVar("T")


def _strict_load(raw: str, cls: type[T]) -> T:  # noqa: UP047
    try:
        value = json.loads(raw, object_pairs_hook=_unique_object)
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise ValueError("artifact must be exact canonical JSON") from exc
    if (
        type(value) is not dict
        or _canonical(value) != raw
        or set(value) != set(cls.__dataclass_fields__)  # type: ignore[attr-defined]
    ):
        raise ValueError("artifact must be exact canonical JSON")
    return cls(**value)


@dataclass(frozen=True)
class LiveGuardAcquisitionCommand:
    command_id: str
    cycle34_receipt_digest: str
    organization_id: str
    management_account_id: str
    member_account_id: str
    scp_policy_id: str
    rcp_policy_id: str
    predecessor_receipt_digest: str | None
    max_revocation_lag_seconds: int

    def __post_init__(self) -> None:
        if type(self.command_id) is not str or _COMMAND_ID.fullmatch(self.command_id) is None:
            raise ValueError("command_id is invalid")
        _require_digest("cycle34_receipt_digest", self.cycle34_receipt_digest)
        if self.predecessor_receipt_digest is not None:
            _require_digest("predecessor_receipt_digest", self.predecessor_receipt_digest)
        if type(self.organization_id) is not str or _ORG_ID.fullmatch(self.organization_id) is None:
            raise ValueError("organization_id is invalid")
        for name in ("management_account_id", "member_account_id"):
            value = getattr(self, name)
            if type(value) is not str or re.fullmatch(r"\d{12}", value) is None:
                raise ValueError(f"{name} must be a 12-digit account")
        if self.management_account_id == self.member_account_id:
            raise ValueError("management and member accounts must differ")
        for name in ("scp_policy_id", "rcp_policy_id"):
            value = getattr(self, name)
            if type(value) is not str or _POLICY_ID.fullmatch(value) is None:
                raise ValueError(f"{name} is invalid")
        if (
            type(self.max_revocation_lag_seconds) is not int
            or not 1 <= self.max_revocation_lag_seconds <= 900
        ):
            raise ValueError("max_revocation_lag_seconds must be between 1 and 900")

    @property
    def canonical_json(self) -> str:
        return _canonical(self.__dict__)

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.canonical_json.encode("ascii")).hexdigest()

    @classmethod
    def from_json(cls, raw: str) -> LiveGuardAcquisitionCommand:
        return _strict_load(raw, cls)


@dataclass(frozen=True)
class LiveGuardAcquisitionAttempt:
    command_digest: str
    attempt_id: str
    attempt_nonce: str
    trusted_start: str

    def __post_init__(self) -> None:
        _require_digest("command_digest", self.command_digest)
        if type(self.attempt_id) is not str or _ATTEMPT_ID.fullmatch(self.attempt_id) is None:
            raise ValueError("attempt_id is invalid")
        if type(self.attempt_nonce) is not str or re.fullmatch(
            r"[0-9a-f]{32}", self.attempt_nonce
        ) is None:
            raise ValueError("attempt_nonce must be 128 bits of lowercase hexadecimal")
        _parse_time(self.trusted_start)
        expected = "lga_" + hashlib.sha256(
            f"{self.command_digest}:{self.trusted_start}:{self.attempt_nonce}".encode("ascii")
        ).hexdigest()
        if self.attempt_id != expected:
            raise ValueError("attempt_id conflicts with command and trusted start")

    @property
    def canonical_json(self) -> str:
        return _canonical(self.__dict__)

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.canonical_json.encode("ascii")).hexdigest()

    @classmethod
    def from_json(cls, raw: str) -> LiveGuardAcquisitionAttempt:
        return _strict_load(raw, cls)


@dataclass(frozen=True)
class RevocationObservation:
    attempt_id: str
    guard_snapshot_digest: str
    attestation_digest: str
    custody_receipt_digest: str
    audit_source_digest: str
    verifier_digest: str
    trust_root_digest: str
    observed_at: str
    audit_complete_through: str
    revoked: bool

    def __post_init__(self) -> None:
        if type(self.attempt_id) is not str or _ATTEMPT_ID.fullmatch(self.attempt_id) is None:
            raise ValueError("revocation attempt_id is invalid")
        for name in (
            "guard_snapshot_digest",
            "attestation_digest",
            "custody_receipt_digest",
            "audit_source_digest",
            "verifier_digest",
            "trust_root_digest",
        ):
            _require_digest(name, getattr(self, name))
        observed = _parse_time(self.observed_at)
        complete = _parse_time(self.audit_complete_through)
        if complete > observed:
            raise ValueError("revocation audit watermark cannot be future")
        if self.revoked is not False:
            raise ValueError("revocation observation must be explicitly unrevoked")

    @property
    def canonical_json(self) -> str:
        return _canonical(self.__dict__)

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.canonical_json.encode("ascii")).hexdigest()

    @classmethod
    def from_json(cls, raw: str) -> RevocationObservation:
        return _strict_load(raw, cls)


@dataclass(frozen=True)
class VerifiedRevocationResult:
    observation_digest: str
    verifier_digest: str
    trust_root_digest: str
    audit_source_digest: str

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            _require_digest(name, getattr(self, name))


@dataclass(frozen=True)
class LiveGuardAcquisitionReceipt:
    command_digest: str
    attempt_digest: str
    attempt_id: str
    attempt_nonce: str
    cycle34_receipt_digest: str
    initial_snapshot_digest: str
    final_snapshot_digest: str
    attestation_digest: str
    custody_receipt_digest: str
    custody_receipt_json: str
    revocation_observation_digest: str
    revocation_verifier_digest: str
    revocation_trust_root_digest: str
    audit_source_digest: str
    predecessor_receipt_digest: str | None
    trusted_start: str
    revocation_observed_at: str
    revocation_complete_through: str
    completed_at: str
    organizations_rechecked: bool
    revocation_observed: bool
    management_account_constrained: bool
    prospective_unrevocability: bool
    production_eligible: bool
    bedrock_version_selected: bool
    bedrock_read_observed: bool

    def __post_init__(self) -> None:
        for name in (
            "command_digest",
            "attempt_digest",
            "cycle34_receipt_digest",
            "initial_snapshot_digest",
            "final_snapshot_digest",
            "attestation_digest",
            "custody_receipt_digest",
            "revocation_observation_digest",
            "revocation_verifier_digest",
            "revocation_trust_root_digest",
            "audit_source_digest",
        ):
            _require_digest(name, getattr(self, name))
        if type(self.attempt_id) is not str or _ATTEMPT_ID.fullmatch(self.attempt_id) is None:
            raise ValueError("receipt attempt_id is invalid")
        if self.predecessor_receipt_digest is not None:
            _require_digest("predecessor_receipt_digest", self.predecessor_receipt_digest)
        try:
            custody = LiveGuardCustodyReceipt.from_json(self.custody_receipt_json)
        except ValueError as exc:
            raise ValueError("embedded custody receipt is invalid") from exc
        if (
            custody.digest != self.custody_receipt_digest
            or custody.cycle34_receipt_digest != self.cycle34_receipt_digest
            or custody.guard_snapshot_digest != self.initial_snapshot_digest
            or custody.attestation_digest != self.attestation_digest
            or custody.predecessor_receipt_digest != self.predecessor_receipt_digest
            or custody.audit_source_digest != self.audit_source_digest
        ):
            raise ValueError("embedded custody receipt conflicts with acquisition receipt")
        observed = _parse_time(self.revocation_observed_at)
        watermark = _parse_time(self.revocation_complete_through)
        if watermark > observed:
            raise ValueError("receipt revocation watermark cannot be future")
        if _parse_time(self.completed_at) < _parse_time(self.trusted_start):
            raise ValueError("receipt clock cannot move backward")
        if _parse_time(self.completed_at) < observed:
            raise ValueError("receipt completion cannot precede revocation observation")
        expected_attempt = LiveGuardAcquisitionAttempt(
            command_digest=self.command_digest,
            attempt_id=self.attempt_id,
            attempt_nonce=self.attempt_nonce,
            trusted_start=self.trusted_start,
        )
        if self.attempt_digest != expected_attempt.digest:
            raise ValueError("receipt attempt digest is inconsistent")
        if any(
            value is not True
            for value in (
                self.organizations_rechecked,
                self.revocation_observed,
            )
        ):
            raise ValueError("observed acquisition claims must be exactly true")
        if any(
            value is not False
            for value in (
                self.management_account_constrained,
                self.prospective_unrevocability,
                self.production_eligible,
                self.bedrock_version_selected,
                self.bedrock_read_observed,
            )
        ):
            raise ValueError("unproved acquisition capabilities must be exactly false")

    @property
    def canonical_json(self) -> str:
        return _canonical(self.__dict__)

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.canonical_json.encode("ascii")).hexdigest()

    @property
    def custody_receipt(self) -> LiveGuardCustodyReceipt:
        return LiveGuardCustodyReceipt.from_json(self.custody_receipt_json)

    @classmethod
    def from_json(cls, raw: str) -> LiveGuardAcquisitionReceipt:
        return _strict_load(raw, cls)


class LiveGuardAcquisitionCoordinator:
    def __init__(
        self,
        *,
        organizations: OrganizationsGuardEvidenceClient,
        custody: CustodyAttestationClient,
        revocations: RevocationEvidenceClient,
        revocation_verifier: RevocationEvidenceVerifier,
        qualifier: LiveGuardCustodyQualifier,
        journal: LiveGuardAcquisitionJournal,
        clock: Callable[[], datetime],
        approved_revocation_verifier_digest: str,
        approved_revocation_trust_root_digest: str,
        approved_audit_source_digest: str,
    ) -> None:
        for name, value in (
            ("approved_revocation_verifier_digest", approved_revocation_verifier_digest),
            ("approved_revocation_trust_root_digest", approved_revocation_trust_root_digest),
            ("approved_audit_source_digest", approved_audit_source_digest),
        ):
            _require_digest(name, value)
        if len(
            {
                approved_revocation_verifier_digest,
                approved_revocation_trust_root_digest,
                approved_audit_source_digest,
            }
        ) != 3:
            raise ValueError("revocation verifier, trust root, and audit source must differ")
        self.organizations = organizations
        self.custody = custody
        self.revocations = revocations
        self.revocation_verifier = revocation_verifier
        self.qualifier = qualifier
        self.journal = journal
        self.clock = clock
        self.approved_revocation_verifier_digest = approved_revocation_verifier_digest
        self.approved_revocation_trust_root_digest = approved_revocation_trust_root_digest
        self.approved_audit_source_digest = approved_audit_source_digest

    def acquire(
        self,
        *,
        command: LiveGuardAcquisitionCommand,
        cycle34_receipt: BedrockS3NamespaceLeaseReceipt,
        attempt_nonce: str,
        predecessor: LiveGuardCustodyReceipt | None = None,
    ) -> LiveGuardAcquisitionReceipt:
        self._verify_command_bindings(command, cycle34_receipt, predecessor)
        started = self._read_clock("trusted start")
        start_text = _time_text(started)
        attempt = LiveGuardAcquisitionAttempt(
            command_digest=command.digest,
            attempt_id="lga_"
            + hashlib.sha256(
                f"{command.digest}:{start_text}:{attempt_nonce}".encode("ascii")
            ).hexdigest(),
            attempt_nonce=attempt_nonce,
            trusted_start=start_text,
        )
        try:
            self.journal.record_intent(
                command_json=command.canonical_json,
                attempt_json=attempt.canonical_json,
            )
        except Exception as exc:
            raise BedrockLiveGuardAcquisitionError("acquisition intent journal failed") from exc

        initial = self._acquire_snapshot(command, start_text)
        attestation = self._acquire_attestation(
            command, attempt, cycle34_receipt, initial, predecessor
        )
        try:
            custody_receipt = self.qualifier.qualify(
                cycle34_receipt=cycle34_receipt,
                guard_snapshot=initial,
                attestation=attestation,
                predecessor=predecessor,
                verified_at=started,
            )
        except Exception as exc:
            raise BedrockLiveGuardAcquisitionError("Cycle 35 custody qualification failed") from exc

        recheck_started = self._read_clock("Organizations recheck")
        if recheck_started < max(started, _parse_time(custody_receipt.verified_at)):
            raise BedrockLiveGuardAcquisitionError("trusted clock moved backward")
        final = self._acquire_snapshot(command, _time_text(recheck_started))
        if self._snapshot_semantics(initial) != self._snapshot_semantics(final):
            raise BedrockLiveGuardAcquisitionError("Organizations guard changed during acquisition")

        revocation_time = self._read_clock("revocation observation")
        if revocation_time < recheck_started:
            raise BedrockLiveGuardAcquisitionError("trusted clock moved backward")
        observation = self._observe_revocation(
            command, attempt, final, attestation, custody_receipt, revocation_time
        )
        completed = self._read_clock("completion")
        if completed < revocation_time:
            raise BedrockLiveGuardAcquisitionError("trusted clock moved backward")
        self._verify_revocation_freshness(command, observation, completed)
        self._verify_custody_freshness(attestation, completed)
        receipt = LiveGuardAcquisitionReceipt(
            command_digest=command.digest,
            attempt_digest=attempt.digest,
            attempt_id=attempt.attempt_id,
            attempt_nonce=attempt.attempt_nonce,
            cycle34_receipt_digest=cycle34_receipt.digest,
            initial_snapshot_digest=initial.digest,
            final_snapshot_digest=final.digest,
            attestation_digest=attestation.digest,
            custody_receipt_digest=custody_receipt.digest,
            custody_receipt_json=custody_receipt.canonical_json,
            revocation_observation_digest=observation.digest,
            revocation_verifier_digest=observation.verifier_digest,
            revocation_trust_root_digest=observation.trust_root_digest,
            audit_source_digest=observation.audit_source_digest,
            predecessor_receipt_digest=custody_receipt.predecessor_receipt_digest,
            trusted_start=start_text,
            revocation_observed_at=observation.observed_at,
            revocation_complete_through=observation.audit_complete_through,
            completed_at=_time_text(completed),
            organizations_rechecked=True,
            revocation_observed=True,
            management_account_constrained=False,
            prospective_unrevocability=False,
            production_eligible=False,
            bedrock_version_selected=False,
            bedrock_read_observed=False,
        )
        commit_error: Exception | None = None
        try:
            self.journal.commit_attempt(
                attempt_id=attempt.attempt_id,
                receipt_json=receipt.canonical_json,
            )
        except Exception as exc:
            commit_error = exc
        try:
            reopened = self.journal.read_attempt(attempt_id=attempt.attempt_id)
        except Exception as exc:
            raise BedrockLiveGuardAcquisitionError("completed attempt journal readback failed") from exc
        if reopened != receipt.canonical_json:
            raise BedrockLiveGuardAcquisitionError("completed attempt journal failed") from commit_error
        try:
            reopened_receipt = LiveGuardAcquisitionReceipt.from_json(reopened)
        except ValueError as exc:
            raise BedrockLiveGuardAcquisitionError("completed attempt journal is corrupt") from exc
        returned_at = self._read_clock("post-journal freshness")
        if returned_at < completed:
            raise BedrockLiveGuardAcquisitionError("trusted clock moved backward")
        self._verify_revocation_freshness(command, observation, returned_at)
        self._verify_custody_freshness(attestation, returned_at)
        return reopened_receipt

    @staticmethod
    def _verify_command_bindings(
        command: LiveGuardAcquisitionCommand,
        cycle34: BedrockS3NamespaceLeaseReceipt,
        predecessor: LiveGuardCustodyReceipt | None,
    ) -> None:
        expected_predecessor = predecessor.digest if predecessor is not None else None
        if (
            command.cycle34_receipt_digest != cycle34.digest
            or command.predecessor_receipt_digest != expected_predecessor
            or hashlib.sha256(command.member_account_id.encode("ascii")).hexdigest()
            != cycle34.owner_digest
        ):
            raise BedrockLiveGuardAcquisitionError("command authority binding is incomplete")
        if predecessor is not None and (
            predecessor.organization_id != command.organization_id
            or predecessor.management_account_id != command.management_account_id
            or predecessor.member_account_id != command.member_account_id
            or predecessor.scp_policy_id != command.scp_policy_id
            or predecessor.rcp_policy_id != command.rcp_policy_id
        ):
            raise BedrockLiveGuardAcquisitionError("renewal command conflicts with predecessor")

    def _acquire_snapshot(
        self, command: LiveGuardAcquisitionCommand, observed_at: str
    ) -> OrganizationGuardSnapshot:
        evidence: dict[str, str] = {}
        for prefix, policy_id in (
            ("scp", command.scp_policy_id),
            ("rcp", command.rcp_policy_id),
        ):
            try:
                described = self.organizations.describe_policy(PolicyId=policy_id)
                targets = self.organizations.list_targets_for_policy(PolicyId=policy_id)
                described_json = self._canonical_mapping(described)
                targets_json = self._canonical_mapping(targets)
            except Exception as exc:
                raise BedrockLiveGuardAcquisitionError(
                    f"{prefix} Organizations evidence acquisition failed"
                ) from exc
            try:
                described_value = json.loads(described_json)
                summary = described_value["PolicySummary"]
                evidence.update(
                    {
                        f"{prefix}_policy_id": policy_id,
                        f"{prefix}_policy_arn": summary["Arn"],
                        f"{prefix}_policy_document": described_value["Content"],
                        f"{prefix}_describe_response": described_json,
                        f"{prefix}_targets_response": targets_json,
                    }
                )
            except (KeyError, TypeError) as exc:
                raise BedrockLiveGuardAcquisitionError(
                    f"{prefix} Organizations evidence shape is invalid"
                ) from exc
        try:
            return OrganizationGuardSnapshot(
                organization_id=command.organization_id,
                management_account_id=command.management_account_id,
                member_account_id=command.member_account_id,
                observed_at=observed_at,
                **evidence,
            )
        except (TypeError, ValueError) as exc:
            raise BedrockLiveGuardAcquisitionError("Organizations snapshot is invalid") from exc

    @staticmethod
    def _canonical_mapping(value: object) -> str:
        if type(value) is not dict:
            raise ValueError("Organizations response must be an exact dict")
        raw = _canonical(value)
        if len(raw.encode("ascii")) > 256_000:
            raise ValueError("Organizations response exceeds evidence bound")
        return raw

    def _acquire_attestation(
        self,
        command: LiveGuardAcquisitionCommand,
        attempt: LiveGuardAcquisitionAttempt,
        cycle34: BedrockS3NamespaceLeaseReceipt,
        snapshot: OrganizationGuardSnapshot,
        predecessor: LiveGuardCustodyReceipt | None,
    ) -> IndependentCustodyAttestation:
        request_json = _canonical(
            {
                "attempt_id": attempt.attempt_id,
                "attempt_json": attempt.canonical_json,
                "command_json": command.canonical_json,
                "command_digest": command.digest,
                "cycle34_receipt_digest": cycle34.digest,
                "guard_snapshot_digest": snapshot.digest,
                "predecessor_receipt_digest": predecessor.digest
                if predecessor is not None
                else None,
            }
        )
        context_digest = hashlib.sha256(request_json.encode("ascii")).hexdigest()
        try:
            raw = self.custody.acquire_attestation(
                request_json=request_json,
                idempotency_key=attempt.attempt_id,
            )
            if type(raw) is not str or len(raw.encode("ascii")) > 64_000:
                raise ValueError("attestation response must be bounded canonical text")
            attestation = IndependentCustodyAttestation.from_json(raw)
        except Exception as exc:
            raise BedrockLiveGuardAcquisitionError("custody attestation acquisition failed") from exc
        if (
            attestation.cycle34_receipt_digest != cycle34.digest
            or attestation.guard_snapshot_digest != snapshot.digest
            or attestation.predecessor_receipt_digest
            != (predecessor.digest if predecessor is not None else None)
            or attestation.acquisition_context_digest != context_digest
        ):
            raise BedrockLiveGuardAcquisitionError("custody attestation response was substituted")
        return attestation

    def _observe_revocation(
        self,
        command: LiveGuardAcquisitionCommand,
        attempt: LiveGuardAcquisitionAttempt,
        final_snapshot: OrganizationGuardSnapshot,
        attestation: IndependentCustodyAttestation,
        custody_receipt: LiveGuardCustodyReceipt,
        observed_at: datetime,
    ) -> RevocationObservation:
        request_json = _canonical(
            {
                "attempt_id": attempt.attempt_id,
                "attestation_digest": attestation.digest,
                "audit_source_digest": self.approved_audit_source_digest,
                "command_digest": command.digest,
                "custody_receipt_digest": custody_receipt.digest,
                "guard_snapshot_digest": final_snapshot.digest,
                "observed_at": _time_text(observed_at),
            }
        )
        try:
            raw = self.revocations.observe_revocation(request_json=request_json)
            if type(raw) is not str or len(raw.encode("ascii")) > 64_000:
                raise ValueError("revocation response must be bounded canonical text")
            observation = RevocationObservation.from_json(raw)
        except Exception as exc:
            raise BedrockLiveGuardAcquisitionError("revocation observation failed") from exc
        if (
            observation.attempt_id != attempt.attempt_id
            or observation.guard_snapshot_digest != final_snapshot.digest
            or observation.attestation_digest != attestation.digest
            or observation.custody_receipt_digest != custody_receipt.digest
            or observation.audit_source_digest != self.approved_audit_source_digest
            or observation.observed_at != _time_text(observed_at)
        ):
            raise BedrockLiveGuardAcquisitionError("revocation observation was substituted")
        try:
            verifier_digest = self.revocation_verifier.verifier_digest
            trust_root_digest = self.revocation_verifier.trust_root_digest
            _require_digest("revocation verifier digest", verifier_digest)
            _require_digest("revocation trust root digest", trust_root_digest)
            verified = self.revocation_verifier.verify(observation)
        except Exception as exc:
            raise BedrockLiveGuardAcquisitionError("revocation evidence was not authenticated") from exc
        if (
            verifier_digest != self.approved_revocation_verifier_digest
            or trust_root_digest != self.approved_revocation_trust_root_digest
            or observation.verifier_digest != verifier_digest
            or observation.trust_root_digest != trust_root_digest
            or type(verified) is not VerifiedRevocationResult
            or verified.observation_digest != observation.digest
            or verified.verifier_digest != verifier_digest
            or verified.trust_root_digest != trust_root_digest
            or verified.audit_source_digest != self.approved_audit_source_digest
        ):
            raise BedrockLiveGuardAcquisitionError("revocation authority is unapproved")
        self._verify_revocation_freshness(command, observation, observed_at)
        if _parse_time(observation.audit_complete_through) < _parse_time(
            custody_receipt.audit_complete_through
        ):
            raise BedrockLiveGuardAcquisitionError("revocation audit watermark regressed")
        return observation

    @staticmethod
    def _verify_revocation_freshness(
        command: LiveGuardAcquisitionCommand,
        observation: RevocationObservation,
        now: datetime,
    ) -> None:
        observed = _parse_time(observation.observed_at)
        watermark = _parse_time(observation.audit_complete_through)
        if observed > now:
            raise BedrockLiveGuardAcquisitionError("revocation observation is future")
        lag = (now - watermark).total_seconds()
        if lag < 0 or lag > command.max_revocation_lag_seconds:
            raise BedrockLiveGuardAcquisitionError("revocation audit watermark is stale or future")

    @staticmethod
    def _verify_custody_freshness(
        attestation: IndependentCustodyAttestation,
        now: datetime,
    ) -> None:
        if not _parse_time(attestation.not_before) <= now < _parse_time(attestation.expires_at):
            raise BedrockLiveGuardAcquisitionError("custody expired during acquisition")
        lag = (now - _parse_time(attestation.audit_complete_through)).total_seconds()
        if lag < 0 or lag > attestation.max_audit_lag_seconds:
            raise BedrockLiveGuardAcquisitionError("custody audit became stale during acquisition")

    @staticmethod
    def _snapshot_semantics(snapshot: OrganizationGuardSnapshot) -> str:
        value = dict(snapshot.__dict__)
        value.pop("observed_at")
        return _canonical(value)

    def _read_clock(self, label: str) -> datetime:
        try:
            value = self.clock()
            _time_text(value)
            return value
        except Exception as exc:
            raise BedrockLiveGuardAcquisitionError(f"{label} clock failed") from exc


__all__ = [
    "BedrockLiveGuardAcquisitionError",
    "CustodyAttestationClient",
    "LiveGuardAcquisitionCommand",
    "LiveGuardAcquisitionCoordinator",
    "LiveGuardAcquisitionAttempt",
    "LiveGuardAcquisitionJournal",
    "LiveGuardAcquisitionReceipt",
    "OrganizationsGuardEvidenceClient",
    "RevocationEvidenceClient",
    "RevocationEvidenceVerifier",
    "RevocationObservation",
    "VerifiedRevocationResult",
]
