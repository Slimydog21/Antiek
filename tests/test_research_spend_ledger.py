"""Behavioral and durability proofs for the research spend ledger."""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest

from substrate.research_spend import (
    BindingConflict,
    FallbackChainManifest,
    FallbackChainOutcome,
    FallbackRouteManifest,
    FallbackRouteState,
    IdempotencyConflict,
    InvalidTransition,
    LedgerIntegrityError,
    PaidHoldIntent,
    PaidHoldState,
    ResearchSpendLedger,
    RunBinding,
    RunStatus,
    SpendCeilingExceeded,
    ZeroCostIntent,
    ZeroCostState,
    ZeroReplayClass,
)
from substrate.research_spend.ledger import (
    _DDL,
    APPLICATION_ID,
    MAX_ACTUAL_CENTS,
    SCHEMA_VERSION,
    _binding_payload,
    _canonical,
    _sha256,
)

ROOT = Path(__file__).resolve().parents[1]


def _binding(run_id: str = "run-1") -> RunBinding:
    return RunBinding(run_id, "owner-1", "session-1", "plan-sha", 7)


def _paid(key: str = "hold-1") -> PaidHoldIntent:
    return PaidHoldIntent(
        reservation_key=key,
        seam_id="provider-call",
        provider="openai",
        model="research-model",
        operation="deep-research",
        operation_digest=f"operation-{key}",
        projection_digest=f"projection-{key}",
        rate_snapshot="openai:2026-07-13",
        provider_idempotency_key=f"provider-{key}",
    )


def _zero(key: str = "zero-1") -> ZeroCostIntent:
    return ZeroCostIntent(
        attempt_key=key,
        seam_id="local-index",
        operation="index-evidence",
        operation_digest=f"operation-{key}",
        replay_class=ZeroReplayClass.CHECKPOINT_RESUMABLE,
    )


def _fallback_manifest(
    *, chain_id: str = "chain-1", logical_operation_id: str = "logical-1"
) -> FallbackChainManifest:
    routes = tuple(
        FallbackRouteManifest(
            fallback_index=index,
            seam_id="provider-call",
            provider=f"provider-{index}",
            model=f"model-{index}",
            operation="deep-research",
            operation_digest="chain-operation-digest",
            projection_digest=f"projection-{index}",
            rate_snapshot=f"rates-{index}",
            projected_max_cents=100 - index * 10,
            reservation_key=f"reservation-{chain_id}-{index}",
            provider_idempotency_key=f"provider-key-{chain_id}-{index}",
            route_authority_digest=f"authority-{chain_id}-{index}",
        )
        for index in range(2)
    )
    return FallbackChainManifest(
        chain_id=chain_id,
        logical_operation_id=logical_operation_id,
        operation_digest="chain-operation-digest",
        routes=routes,
    )


def _register_manifest(
    ledger: ResearchSpendLedger, manifest: FallbackChainManifest | None = None
) -> FallbackChainManifest:
    value = manifest or _fallback_manifest()
    return ledger.register_fallback_manifest("register-" + value.chain_id, _binding(), value)


def _ledger(tmp_path: Path, *, ceiling: int = 1_000) -> ResearchSpendLedger:
    ledger = ResearchSpendLedger(tmp_path / "research-spend.sqlite3")
    ledger.ensure_schema()
    ledger.create_or_reopen_run("create-run", _binding(), ceiling)
    return ledger


def _dispatch(
    ledger: ResearchSpendLedger,
    *,
    key: str = "hold-1",
    cents: int = 100,
) -> str:
    hold = ledger.reserve_paid(f"reserve-{key}", _binding(), _paid(key), cents)
    ledger.mark_dispatch_possible(f"dispatch-{key}", hold.hold_id)
    return hold.hold_id


def _manifest_hold(route: FallbackRouteManifest) -> PaidHoldIntent:
    return PaidHoldIntent(
        reservation_key=route.reservation_key,
        seam_id=route.seam_id,
        provider=route.provider,
        model=route.model,
        operation=route.operation,
        operation_digest=route.operation_digest,
        projection_digest=route.projection_digest,
        rate_snapshot=route.rate_snapshot,
        provider_idempotency_key=route.provider_idempotency_key,
        route_authority_digest=route.route_authority_digest,
    )


