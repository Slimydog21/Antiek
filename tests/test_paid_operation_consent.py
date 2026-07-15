from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from substrate.paid_operations import (
    ConsentAlreadyIssued,
    ConsentConflict,
    ConsentKeyring,
    OperationConflict,
    PaidOperationConsentService,
    PaidOperationStore,
    Subject,
    token_hash,
)
from tests.test_paid_operation_store import HASH_A, collective_payload


def _subject() -> Subject:
    return Subject(owner_user_id="owner-1", account_id="acct-1")


def _service(tmp_path: Path, *, now: int = 1_100) -> tuple[PaidOperationStore, PaidOperationConsentService]:
    store = PaidOperationStore(tmp_path / "authority.sqlite3")
    keyring = ConsentKeyring(active_key_id="key-1", keys={"key-1": b"k" * 32})
    service = PaidOperationConsentService(
        store,
        keyring,
        clock_ms=lambda: now,
        nonce_factory=lambda: b"n" * 32,
        ttl_ms=500,
    )
    return store, service


def test_issue_returns_bearer_once_and_persists_only_hash(tmp_path: Path) -> None:
    store, service = _service(tmp_path)
    store.create_or_replay(_subject(), "op-1", "collective_interrogation_v1", collective_payload())

    issued = service.issue(_subject(), "op-1")
    assert issued.cache_control == "no-store, private"
    assert issued.token
    snapshot = store.get_owned(_subject(), "op-1")
    assert snapshot is not None
    assert snapshot.state == "consent_issued"
    assert snapshot.consent_token_hash == token_hash(issued.token)
    assert issued.token not in snapshot.canonical_intent_json

    with sqlite3.connect(tmp_path / "authority.sqlite3") as con:
        dumped = "\n".join(str(row) for row in con.iterdump())
    assert issued.token not in dumped

    with pytest.raises(ConsentAlreadyIssued) as exc:
        service.issue(_subject(), "op-1")
    assert exc.value.snapshot.state == "consent_issued"
    assert not hasattr(exc.value.snapshot, "token")


def test_claim_rejects_wrong_owner_expired_wrong_key_and_drift(tmp_path: Path) -> None:
    store, service = _service(tmp_path)
    store.create_or_replay(_subject(), "op-1", "collective_interrogation_v1", collective_payload())
    token = service.issue(_subject(), "op-1").token

    with pytest.raises(OperationConflict):
        service.claim(Subject(owner_user_id="owner-2", account_id="acct-1"), "op-1", token=token, options={})

    expired = PaidOperationConsentService(
        store,
        ConsentKeyring(active_key_id="key-1", keys={"key-1": b"k" * 32}),
        clock_ms=lambda: 1_700,
    )
    with pytest.raises(ConsentConflict):
        expired.claim(_subject(), "op-1", token=token, options={})

    wrong_key = PaidOperationConsentService(
        store,
        ConsentKeyring(active_key_id="key-1", keys={"key-1": b"x" * 32}),
        clock_ms=lambda: 1_200,
    )
    with pytest.raises(ConsentConflict):
        wrong_key.claim(_subject(), "op-1", token=token, options={})

    changed = collective_payload()
    changed["ceiling_cents"] = 21
    other = Subject(owner_user_id="owner-2", account_id="acct-1")
    store.create_or_replay(other, "op-1", "collective_interrogation_v1", changed)
    with pytest.raises(OperationConflict):
        service.claim(other, "op-1", token=token, options={})


def test_replay_after_claim_returns_existing_queue_without_requiring_new_bearer(tmp_path: Path) -> None:
    store, service = _service(tmp_path, now=1_100)
    store.create_or_replay(_subject(), "op-1", "collective_interrogation_v1", collective_payload())
    token = service.issue(_subject(), "op-1").token
    first = service.claim(_subject(), "op-1", token=token, options={"mode": "approved"})
    assert first.snapshot.state == "queued"
    second = service.claim(_subject(), "op-1", token=None, options={"mode": "approved"})
    assert second.queue == first.queue
    exact = service.claim(_subject(), "op-1", token=token, options={"mode": "approved"})
    assert exact.queue == first.queue
    with pytest.raises(ConsentConflict):
        service.claim(_subject(), "op-1", token=token, options={"mode": "changed"})
    with pytest.raises(ConsentAlreadyIssued):
        service.issue(_subject(), "op-1")


def test_options_reject_unstable_material(tmp_path: Path) -> None:
    store, service = _service(tmp_path)
    store.create_or_replay(_subject(), "op-1", "collective_interrogation_v1", collective_payload())
    token = service.issue(_subject(), "op-1").token
    with pytest.raises(ValueError, match="float"):
        service.claim(_subject(), "op-1", token=token, options={"temperature": 0.1})


def test_token_canary_absent_from_exception_text(tmp_path: Path) -> None:
    store, service = _service(tmp_path)
    store.create_or_replay(_subject(), "op-1", "collective_interrogation_v1", collective_payload())
    token = service.issue(_subject(), "op-1").token
    tampered = token[:-1] + ("a" if token[-1] != "a" else "b")
    with pytest.raises(ConsentConflict) as exc:
        service.claim(_subject(), "op-1", token=tampered, options={})
    assert token not in str(exc.value)
    assert tampered not in str(exc.value)
    assert HASH_A not in str(exc.value)


def test_token_canary_cannot_enter_durable_queue_options(tmp_path: Path) -> None:
    store, service = _service(tmp_path)
    store.create_or_replay(_subject(), "op-1", "collective_interrogation_v1", collective_payload())
    token = service.issue(_subject(), "op-1").token
    with pytest.raises(ConsentConflict):
        service.claim(_subject(), "op-1", token=token, options={"nested": [f"prefix-{token}-suffix"]})
    with sqlite3.connect(tmp_path / "authority.sqlite3") as con:
        dumped = "\n".join(str(row) for row in con.iterdump())
    assert token not in dumped


def test_signing_key_canary_cannot_enter_durable_queue_options(tmp_path: Path) -> None:
    store, service = _service(tmp_path)
    store.create_or_replay(_subject(), "op-1", "collective_interrogation_v1", collective_payload())
    token = service.issue(_subject(), "op-1").token
    signing_canary = "k" * 32
    with pytest.raises(ConsentConflict):
        service.claim(_subject(), "op-1", token=token, options={"canary": signing_canary})
    with sqlite3.connect(tmp_path / "authority.sqlite3") as con:
        dumped = "\n".join(str(row) for row in con.iterdump())
    assert signing_canary not in dumped
