from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

import pytest

from substrate.multimedia.bedrock_live_guard_custody import (
    BedrockLiveGuardCustodyError,
    IndependentCustodyAttestation,
    LiveGuardCustodyQualifier,
    OrganizationGuardSnapshot,
    VerifiedCustodyResult,
)
from substrate.multimedia.bedrock_s3_namespace import (
    NAMESPACE_CONTROL_ACTIONS,
    NAMESPACE_MUTATION_ACTIONS,
)
from tests.test_multimedia_bedrock_s3_namespace import _qualified


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("ascii")).hexdigest()


def _snapshot(**changes: object) -> OrganizationGuardSnapshot:
    actions = sorted((*NAMESPACE_MUTATION_ACTIONS, *NAMESPACE_CONTROL_ACTIONS))
    policy = {
        "Statement": [{"Action": actions, "Effect": "Deny", "Principal": "*", "Resource": "*"}],
        "Version": "2012-10-17",
    }
    def policy_evidence(prefix: str, policy_type: str) -> dict[str, str]:
        policy_id = f"p-{prefix}abcde"
        arn = (
            "arn:aws:organizations::999999999999:policy/"
            f"o-abcdefghij12/{policy_type.lower()}/{policy_id}"
        )
        document = _canonical(policy)
        describe = _canonical(
            {
                "Content": document,
                "PolicySummary": {"Arn": arn, "Id": policy_id, "Type": policy_type},
            }
        )
        targets = _canonical(
            {
                "NextToken": None,
                "Targets": [{"TargetId": "123456789012", "Type": "ACCOUNT"}],
            }
        )
        return {
            f"{prefix}_policy_id": policy_id,
            f"{prefix}_policy_arn": arn,
            f"{prefix}_policy_document": document,
            f"{prefix}_describe_response": describe,
            f"{prefix}_targets_response": targets,
        }

    scp = json.loads(_canonical(policy))
    del scp["Statement"][0]["Principal"]
    policy = scp
    scp_values = policy_evidence("scp", "SERVICE_CONTROL_POLICY")
    policy = {
        "Statement": [
            {
                "Action": sorted(NAMESPACE_MUTATION_ACTIONS),
                "Effect": "Deny",
                "Principal": "*",
                "Resource": "*",
            }
        ],
        "Version": "2012-10-17",
    }
    rcp_values = policy_evidence("rcp", "RESOURCE_CONTROL_POLICY")
    values = {
        "organization_id": "o-abcdefghij12",
        "management_account_id": "999999999999",
        "member_account_id": "123456789012",
        **scp_values,
        **rcp_values,
        "observed_at": "2026-07-15T01:00:00Z",
    }
    values.update(changes)
    return OrganizationGuardSnapshot(**values)  # type: ignore[arg-type]


class CustodyVerifier:
    verifier_digest = "d" * 64
    trust_root_digest = "e" * 64

    def __init__(self, calls: list[str]) -> None:
        self.calls = calls
        self.reject = False

    def verify(self, attestation: IndependentCustodyAttestation) -> VerifiedCustodyResult:
        self.calls.append("custody")
        if self.reject:
            raise ValueError("signature rejected")
        return VerifiedCustodyResult(
            attestation_digest=attestation.digest,
            signer_digests=attestation.signer_digests,
            signer_quorum=attestation.signer_quorum,
            administration_domain_digests=("7" * 64, "8" * 64),
            audit_source_digest=attestation.audit_source_digest,
        )


class Cycle34Verifier:
    def __init__(self, receipt: object, calls: list[str]) -> None:
        self.receipt = receipt
        self.calls = calls
        self.reject = False

    def verify(self, receipt: object):
        self.calls.append("cycle34")
        if self.reject:
            raise ValueError("current authority changed")
        assert receipt == self.receipt
        return receipt