def test_v2_to_v3_fallback_migration_is_atomic(tmp_path: Path) -> None:
    db_path = tmp_path / "research-spend.sqlite3"
    ledger = ResearchSpendLedger(db_path)
    ledger.ensure_schema()
    with sqlite3.connect(db_path) as connection:
        for name in (
            "research_fallback_chains_no_update",
            "research_fallback_chains_no_delete",
            "research_fallback_routes_no_update",
            "research_fallback_routes_no_delete",
        ):
            connection.execute(f"DROP TRIGGER {name}")
        connection.execute("DROP TABLE research_fallback_routes")
        connection.execute("DROP TABLE research_fallback_chains")
        connection.execute("PRAGMA user_version=2")

    def fail(checkpoint: str) -> None:
        if checkpoint == "schema:2:after_migration:2":
            raise RuntimeError("migration crash")

    with pytest.raises(RuntimeError, match="migration crash"):
        ResearchSpendLedger(db_path, failure_injector=fail).ensure_schema()
    with sqlite3.connect(db_path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
        assert connection.execute(
            "SELECT 1 FROM sqlite_master WHERE name='research_fallback_chains'"
        ).fetchone() is None

    ledger.ensure_schema()
    with sqlite3.connect(db_path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 3
        names = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE name LIKE 'research_fallback_%'"
            )
        }
    assert {
        "research_fallback_chains",
        "research_fallback_routes",
        "research_fallback_chains_no_update",
        "research_fallback_chains_no_delete",
        "research_fallback_routes_no_update",
        "research_fallback_routes_no_delete",
        "research_fallback_history_owner_idx",
        "research_fallback_routes_reservation_idx",
    } <= names


