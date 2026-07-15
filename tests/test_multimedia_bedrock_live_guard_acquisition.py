from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

import pytest

from substrate.multimedia.bedrock_live_guard_acquisition import (
    BedrockLiveGuardAcquisitionError,
    LiveGuardAcquisitionCommand,
    LiveGuardAcquisitionCoordinator,
    LiveGuardAcquisitionReceipt,
    RevocationObservation,
    VerifiedRevocationResult,
)
from substrate.multimedia.bedrock_live_guard_custody import OrganizationGuardSnapshot
from tests.test_multimedia_bedrock_live_guard_custody import _attestation, _setup, _snapshot


class OrganizationsClient:
    def __init__(self, snapshot: OrganizationGuardSnapshot, calls: list[str]) -> None:
        self.calls = calls
        self.responses: dict[str, dict[str, object]] = {
            snapshot.scp_policy_id: {
                "describe": json.loads(snapshot.scp_describe_response),
                "targets": json.loads(snapshot.scp_targets_response),
            },
            snapshot.rcp_policy_id: {
                "describe": json.loads(snapshot.rcp_describe_response),
                "targets": json.loads(snapshot.rcp_targets_response),
            },
        }
        self.drift_after = 0
        self.reads = 0

    def describe_policy(self, **request: object) -> dict[str, object]:
        assert set(request) == {"PolicyId"}
        policy_id = request["PolicyId"]
        assert isinstance(policy_id, str)
        self.calls.append(f"describe:{policy_id}")
        self.reads += 1
        response = json.loads(json.dumps(self.responses[policy_id]["describe"]))
        if self.drift_after and self.reads > self.drift_after:
            response["Content"] = "{}"
        return response

    def list_targets_for_policy(self, **request: object) -> dict[str, object]:
        assert set(request) == {"PolicyId"}
        policy_id = request["PolicyId"]
        assert isinstance(policy_id, str)
        self.calls.append(f"targets:{policy_id}")
        self.reads += 1
        return json.loads(json.dumps(self.responses[policy_id]["targets"]))


class CustodyClient:
    def __init__(self, cycle34: object, calls: list[str]) -> None:
        self.cycle34 = cycle34
        self.calls = calls
        self.substitute = False
        self.wrong_context = False

    def acquire_attestation(self, *, request_json: str, idempotency_key: str) -> str:
        self.calls.append("attestation")
        request = json.loads(request_json)
        assert set(request) == {
            "attempt_id",
            "attempt_json",
            "command_json",
            "command_digest",
            "cycle34_receipt_digest",
            "guard_snapshot_digest",
            "predecessor_receipt_digest",
        }
        assert idempotency_key == request["attempt_id"]
        assert json.loads(request["attempt_json"])["attempt_id"] == idempotency_key
        assert json.loads(request["command_json"])["cycle34_receipt_digest"] == self.cycle34.digest
        snapshot_digest = "f" * 64 if self.substitute else request["guard_snapshot_digest"]
        values = {
            "cycle34_receipt_digest": self.cycle34.digest,
            "guard_snapshot_digest": snapshot_digest,
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
            "predecessor_receipt_digest": request["predecessor_receipt_digest"],
            "acquisition_context_digest": "f" * 64
            if self.wrong_context
            else hashlib.sha256(request_json.encode("ascii")).hexdigest(),
        }
        return _attestation(self.cycle34, _snapshot(), **values).canonical_json


class RevocationClient:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls
        self.revoked = False
        self.watermark = "2026-07-15T00:59:30Z"
        self.source = "6" * 64

    def observe_revocation(self, *, request_json: str) -> str:
        self.calls.append("revocation")
        request = json.loads(request_json)
        assert set(request) == {
            "attempt_id",
            "attestation_digest",
            "audit_source_digest",
            "command_digest",
            "custody_receipt_digest",
            "guard_snapshot_digest",
            "observed_at",
        }
        return RevocationObservation(
            attempt_id=request["attempt_id"],
            guard_snapshot_digest=request["guard_snapshot_digest"],
            attestation_digest=request["attestation_digest"],
            custody_receipt_digest=request["custody_receipt_digest"],
            audit_source_digest=self.source,
            verifier_digest="9" * 64,
            trust_root_digest="a" * 64,
            observed_at=request["observed_at"],
            audit_complete_through=self.watermark,
            revoked=self.revoked,
        ).canonical_json


class RevocationVerifier:
    verifier_digest = "9" * 64
    trust_root_digest = "a" * 64

    def __init__(self, calls: list[str]) -> None:
        self.calls = calls
        self.reject = False

    def verify(self, observation: RevocationObservation) -> VerifiedRevocationResult:
        self.calls.append("verify-revocation")
        if self.reject:
            raise ValueError("revocation signature rejected")
        return VerifiedRevocationResult(
            observation_digest=observation.digest,
            verifier_digest=self.verifier_digest,
            trust_root_digest=self.trust_root_digest,
            audit_source_digest=observation.audit_source_digest,
        )


