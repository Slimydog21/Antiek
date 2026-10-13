"""Internal replay scopes are lookup keys, never paid or owner identities."""

from __future__ import annotations

import asyncio
import sqlite3
import threading
from dataclasses import replace
from pathlib import Path

import pytest

from interfaces.research.api import note_taking
from roles.note_taker.replay import DurableNoteTakerReplay
from substrate.byot_usage.actions import (
    ApprovedOwnerRoute,
    AttemptProposal,
    OwnerActionDecision,
    OwnerActionRef,
    VerifiedAttemptFacts,
)
from substrate.byot_usage.ledger import ByotUsageLedger, OperationConflict
from substrate.dispatch.base import NormalizedUsage
from substrate.dispatch.router import _emit_dispatch_call
from substrate.event_log import iter_physical_events

INTERNAL_SCOPES = ("__sidecar__", "__complete__")


@pytest.fixture
def private_ledger(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    path = tmp_path / "usage.sqlite3"
    monkeypatch.setenv("ANTIEK_BYOT_USAGE_DB", str(path))
    return ByotUsageLedger(path), path


@pytest.fixture(autouse=True)
def forbid_provider_dispatch(monkeypatch: pytest.MonkeyPatch):
    calls = []

    def forbidden(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("provider dispatch is forbidden in lookup controls")

    monkeypatch.setattr(note_taking, "dispatch", forbidden)
    yield
    assert calls == []


def decision() -> OwnerActionDecision:
    return OwnerActionDecision(
        "owner-a", "action-a", "long_document_wrestling", 100,
        "b" * 64, "d" * 64,
        (ApprovedOwnerRoute("record", "provider", "model", "a" * 64),),
    )


def admit(ledger: ByotUsageLedger, scope: str = "owned-investigation"):
    return ledger.admit_owned_wrestling(
        decision(), investigation_id=scope, document_id="book-a",
        source_reference="source-a", source_digest="c" * 64,
        request_event_id="request-a", delivered_event_id="delivered-a",
        request_payload_digest="e" * 64,
    )


@pytest.mark.parametrize("scope", INTERNAL_SCOPES)
def test_internal_lookup_uses_real_ledger(private_ledger, scope):
    ledger, _ = private_ledger
    assert ledger.owned_wrestling_for_investigation(scope) is None


@pytest.mark.parametrize("scope", INTERNAL_SCOPES)
def test_actual_replay_guard_accepts_unowned_internal_scope(private_ledger, scope):
    assert note_taking._is_owned_investigation(scope) is False


@pytest.mark.parametrize("scope", INTERNAL_SCOPES)
def test_internal_lookup_does_not_skip_the_ownership_query(private_ledger, scope):
    ledger, path = private_ledger
    job = admit(ledger)
    # A retained private journal row proves lookup cannot assume these scopes
    # are unowned. This does not admit a reserved scope as a new paid action.
    with sqlite3.connect(path) as con:
        con.execute(
            "UPDATE byot_owned_wrestling_job SET investigation_id=?"
            " WHERE owner_user_id=? AND action_id=?",
            (scope, job.owner_user_id, job.action_id),
        )
    found = ledger.owned_wrestling_for_investigation(scope)
    assert found == replace(job, investigation_id=scope)
    assert note_taking._is_owned_investigation(scope) is True
    service = note_taking._default_replay_service()
    assert service.catch_up(scope) == []
    assert ledger.action("owner-a", "action-a").reserved_cents == 0


def test_ordinary_owned_lookup_and_contradictory_admission_remain_exact(private_ledger):
    ledger, _ = private_ledger
    job = admit(ledger)
    assert ledger.owned_wrestling_for_investigation(job.investigation_id) == job
    assert note_taking._is_owned_investigation(job.investigation_id) is True
    assert ledger.owned_wrestling_for_investigation("ordinary-unowned") is None
    with pytest.raises(OperationConflict, match="cannot be rebound"):
        ledger.admit_owned_wrestling(
            decision(), investigation_id="changed-investigation", document_id="book-a",
            source_reference="source-a", source_digest="c" * 64,
            request_event_id="request-a", delivered_event_id="delivered-a",
            request_payload_digest="e" * 64,
        )
    assert ledger.owned_wrestling_for_investigation(job.investigation_id) == job


class StringSubclass(str):
    pass


@pytest.mark.parametrize("scope", [
    None, True, 7, 1.5, [], {}, "", "_other", "__sidecar__x",
    "__complete__/child", " __sidecar__", "__complete__ ", "a b",
    "a\x00b", "x" * 257, StringSubclass("__sidecar__"),
])
def test_other_invalid_lookup_identities_remain_refused(private_ledger, scope):
    ledger, _ = private_ledger
    with pytest.raises(ValueError, match="accounting identity is invalid"):
        ledger.owned_wrestling_for_investigation(scope)


@pytest.mark.parametrize("scope", INTERNAL_SCOPES)
@pytest.mark.parametrize("role", [
    "owner", "action", "user_model", "provider", "model", "operation",
    "request", "paid_investigation", "owned_owner", "owned_action",
])
def test_internal_scopes_cannot_become_authority_identities(private_ledger, scope, role):
    ledger, _ = private_ledger
    route = decision().approved_routes[0]
    with pytest.raises(ValueError, match="accounting identity is invalid"):
        if role == "owner":
            replace(decision(), owner_user_id=scope)
        elif role == "action":
            OwnerActionRef("owner-a", scope, 0)
        elif role in ("user_model", "provider", "model"):
            replace(route, **{role + "_id": scope})
        elif role == "operation":
            AttemptProposal(scope, "record", "provider", "model", "a" * 64,
                            "b" * 64, "c" * 64, 1, 0)
        elif role == "request":
            ledger.owned_wrestling_for_request(scope)
        elif role == "paid_investigation":
            admit(ledger, scope)
        elif role == "owned_owner":
            ledger.owned_wrestling_job(scope, "action-a")
        else:
            ledger.owned_wrestling_job("owner-a", scope)
    assert ledger.action("owner-a", "action-a") is None


@pytest.mark.parametrize("scope", INTERNAL_SCOPES)
def test_internal_scope_cannot_be_a_provider_settlement_event(scope):
    with pytest.raises(ValueError, match="accounting identity is invalid"):
        VerifiedAttemptFacts("provider", "model", scope, "a" * 64, "b" * 64, 1)


@pytest.mark.parametrize("scope", INTERNAL_SCOPES)
def test_real_lookup_failure_is_not_reported_as_unowned(private_ledger, scope):
    _, path = private_ledger
    with sqlite3.connect(path) as con:
        con.execute(
            "ALTER TABLE byot_owned_wrestling_job"
            " RENAME COLUMN investigation_id TO unavailable_investigation_id"
        )
    with pytest.raises(sqlite3.OperationalError):
        note_taking._is_owned_investigation(scope)
    with pytest.raises(sqlite3.OperationalError):
        note_taking._default_replay_service().catch_up(scope)


def emit_cost_event(scope: str) -> str:
    # Exercise the existing event emitter, not a provider or a charge receipt.
    event_id = _emit_dispatch_call(
        investigation_id=scope, parent_event_id=None, role="autocomplete",
        tier="flash", provider="unit-provider", model="unit-model",
        usage=NormalizedUsage(input_tokens=17, output_tokens=11), cost_usd=0.125,
        latency_ms=3, verification_required=False, fallback_chain_index=0,
        prompt_hash="a" * 64, finish_reason="stop", context_pack_event_id=None,
    )
    assert event_id is not None
    return event_id


@pytest.mark.parametrize("scope", INTERNAL_SCOPES)
def test_dispatch_cost_fields_survive_actual_internal_replay(
    private_ledger, tmp_path, monkeypatch, scope,
):
    events = tmp_path / "events"
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(events))
    event_id = emit_cost_event(scope)
    before = list(iter_physical_events(scope, events_dir=str(events)))
    service = note_taking._default_replay_service(events_dir=str(events))
    assert service.catch_up(scope) == []
    after = list(iter_physical_events(scope, events_dir=str(events)))
    assert after == before
    assert len(after) == 1 and after[0]["event_id"] == event_id
    assert after[0]["action_type"] == "dispatch.call"
    assert after[0]["payload"]["input_tokens"] == 17
    assert after[0]["payload"]["output_tokens"] == 11
    assert after[0]["payload"]["cost_usd"] == 0.125


def test_actual_recovery_processes_internal_streams_and_excludes_owned_work(
    private_ledger, tmp_path, monkeypatch,
):
    ledger, _ = private_ledger
    owned = admit(ledger)
    events = tmp_path / "events"
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(events))
    monkeypatch.setenv("ANTIEK_NOTE_TAKER_REPLAY_LOCK_YIELD_S", "0")
    for scope in (*INTERNAL_SCOPES, owned.investigation_id):
        emit_cost_event(scope)
    processed = []
    stop = threading.Event()
    original = DurableNoteTakerReplay.catch_up
    state = {}
    original_wait = stop.wait

    def observed(self, investigation_id):
        result = original(self, investigation_id)
        processed.append(investigation_id)
        return result

    def stop_after_completed_pass(timeout=None):
        if state.get("status") == "current":
            stop.set()
        return original_wait(timeout)

    monkeypatch.setattr(DurableNoteTakerReplay, "catch_up", observed)
    monkeypatch.setattr(stop, "wait", stop_after_completed_pass)
    service = note_taking._default_replay_service(events_dir=str(events))
    thread = note_taking.start_replay_recovery(
        db_path=service.db_path, events_dir=str(events), stop_event=stop,
        poll_interval_s=0.01, state=state,
    )
    try:
        thread.join(5)
    finally:
        stop.set()
        thread.join(5)
    assert not thread.is_alive()
    assert sorted(processed) == sorted(INTERNAL_SCOPES)
    assert state["status"] == "current" and state["failures"] == 0
    assert ledger.owned_wrestling_for_investigation(owned.investigation_id) == owned


@pytest.mark.parametrize("scope", INTERNAL_SCOPES)
def test_live_subscriber_retains_unknown_lookup_refusal(private_ledger, monkeypatch, scope):
    _, path = private_ledger
    with sqlite3.connect(path) as con:
        con.execute(
            "ALTER TABLE byot_owned_wrestling_job"
            " RENAME COLUMN investigation_id TO unavailable_investigation_id"
        )
    # The real subscriber refuses a failed authority read before replay.
    from types import SimpleNamespace

    service = note_taking._default_replay_service()
    attempted = []

    def forbidden_replay(investigation_id):
        attempted.append(investigation_id)
        raise AssertionError("unknown ownership must not reach replay")

    monkeypatch.setattr(service, "catch_up", forbidden_replay)
    event = SimpleNamespace(
        role="grounder", action_type="claim.grounding_check_passed",
        policy_id=None, investigation_id=scope,
    )
    handler = note_taking.make_note_taker_handler(None, replay_service=service)
    asyncio.run(handler(event))
    assert attempted == []
