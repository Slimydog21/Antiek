from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

import pytest

from substrate.multimedia.bedrock_s3_namespace import (
    NAMESPACE_CONTROL_ACTIONS,
    NAMESPACE_MUTATION_ACTIONS,
    BedrockS3NamespaceError,
    BedrockS3NamespaceLeaseQualifier,
    IndependentNamespaceLease,
)
from substrate.multimedia.bedrock_s3_publication import BedrockS3VersionPublisher
from tests.test_multimedia_bedrock_batch_adapter import _bounded_workload
from tests.test_multimedia_bedrock_s3_publication import ExactS3, _profile


class MissingConfiguration(Exception):
    def __init__(self, code: str) -> None:
        self.response = {"Error": {"Code": code}}


class Evidence:
    def __init__(self, policy: dict[str, object]) -> None:
        self.policy = policy
        self.lifecycle_code = "NoSuchLifecycleConfiguration"
        self.replication_code = "ReplicationConfigurationNotFoundError"
        self.lifecycle_present = False
        self.replication_present = False
        self.public = {
            "BlockPublicAcls": True,
            "IgnorePublicAcls": True,
            "BlockPublicPolicy": True,
            "RestrictPublicBuckets": True,
        }
        self.ownership = "BucketOwnerEnforced"
        self.versioning = "Enabled"
        self.object_lock = "Enabled"

    def get_bucket_policy(self, **request: object) -> dict[str, object]:
        self._owner(request)
        return {"Policy": json.dumps(self.policy)}

    def get_bucket_lifecycle_configuration(self, **request: object) -> dict[str, object]:
        self._owner(request)
        if self.lifecycle_present:
            return {"Rules": []}
        raise MissingConfiguration(self.lifecycle_code)

    def get_bucket_replication(self, **request: object) -> dict[str, object]:
        self._owner(request)
        if self.replication_present:
            return {"ReplicationConfiguration": {"Role": "role", "Rules": []}}
        raise MissingConfiguration(self.replication_code)

    def get_public_access_block(self, **request: object) -> dict[str, object]:
        self._owner(request)
        return {"PublicAccessBlockConfiguration": self.public}

    def get_bucket_ownership_controls(self, **request: object) -> dict[str, object]:
        self._owner(request)
        return {"OwnershipControls": {"Rules": [{"ObjectOwnership": self.ownership}]}}

    def get_bucket_versioning(self, **request: object) -> dict[str, object]:
        self._owner(request)
        return {"Status": self.versioning}

    def get_object_lock_configuration(self, **request: object) -> dict[str, object]:
        self._owner(request)
        return {"ObjectLockConfiguration": {"ObjectLockEnabled": self.object_lock}}

    @staticmethod
    def _owner(request: dict[str, object]) -> None:
        assert request == {
            "Bucket": "antiek-bedrock-input",
            "ExpectedBucketOwner": "123456789012",
        }


class Verifier:
    verifier_digest = "d" * 64
    trust_root_digest = "e" * 64

    def __init__(self) -> None:
        self.calls = 0
        self.reject = False

    def verify(self, lease: IndependentNamespaceLease) -> None:
        self.calls += 1
        if self.reject:
            raise ValueError("bad external signature")


def _policy(key: str) -> dict[str, object]:
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "ExactNamespaceDeny",
                "Effect": "Deny",
                "Principal": "*",
                "Action": list(NAMESPACE_MUTATION_ACTIONS),
                "Resource": f"arn:aws:s3:::antiek-bedrock-input/{key}",
            },
            {
                "Effect": "Allow",
                "Principal": {"AWS": "role"},
                "Action": "s3:GetObject",
                "Resource": "*",
            },
        ],
    }


def _digest(value: object) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("ascii")).hexdigest()


def _publish(client: ExactS3):
    body, bound = _bounded_workload()
    key = f"server/bedrock/{bound.workload_sha256}/manifest.jsonl"
    policy = _policy(key)
    profile = _profile(namespace_policy_digest=_digest(policy))
    receipt = BedrockS3VersionPublisher(client, profile).publish(
        workload_bound=bound,
        workload_bytes=body,
        verified_at=datetime(2026, 7, 15, 1, tzinfo=UTC),
        bedrock_timeout_hours=24,
    )
    return receipt, policy, profile


