from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from orchestration.rlm.prime_accounting import drain_owner_attempt_projections
from orchestration.rlm.prime_authority import (
    PrimeAuthorizationRequest,
    PrimeLedgerCorrupt,
    PrimeReplayMismatch,
    PrimeUsage,
)
from orchestration.rlm.prime_ledger import PrimeLedger


def _request(number: int) -> PrimeAuthorizationRequest:
    return PrimeAuthorizationRequest(
        owner_id="legacy-owner",
        payer_id="legacy-payer",
        session_id="legacy-session",
        request_id=f"legacy-{number}",
        idempotency_key=f"legacy-idem-{number}",
        workflow="repl",
        prompt_digest=f"{number:064x}",
        provider="anthropic",
        credential_id="legacy-credential",
        credential_fingerprint="a" * 64,
        credential_env_name="ANTHROPIC_API_KEY",
        model="legacy-model",
        prime_version="1.2.3",
        max_cost_micro_usd=100_000,
        issued_at_ms=100,
        expires_at_ms=1_000,
        nonce=f"legacy-nonce-{number}",
    )


def _snapshot(path: Path) -> tuple[list[tuple[object, ...]], list[tuple[object, ...]]]:
    with sqlite3.connect(path) as connection:
        authorizations = connection.execute(
            "SELECT * FROM authorizations ORDER BY request_id"
        ).fetchall()
        events = connection.execute("SELECT * FROM events ORDER BY sequence").fetchall()
    return authorizations, events


def test_v2_migration_keeps_legacy_facts_and_permissions(tmp_path: Path) -> None:
    path = tmp_path / "prime.sqlite3"
    old = PrimeLedger(path)
    old.authorize(_request(1), now_ms=200)
    old.mark_started("legacy-1", now_ms=210)
    old.observe_usage(
        "legacy-1", PrimeUsage("anthropic", "legacy-model", "1.2.3", 5, 2, 15_000, 300),
        now_ms=310,
    )
    old.succeed("legacy-1", now_ms=320)
    old.authorize(_request(2), now_ms=200)
    old.mark_started("legacy-2", now_ms=210)
    old.mark_unknown("legacy-2", now_ms=220)
    with sqlite3.connect(path) as connection:
        connection.execute("DROP TABLE owner_attempt_projection")
        connection.execute("PRAGMA user_version=2")
    before = _snapshot(path)
    assert path.stat().st_mode & 0o777 == 0o600

    migrated = PrimeLedger(path)
    assert _snapshot(path) == before
    assert migrated.receipt("legacy-1").charged_micro_usd == 15_000
    assert migrated.receipt("legacy-2").held_micro_usd == 100_000
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 3
        assert connection.execute("SELECT COUNT(*) FROM owner_attempt_projection").fetchone()[0] == 0
    assert path.stat().st_mode & 0o777 == 0o600


def test_future_prime_version_refuses_without_rewriting_file(tmp_path: Path) -> None:
    path = tmp_path / "prime.sqlite3"
    PrimeLedger(path)
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA user_version=999")
    before = path.read_bytes()
    with pytest.raises(PrimeLedgerCorrupt, match="unsupported"):
        PrimeLedger(path)
    assert path.read_bytes() == before


def _event(*, sequence: int = 1, request_digest: str = "b" * 64):
    from substrate.byot_usage.actions import OwnerAttemptEvent

    facts = {
        "journal_id": "f" * 32,
        "sequence": sequence,
        "owner_user_id": "owner-1",
        "action_id": "action-1",
        "operation_id": "attempt-1",
        "user_model_id": "owner-model-1",
        "provider_id": "anthropic",
        "model_id": "claude-example",
        "authority_digest": "a" * 64,
        "request_digest": request_digest,
        "evidence_sha256": "c" * 64,
        "provider_attempt_event_id": "provider-event-1",
        "cost_micro_usd": 12_000,
        "actual_cents": 2,
        "occurred_at": "2026-10-05T00:00:00+00:00",
    }
    payload = json.dumps(
        {**facts, "schema": "byot-owner-attempt-settled-v1", "event_kind": "settled"},
        sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    )
    return OwnerAttemptEvent(
        **facts, digest=hashlib.sha256(payload.encode("utf-8")).hexdigest()
    )


def test_projection_replays_exact_event_and_refuses_changed_facts(tmp_path: Path) -> None:
    path = tmp_path / "prime.sqlite3"
    ledger = PrimeLedger(path)
    event = _event()
    receipt = ledger.project_owner_attempt(event, now_ms=500)
    assert ledger.project_owner_attempt(event, now_ms=900) == receipt
    assert PrimeLedger(path).owner_attempt_projection(event.journal_id, event.sequence) == receipt
    assert ledger.owner_action_projections("owner-1", "action-1") == (receipt,)
    with pytest.raises(PrimeReplayMismatch):
        ledger.project_owner_attempt(_event(request_digest="d" * 64), now_ms=900)
    with pytest.raises(PrimeReplayMismatch):
        ledger.project_owner_attempt(_event(sequence=2), now_ms=900)
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM authorizations").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM owner_attempt_projection").fetchone()[0] == 1


def test_outbox_drain_replays_after_prime_commit_before_byot_ack(tmp_path: Path) -> None:
    from substrate.byot_usage.actions import (
        ApprovedOwnerRoute,
        AttemptProposal,
        FinalSendFacts,
        OwnerActionDecision,
        VerifiedAttemptFacts,
    )
    from substrate.byot_usage.ledger import ByotUsageLedger

    byot_path = tmp_path / "byot.sqlite3"
    prime_path = tmp_path / "prime.sqlite3"
    byot = ByotUsageLedger(byot_path)
    prime = PrimeLedger(prime_path)
    byot.begin_action(OwnerActionDecision(
        "owner", "action", "long_document_wrestling", 100,
        "b" * 64, "d" * 64,
        (ApprovedOwnerRoute("record", "provider", "model", "a" * 64),),
    ))
    byot.allocate_action_attempt("owner", "action", AttemptProposal(
        "attempt", "record", "provider", "model", "a" * 64,
        "c" * 64, "e" * 64, 30, 0,
    ))
    assert byot.claim_action_attempt("owner", "attempt", FinalSendFacts(
        "f" * 64, "c" * 64, "a" * 64, "e" * 64,
        "b" * 64, "1" * 64, 0,
    )).won
    byot.record_action_attempt_result("owner", "attempt", VerifiedAttemptFacts(
        "provider", "model", "provider-event", "2" * 64, "f" * 64, 100_000,
    ))
    assert byot.settle_action_attempt("owner", "attempt").operation.actual_cents == 10
    (event,) = byot.pending_projection_events()
    assert byot.key_usage("record", "owner").used_cents == 10

    # Simulate a process loss after Prime commits but before BYOT acknowledges.
    receipt = prime.project_owner_attempt(event)
    reopened_byot = ByotUsageLedger(byot_path)
    reopened_prime = PrimeLedger(prime_path)
    assert reopened_byot.pending_projection_events() == (event,)
    assert drain_owner_attempt_projections(reopened_byot, reopened_prime) == (receipt,)
    assert drain_owner_attempt_projections(reopened_byot, reopened_prime) == ()
    assert reopened_byot.pending_projection_events() == ()
    assert reopened_byot.key_usage("record", "owner").used_cents == 10
    assert reopened_byot.operation("owner", "attempt").state == "settled"
    with sqlite3.connect(prime_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM owner_attempt_projection").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM authorizations").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0