def _attestation(cycle34: object, snapshot: OrganizationGuardSnapshot, **changes: object):
    values = {
        "cycle34_receipt_digest": cycle34.digest,
        "guard_snapshot_digest": snapshot.digest,
        "workload_runtime_digest": "1" * 64,
        "issuer_digest": "2" * 64,
        "verifier_digest": "d" * 64,
        "trust_root_digest": "e" * 64,
        "signer_digests": ("3" * 64, "4" * 64, "5" * 64),
        "signer_quorum": 2,
        "not_before": "2026-07-15T00:59:00Z",
        "expires_at": "2026-07-16T13:00:00Z",
        "audit_source_digest": "6" * 64,
        "audit_complete_through": "2026-07-15T00:59:30Z",
        "max_audit_lag_seconds": 60,
        "predecessor_receipt_digest": None,
    }
    values.update(changes)
    return IndependentCustodyAttestation(**values)


def _setup(times: list[datetime] | None = None):
    cycle34 = _qualified()[0]
    snapshot = _snapshot()
    calls: list[str] = []
    custody = CustodyVerifier(calls)
    cycle34_verifier = Cycle34Verifier(cycle34, calls)
    clock_values = iter(
        times
        or [
            datetime(2026, 7, 15, 1, tzinfo=UTC),
            datetime(2026, 7, 15, 1, tzinfo=UTC),
        ]
    )
    qualifier = LiveGuardCustodyQualifier(
        verifier=custody,
        cycle34_verifier=cycle34_verifier,
        clock=lambda: next(clock_values),
        workload_runtime_digest="1" * 64,
        approved_signer_digests=("3" * 64, "4" * 64, "5" * 64),
        required_signer_quorum=2,
        approved_administration_domain_digests=("7" * 64, "8" * 64),
        approved_audit_source_digest="6" * 64,
    )
    return (
        cycle34,
        snapshot,
        _attestation(cycle34, snapshot),
        qualifier,
        custody,
        cycle34_verifier,
        calls,
    )


def test_exact_evidence_yields_truthful_negative_capability_receipt() -> None:
    cycle34, snapshot, attestation, qualifier, _, _, calls = _setup()
    receipt = qualifier.qualify(
        cycle34_receipt=cycle34,
        guard_snapshot=snapshot,
        attestation=attestation,
        verified_at=datetime(2026, 7, 15, 1, tzinfo=UTC),
    )
    assert calls == ["custody", "cycle34"]
    assert receipt.current_guard_observed is True
    assert receipt.attachment_scope_verified is True
    assert receipt.external_custody_authenticated is True
    assert receipt.audit_complete_through_watermark is True
    assert receipt.management_account_constrained is False
    assert receipt.prospective_unrevocability is False
    assert receipt.production_eligible is False
    assert receipt.bedrock_version_selected is False
    assert receipt.bedrock_read_observed is False
    assert type(receipt).from_json(receipt.canonical_json) == receipt
    assert OrganizationGuardSnapshot.from_json(snapshot.canonical_json) == snapshot
    assert IndependentCustodyAttestation.from_json(attestation.canonical_json) == attestation