def _lease(
    receipt: object, policy: dict[str, object], **changes: object
) -> IndependentNamespaceLease:
    values = {
        "account_id": "123456789012",
        "bucket": receipt.bucket,
        "prefix": "server/bedrock/",
        "key": receipt.key,
        "workload_bound_digest": receipt.workload_bound_digest,
        "version_id": receipt.version_id,
        "policy_digest": _digest(policy),
        "organization_guard_digest": "c" * 64,
        "verifier_digest": "d" * 64,
        "trust_root_digest": "e" * 64,
        "not_before": "2026-07-15T00:59:59Z",
        "expires_at": "2026-07-16T13:00:00Z",
        "data_deny_actions": NAMESPACE_MUTATION_ACTIONS,
        "control_deny_actions": NAMESPACE_CONTROL_ACTIONS,
        "lifecycle_history_clear": True,
        "alternate_access_paths_denied": True,
        "guard_semantics_validated": True,
    }
    values.update(changes)
    return IndependentNamespaceLease(**values)  # type: ignore[arg-type]


def _qualified():
    publication_client = ExactS3()
    publication, policy, profile = _publish(publication_client)
    evidence = Evidence(policy)
    verifier = Verifier()
    qualifier = BedrockS3NamespaceLeaseQualifier(
        evidence,
        profile,
        BedrockS3VersionPublisher(publication_client, profile),
        verifier,
        lambda: datetime(2026, 7, 15, 1, tzinfo=UTC),
    )
    receipt = qualifier.qualify(
        publication_receipt=publication,
        independent_lease=_lease(publication, policy),
        verified_at=datetime(2026, 7, 15, 1, tzinfo=UTC),
        bedrock_timeout_hours=24,
    )
    return receipt, publication, policy, evidence, verifier, qualifier


def test_exact_evidence_yields_canonical_truthful_receipt() -> None:
    receipt, _, _, _, verifier, _ = _qualified()
    assert verifier.calls == 1
    assert receipt.version_immutable is True
    assert receipt.current_for_lease is True
    assert receipt.exact_key_mutation_denied is True
    assert receipt.lifecycle_absent is True
    assert receipt.replication_absent is True
    assert receipt.independent_control_lease_verified is True
    assert receipt.bedrock_version_selected is False
    assert receipt.bedrock_read_observed is False
    assert type(receipt).from_json(receipt.canonical_json) == receipt


def test_lease_canonical_round_trip_and_noncanonical_input_rejection() -> None:
    _, publication, policy, _, _, _ = _qualified()
    lease = _lease(publication, policy)
    assert IndependentNamespaceLease.from_json(lease.canonical_json) == lease
    with pytest.raises(ValueError, match="exact canonical JSON"):
        IndependentNamespaceLease.from_json(json.dumps(json.loads(lease.canonical_json), indent=2))


@pytest.mark.parametrize(
    "claim",
    ["lifecycle_history_clear", "alternate_access_paths_denied", "guard_semantics_validated"],
)
def test_independent_operational_claims_are_mandatory(claim: str) -> None:
    _, publication, policy, _, _, _ = _qualified()
    with pytest.raises(ValueError, match="operational guard claims"):
        _lease(publication, policy, **{claim: False})


@pytest.mark.parametrize("mutation", ["missing", "condition", "principal", "resource", "wildcard"])
def test_policy_deny_is_structural_exact_and_unconditional(mutation: str) -> None:
    _, publication, policy, evidence, _, qualifier = _qualified()
    deny = policy["Statement"][0]
    if mutation == "missing":
        deny["Action"].pop()
    elif mutation == "condition":
        deny["Condition"] = {"StringEquals": {"aws:PrincipalArn": "role"}}
    elif mutation == "principal":
        deny["Principal"] = {"AWS": "*"}
    elif mutation == "resource":
        deny["Resource"] = "arn:aws:s3:::other/key"
    else:
        deny["Resource"] = "arn:aws:s3:::antiek-bedrock-input/server/bedrock/*"
    evidence.policy = policy
    with pytest.raises(BedrockS3NamespaceError, match="exact unconditional"):
        qualifier.qualify(
            publication_receipt=publication,
            independent_lease=_lease(publication, policy),
            verified_at=datetime(2026, 7, 15, 1, tzinfo=UTC),
            bedrock_timeout_hours=24,
        )