def test_fallback_manifest_history_is_private_ordered_and_integrity_checked(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    manifest = _register_manifest(ledger)
    assert _register_manifest(ledger, manifest) == manifest
    assert ledger.fallback_history("other-owner").items == ()

    first, second = manifest.routes
    first_hold = ledger.reserve_paid(
        "reserve-first", _binding(), _manifest_hold(first), first.projected_max_cents
    )
    ledger.mark_dispatch_possible("dispatch-first", first_hold.hold_id)
    ledger.release(
        "release-first",
        first_hold.hold_id,
        {"accepted": False},
        provider_authoritative=True,
    )
    second_hold = ledger.reserve_paid(
        "reserve-second", _binding(), _manifest_hold(second), second.projected_max_cents
    )
    ledger.mark_dispatch_possible("dispatch-second", second_hold.hold_id)
    ledger.settle("settle-second", second_hold.hold_id, 70, {"receipt": "private-body"})

    chain = ledger.fallback_history("owner-1").items[0]
    assert chain.outcome is FallbackChainOutcome.SETTLED
    assert [route.state for route in chain.routes] == [
        FallbackRouteState.RELEASED,
        FallbackRouteState.SETTLED,
    ]
    assert chain.routes[1].settlement_evidence_sha256
    assert "private-body" not in repr(chain)
    assert first.reservation_key not in repr(chain)

    with sqlite3.connect(tmp_path / "research-spend.sqlite3") as connection:
        connection.execute(
            "UPDATE research_spend_holds SET resolution_intent_sha256='bad' WHERE hold_id=?",
            (second_hold.hold_id,),
        )
    with pytest.raises(LedgerIntegrityError, match="settlement receipt"):
        ledger.fallback_history("owner-1")


def test_fallback_history_rejects_impossible_later_attempt(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    second = _register_manifest(ledger).routes[1]
    ledger.reserve_paid(
        "reserve-second", _binding(), _manifest_hold(second), second.projected_max_cents
    )
    with pytest.raises(LedgerIntegrityError, match="order is impossible"):
        ledger.fallback_history("owner-1")


def test_final_cent_race_has_one_winner_across_100_connections(tmp_path: Path) -> None:
    db_path = tmp_path / "research-spend.sqlite3"
    ledger = ResearchSpendLedger(db_path)
    ledger.ensure_schema()
    ledger.create_or_reopen_run("create-run", _binding(), 1)
    barrier = threading.Barrier(100)

    def reserve(worker: int) -> str:
        contender = ResearchSpendLedger(db_path)
        barrier.wait()
        try:
            contender.reserve_paid(
                f"command-{worker}", _binding(), _paid(f"worker-{worker}"), 1
            )
            return "won"
        except SpendCeilingExceeded:
            return "ceiling"

    with ThreadPoolExecutor(max_workers=100) as pool:
        outcomes = list(pool.map(reserve, range(100)))

    assert outcomes.count("won") == 1
    assert outcomes.count("ceiling") == 99
    assert ledger.balance("run-1").held_cents == 1
    assert [event.event_kind for event in ledger.events("run-1")].count("hold_reserved") == 1


def test_exact_headroom_succeeds_and_next_cent_fails(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path, ceiling=500)
    ledger.reserve_paid("reserve-all", _binding(), _paid(), 500)
    with pytest.raises(SpendCeilingExceeded) as error:
        ledger.reserve_paid("reserve-extra", _binding(), _paid("extra"), 1)
    assert error.value.available_cents == 0
    assert ledger.balance("run-1").available_cents == 0


def test_session_balance_lookup_is_owner_scoped(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path, ceiling=500)
    visible = ledger.balance_for_session("owner-1", "session-1")
    assert visible is not None
    assert visible.binding == _binding()
    assert ledger.owner_for_session("session-1") == "owner-1"
    assert ledger.balance_for_session("other-owner", "session-1") is None
    assert ledger.balance_for_session("owner-1", "other-session") is None
    assert ledger.owner_for_session("other-session") is None


@pytest.mark.parametrize(
    "binding",
    [
        replace(_binding(), owner_id="other"),
        replace(_binding(), session_id="other"),
        replace(_binding(), plan_digest="other"),
        replace(_binding(), approval_revision=8),
    ],
)
def test_reservation_rejects_stale_full_run_binding(
    tmp_path: Path, binding: RunBinding
) -> None:
    ledger = _ledger(tmp_path)
    with pytest.raises(BindingConflict):
        ledger.reserve_paid("stale", binding, _paid(), 10)


def test_non_usd_and_invalid_money_never_reach_storage(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="USD-only"):
        replace(_binding(), currency="EUR")
    with pytest.raises(ValueError, match="hard_ceiling"):
        replace(_binding(), mode="stop_limit")
    ledger = _ledger(tmp_path)
    with pytest.raises(ValueError):
        ledger.reserve_paid("zero", _binding(), _paid(), 0)
    with pytest.raises(TypeError):
        ledger.reserve_paid("bool", _binding(), _paid(), True)  # type: ignore[arg-type]


def test_direct_database_constraints_reject_invalid_authority_and_decimals(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path, ceiling=10)
    db_path = tmp_path / "research-spend.sqlite3"
    with sqlite3.connect(db_path) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE research_spend_runs SET held_cents = -1 WHERE run_id = 'run-1'"
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE research_spend_runs SET held_cents = 11 WHERE run_id = 'run-1'"
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE research_spend_runs SET observed_provider_spend_dec = '01' "
                "WHERE run_id = 'run-1'"
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE research_spend_runs SET currency = 'EUR' WHERE run_id = 'run-1'"
            )
    assert ledger.balance("run-1").available_cents == 10


def test_reservation_exact_replay_and_changed_intent_conflict(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    first = ledger.reserve_paid("reserve", _binding(), _paid(), 100)
    assert ledger.reserve_paid("reserve", _binding(), _paid(), 100) == first
    assert ledger.balance("run-1").held_cents == 100
    with pytest.raises(IdempotencyConflict):
        ledger.reserve_paid("reserve", _binding(), replace(_paid(), model="changed"), 100)
    with pytest.raises(IdempotencyConflict):
        ledger.reserve_paid("different-command", _binding(), _paid(), 100)


def test_reserved_hold_survives_restart_but_cannot_settle(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    hold = ledger.reserve_paid("reserve", _binding(), _paid(), 100)
    reopened = ResearchSpendLedger(tmp_path / "research-spend.sqlite3")
    with pytest.raises(InvalidTransition):
        reopened.settle("settle", hold.hold_id, 80, {"receipt": "r-1"})
    assert reopened.recovery_work("run-1")[0].action == "resume_or_release"
    assert reopened.balance("run-1").held_cents == 100


def test_zero_attempt_lookup_by_run_scoped_key_includes_terminal_receipts(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    attempt = ledger.prepare_zero_cost("prepare", _binding(), _zero())
    assert ledger.zero_attempt_for_key("run-1", "zero-1") == attempt
    completed = ledger.complete_zero_cost("complete", attempt.attempt_id, "outcome-sha")
    assert ledger.zero_attempt_for_key("run-1", "zero-1") == completed
    assert ledger.zero_attempt_for_key("run-1", "absent") is None


def test_dispatch_unknown_and_authoritative_release_rules(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    hold_id = _dispatch(ledger)
    ledger.mark_unknown("unknown", hold_id, {"timeout": True})
    with pytest.raises(InvalidTransition):
        ledger.release("release", hold_id, {"operator": "guess"})
    released = ledger.release(
        "release-authoritative",
        hold_id,
        {"provider_lookup": "not_found"},
        provider_authoritative=True,
    )
    assert released.held_cents == 0
    assert ledger.hold(hold_id).state is PaidHoldState.RELEASED
    assert ledger.release(
        "release-authoritative",
        hold_id,
        {"provider_lookup": "not_found"},
        provider_authoritative=True,
    ) == released


def test_settlement_is_exactly_once_and_evidence_bound(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    hold_id = _dispatch(ledger)
    first = ledger.settle("settle", hold_id, 80, {"receipt": "r-1"})
    assert ledger.settle("settle", hold_id, 80, {"receipt": "r-1"}) == first
    assert first.authorized_spent_cents == 80
    assert first.observed_provider_spend_cents == 80
    with pytest.raises(IdempotencyConflict):
        ledger.settle("settle", hold_id, 81, {"receipt": "r-1"})
    with pytest.raises(InvalidTransition):
        ledger.settle("settle-again", hold_id, 80, {"receipt": "r-1"})


def test_above_hold_breach_freezes_work_and_preserves_ambiguous_spend(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path, ceiling=300)
    breached_id = _dispatch(ledger, key="breached", cents=100)
    ambiguous_id = _dispatch(ledger, key="ambiguous", cents=100)
    reserved = ledger.reserve_paid("reserve-unsent", _binding(), _paid("unsent"), 100)

    breached = ledger.settle("settle-breach", breached_id, 250, {"receipt": "r-1"})
    assert breached.authorized_spent_cents == 100
    assert breached.observed_provider_spend_cents == 250
    assert breached.held_cents == 200
    assert breached.status is RunStatus.CEILING_BREACHED
    assert breached.ceiling_breached
    with pytest.raises(InvalidTransition):
        ledger.reserve_paid("frozen", _binding(), _paid("frozen"), 1)
    with pytest.raises(InvalidTransition):
        ledger.mark_dispatch_possible("dispatch-unsent", reserved.hold_id)

    closed = ledger.close_execution("close", "run-1", "operator stop")
    assert closed.status is RunStatus.CLOSED_UNRESOLVED
    assert closed.held_cents == 100
    assert ledger.hold(reserved.hold_id).state is PaidHoldState.RELEASED
    reconciled = ledger.settle(
        "settle-ambiguous", ambiguous_id, 70, {"receipt": "r-2"}
    )
    assert reconciled.status is RunStatus.CLOSED_RECONCILED
    assert reconciled.ceiling_breached
    assert reconciled.authorized_spent_cents == 170
    assert reconciled.observed_provider_spend_cents == 320


def test_observed_provider_evidence_accumulates_beyond_sqlite_int64(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path, ceiling=2)
    first = _dispatch(ledger, key="first", cents=1)
    second = _dispatch(ledger, key="second", cents=1)
    ledger.settle("settle-first", first, MAX_ACTUAL_CENTS, {"receipt": "one"})
    ledger.settle("settle-second", second, MAX_ACTUAL_CENTS, {"receipt": "two"})
    run = ledger.balance("run-1")
    assert run.observed_provider_spend_cents == 2 * MAX_ACTUAL_CENTS
    assert run.authorized_spent_cents == 2


def test_zero_cost_work_is_replayable_without_balance_mutation(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    prepared = ledger.prepare_zero_cost("prepare", _binding(), _zero())
    assert ledger.prepare_zero_cost("prepare", _binding(), _zero()) == prepared
    with pytest.raises(IdempotencyConflict):
        ledger.prepare_zero_cost(
            "prepare", _binding(), replace(_zero(), operation_digest="changed")
        )
    completed = ledger.complete_zero_cost("complete", prepared.attempt_id, "output-sha")
    assert completed.state is ZeroCostState.COMPLETED
    assert ledger.complete_zero_cost(
        "complete", prepared.attempt_id, "output-sha"
    ) == completed
    with pytest.raises(InvalidTransition):
        ledger.fail_zero_cost("fail-late", prepared.attempt_id, "failure-sha")
    run = ledger.balance("run-1")
    assert (run.authorized_spent_cents, run.held_cents, run.observed_provider_spend_cents) == (
        0,
        0,
        0,
    )


def test_close_releases_only_provably_unsent_and_fails_prepared_local_work(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    reserved = ledger.reserve_paid("reserve", _binding(), _paid(), 100)
    ambiguous = _dispatch(ledger, key="ambiguous", cents=100)
    local = ledger.prepare_zero_cost("prepare", _binding(), _zero())
    closed = ledger.close_execution("close", "run-1", "time expired")
    assert closed.status is RunStatus.CLOSED_UNRESOLVED
    assert closed.held_cents == 100
    assert ledger.hold(reserved.hold_id).state is PaidHoldState.RELEASED
    assert ledger.hold(ambiguous).state is PaidHoldState.DISPATCH_POSSIBLE
    assert ledger.zero_attempt(local.attempt_id).state is ZeroCostState.FAILED
    assert ledger.close_execution("close", "run-1", "time expired") == closed
    assert ledger.reserve_paid("reserve", _binding(), _paid(), 100).state is PaidHoldState.RELEASED
    assert ledger.prepare_zero_cost("prepare", _binding(), _zero()).state is ZeroCostState.FAILED


def test_close_events_replay_sequential_held_balances(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path, ceiling=300)
    ledger.reserve_paid("reserve-one", _binding(), _paid("one"), 100)
    ledger.reserve_paid("reserve-two", _binding(), _paid("two"), 200)
    ledger.close_execution("close", "run-1", "done")
    releases = [
        event
        for event in ledger.events("run-1")
        if event.event_kind == "hold_released_on_close"
    ]
    assert sorted(event.held_delta_cents for event in releases) == [-200, -100]
    running = 300
    for event in releases:
        running += event.held_delta_cents
        assert event.post_held_cents == running
    assert running == 0


def test_close_and_reserve_race_never_leaves_work_after_closed_state(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path, ceiling=1)
    barrier = threading.Barrier(2)
    outcomes: list[str] = []

    def reserve() -> None:
        barrier.wait()
        try:
            ResearchSpendLedger(tmp_path / "research-spend.sqlite3").reserve_paid(
                "racing-reserve", _binding(), _paid("race"), 1
            )
            outcomes.append("reserved")
        except InvalidTransition:
            outcomes.append("closed")

    thread = threading.Thread(target=reserve)
    thread.start()
    barrier.wait()
    ledger.close_execution("close", "run-1", "race")
    thread.join()
    assert outcomes in (["reserved"], ["closed"])
    run = ledger.balance("run-1")
    assert run.status is RunStatus.CLOSED_RECONCILED
    assert run.held_cents == 0
    assert ledger.recovery_work("run-1") == ()


def _run_crashing_child(db_path: Path, target: str, operation: str) -> int:
    source = f"""
import os
from substrate.research_spend import PaidHoldIntent, ResearchSpendLedger, RunBinding
db = {str(db_path)!r}
target = {target!r}
def fail(name):
    if name == target:
        os._exit(71)
ledger = ResearchSpendLedger(db, failure_injector=fail)
binding = RunBinding('run-1', 'owner-1', 'session-1', 'plan-sha', 7)
intent = PaidHoldIntent('crash-hold', 'provider-call', 'openai', 'research-model', 'deep-research', 'operation-crash-hold', 'projection-crash-hold', 'openai:2026-07-13', 'provider-crash-hold')
if {operation!r} == 'reserve':
    ledger.reserve_paid('crash-command', binding, intent, 100)
else:
    ledger.settle('crash-settle', {operation!r}, 80, {{'receipt': 'crash'}})
"""
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT)
    return subprocess.run(
        [sys.executable, "-c", source],
        cwd=ROOT,
        env=environment,
        check=False,
    ).returncode


def _run_other_crashing_child(
    db_path: Path, target: str, operation: str, entity_id: str
) -> int:
    source = f"""
import os
from substrate.research_spend import ResearchSpendLedger
target = {target!r}
def fail(name):
    if name == target:
        os._exit(71)
ledger = ResearchSpendLedger({str(db_path)!r}, failure_injector=fail)
operation = {operation!r}
entity_id = {entity_id!r}
if operation == 'dispatch':
    ledger.mark_dispatch_possible('crash-dispatch', entity_id)
elif operation == 'release':
    ledger.release('crash-release', entity_id, {{'proof': 'unsent'}})
elif operation == 'zero':
    ledger.complete_zero_cost('crash-zero', entity_id, 'output-sha')
else:
    ledger.close_execution('crash-close', 'run-1', 'crash test')
"""
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT)
    return subprocess.run(
        [sys.executable, "-c", source], cwd=ROOT, env=environment, check=False
    ).returncode


@pytest.mark.parametrize(
    "checkpoint",
    [
        "reserve_paid:after_authority",
        "reserve_paid:after_hold",
        "reserve_paid:after_command",
        "reserve_paid:after_event",
        "reserve_paid:before_commit",
    ],
)
def test_reservation_process_crash_before_commit_rolls_back_every_boundary(
    tmp_path: Path, checkpoint: str
) -> None:
    ledger = _ledger(tmp_path)
    baseline_events = ledger.events("run-1")
    assert _run_crashing_child(tmp_path / "research-spend.sqlite3", checkpoint, "reserve") == 71
    assert ledger.balance("run-1").held_cents == 0
    assert ledger.events("run-1") == baseline_events
    recovered = ledger.reserve_paid("crash-command", _binding(), _paid("crash-hold"), 100)
    assert recovered.state is PaidHoldState.RESERVED


def test_reservation_process_crash_after_commit_is_exactly_replayable(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    assert _run_crashing_child(
        tmp_path / "research-spend.sqlite3", "reserve_paid:after_commit", "reserve"
    ) == 71
    first = ledger.reserve_paid("crash-command", _binding(), _paid("crash-hold"), 100)
    assert first.state is PaidHoldState.RESERVED
    assert ledger.balance("run-1").held_cents == 100
    assert [event.event_kind for event in ledger.events("run-1")] == [
        "run_created",
        "hold_reserved",
    ]


@pytest.mark.parametrize(
    "checkpoint",
    [
        "settle:after_run_update",
        "settle:after_hold_update",
        "settle:after_command",
        "settle:after_event",
        "settle:before_commit",
    ],
)
def test_settlement_process_crash_before_commit_preserves_ambiguous_hold(
    tmp_path: Path, checkpoint: str
) -> None:
    ledger = _ledger(tmp_path)
    hold_id = _dispatch(ledger, key="crash-hold", cents=100)
    assert _run_crashing_child(
        tmp_path / "research-spend.sqlite3", checkpoint, hold_id
    ) == 71
    assert ledger.hold(hold_id).state is PaidHoldState.DISPATCH_POSSIBLE
    run = ledger.balance("run-1")
    assert (run.authorized_spent_cents, run.observed_provider_spend_cents, run.held_cents) == (
        0,
        0,
        100,
    )


def test_settlement_process_crash_after_commit_does_not_double_charge(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    hold_id = _dispatch(ledger, key="crash-hold", cents=100)
    assert _run_crashing_child(
        tmp_path / "research-spend.sqlite3", "settle:after_commit", hold_id
    ) == 71
    first = ledger.settle("crash-settle", hold_id, 80, {"receipt": "crash"})
    assert first.authorized_spent_cents == 80
    assert first.observed_provider_spend_cents == 80


@pytest.mark.parametrize(
    ("operation", "checkpoint"),
    [
        ("dispatch", "mark_dispatch_possible:after_command"),
        ("dispatch", "mark_dispatch_possible:after_event"),
        ("dispatch", "mark_dispatch_possible:before_commit"),
        ("release", "release:after_state_updates"),
        ("release", "release:after_command"),
        ("release", "release:after_event"),
        ("release", "release:before_commit"),
        ("zero", "complete_zero:after_state_update"),
        ("zero", "complete_zero:after_command"),
        ("zero", "complete_zero:after_event"),
        ("zero", "complete_zero:before_commit"),
        ("close", "close_execution:after_state_updates"),
        ("close", "close_execution:after_command"),
        ("close", "close_execution:after_events"),
        ("close", "close_execution:before_commit"),
    ],
)
def test_other_process_crashes_before_commit_roll_back_atomically(
    tmp_path: Path, operation: str, checkpoint: str
) -> None:
    case_path = tmp_path / operation / checkpoint.replace(":", "-")
    case_path.mkdir(parents=True)
    ledger = _ledger(case_path)
    if operation in ("dispatch", "release", "close"):
        entity_id = ledger.reserve_paid("reserve", _binding(), _paid(), 100).hold_id
    else:
        entity_id = ledger.prepare_zero_cost("prepare", _binding(), _zero()).attempt_id
    before = ledger.balance("run-1")
    assert _run_other_crashing_child(
        case_path / "research-spend.sqlite3", checkpoint, operation, entity_id
    ) == 71
    assert ledger.balance("run-1") == before
    if operation == "zero":
        assert ledger.zero_attempt(entity_id).state is ZeroCostState.PREPARED
    else:
        assert ledger.hold(entity_id).state is PaidHoldState.RESERVED


@pytest.mark.parametrize("operation", ["dispatch", "release", "zero", "close"])
def test_other_process_crashes_after_commit_are_exactly_replayable(
    tmp_path: Path, operation: str
) -> None:
    case_path = tmp_path / operation
    case_path.mkdir()
    ledger = _ledger(case_path)
    if operation in ("dispatch", "release", "close"):
        entity_id = ledger.reserve_paid("reserve", _binding(), _paid(), 100).hold_id
    else:
        entity_id = ledger.prepare_zero_cost("prepare", _binding(), _zero()).attempt_id
    checkpoint = {
        "dispatch": "mark_dispatch_possible:after_commit",
        "release": "release:after_commit",
        "zero": "complete_zero:after_commit",
        "close": "close_execution:after_commit",
    }[operation]
    assert _run_other_crashing_child(
        case_path / "research-spend.sqlite3", checkpoint, operation, entity_id
    ) == 71
    if operation == "dispatch":
        assert ledger.mark_dispatch_possible("crash-dispatch", entity_id).state is (
            PaidHoldState.DISPATCH_POSSIBLE
        )
    elif operation == "release":
        ledger.release("crash-release", entity_id, {"proof": "unsent"})
        assert ledger.balance("run-1").held_cents == 0
    elif operation == "zero":
        assert ledger.complete_zero_cost("crash-zero", entity_id, "output-sha").state is (
            ZeroCostState.COMPLETED
        )
    else:
        assert ledger.close_execution("crash-close", "run-1", "crash test").status is (
            RunStatus.CLOSED_RECONCILED
        )


@pytest.mark.parametrize("statement_index", range(1, len(_DDL) + 1))
def test_schema_migration_failure_rolls_back_atomically(
    tmp_path: Path, statement_index: int
) -> None:
    db_path = tmp_path / f"migration-{statement_index}.sqlite3"

    def fail(name: str) -> None:
        if name == f"schema:after_statement:{statement_index}":
            raise RuntimeError("injected migration failure")

    with pytest.raises(RuntimeError, match="injected"):
        ResearchSpendLedger(db_path, failure_injector=fail).ensure_schema()
    with sqlite3.connect(db_path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 0
        tables = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' "
            "AND name LIKE 'research_spend_%'"
        ).fetchall()
        assert tables == []
    ResearchSpendLedger(db_path).ensure_schema()


def test_schema_rejects_wrong_application_and_future_version(tmp_path: Path) -> None:
    wrong = tmp_path / "wrong.sqlite3"
    with sqlite3.connect(wrong) as connection:
        connection.execute("PRAGMA application_id = 123")
    with pytest.raises(LedgerIntegrityError, match="another application"):
        ResearchSpendLedger(wrong).ensure_schema()

    future = tmp_path / "future.sqlite3"
    with sqlite3.connect(future) as connection:
        connection.execute(f"PRAGMA application_id = {APPLICATION_ID}")
        connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
    with pytest.raises(LedgerIntegrityError, match="unsupported"):
        ResearchSpendLedger(future).ensure_schema()


def test_schema_one_migrates_mode_binding_atomically(tmp_path: Path) -> None:
    legacy = tmp_path / "legacy-v1.sqlite3"
    with sqlite3.connect(legacy) as connection:
        connection.execute(f"PRAGMA application_id = {APPLICATION_ID}")
        connection.execute("PRAGMA user_version = 1")
        connection.execute("CREATE TABLE research_spend_runs (run_id TEXT PRIMARY KEY)")
    ResearchSpendLedger(legacy).ensure_schema()
    with sqlite3.connect(legacy) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        columns = {
            row[1]: row for row in connection.execute("PRAGMA table_info(research_spend_runs)")
        }
        assert columns["mode"][3] == 1


def test_schema_one_mode_migration_rolls_back_on_process_failure(tmp_path: Path) -> None:
    legacy = tmp_path / "legacy-v1-crash.sqlite3"
    with sqlite3.connect(legacy) as connection:
        connection.execute(f"PRAGMA application_id = {APPLICATION_ID}")
        connection.execute("PRAGMA user_version = 1")
        connection.execute("CREATE TABLE research_spend_runs (run_id TEXT PRIMARY KEY)")

    def fail(name: str) -> None:
        if name == "schema:1:after_migration:1":
            raise RuntimeError("injected migration crash")

    with pytest.raises(RuntimeError, match="migration crash"):
        ResearchSpendLedger(legacy, failure_injector=fail).ensure_schema()
    with sqlite3.connect(legacy) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
        assert "mode" not in {
            row[1] for row in connection.execute("PRAGMA table_info(research_spend_runs)")
        }
    ResearchSpendLedger(legacy).ensure_schema()


def test_populated_schema_one_run_and_hold_replay_after_mode_migration(
    tmp_path: Path,
) -> None:
    legacy = tmp_path / "legacy-v1-populated.sqlite3"
    binding = _binding()
    paid = _paid()
    create_intent = _canonical({**_binding_payload(binding), "ceiling_cents": 1_000})
    hold_intent = ResearchSpendLedger._paid_intent_json(binding, paid, 100)
    timestamp = "2026-07-13T00:00:00.000000Z"
    with sqlite3.connect(legacy) as connection:
        for statement in _DDL:
            connection.execute(
                statement.replace(
                    "        mode TEXT NOT NULL CHECK (mode = 'hard_ceiling'),\n", ""
                )
            )
        connection.execute(f"PRAGMA application_id = {APPLICATION_ID}")
        connection.execute("PRAGMA user_version = 1")
        connection.execute(
            "INSERT INTO research_spend_runs "
            "(run_id, owner_id, session_id, plan_digest, approval_revision, currency, "
            "ceiling_cents, authorized_spent_cents, observed_provider_spend_dec, "
            "held_cents, status, ceiling_breached, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, 'USD', 1000, 0, '0', 100, 'active', 0, ?, ?)",
            (
                binding.run_id,
                binding.owner_id,
                binding.session_id,
                binding.plan_digest,
                binding.approval_revision,
                timestamp,
                timestamp,
            ),
        )
        connection.execute(
            "INSERT INTO research_spend_holds "
            "(hold_id, run_id, reservation_key, intent_json, intent_sha256, seam_id, "
            "provider, model, operation, operation_digest, projection_digest, "
            "rate_snapshot, provider_idempotency_key, projected_max_cents, state, "
            "created_at, updated_at) VALUES "
            "('legacy-hold', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 100, 'reserved', ?, ?)",
            (
                binding.run_id,
                paid.reservation_key,
                hold_intent,
                _sha256(hold_intent),
                paid.seam_id,
                paid.provider,
                paid.model,
                paid.operation,
                paid.operation_digest,
                paid.projection_digest,
                paid.rate_snapshot,
                paid.provider_idempotency_key,
                timestamp,
                timestamp,
            ),
        )
        connection.execute(
            "INSERT INTO research_spend_commands "
            "(command_key, command_kind, scope_id, intent_json, intent_sha256, "
            "result_json, result_sha256, created_at) "
            "VALUES ('create-run', 'create_run', ?, ?, ?, '{}', ?, ?)",
            (
                binding.run_id,
                create_intent,
                _sha256(create_intent),
                _sha256("{}"),
                timestamp,
            ),
        )

    ledger = ResearchSpendLedger(legacy)
    ledger.ensure_schema()
    reopened = ledger.create_or_reopen_run("create-run", binding, 1_000)
    assert reopened.binding.mode == "hard_ceiling"
    assert reopened.held_cents == 100
    assert ledger.hold("legacy-hold").intent == paid


def test_commands_and_events_are_immutable_and_intents_are_verified(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    hold = ledger.reserve_paid("reserve", _binding(), _paid(), 100)
    db_path = tmp_path / "research-spend.sqlite3"
    with sqlite3.connect(db_path) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute("DELETE FROM research_spend_events")
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                "UPDATE research_spend_commands SET intent_json = '{}' "
                "WHERE command_key = 'reserve'"
            )
        connection.execute(
            "UPDATE research_spend_holds SET model = 'tampered' WHERE hold_id = ?",
            (hold.hold_id,),
        )
    with pytest.raises(LedgerIntegrityError, match="intent"):
        ledger.hold(hold.hold_id)


def test_replay_rejects_corrupt_result_and_balance_rejects_cross_table_drift(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    ledger.reserve_paid("reserve", _binding(), _paid(), 100)
    db_path = tmp_path / "research-spend.sqlite3"
    with sqlite3.connect(db_path) as connection:
        connection.execute("DROP TRIGGER research_spend_commands_no_update")
        connection.execute(
            "UPDATE research_spend_commands SET result_json = '{}' "
            "WHERE command_key = 'reserve'"
        )
    with pytest.raises(LedgerIntegrityError, match="corrupt result"):
        ledger.reserve_paid("reserve", _binding(), _paid(), 100)

    drift = tmp_path / "drift"
    drift.mkdir()
    drift_ledger = _ledger(drift)
    drift_ledger.reserve_paid("reserve", _binding(), _paid(), 100)
    with sqlite3.connect(drift / "research-spend.sqlite3") as connection:
        connection.execute(
            "UPDATE research_spend_runs SET held_cents = 0 WHERE run_id = 'run-1'"
        )
    with pytest.raises(LedgerIntegrityError, match="unresolved holds"):
        drift_ledger.balance("run-1")
    with pytest.raises(LedgerIntegrityError, match="unresolved holds"):
        drift_ledger.reserve_paid("another", _binding(), _paid("another"), 100)


def test_event_deltas_and_post_balances_are_auditable(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    hold_id = _dispatch(ledger, cents=100)
    ledger.settle("settle", hold_id, 80, {"receipt": "r-1"})
    events = ledger.events("run-1")
    assert [event.event_kind for event in events] == [
        "run_created",
        "hold_reserved",
        "dispatch_possible",
        "hold_settled",
    ]
    assert events[1].held_delta_cents == 100
    assert events[-1].authorized_delta_cents == 80
    assert events[-1].held_delta_cents == -100
    assert events[-1].observed_delta_cents == 80
    assert events[-1].post_authorized_cents == 80
    assert events[-1].post_held_cents == 0
    assert events[-1].post_observed_cents == 80
    assert ledger.integrity_check() == "ok"
