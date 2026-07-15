"""Qualification-only evidence for independently administered S3 guard custody."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol, TypeVar

from substrate.multimedia.bedrock_s3_namespace import (
    NAMESPACE_CONTROL_ACTIONS,
    NAMESPACE_MUTATION_ACTIONS,
    BedrockS3NamespaceLeaseReceipt,
)

_SHA256 = re.compile(r"[0-9a-f]{64}")
_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
_ORG_ID = re.compile(r"o-[a-z0-9]{10,32}")
_POLICY_ID = re.compile(r"p-[a-z0-9]{8,128}")
_GUARD_ACTIONS = tuple(sorted((*NAMESPACE_MUTATION_ACTIONS, *NAMESPACE_CONTROL_ACTIONS)))


class BedrockLiveGuardCustodyError(RuntimeError):
    """Live guard or independently administered custody evidence failed closed."""


class IndependentCustodyVerifier(Protocol):
    @property
    def verifier_digest(self) -> str: ...

    @property
    def trust_root_digest(self) -> str: ...

    def verify(self, attestation: IndependentCustodyAttestation) -> VerifiedCustodyResult: ...


class Cycle34AuthorityVerifier(Protocol):
    def verify(self, receipt: BedrockS3NamespaceLeaseReceipt) -> BedrockS3NamespaceLeaseReceipt: ...


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("ascii")).hexdigest()


def _parse_time(value: str) -> datetime:
    if type(value) is not str or _TIMESTAMP.fullmatch(value) is None:
        raise ValueError("timestamp must be canonical whole-second UTC text")
    parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        raise ValueError("timestamp must be canonical whole-second UTC text")
    return parsed


def _time_text(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() != timedelta(0) or value.microsecond:
        raise ValueError("trusted time must be a whole-second UTC datetime")
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _require_digest(name: str, value: object) -> None:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{name} must be a lowercase SHA-256")


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


T = TypeVar("T")


def _strict_load(raw: str, cls: type[T], arrays: tuple[str, ...] = ()) -> T:  # noqa: UP047
    try:
        value = json.loads(raw, object_pairs_hook=_unique_object)
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise ValueError("artifact must be exact canonical JSON") from exc
    fields = set(cls.__dataclass_fields__)  # type: ignore[attr-defined]
    if type(value) is not dict or _canonical(value) != raw or set(value) != fields:
        raise ValueError("artifact must be exact canonical JSON")
    for field in arrays:
        if type(value[field]) is not list:
            raise ValueError(f"{field} must be a canonical JSON array")
        value[field] = tuple(value[field])
    return cls(**value)


@dataclass(frozen=True)
class OrganizationGuardSnapshot:
    organization_id: str
    management_account_id: str
    member_account_id: str
    scp_policy_id: str
    scp_policy_arn: str
    scp_policy_document: str
    scp_describe_response: str
    scp_targets_response: str
    rcp_policy_id: str
    rcp_policy_arn: str
    rcp_policy_document: str
    rcp_describe_response: str
    rcp_targets_response: str
    observed_at: str

    def __post_init__(self) -> None:
        if type(self.organization_id) is not str or _ORG_ID.fullmatch(self.organization_id) is None:
            raise ValueError("organization_id is invalid")
        for name in ("management_account_id", "member_account_id"):
            if (
                type(getattr(self, name)) is not str
                or re.fullmatch(r"\d{12}", getattr(self, name)) is None
            ):
                raise ValueError(f"{name} must be a 12-digit account")
        if self.management_account_id == self.member_account_id:
            raise ValueError("workload member account must differ from management account")
        self._verify_policy_evidence("scp", "SERVICE_CONTROL_POLICY")
        self._verify_policy_evidence("rcp", "RESOURCE_CONTROL_POLICY")
        _parse_time(self.observed_at)

    @staticmethod
    def _parse_exact_object(raw: str, label: str) -> Mapping[str, object]:
        try:
            value = json.loads(raw, object_pairs_hook=_unique_object)
        except (json.JSONDecodeError, ValueError) as exc:
            raise ValueError(f"{label} is malformed or ambiguous") from exc
        if type(value) is not dict or _canonical(value) != raw:
            raise ValueError(f"{label} must be exact canonical JSON")
        return value

    def _verify_policy_evidence(self, prefix: str, policy_type: str) -> None:
        policy_id = getattr(self, f"{prefix}_policy_id")
        policy_arn = getattr(self, f"{prefix}_policy_arn")
        policy_document = getattr(self, f"{prefix}_policy_document")
        if type(policy_id) is not str or _POLICY_ID.fullmatch(policy_id) is None:
            raise ValueError(f"{prefix} policy_id is invalid")
        expected_arn = (
            f"arn:aws:organizations::{self.management_account_id}:policy/"
            f"{self.organization_id}/{policy_type.lower()}/{policy_id}"
        )
        if policy_arn != expected_arn:
            raise ValueError(f"{prefix} policy ARN conflicts with organization topology")
        policy = self._parse_exact_object(policy_document, f"{prefix} policy document")
        if set(policy) != {"Version", "Statement"} or policy.get("Version") != "2012-10-17":
            raise ValueError("guard policy top-level shape is noncanonical")
        statements = policy.get("Statement")
        if type(statements) is not list or len(statements) != 1 or type(statements[0]) is not dict:
            raise ValueError("guard policy must contain one exact deny statement")
        statement = statements[0]
        required = {"Effect", "Action", "Resource"}
        if policy_type == "RESOURCE_CONTROL_POLICY":
            required.add("Principal")
        actions = statement.get("Action")
        expected_actions = (
            tuple(sorted(NAMESPACE_MUTATION_ACTIONS))
            if policy_type == "RESOURCE_CONTROL_POLICY"
            else _GUARD_ACTIONS
        )
        if (
            set(statement) != required
            or statement.get("Effect") != "Deny"
            or type(actions) is not list
            or any(type(action) is not str for action in actions)
            or tuple(actions) != expected_actions
            or statement.get("Resource") != "*"
            or (policy_type == "RESOURCE_CONTROL_POLICY" and statement.get("Principal") != "*")
        ):
            raise ValueError("guard policy deny is partial, conditional, or noncanonical")
        describe = self._parse_exact_object(
            getattr(self, f"{prefix}_describe_response"), f"{prefix} describe response"
        )
        expected_describe = {
            "Content": policy_document,
            "PolicySummary": {"Arn": policy_arn, "Id": policy_id, "Type": policy_type},
        }
        if describe != expected_describe:
            raise ValueError(f"{prefix} describe response conflicts with policy evidence")
        targets = self._parse_exact_object(
            getattr(self, f"{prefix}_targets_response"), f"{prefix} targets response"
        )
        expected_targets = {
            "NextToken": None,
            "Targets": [{"TargetId": self.member_account_id, "Type": "ACCOUNT"}],
        }
        if targets != expected_targets:
            raise ValueError(f"{prefix} target response is incomplete or wrong-scope")

    @property
    def canonical_json(self) -> str:
        return _canonical(self.__dict__)

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.canonical_json.encode("ascii")).hexdigest()

    @classmethod
    def from_json(cls, raw: str) -> OrganizationGuardSnapshot:
        return _strict_load(raw, cls)


@dataclass(frozen=True)
class VerifiedCustodyResult:
    attestation_digest: str
    signer_digests: tuple[str, ...]
    signer_quorum: int
    administration_domain_digests: tuple[str, ...]
    audit_source_digest: str

    def __post_init__(self) -> None:
        _require_digest("attestation_digest", self.attestation_digest)
        _require_digest("audit_source_digest", self.audit_source_digest)
        for name, values in (
            ("signer_digests", self.signer_digests),
            ("administration_domain_digests", self.administration_domain_digests),
        ):
            if type(values) is not tuple or tuple(sorted(set(values))) != values or not values:
                raise ValueError(f"{name} must be a sorted unique non-empty tuple")
            for value in values:
                _require_digest(name, value)
        if type(self.signer_quorum) is not int or not 2 <= self.signer_quorum <= len(
            self.signer_digests
        ):
            raise ValueError("verified signer quorum is invalid")


@dataclass(frozen=True)
class IndependentCustodyAttestation:
    cycle34_receipt_digest: str
    guard_snapshot_digest: str
    workload_runtime_digest: str
    issuer_digest: str
    verifier_digest: str
    trust_root_digest: str
    signer_digests: tuple[str, ...]
    signer_quorum: int
    not_before: str
    expires_at: str
    audit_source_digest: str
    audit_complete_through: str
    max_audit_lag_seconds: int
    predecessor_receipt_digest: str | None
    acquisition_context_digest: str | None = None
    management_account_constrained: bool = False
    prospective_unrevocability: bool = False
    production_eligible: bool = False

    def __post_init__(self) -> None:
        for name in (
            "cycle34_receipt_digest",
            "guard_snapshot_digest",
            "workload_runtime_digest",
            "issuer_digest",
            "verifier_digest",
            "trust_root_digest",
            "audit_source_digest",
        ):
            _require_digest(name, getattr(self, name))
        if self.predecessor_receipt_digest is not None:
            _require_digest("predecessor_receipt_digest", self.predecessor_receipt_digest)
        if self.acquisition_context_digest is not None:
            _require_digest("acquisition_context_digest", self.acquisition_context_digest)
        if (
            type(self.signer_digests) is not tuple
            or not self.signer_digests
            or tuple(sorted(set(self.signer_digests))) != self.signer_digests
        ):
            raise ValueError("signer digests must be a non-empty sorted unique tuple")
        for signer in self.signer_digests:
            _require_digest("signer_digest", signer)
        if type(self.signer_quorum) is not int or not 2 <= self.signer_quorum <= len(
            self.signer_digests
        ):
            raise ValueError("signer quorum must be independently plural and satisfiable")
        if self.workload_runtime_digest in {
            self.issuer_digest,
            self.verifier_digest,
            self.trust_root_digest,
            *self.signer_digests,
            self.audit_source_digest,
        }:
            raise ValueError("workload runtime cannot issue or verify its own custody")
        if len({self.issuer_digest, self.verifier_digest, self.trust_root_digest}) != 3:
            raise ValueError("issuer, verifier, and trust root must be independent identities")
        if any(
            signer in {self.issuer_digest, self.verifier_digest, self.trust_root_digest}
            for signer in self.signer_digests
        ):
            raise ValueError("custody signers must be distinct from issuer and verifier authorities")
        starts, expires = _parse_time(self.not_before), _parse_time(self.expires_at)
        if not timedelta(hours=24) <= expires - starts <= timedelta(hours=192):
            raise ValueError("custody interval must be between 24 and 192 hours")
        _parse_time(self.audit_complete_through)
        if (
            type(self.max_audit_lag_seconds) is not int
            or not 1 <= self.max_audit_lag_seconds <= 900
        ):
            raise ValueError("max audit lag must be between 1 and 900 seconds")
        if any(
            value is not False
            for value in (
                self.management_account_constrained,
                self.prospective_unrevocability,
                self.production_eligible,
            )
        ):
            raise ValueError("negative capability claims must remain exactly false")

    @property
    def canonical_json(self) -> str:
        return _canonical(self.__dict__)

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.canonical_json.encode("ascii")).hexdigest()

    @classmethod
    def from_json(cls, raw: str) -> IndependentCustodyAttestation:
        return _strict_load(raw, cls, ("signer_digests",))


@dataclass(frozen=True)
class LiveGuardCustodyReceipt:
    cycle34_receipt_digest: str
    guard_snapshot_digest: str
    attestation_digest: str
    verifier_digest: str
    trust_root_digest: str
    audit_source_digest: str
    predecessor_receipt_digest: str | None
    organization_id: str
    management_account_id: str
    member_account_id: str
    scp_policy_id: str
    rcp_policy_id: str
    audit_complete_through: str
    custody_not_before: str
    custody_expires_at: str
    verified_at: str
    current_guard_observed: bool
    attachment_scope_verified: bool
    external_custody_authenticated: bool
    audit_complete_through_watermark: bool
    management_account_constrained: bool
    prospective_unrevocability: bool
    production_eligible: bool
    bedrock_version_selected: bool
    bedrock_read_observed: bool

    def __post_init__(self) -> None:
        for name in (
            "cycle34_receipt_digest",
            "guard_snapshot_digest",
            "attestation_digest",
            "verifier_digest",
            "trust_root_digest",
            "audit_source_digest",
        ):
            _require_digest(name, getattr(self, name))
        if self.predecessor_receipt_digest is not None:
            _require_digest("predecessor_receipt_digest", self.predecessor_receipt_digest)
        if type(self.organization_id) is not str or _ORG_ID.fullmatch(self.organization_id) is None:
            raise ValueError("receipt organization_id is invalid")
        for name in ("management_account_id", "member_account_id"):
            if (
                type(getattr(self, name)) is not str
                or re.fullmatch(r"\d{12}", getattr(self, name)) is None
            ):
                raise ValueError(f"receipt {name} must be a 12-digit account")
        if self.management_account_id == self.member_account_id:
            raise ValueError("receipt management and member accounts must differ")
        for name in ("scp_policy_id", "rcp_policy_id"):
            if type(getattr(self, name)) is not str or _POLICY_ID.fullmatch(getattr(self, name)) is None:
                raise ValueError(f"receipt {name} is invalid")
        _parse_time(self.audit_complete_through)
        starts, expires = _parse_time(self.custody_not_before), _parse_time(self.custody_expires_at)
        if not timedelta(hours=24) <= expires - starts <= timedelta(hours=192):
            raise ValueError("receipt custody interval must be between 24 and 192 hours")
        verified = _parse_time(self.verified_at)
        if not starts <= verified < expires:
            raise ValueError("receipt verification time must be inside custody interval")
        if any(
            value is not True
            for value in (
                self.current_guard_observed,
                self.attachment_scope_verified,
                self.external_custody_authenticated,
                self.audit_complete_through_watermark,
            )
        ):
            raise ValueError("observed receipt claims must be exactly true")
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
            raise ValueError("unproved receipt capabilities must be exactly false")

    @property
    def canonical_json(self) -> str:
        return _canonical(self.__dict__)

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.canonical_json.encode("ascii")).hexdigest()

    @classmethod
    def from_json(cls, raw: str) -> LiveGuardCustodyReceipt:
        return _strict_load(raw, cls)


class LiveGuardCustodyQualifier:
    def __init__(
        self,
        *,
        verifier: IndependentCustodyVerifier,
        cycle34_verifier: Cycle34AuthorityVerifier,
        clock: Callable[[], datetime],
        workload_runtime_digest: str,
        approved_signer_digests: tuple[str, ...],
        required_signer_quorum: int,
        approved_administration_domain_digests: tuple[str, ...],
        approved_audit_source_digest: str,
    ) -> None:
        _require_digest("workload_runtime_digest", workload_runtime_digest)
        self.verifier = verifier
        self.cycle34_verifier = cycle34_verifier
        self.clock = clock
        self.workload_runtime_digest = workload_runtime_digest
        if tuple(sorted(set(approved_signer_digests))) != approved_signer_digests:
            raise ValueError("approved signer digests must be sorted and unique")
        for digest in (*approved_signer_digests, *approved_administration_domain_digests):
            _require_digest("approved authority digest", digest)
        if (
            type(required_signer_quorum) is not int
            or not 2 <= required_signer_quorum <= len(approved_signer_digests)
        ):
            raise ValueError("required signer quorum is invalid")
        if (
            tuple(sorted(set(approved_administration_domain_digests)))
            != approved_administration_domain_digests
            or len(approved_administration_domain_digests) < 2
        ):
            raise ValueError("approved administration domains must be plural and unique")
        _require_digest("approved_audit_source_digest", approved_audit_source_digest)
        if approved_audit_source_digest in {
            workload_runtime_digest,
            *approved_signer_digests,
            *approved_administration_domain_digests,
        }:
            raise ValueError("audit source must be independently administered")
        if workload_runtime_digest in {
            *approved_signer_digests,
            *approved_administration_domain_digests,
        }:
            raise ValueError("approved custody authorities must be external to the workload")
        self.approved_signer_digests = approved_signer_digests
        self.required_signer_quorum = required_signer_quorum
        self.approved_administration_domain_digests = approved_administration_domain_digests
        self.approved_audit_source_digest = approved_audit_source_digest

    def qualify(
        self,
        *,
        cycle34_receipt: BedrockS3NamespaceLeaseReceipt,
        guard_snapshot: OrganizationGuardSnapshot,
        attestation: IndependentCustodyAttestation,
        verified_at: datetime,
        predecessor: LiveGuardCustodyReceipt | None = None,
    ) -> LiveGuardCustodyReceipt:
        try:
            started = self.clock()
            _time_text(started)
        except Exception as exc:
            raise BedrockLiveGuardCustodyError("trusted start clock failed") from exc
        if verified_at != started:
            raise BedrockLiveGuardCustodyError("verified_at conflicts with trusted clock")
        try:
            verifier_digest = self.verifier.verifier_digest
            trust_root_digest = self.verifier.trust_root_digest
            _require_digest("verifier_digest", verifier_digest)
            _require_digest("trust_root_digest", trust_root_digest)
        except Exception as exc:
            raise BedrockLiveGuardCustodyError("verifier authority is invalid") from exc
        if (
            attestation.verifier_digest != verifier_digest
            or attestation.trust_root_digest != trust_root_digest
        ):
            raise BedrockLiveGuardCustodyError("attestation conflicts with verifier authority")
        try:
            verified_custody = self.verifier.verify(attestation)
        except Exception as exc:
            raise BedrockLiveGuardCustodyError("custody attestation was not authenticated") from exc
        if (
            type(verified_custody) is not VerifiedCustodyResult
            or verified_custody.attestation_digest != attestation.digest
            or verified_custody.signer_digests != self.approved_signer_digests
            or verified_custody.signer_quorum != self.required_signer_quorum
            or verified_custody.administration_domain_digests
            != self.approved_administration_domain_digests
            or verified_custody.audit_source_digest != self.approved_audit_source_digest
            or attestation.signer_digests != self.approved_signer_digests
            or attestation.signer_quorum != self.required_signer_quorum
            or attestation.audit_source_digest != self.approved_audit_source_digest
        ):
            raise BedrockLiveGuardCustodyError("verified custody result is incomplete or unapproved")
        self._verify_bindings(cycle34_receipt, guard_snapshot, attestation, predecessor)
        if _parse_time(guard_snapshot.observed_at) != started:
            raise BedrockLiveGuardCustodyError(
                "guard snapshot observation conflicts with trusted time"
            )
        self._verify_time(attestation, started)
        try:
            reverified = self.cycle34_verifier.verify(cycle34_receipt)
        except Exception as exc:
            raise BedrockLiveGuardCustodyError("Cycle 34 authority reverify failed") from exc
        if (
            type(reverified) is not type(cycle34_receipt)
            or reverified.digest != cycle34_receipt.digest
        ):
            raise BedrockLiveGuardCustodyError("Cycle 34 reverify substituted receipt identity")
        try:
            finished = self.clock()
            finished_text = _time_text(finished)
        except Exception as exc:
            raise BedrockLiveGuardCustodyError("trusted final clock failed") from exc
        if finished < started:
            raise BedrockLiveGuardCustodyError("trusted clock moved backward")
        self._verify_time(attestation, finished)
        return LiveGuardCustodyReceipt(
            cycle34_receipt_digest=cycle34_receipt.digest,
            guard_snapshot_digest=guard_snapshot.digest,
            attestation_digest=attestation.digest,
            verifier_digest=verifier_digest,
            trust_root_digest=trust_root_digest,
            audit_source_digest=attestation.audit_source_digest,
            predecessor_receipt_digest=attestation.predecessor_receipt_digest,
            organization_id=guard_snapshot.organization_id,
            management_account_id=guard_snapshot.management_account_id,
            member_account_id=guard_snapshot.member_account_id,
            scp_policy_id=guard_snapshot.scp_policy_id,
            rcp_policy_id=guard_snapshot.rcp_policy_id,
            audit_complete_through=attestation.audit_complete_through,
            custody_not_before=attestation.not_before,
            custody_expires_at=attestation.expires_at,
            verified_at=finished_text,
            current_guard_observed=True,
            attachment_scope_verified=True,
            external_custody_authenticated=True,
            audit_complete_through_watermark=True,
            management_account_constrained=False,
            prospective_unrevocability=False,
            production_eligible=False,
            bedrock_version_selected=False,
            bedrock_read_observed=False,
        )

    def _verify_bindings(
        self,
        cycle34: BedrockS3NamespaceLeaseReceipt,
        snapshot: OrganizationGuardSnapshot,
        attestation: IndependentCustodyAttestation,
        predecessor: LiveGuardCustodyReceipt | None,
    ) -> None:
        if (
            attestation.cycle34_receipt_digest != cycle34.digest
            or attestation.guard_snapshot_digest != snapshot.digest
            or attestation.workload_runtime_digest != self.workload_runtime_digest
            or cycle34.owner_digest
            != hashlib.sha256(snapshot.member_account_id.encode("ascii")).hexdigest()
        ):
            raise BedrockLiveGuardCustodyError("custody evidence has the wrong bound identity")
        expected_predecessor = predecessor.digest if predecessor is not None else None
        if attestation.predecessor_receipt_digest != expected_predecessor:
            raise BedrockLiveGuardCustodyError("custody predecessor binding is incomplete")
        if predecessor is not None and (
            predecessor.organization_id != snapshot.organization_id
            or predecessor.management_account_id != snapshot.management_account_id
            or predecessor.member_account_id != snapshot.member_account_id
            or predecessor.scp_policy_id != snapshot.scp_policy_id
            or predecessor.rcp_policy_id != snapshot.rcp_policy_id
            or _parse_time(attestation.not_before) > _parse_time(predecessor.custody_expires_at)
            or _parse_time(attestation.audit_complete_through)
            < _parse_time(predecessor.audit_complete_through)
        ):
            raise BedrockLiveGuardCustodyError("custody renewal has a gap or regressed identity")

    @staticmethod
    def _verify_time(attestation: IndependentCustodyAttestation, now: datetime) -> None:
        starts = _parse_time(attestation.not_before)
        expires = _parse_time(attestation.expires_at)
        watermark = _parse_time(attestation.audit_complete_through)
        if not starts <= now < expires:
            raise BedrockLiveGuardCustodyError("custody interval is not current")
        lag = (now - watermark).total_seconds()
        if lag < 0 or lag > attestation.max_audit_lag_seconds:
            raise BedrockLiveGuardCustodyError("audit watermark is future or stale")


__all__ = [
    "BedrockLiveGuardCustodyError",
    "Cycle34AuthorityVerifier",
    "IndependentCustodyAttestation",
    "IndependentCustodyVerifier",
    "LiveGuardCustodyQualifier",
    "LiveGuardCustodyReceipt",
    "OrganizationGuardSnapshot",
    "VerifiedCustodyResult",
]