@pytest.mark.parametrize(
    "change",
    [
        {"management_account_id": "123456789012"},
        {"scp_policy_id": "bad"},
        {"rcp_policy_arn": "wrong"},
        {"scp_targets_response": '{"NextToken":"more","Targets":[]}'},
        {"observed_at": "2026-07-15T01:00:00+00:00"},
    ],
)
def test_snapshot_topology_and_identity_fail_closed(change: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        _snapshot(**change)


def test_policy_top_level_shape_is_exact() -> None:
    snapshot = _snapshot()
    policy = json.loads(snapshot.rcp_policy_document)
    policy["Id"] = "extra"
    document = _canonical(policy)
    describe = json.loads(snapshot.rcp_describe_response)
    describe["Content"] = document
    with pytest.raises(ValueError, match="top-level"):
        _snapshot(
            rcp_policy_document=document,
            rcp_describe_response=_canonical(describe),
        )


@pytest.mark.parametrize(
    "change",
    [
        {"signer_quorum": 1},
        {"issuer_digest": "1" * 64},
        {"production_eligible": True},
        {"prospective_unrevocability": True},
        {"management_account_constrained": True},
        {"max_audit_lag_seconds": 0},
        {"expires_at": "2026-08-01T00:00:00Z"},
    ],
)
def test_attestation_independence_and_negative_capabilities_are_strict(
    change: dict[str, object],
) -> None:
    cycle34, snapshot, _, _, _, _, _ = _setup()
    with pytest.raises(ValueError):
        _attestation(cycle34, snapshot, **change)


@pytest.mark.parametrize(
    "change",
    [
        {"cycle34_receipt_digest": "f" * 64},
        {"guard_snapshot_digest": "f" * 64},
        {"workload_runtime_digest": "f" * 64},
        {"verifier_digest": "f" * 64},
        {"trust_root_digest": "f" * 64},
    ],
)
def test_every_authority_binding_is_checked(change: dict[str, object]) -> None:
    cycle34, snapshot, _, qualifier, _, _, _ = _setup()
    with pytest.raises(BedrockLiveGuardCustodyError):
        qualifier.qualify(
            cycle34_receipt=cycle34,
            guard_snapshot=snapshot,
            attestation=_attestation(cycle34, snapshot, **change),
            verified_at=datetime(2026, 7, 15, 1, tzinfo=UTC),
        )


@pytest.mark.parametrize(
    "watermark",
    ["2026-07-15T01:00:01Z", "2026-07-15T00:58:59Z"],
)
def test_future_or_stale_audit_watermark_fails(watermark: str) -> None:
    cycle34, snapshot, _, qualifier, _, _, _ = _setup()
    with pytest.raises(BedrockLiveGuardCustodyError, match="watermark"):
        qualifier.qualify(
            cycle34_receipt=cycle34,
            guard_snapshot=snapshot,
            attestation=_attestation(cycle34, snapshot, audit_complete_through=watermark),
            verified_at=datetime(2026, 7, 15, 1, tzinfo=UTC),
        )


def test_custody_rejection_stops_before_cycle34_reverify() -> None:
    cycle34, snapshot, attestation, qualifier, custody, _, calls = _setup()
    custody.reject = True
    with pytest.raises(BedrockLiveGuardCustodyError, match="not authenticated"):
        qualifier.qualify(
            cycle34_receipt=cycle34,
            guard_snapshot=snapshot,
            attestation=attestation,
            verified_at=datetime(2026, 7, 15, 1, tzinfo=UTC),
        )
    assert calls == ["custody"]


def test_cycle34_reverify_is_mandatory_and_precedes_final_clock() -> None:
    cycle34, snapshot, attestation, qualifier, _, cycle34_verifier, calls = _setup()
    cycle34_verifier.reject = True
    with pytest.raises(BedrockLiveGuardCustodyError, match="Cycle 34"):
        qualifier.qualify(
            cycle34_receipt=cycle34,
            guard_snapshot=snapshot,
            attestation=attestation,
            verified_at=datetime(2026, 7, 15, 1, tzinfo=UTC),
        )
    assert calls == ["custody", "cycle34"]


def test_invalid_injected_boundaries_are_normalized() -> None:
    cycle34, snapshot, attestation, qualifier, custody, cycle34_verifier, _ = _setup()
    custody.verifier_digest = "bad"
    with pytest.raises(BedrockLiveGuardCustodyError, match="authority"):
        qualifier.qualify(
            cycle34_receipt=cycle34,
            guard_snapshot=snapshot,
            attestation=attestation,
            verified_at=datetime(2026, 7, 15, 1, tzinfo=UTC),
        )
    custody.verifier_digest = "d" * 64
    cycle34_verifier.receipt = object()
    cycle34_verifier.verify = lambda receipt: object()  # type: ignore[method-assign]
    with pytest.raises(BedrockLiveGuardCustodyError, match="substituted"):
        qualifier.qualify(
            cycle34_receipt=cycle34,
            guard_snapshot=snapshot,
            attestation=attestation,
            verified_at=datetime(2026, 7, 15, 1, tzinfo=UTC),
        )


def test_audit_freshness_is_rechecked_after_cycle34_authority() -> None:
    cycle34, snapshot, attestation, qualifier, _, _, _ = _setup(
        [
            datetime(2026, 7, 15, 1, tzinfo=UTC),
            datetime(2026, 7, 15, 1, 1, tzinfo=UTC),
        ]
    )
    with pytest.raises(BedrockLiveGuardCustodyError, match="watermark"):
        qualifier.qualify(
            cycle34_receipt=cycle34,
            guard_snapshot=snapshot,
            attestation=attestation,
            verified_at=datetime(2026, 7, 15, 1, tzinfo=UTC),
        )


def test_trusted_clock_cannot_move_backward() -> None:
    cycle34, snapshot, attestation, qualifier, _, _, _ = _setup(
        [
            datetime(2026, 7, 15, 1, tzinfo=UTC),
            datetime(2026, 7, 15, 0, 59, 59, tzinfo=UTC),
        ]
    )
    with pytest.raises(BedrockLiveGuardCustodyError, match="backward"):
        qualifier.qualify(
            cycle34_receipt=cycle34,
            guard_snapshot=snapshot,
            attestation=attestation,
            verified_at=datetime(2026, 7, 15, 1, tzinfo=UTC),
        )


def test_guard_snapshot_must_be_observed_at_trusted_start() -> None:
    cycle34, _, _, qualifier, _, _, _ = _setup()
    snapshot = _snapshot(observed_at="2026-07-15T00:59:59Z")
    with pytest.raises(BedrockLiveGuardCustodyError, match="snapshot observation"):
        qualifier.qualify(
            cycle34_receipt=cycle34,
            guard_snapshot=snapshot,
            attestation=_attestation(cycle34, snapshot),
            verified_at=datetime(2026, 7, 15, 1, tzinfo=UTC),
        )


def test_contiguous_monotonic_renewal_binds_predecessor() -> None:
    cycle34, snapshot, attestation, qualifier, _, _, _ = _setup()
    predecessor = qualifier.qualify(
        cycle34_receipt=cycle34,
        guard_snapshot=snapshot,
        attestation=attestation,
        verified_at=datetime(2026, 7, 15, 1, tzinfo=UTC),
    )
    cycle34, snapshot, _, qualifier, _, _, _ = _setup()
    renewed = _attestation(
        cycle34,
        snapshot,
        predecessor_receipt_digest=predecessor.digest,
    )
    receipt = qualifier.qualify(
        cycle34_receipt=cycle34,
        guard_snapshot=snapshot,
        attestation=renewed,
        predecessor=predecessor,
        verified_at=datetime(2026, 7, 15, 1, tzinfo=UTC),
    )
    assert receipt.predecessor_receipt_digest == predecessor.digest


def test_renewal_gap_fails_before_receipt() -> None:
    cycle34, snapshot, attestation, qualifier, _, _, _ = _setup()
    predecessor = qualifier.qualify(
        cycle34_receipt=cycle34,
        guard_snapshot=snapshot,
        attestation=attestation,
        verified_at=datetime(2026, 7, 15, 1, tzinfo=UTC),
    )
    cycle34, snapshot, _, qualifier, _, _, _ = _setup()
    with pytest.raises(BedrockLiveGuardCustodyError, match="renewal"):
        qualifier.qualify(
            cycle34_receipt=cycle34,
            guard_snapshot=snapshot,
            attestation=_attestation(
                cycle34,
                snapshot,
                predecessor_receipt_digest=predecessor.digest,
                not_before="2026-07-16T13:00:01Z",
                expires_at="2026-07-17T14:00:00Z",
            ),
            predecessor=predecessor,
            verified_at=datetime(2026, 7, 15, 1, tzinfo=UTC),
        )


def test_noncanonical_and_duplicate_json_are_rejected() -> None:
    snapshot = _snapshot()
    with pytest.raises(ValueError, match="canonical"):
        OrganizationGuardSnapshot.from_json(
            json.dumps(json.loads(snapshot.canonical_json), indent=2)
        )
    duplicate = snapshot.canonical_json[:-1] + ',"organization_id":"o-abcdefghij12"}'
    with pytest.raises(ValueError, match="canonical"):
        OrganizationGuardSnapshot.from_json(duplicate)
