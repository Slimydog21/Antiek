from __future__ import annotations

from pathlib import Path

from substrate.paid_operations import (
    ConsentKeyring,
    FakePaidOperationProvider,
    PaidOperationConsentService,
    PaidOperationLedger,
    PaidOperationStore,
    PaidOperationWorker,
    ProviderCapabilityAttestation,
    ProviderResult,
    Subject,
)
from substrate.paid_operations.adapters import (
    collective_interrogation_enablement,
    midnight_oil_enablement,
)
from tests.test_paid_operation_contracts import midnight_payload
from tests.test_paid_operation_store import collective_payload


class Clock:
    value = 1_200

    def __call__(self) -> int:
        return self.value


def _cap(kind: str) -> ProviderCapabilityAttestation:
    return ProviderCapabilityAttestation(
        provider_id="provider-1",
        endpoint_id="route-1",
        operation_kind=kind,
        api_version="fake-v1",
        retention_window_ms=86_400_000,
        documentation_url="https://example.invalid/fake",
        request_body_scope="intent+step",
        duplicate_same_body_behavior="same logical result",
        duplicate_changed_body_behavior="conflict",
        billing_semantics="one charge per idempotency key",
        live_smoke_receipt_hash="a" * 64,
        expires_at_ms=9_999_999,
        enabled=True,
        documentation_hash="b" * 64,
        behavior_evidence_hash="c" * 64,
        live_smoke_operator_id="operator-1",
        live_smoke_authorization_hash="d" * 64,
    )


def _queue(
    store: PaidOperationStore,
    service: PaidOperationConsentService,
    subject: Subject,
    operation_id: str,
    kind: str,
    payload: dict[str, object],
) -> None:
    store.create_or_replay(subject, operation_id, kind, payload)
    token = service.issue(subject, operation_id).token
    service.claim(subject, operation_id, token=token, options={"attempt": 1})


def test_fake_provider_e2e_for_both_profiles_and_live_adapters_remain_disabled(tmp_path: Path) -> None:
    db = tmp_path / "authority.sqlite3"
    clock = Clock()
    subject = Subject("owner-1", "acct-1")
    store = PaidOperationStore(db)
    service = PaidOperationConsentService(
        store,
        ConsentKeyring(active_key_id="key-1", keys={"key-1": b"k" * 32}),
        clock_ms=lambda: 1_100,
        nonce_factory=lambda: b"n" * 32,
    )
    _queue(store, service, subject, "op-1", "collective_interrogation_v1", collective_payload())
    midnight = midnight_payload()
    _queue(store, service, subject, "op-2", "midnight_oil_v1", midnight)
    PaidOperationLedger(db).set_account_budget("acct-1", "period-1", 200)

    collective_provider = FakePaidOperationProvider(
        _cap("collective_interrogation_v1"),
        results={"dispatch": ProviderResult({"answer": "collective"}, "receipt-coll", 7)},
    )
    midnight_provider = FakePaidOperationProvider(
        _cap("midnight_oil_v1"),
        results={"dispatch": ProviderResult({"answer": "midnight"}, "receipt-mo", 11)},
    )

    first = PaidOperationWorker(db, collective_provider, clock_ms=clock).execute_one("worker-1", lease_ms=500)
    assert first is not None
    second = PaidOperationWorker(db, midnight_provider, clock_ms=clock).execute_one("worker-2", lease_ms=500)
    assert second is not None

    assert first.state == second.state == "complete"
    assert first.idempotency_key != second.idempotency_key
    budget = PaidOperationLedger(db).get_budget("acct-1")
    assert budget is not None
    assert budget.reserved_cents == 0
    assert budget.settled_cents == 18
    assert collective_interrogation_enablement().enabled is False
    assert midnight_oil_enablement().enabled is False