class Journal:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls
        self.commands: dict[str, str] = {}
        self.attempts: dict[str, str] = {}
        self.receipts: dict[str, str] = {}
        self.reject_commit = False
        self.write_then_raise = False

    def record_intent(self, *, command_json: str, attempt_json: str) -> None:
        self.calls.append("intent")
        command = LiveGuardAcquisitionCommand.from_json(command_json)
        attempt = json.loads(attempt_json)
        existing = self.commands.setdefault(command.command_id, command_json)
        if existing != command_json:
            raise ValueError("command conflict")
        existing_attempt = self.attempts.setdefault(attempt["attempt_id"], attempt_json)
        if existing_attempt != attempt_json:
            raise ValueError("attempt conflict")

    def commit_attempt(self, *, attempt_id: str, receipt_json: str) -> None:
        self.calls.append("commit")
        if self.reject_commit:
            raise ValueError("disk unavailable")
        receipt = LiveGuardAcquisitionReceipt.from_json(receipt_json)
        assert receipt.attempt_id == attempt_id
        existing = self.receipts.setdefault(attempt_id, receipt_json)
        if existing != receipt_json:
            raise ValueError("receipt conflict")
        if self.write_then_raise:
            raise OSError("acknowledgment lost after durable write")

    def read_attempt(self, *, attempt_id: str) -> str | None:
        self.calls.append("readback")
        return self.receipts.get(attempt_id)


def _command(cycle34: object, **changes: object) -> LiveGuardAcquisitionCommand:
    values = {
        "command_id": "lgc_" + "b" * 32,
        "cycle34_receipt_digest": cycle34.digest,
        "organization_id": "o-abcdefghij12",
        "management_account_id": "999999999999",
        "member_account_id": "123456789012",
        "scp_policy_id": "p-scpabcde",
        "rcp_policy_id": "p-rcpabcde",
        "predecessor_receipt_digest": None,
        "max_revocation_lag_seconds": 60,
    }
    values.update(changes)
    return LiveGuardAcquisitionCommand(**values)


def _coordinator(now: datetime | None = None):
    current = now or datetime(2026, 7, 15, 1, tzinfo=UTC)
    cycle34, snapshot, _, qualifier, _, _, _ = _setup([current, current])
    calls: list[str] = []
    organizations = OrganizationsClient(snapshot, calls)
    custody = CustodyClient(cycle34, calls)
    revocations = RevocationClient(calls)
    revocation_verifier = RevocationVerifier(calls)
    journal = Journal(calls)
    coordinator = LiveGuardAcquisitionCoordinator(
        organizations=organizations,
        custody=custody,
        revocations=revocations,
        revocation_verifier=revocation_verifier,
        qualifier=qualifier,
        journal=journal,
        clock=lambda: current,
        approved_revocation_verifier_digest="9" * 64,
        approved_revocation_trust_root_digest="a" * 64,
        approved_audit_source_digest="6" * 64,
    )
    return (
        cycle34,
        coordinator,
        organizations,
        custody,
        revocations,
        revocation_verifier,
        journal,
        calls,
    )


def test_exact_read_only_acquisition_commits_truthful_receipt() -> None:
    cycle34, coordinator, _, _, _, _, journal, calls = _coordinator()
    receipt = coordinator.acquire(
        command=_command(cycle34), cycle34_receipt=cycle34, attempt_nonce="c" * 32
    )
    assert calls[0] == "intent"
    assert calls[-4:] == ["revocation", "verify-revocation", "commit", "readback"]
    assert len([call for call in calls if call.startswith("describe:")]) == 4
    assert len([call for call in calls if call.startswith("targets:")]) == 4
    assert journal.receipts[receipt.attempt_id] == receipt.canonical_json
    assert receipt.organizations_rechecked is True
    assert receipt.revocation_observed is True
    assert receipt.management_account_constrained is False
    assert receipt.prospective_unrevocability is False
    assert receipt.production_eligible is False
    assert receipt.bedrock_version_selected is False
    assert receipt.bedrock_read_observed is False
    assert receipt.custody_receipt.digest == receipt.custody_receipt_digest
    assert LiveGuardAcquisitionReceipt.from_json(receipt.canonical_json) == receipt