@pytest.mark.parametrize("bad_action", [{"nested": True}, ["nested"], True, 1, None])
def test_malformed_policy_actions_fail_with_namespace_error(bad_action: object) -> None:
    _, publication, policy, evidence, _, qualifier = _qualified()
    policy["Statement"][0]["Action"][0] = bad_action
    evidence.policy = policy
    with pytest.raises(BedrockS3NamespaceError, match="exact unconditional"):
        qualifier.qualify(
            publication_receipt=publication,
            independent_lease=_lease(publication, policy),
            verified_at=datetime(2026, 7, 15, 1, tzinfo=UTC),
            bedrock_timeout_hours=24,
        )


def test_live_policy_and_lease_cannot_substitute_publication_profile_policy() -> None:
    _, publication, policy, evidence, _, qualifier = _qualified()
    policy["Statement"].append(
        {"Effect": "Allow", "Principal": "role-2", "Action": "s3:GetObject", "Resource": "*"}
    )
    evidence.policy = policy
    with pytest.raises(BedrockS3NamespaceError, match="publication profile"):
        qualifier.qualify(
            publication_receipt=publication,
            independent_lease=_lease(publication, policy),
            verified_at=datetime(2026, 7, 15, 1, tzinfo=UTC),
            bedrock_timeout_hours=24,
        )


@pytest.mark.parametrize(
    ("surface", "code"),
    [
        ("lifecycle", "AccessDenied"),
        ("replication", "NoSuchReplicationConfiguration"),
    ],
)
def test_only_documented_absence_codes_are_accepted(surface: str, code: str) -> None:
    _, publication, policy, evidence, _, qualifier = _qualified()
    setattr(evidence, f"{surface}_code", code)
    with pytest.raises(BedrockS3NamespaceError, match=f"{surface} absence"):
        qualifier.qualify(
            publication_receipt=publication,
            independent_lease=_lease(publication, policy),
            verified_at=datetime(2026, 7, 15, 1, tzinfo=UTC),
            bedrock_timeout_hours=24,
        )


@pytest.mark.parametrize("surface", ["lifecycle", "replication"])
def test_present_lifecycle_or_replication_configuration_fails(surface: str) -> None:
    _, publication, policy, evidence, _, qualifier = _qualified()
    setattr(evidence, f"{surface}_present", True)
    with pytest.raises(BedrockS3NamespaceError, match=f"{surface} configuration is present"):
        qualifier.qualify(
            publication_receipt=publication,
            independent_lease=_lease(publication, policy),
            verified_at=datetime(2026, 7, 15, 1, tzinfo=UTC),
            bedrock_timeout_hours=24,
        )


@pytest.mark.parametrize(
    ("surface", "value", "message"),
    [
        ("BlockPublicAcls", False, "public-access"),
        ("IgnorePublicAcls", False, "public-access"),
        ("BlockPublicPolicy", False, "public-access"),
        ("RestrictPublicBuckets", False, "public-access"),
        ("ownership", "ObjectWriter", "ownership"),
        ("versioning", "Suspended", "versioning"),
        ("object_lock", "Disabled", "Object Lock"),
    ],
)
def test_every_bucket_control_is_fail_closed(surface: str, value: object, message: str) -> None:
    _, publication, policy, evidence, _, qualifier = _qualified()
    if surface in evidence.public:
        evidence.public[surface] = value
    else:
        setattr(evidence, surface, value)
    with pytest.raises(BedrockS3NamespaceError, match=message):
        qualifier.qualify(
            publication_receipt=publication,
            independent_lease=_lease(publication, policy),
            verified_at=datetime(2026, 7, 15, 1, tzinfo=UTC),
            bedrock_timeout_hours=24,
        )


def test_external_verifier_rejection_stops_before_s3_evidence() -> None:
    _, publication, policy, evidence, verifier, qualifier = _qualified()
    verifier.reject = True
    evidence.get_bucket_policy = lambda **_: pytest.fail("S3 must not be read")  # type: ignore[method-assign]
    with pytest.raises(BedrockS3NamespaceError, match="not authenticated"):
        qualifier.qualify(
            publication_receipt=publication,
            independent_lease=_lease(publication, policy),
            verified_at=datetime(2026, 7, 15, 1, tzinfo=UTC),
            bedrock_timeout_hours=24,
        )


