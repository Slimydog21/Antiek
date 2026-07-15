"""Time-bounded qualification of an S3 key namespace used by Bedrock.

This module deliberately has no AWS client factory or signing implementation.  Both the S3
evidence reader and the independently administered lease verifier are injected authorities.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from substrate.multimedia.bedrock_s3_publication import (
    BedrockS3PublicationProfile,
    BedrockS3VersionPublicationReceipt,
    BedrockS3VersionPublisher,
)

_SHA256 = re.compile(r"[0-9a-f]{64}")
_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")

NAMESPACE_MUTATION_ACTIONS = (
    "s3:DeleteObject",
    "s3:DeleteObjectVersion",
    "s3:PutObject",
    "s3:ReplicateDelete",
    "s3:ReplicateObject",
    "s3:RestoreObject",
)
NAMESPACE_CONTROL_ACTIONS = (
    "s3:CreateAccessPoint",
    "s3:CreateMultiRegionAccessPoint",
    "s3:DeleteBucketOwnershipControls",
    "s3:DeleteBucketPolicy",
    "s3:DeleteBucketPublicAccessBlock",
    "s3:DeleteAccessPointPolicy",
    "s3:DeleteMultiRegionAccessPointPolicy",
    "s3:PutLifecycleConfiguration",
    "s3:PutAccessPointPolicy",
    "s3:PutBucketObjectLockConfiguration",
    "s3:PutBucketOwnershipControls",
    "s3:PutBucketPolicy",
    "s3:PutBucketPublicAccessBlock",
    "s3:PutReplicationConfiguration",
    "s3:PutMultiRegionAccessPointPolicy",
    "s3:PutBucketVersioning",
)


class BedrockS3NamespaceError(RuntimeError):
    """Namespace evidence was absent, ambiguous, or contradictory."""


class S3NamespaceEvidenceClient(Protocol):
    def get_bucket_policy(self, **request: object) -> Mapping[str, object]: ...
    def get_bucket_lifecycle_configuration(self, **request: object) -> Mapping[str, object]: ...
    def get_bucket_replication(self, **request: object) -> Mapping[str, object]: ...
    def get_public_access_block(self, **request: object) -> Mapping[str, object]: ...
    def get_bucket_ownership_controls(self, **request: object) -> Mapping[str, object]: ...
    def get_bucket_versioning(self, **request: object) -> Mapping[str, object]: ...
    def get_object_lock_configuration(self, **request: object) -> Mapping[str, object]: ...


class IndependentNamespaceLeaseVerifier(Protocol):
    """External authority; implementations authenticate, they do not mint lease claims."""

    @property
    def verifier_digest(self) -> str: ...

    @property
    def trust_root_digest(self) -> str: ...

    def verify(self, lease: IndependentNamespaceLease) -> None: ...


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("ascii")).hexdigest()


def _parse_time(value: str) -> datetime:
    if not isinstance(value, str) or _TIMESTAMP.fullmatch(value) is None:
        raise ValueError("lease timestamps must be canonical whole-second UTC text")
    parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        raise ValueError("lease timestamps must be canonical whole-second UTC text")
    return parsed


def _canonical_now(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() != timedelta(0) or value.microsecond:
        raise ValueError("verified_at must be a whole-second UTC datetime")
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _strict_tuple(name: str, value: tuple[str, ...], expected: tuple[str, ...]) -> None:
    if type(value) is not tuple or value != expected:
        raise ValueError(f"{name} must be the exact canonical complete action set")


@dataclass(frozen=True)
class IndependentNamespaceLease:
    account_id: str
    bucket: str
    prefix: str
    key: str
    workload_bound_digest: str
    version_id: str
    policy_digest: str
    organization_guard_digest: str
    verifier_digest: str
    trust_root_digest: str
    not_before: str
    expires_at: str
    data_deny_actions: tuple[str, ...]
    control_deny_actions: tuple[str, ...]
    lifecycle_history_clear: bool
    alternate_access_paths_denied: bool
    guard_semantics_validated: bool

    def __post_init__(self) -> None:
        if re.fullmatch(r"\d{12}", self.account_id) is None:
            raise ValueError("account_id must be a 12-digit AWS account")
        if (
            not self.bucket
            or not self.prefix
            or not self.key
            or not self.key.startswith(self.prefix)
        ):
            raise ValueError("lease bucket, prefix, and key scope is invalid")
        if not self.version_id:
            raise ValueError("lease version_id must be non-empty")
        for name in (
            "workload_bound_digest",
            "policy_digest",
            "organization_guard_digest",
            "verifier_digest",
            "trust_root_digest",
        ):
            if _SHA256.fullmatch(getattr(self, name)) is None:
                raise ValueError(f"{name} must be a lowercase SHA-256")
        if _parse_time(self.not_before) >= _parse_time(self.expires_at):
            raise ValueError("lease interval must be positive")
        _strict_tuple("data_deny_actions", self.data_deny_actions, NAMESPACE_MUTATION_ACTIONS)
        _strict_tuple("control_deny_actions", self.control_deny_actions, NAMESPACE_CONTROL_ACTIONS)
        if any(
            value is not True
            for value in (
                self.lifecycle_history_clear,
                self.alternate_access_paths_denied,
                self.guard_semantics_validated,
            )
        ):
            raise ValueError("independent operational guard claims must be exactly true")

    @property
    def canonical_json(self) -> str:
        return _canonical(self.__dict__)

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.canonical_json.encode("ascii")).hexdigest()

    @classmethod
    def from_json(cls, raw: str) -> IndependentNamespaceLease:
        try:
            value = json.loads(raw)
        except (json.JSONDecodeError, TypeError) as exc:
            raise ValueError("lease must be exact canonical JSON") from exc
        if (
            not isinstance(value, dict)
            or _canonical(value) != raw
            or set(value) != set(cls.__dataclass_fields__)
        ):
            raise ValueError("lease must be exact canonical JSON")
        for name in ("data_deny_actions", "control_deny_actions"):
            if not isinstance(value[name], list):
                raise ValueError("lease action sets must be canonical JSON arrays")
            value[name] = tuple(value[name])
        return cls(**value)


@dataclass(frozen=True)
class BedrockS3NamespaceLeaseReceipt:
    publication_receipt_digest: str
    profile_digest: str
    lease_digest: str
    verifier_digest: str
    trust_root_digest: str
    policy_digest: str
    organization_guard_digest: str
    owner_digest: str
    bucket: str
    prefix: str
    key: str
    version_id: str
    lease_not_before: str
    lease_expires_at: str
    verified_at: str
    version_immutable: bool = True
    current_for_lease: bool = True
    exact_key_mutation_denied: bool = True
    lifecycle_absent: bool = True
    replication_absent: bool = True
    independent_control_lease_verified: bool = True
    bedrock_version_selected: bool = False
    bedrock_read_observed: bool = False

    def __post_init__(self) -> None:
        for name in (
            "publication_receipt_digest",
            "profile_digest",
            "lease_digest",
            "verifier_digest",
            "trust_root_digest",
            "policy_digest",
            "organization_guard_digest",
            "owner_digest",
        ):
            if _SHA256.fullmatch(getattr(self, name)) is None:
                raise ValueError(f"{name} must be a lowercase SHA-256")
        if (
            not self.bucket
            or not self.prefix
            or not self.key.startswith(self.prefix)
            or not self.version_id
        ):
            raise ValueError("receipt namespace identity is invalid")
        if not (
            _parse_time(self.lease_not_before)
            <= _parse_time(self.verified_at)
            < _parse_time(self.lease_expires_at)
        ):
            raise ValueError("receipt verification must be within the lease")
        truth = (
            self.version_immutable,
            self.current_for_lease,
            self.exact_key_mutation_denied,
            self.lifecycle_absent,
            self.replication_absent,
            self.independent_control_lease_verified,
        )
        if any(value is not True for value in truth):
            raise ValueError("proved receipt booleans must be exactly true")
        if self.bedrock_version_selected is not False or self.bedrock_read_observed is not False:
            raise ValueError("Bedrock selection and read observation must remain exactly false")

    @property
    def canonical_json(self) -> str:
        return _canonical(self.__dict__)

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.canonical_json.encode("ascii")).hexdigest()

    @classmethod
    def from_json(cls, raw: str) -> BedrockS3NamespaceLeaseReceipt:
        try:
            value = json.loads(raw)
        except (json.JSONDecodeError, TypeError) as exc:
            raise ValueError("namespace receipt must be exact canonical JSON") from exc
        if (
            not isinstance(value, dict)
            or _canonical(value) != raw
            or set(value) != set(cls.__dataclass_fields__)
        ):
            raise ValueError("namespace receipt must be exact canonical JSON")
        return cls(**value)


class BedrockS3NamespaceLeaseQualifier:
    def __init__(
        self,
        client: S3NamespaceEvidenceClient,
        profile: BedrockS3PublicationProfile,
        publisher: BedrockS3VersionPublisher,
        verifier: IndependentNamespaceLeaseVerifier,
        clock: Callable[[], datetime],
    ) -> None:
        self.client = client
        self.profile = profile
        self.publisher = publisher
        self.verifier = verifier
        self.clock = clock

    def qualify(
        self,
        *,
        publication_receipt: BedrockS3VersionPublicationReceipt,
        independent_lease: IndependentNamespaceLease,
        verified_at: datetime,
        bedrock_timeout_hours: int,
    ) -> BedrockS3NamespaceLeaseReceipt:
        trusted_start = self.clock()
        now_text = _canonical_now(trusted_start)
        if verified_at != trusted_start:
            raise BedrockS3NamespaceError("verified_at conflicts with the injected trusted clock")
        if type(bedrock_timeout_hours) is not int or not 24 <= bedrock_timeout_hours <= 168:
            raise ValueError("bedrock_timeout_hours must be between 24 and 168")
        verifier_digest = self.verifier.verifier_digest
        trust_root_digest = self.verifier.trust_root_digest
        self._verify_authority_digests(independent_lease, verifier_digest, trust_root_digest)
        try:
            self.verifier.verify(independent_lease)
        except Exception as exc:
            raise BedrockS3NamespaceError(
                "independent namespace lease was not authenticated"
            ) from exc
        self._verify_scope_and_time(
            publication_receipt, independent_lease, verified_at, bedrock_timeout_hours
        )
        policy_digest = self._verify_s3_evidence(publication_receipt.key)
        if not (
            policy_digest == independent_lease.policy_digest == self.profile.namespace_policy_digest
        ):
            raise BedrockS3NamespaceError(
                "bucket policy digest conflicts with lease or publication profile"
            )

        # Deliberately last: current-key evidence must postdate all static-control reads.
        try:
            self.publisher.verify(publication_receipt)
        except Exception as exc:
            raise BedrockS3NamespaceError("final publication reverify failed") from exc
        trusted_finish = self.clock()
        now_text = _canonical_now(trusted_finish)
        self._verify_scope_and_time(
            publication_receipt,
            independent_lease,
            trusted_finish,
            bedrock_timeout_hours,
        )
        return BedrockS3NamespaceLeaseReceipt(
            publication_receipt_digest=publication_receipt.digest,
            profile_digest=self.profile.digest,
            lease_digest=independent_lease.digest,
            verifier_digest=verifier_digest,
            trust_root_digest=trust_root_digest,
            policy_digest=policy_digest,
            organization_guard_digest=independent_lease.organization_guard_digest,
            owner_digest=self.profile.owner_digest,
            bucket=self.profile.bucket,
            prefix=self.profile.prefix,
            key=publication_receipt.key,
            version_id=publication_receipt.version_id,
            lease_not_before=independent_lease.not_before,
            lease_expires_at=independent_lease.expires_at,
            verified_at=now_text,
        )

    def _verify_authority_digests(
        self, lease: IndependentNamespaceLease, verifier_digest: str, trust_root_digest: str
    ) -> None:
        if _SHA256.fullmatch(verifier_digest) is None:
            raise BedrockS3NamespaceError("verifier identity digest is invalid")
        if _SHA256.fullmatch(trust_root_digest) is None:
            raise BedrockS3NamespaceError("verifier trust-root digest is invalid")
        if lease.verifier_digest != verifier_digest or lease.trust_root_digest != trust_root_digest:
            raise BedrockS3NamespaceError("lease conflicts with injected verifier authority")

    def _verify_scope_and_time(
        self,
        publication: BedrockS3VersionPublicationReceipt,
        lease: IndependentNamespaceLease,
        now: datetime,
        timeout_hours: int,
    ) -> None:
        if publication.profile_digest != self.profile.digest:
            raise BedrockS3NamespaceError("publication conflicts with injected profile")
        if (
            lease.account_id != self.profile.expected_owner
            or lease.bucket != self.profile.bucket
            or lease.prefix != self.profile.prefix
            or lease.key != publication.key
            or lease.version_id != publication.version_id
            or lease.workload_bound_digest != publication.workload_bound_digest
        ):
            raise BedrockS3NamespaceError("independent lease has the wrong namespace scope")
        starts, expires = _parse_time(lease.not_before), _parse_time(lease.expires_at)
        required_expiry = now + timedelta(hours=timeout_hours + self.profile.retention_margin_hours)
        if starts > now or expires < required_expiry:
            raise BedrockS3NamespaceError("independent lease does not cover timeout plus margin")
        maximum_duration = timedelta(hours=168 + self.profile.retention_margin_hours)
        if expires - starts > maximum_duration:
            raise BedrockS3NamespaceError("independent lease exceeds the bounded Bedrock window")
        if _parse_time(publication.retain_until) < expires:
            raise BedrockS3NamespaceError("publication retention does not cover the lease")

    def _verify_s3_evidence(self, key: str) -> str:
        common = {"Bucket": self.profile.bucket, "ExpectedBucketOwner": self.profile.expected_owner}
        try:
            policy_response = self.client.get_bucket_policy(**common)
            public = self.client.get_public_access_block(**common)
            ownership = self.client.get_bucket_ownership_controls(**common)
            versioning = self.client.get_bucket_versioning(**common)
            lock = self.client.get_object_lock_configuration(**common)
        except Exception as exc:
            raise BedrockS3NamespaceError("bucket control evidence was unreadable") from exc
        policy = self._parse_policy(policy_response)
        self._verify_exact_deny(policy, key)
        self._require_absent(
            self.client.get_bucket_lifecycle_configuration,
            common,
            "NoSuchLifecycleConfiguration",
            "lifecycle",
        )
        self._require_absent(
            self.client.get_bucket_replication,
            common,
            "ReplicationConfigurationNotFoundError",
            "replication",
        )
        block = public.get("PublicAccessBlockConfiguration")
        flags = (
            "BlockPublicAcls",
            "IgnorePublicAcls",
            "BlockPublicPolicy",
            "RestrictPublicBuckets",
        )
        if not isinstance(block, Mapping) or any(block.get(flag) is not True for flag in flags):
            raise BedrockS3NamespaceError("all public-access block flags must be true")
        controls = ownership.get("OwnershipControls")
        rules = controls.get("Rules") if isinstance(controls, Mapping) else None
        if (
            not isinstance(rules, list)
            or len(rules) != 1
            or not isinstance(rules[0], Mapping)
            or rules[0].get("ObjectOwnership") != "BucketOwnerEnforced"
        ):
            raise BedrockS3NamespaceError("bucket ownership must be exactly BucketOwnerEnforced")
        if versioning.get("Status") != "Enabled":
            raise BedrockS3NamespaceError("bucket versioning must be enabled")
        configuration = lock.get("ObjectLockConfiguration")
        if (
            not isinstance(configuration, Mapping)
            or configuration.get("ObjectLockEnabled") != "Enabled"
        ):
            raise BedrockS3NamespaceError("bucket Object Lock must be enabled")
        return _digest(policy)

    @staticmethod
    def _parse_policy(response: Mapping[str, object]) -> Mapping[str, object]:
        raw = response.get("Policy")
        if not isinstance(raw, str):
            raise BedrockS3NamespaceError("bucket policy response omitted policy JSON")
        try:
            policy = json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
        except (json.JSONDecodeError, ValueError) as exc:
            raise BedrockS3NamespaceError("bucket policy JSON is ambiguous or malformed") from exc
        if not isinstance(policy, Mapping):
            raise BedrockS3NamespaceError("bucket policy must be a JSON object")
        return policy

    def _verify_exact_deny(self, policy: Mapping[str, object], key: str) -> None:
        statements = policy.get("Statement")
        if isinstance(statements, Mapping):
            statements = [statements]
        if not isinstance(statements, list):
            raise BedrockS3NamespaceError("bucket policy has no statement list")
        resource = f"arn:aws:s3:::{self.profile.bucket}/{key}"
        matches = 0
        for statement in statements:
            if not isinstance(statement, Mapping):
                continue
            actions = statement.get("Action")
            if isinstance(actions, str):
                actions = [actions]
            if (
                set(statement) <= {"Sid", "Effect", "Principal", "Action", "Resource"}
                and statement.get("Effect") == "Deny"
                and statement.get("Principal") == "*"
                and statement.get("Resource") == resource
                and "Condition" not in statement
                and isinstance(actions, list)
                and all(type(action) is str for action in actions)
                and len(actions) == len(set(actions))
                and set(actions) == set(NAMESPACE_MUTATION_ACTIONS)
            ):
                matches += 1
        if matches != 1:
            raise BedrockS3NamespaceError(
                "policy must contain exactly one exact unconditional mutation deny"
            )

    @staticmethod
    def _require_absent(method: object, request: dict[str, object], code: str, label: str) -> None:
        try:
            method(**request)  # type: ignore[operator]
        except Exception as exc:
            response = getattr(exc, "response", None)
            error = response.get("Error") if isinstance(response, Mapping) else None
            if isinstance(error, Mapping) and error.get("Code") == code:
                return
            raise BedrockS3NamespaceError(f"{label} absence was not documented") from exc
        raise BedrockS3NamespaceError(f"{label} configuration is present")


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


__all__ = [
    "BedrockS3NamespaceError",
    "BedrockS3NamespaceLeaseQualifier",
    "BedrockS3NamespaceLeaseReceipt",
    "IndependentNamespaceLease",
    "IndependentNamespaceLeaseVerifier",
    "NAMESPACE_CONTROL_ACTIONS",
    "NAMESPACE_MUTATION_ACTIONS",
    "S3NamespaceEvidenceClient",
]