@pytest.mark.parametrize(
    "change",
    [
        {"cycle34_receipt_digest": "f" * 64},
        {"member_account_id": "999999999999"},
        {"scp_policy_id": "bad"},
        {"max_revocation_lag_seconds": 0},
    ],
)
def test_command_identity_and_bounds_are_strict(change: dict[str, object]) -> None:
    cycle34 = _setup()[0]
    with pytest.raises((ValueError, BedrockLiveGuardAcquisitionError)):
        command = _command(cycle34, **change)
        _coordinator()[1].acquire(
            command=command, cycle34_receipt=cycle34, attempt_nonce="c" * 32
        )


def test_organizations_drift_fails_before_revocation_or_commit() -> None:
    cycle34, coordinator, organizations, _, _, _, journal, calls = _coordinator()
    organizations.drift_after = 4
    with pytest.raises(BedrockLiveGuardAcquisitionError, match="Organizations"):
        coordinator.acquire(
            command=_command(cycle34), cycle34_receipt=cycle34, attempt_nonce="c" * 32
        )
    assert "revocation" not in calls
    assert journal.receipts == {}


def test_incomplete_pagination_fails_before_attestation() -> None:
    cycle34, coordinator, organizations, _, _, _, journal, calls = _coordinator()
    organizations.responses["p-scpabcde"]["targets"]["NextToken"] = "more"  # type: ignore[index]
    with pytest.raises(BedrockLiveGuardAcquisitionError, match="snapshot"):
        coordinator.acquire(
            command=_command(cycle34), cycle34_receipt=cycle34, attempt_nonce="c" * 32
        )
    assert "attestation" not in calls
    assert journal.receipts == {}


def test_substituted_attestation_fails_without_completion() -> None:
    cycle34, coordinator, _, custody, _, _, journal, _ = _coordinator()
    custody.substitute = True
    with pytest.raises(BedrockLiveGuardAcquisitionError, match="substituted"):
        coordinator.acquire(
            command=_command(cycle34), cycle34_receipt=cycle34, attempt_nonce="c" * 32
        )
    assert journal.receipts == {}


def test_attestation_signed_for_another_attempt_context_fails() -> None:
    cycle34, coordinator, _, custody, _, _, journal, _ = _coordinator()
    custody.wrong_context = True
    with pytest.raises(BedrockLiveGuardAcquisitionError, match="substituted"):
        coordinator.acquire(
            command=_command(cycle34), cycle34_receipt=cycle34, attempt_nonce="c" * 32
        )
    assert journal.receipts == {}


def test_revoked_or_unauthenticated_observation_fails_closed() -> None:
    cycle34, coordinator, _, _, revocations, _, journal, _ = _coordinator()
    revocations.revoked = True
    with pytest.raises(BedrockLiveGuardAcquisitionError, match="revocation"):
        coordinator.acquire(
            command=_command(cycle34), cycle34_receipt=cycle34, attempt_nonce="c" * 32
        )
    assert journal.receipts == {}

    cycle34, coordinator, _, _, _, verifier, journal, _ = _coordinator()
    verifier.reject = True
    with pytest.raises(BedrockLiveGuardAcquisitionError, match="not authenticated"):
        coordinator.acquire(
            command=_command(cycle34), cycle34_receipt=cycle34, attempt_nonce="c" * 32
        )
    assert journal.receipts == {}


@pytest.mark.parametrize(
    "watermark",
    ["2026-07-15T01:00:01Z", "2026-07-15T00:58:59Z"],
)
def test_revocation_watermark_must_be_current(watermark: str) -> None:
    cycle34, coordinator, _, _, revocations, _, journal, _ = _coordinator()
    revocations.watermark = watermark
    with pytest.raises(BedrockLiveGuardAcquisitionError, match="revocation"):
        coordinator.acquire(
            command=_command(cycle34), cycle34_receipt=cycle34, attempt_nonce="c" * 32
        )
    assert journal.receipts == {}


def test_journal_commit_failure_returns_no_authority() -> None:
    cycle34, coordinator, _, _, _, _, journal, _ = _coordinator()
    journal.reject_commit = True
    with pytest.raises(BedrockLiveGuardAcquisitionError, match="completed attempt journal"):
        coordinator.acquire(
            command=_command(cycle34), cycle34_receipt=cycle34, attempt_nonce="c" * 32
        )
    assert journal.receipts == {}


def test_ambiguous_commit_is_reconciled_by_exact_readback() -> None:
    cycle34, coordinator, _, _, _, _, journal, _ = _coordinator()
    journal.write_then_raise = True
    receipt = coordinator.acquire(
        command=_command(cycle34), cycle34_receipt=cycle34, attempt_nonce="c" * 32
    )
    assert journal.receipts[receipt.attempt_id] == receipt.canonical_json