@pytest.mark.parametrize("timeout", [24.5, "24", True, None])
def test_timeout_requires_an_exact_integer(timeout: object) -> None:
    _, publication, policy, evidence, verifier, qualifier = _qualified()
    evidence.get_bucket_policy = lambda **_: pytest.fail("S3 must not be read")  # type: ignore[method-assign]
    with pytest.raises(ValueError, match="between 24 and 168"):
        qualifier.qualify(
            publication_receipt=publication,
            independent_lease=_lease(publication, policy),
            verified_at=datetime(2026, 7, 15, 1, tzinfo=UTC),
            bedrock_timeout_hours=timeout,  # type: ignore[arg-type]
        )
    assert verifier.calls == 1


def test_verifier_identity_is_snapshotted_once() -> None:
    _, publication, policy, evidence, _, qualifier = _qualified()

    class StatefulVerifier:
        def __init__(self) -> None:
            self.verifier_reads = 0
            self.root_reads = 0

        @property
        def verifier_digest(self) -> str:
            self.verifier_reads += 1
            return "d" * 64 if self.verifier_reads == 1 else "f" * 64

        @property
        def trust_root_digest(self) -> str:
            self.root_reads += 1
            return "e" * 64 if self.root_reads == 1 else "f" * 64

        def verify(self, lease: IndependentNamespaceLease) -> None:
            return None

    verifier = StatefulVerifier()
    qualifier.verifier = verifier
    receipt = qualifier.qualify(
        publication_receipt=publication,
        independent_lease=_lease(publication, policy),
        verified_at=datetime(2026, 7, 15, 1, tzinfo=UTC),
        bedrock_timeout_hours=24,
    )
    assert receipt.verifier_digest == "d" * 64
    assert receipt.trust_root_digest == "e" * 64
    assert (verifier.verifier_reads, verifier.root_reads) == (1, 1)


def test_caller_time_must_equal_injected_trusted_clock() -> None:
    _, publication, policy, _, _, qualifier = _qualified()
    qualifier.clock = lambda: datetime(2026, 7, 15, 1, 0, 1, tzinfo=UTC)
    with pytest.raises(BedrockS3NamespaceError, match="trusted clock"):
        qualifier.qualify(
            publication_receipt=publication,
            independent_lease=_lease(publication, policy),
            verified_at=datetime(2026, 7, 15, 1, tzinfo=UTC),
            bedrock_timeout_hours=24,
        )


def test_lease_coverage_is_rechecked_after_final_publication_verification() -> None:
    _, publication, policy, _, _, qualifier = _qualified()
    times = iter(
        [
            datetime(2026, 7, 15, 1, tzinfo=UTC),
            datetime(2026, 7, 15, 2, tzinfo=UTC),
        ]
    )
    qualifier.clock = lambda: next(times)
    with pytest.raises(BedrockS3NamespaceError, match="timeout plus margin"):
        qualifier.qualify(
            publication_receipt=publication,
            independent_lease=_lease(publication, policy),
            verified_at=datetime(2026, 7, 15, 1, tzinfo=UTC),
            bedrock_timeout_hours=24,
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"not_before": "2026-07-15T01:00:01Z"},
        {"expires_at": "2026-07-16T12:59:59Z"},
        {"not_before": "2026-07-01T00:00:00Z"},
        {"trust_root_digest": "f" * 64},
    ],
)
def test_wrong_authority_or_short_lease_fails(changes: dict[str, object]) -> None:
    _, publication, policy, _, _, qualifier = _qualified()
    with pytest.raises(BedrockS3NamespaceError):
        qualifier.qualify(
            publication_receipt=publication,
            independent_lease=_lease(publication, policy, **changes),
            verified_at=datetime(2026, 7, 15, 1, tzinfo=UTC),
            bedrock_timeout_hours=24,
        )


def test_final_publication_reverify_detects_current_version_substitution() -> None:
    publication_client = ExactS3()
    publication, policy, profile = _publish(publication_client)
    publication_client.current_version = "substituted"
    qualifier = BedrockS3NamespaceLeaseQualifier(
        Evidence(policy),
        profile,
        BedrockS3VersionPublisher(publication_client, profile),
        Verifier(),
        lambda: datetime(2026, 7, 15, 1, tzinfo=UTC),
    )
    with pytest.raises(BedrockS3NamespaceError, match="final publication reverify"):
        qualifier.qualify(
            publication_receipt=publication,
            independent_lease=_lease(publication, policy),
            verified_at=datetime(2026, 7, 15, 1, tzinfo=UTC),
            bedrock_timeout_hours=24,
        )