def test_same_second_attempts_require_distinct_explicit_nonces() -> None:
    cycle34, coordinator, _, _, _, _, journal, _ = _coordinator()
    first = coordinator.acquire(
        command=_command(cycle34), cycle34_receipt=cycle34, attempt_nonce="c" * 32
    )
    cycle34, second_coordinator, _, _, _, _, _, _ = _coordinator()
    second_coordinator.journal = journal
    second = second_coordinator.acquire(
        command=_command(cycle34), cycle34_receipt=cycle34, attempt_nonce="d" * 32
    )
    assert first.attempt_id != second.attempt_id


def test_custody_freshness_is_rechecked_at_completion() -> None:
    cycle34, coordinator, _, _, revocations, _, journal, _ = _coordinator()
    times = iter(
        [
            datetime(2026, 7, 15, 1, tzinfo=UTC),
            datetime(2026, 7, 15, 1, tzinfo=UTC),
            datetime(2026, 7, 15, 1, 0, 50, tzinfo=UTC),
            datetime(2026, 7, 15, 1, 1, 1, tzinfo=UTC),
        ]
    )
    coordinator.clock = lambda: next(times)
    revocations.watermark = "2026-07-15T01:00:50Z"
    with pytest.raises(BedrockLiveGuardAcquisitionError, match="custody audit"):
        coordinator.acquire(
            command=_command(cycle34), cycle34_receipt=cycle34, attempt_nonce="c" * 32
        )
    assert journal.receipts == {}


def test_slow_journal_cannot_return_stale_authority() -> None:
    cycle34, coordinator, _, _, revocations, _, journal, _ = _coordinator()
    times = iter(
        [
            datetime(2026, 7, 15, 1, tzinfo=UTC),
            datetime(2026, 7, 15, 1, tzinfo=UTC),
            datetime(2026, 7, 15, 1, tzinfo=UTC),
            datetime(2026, 7, 15, 1, tzinfo=UTC),
            datetime(2026, 7, 15, 1, 1, 1, tzinfo=UTC),
        ]
    )
    coordinator.clock = lambda: next(times)
    revocations.watermark = "2026-07-15T00:59:30Z"
    with pytest.raises(BedrockLiveGuardAcquisitionError, match="revocation audit"):
        coordinator.acquire(
            command=_command(cycle34), cycle34_receipt=cycle34, attempt_nonce="c" * 32
        )
    assert len(journal.receipts) == 1


def test_later_retry_is_new_attempt_and_reacquires_all_evidence() -> None:
    cycle34, coordinator, _, _, _, _, journal, calls = _coordinator()
    first = coordinator.acquire(
        command=_command(cycle34), cycle34_receipt=cycle34, attempt_nonce="c" * 32
    )
    first_call_count = len(calls)

    cycle34, later, _, _, _, _, _, later_calls = _coordinator(
        datetime(2026, 7, 15, 1, 0, 1, tzinfo=UTC)
    )
    later.journal = journal
    second = later.acquire(
        command=_command(cycle34), cycle34_receipt=cycle34, attempt_nonce="c" * 32
    )
    assert second.attempt_id != first.attempt_id
    assert len(journal.receipts) == 2
    assert first_call_count > 0
    assert len([call for call in later_calls if call.startswith("describe:")]) == 4


def test_durable_custody_receipt_drives_contiguous_renewal() -> None:
    cycle34, coordinator, _, _, _, _, _, _ = _coordinator()
    first = coordinator.acquire(
        command=_command(cycle34), cycle34_receipt=cycle34, attempt_nonce="c" * 32
    )
    predecessor = first.custody_receipt

    cycle34, renewal, _, _, _, _, _, _ = _coordinator()
    command = _command(
        cycle34,
        command_id="lgc_" + "d" * 32,
        predecessor_receipt_digest=predecessor.digest,
    )
    renewed = renewal.acquire(
        command=command,
        cycle34_receipt=cycle34,
        attempt_nonce="e" * 32,
        predecessor=predecessor,
    )
    assert renewed.predecessor_receipt_digest == predecessor.digest
    assert renewed.custody_receipt.predecessor_receipt_digest == predecessor.digest


def test_noncanonical_command_and_receipt_json_fail() -> None:
    cycle34, coordinator, _, _, _, _, _, _ = _coordinator()
    receipt = coordinator.acquire(
        command=_command(cycle34), cycle34_receipt=cycle34, attempt_nonce="c" * 32
    )
    with pytest.raises(ValueError, match="canonical"):
        LiveGuardAcquisitionCommand.from_json(
            json.dumps(json.loads(_command(cycle34).canonical_json), indent=2)
        )
    duplicate = receipt.canonical_json[:-1] + ',"production_eligible":false}'
    with pytest.raises(ValueError, match="canonical"):
        LiveGuardAcquisitionReceipt.from_json(duplicate)
