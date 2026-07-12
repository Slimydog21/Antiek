from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from substrate.midnight_oil.budget_ledger import (
    BudgetLedger,
    CallKeyReplay,
    CallNotDispatched,
    UnknownCallOutcome,
)

STAGE_KEY = "a" * 64


def _ledger(tmp_path: Path) -> BudgetLedger:
    ledger = BudgetLedger(str(tmp_path / "stage-budget.duckdb"))
    ledger.ensure_schema()
    ledger.reserve("run-1", 1_000, {"gatherer": 1_000})
    return ledger


def test_stage_key_open_exposure_and_exact_replay_fail_closed(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    hold = ledger.reserve_call("run-1", "gatherer", 250, call_key=STAGE_KEY)
    exposure = ledger.stage_exposure("run-1", STAGE_KEY)
    assert exposure.call_key == hold.call_key == STAGE_KEY
    assert exposure.hold_id == hold.hold_id
    assert (exposure.projected_cents, exposure.confirmed_cents) == (250, 0)
    assert (exposure.open_cents, exposure.unknown_cents, exposure.state) == (
        250,
        0,
        "open",
    )

    with pytest.raises(CallKeyReplay) as replay:
        ledger.reserve_call("run-1", "gatherer", 250, call_key=STAGE_KEY)
    assert replay.value.exposure == exposure
    assert ledger.balance("run-1").held_cents == 250
    with pytest.raises(ValueError, match="conflicts"):
        ledger.reserve_call("run-1", "gatherer", 251, call_key=STAGE_KEY)
    with pytest.raises(ValueError, match="conflicts"):
        ledger.reserve_call("run-1", "planner", 250, call_key=STAGE_KEY)


@pytest.mark.parametrize("value", ["", "A" * 64, "a" * 63, "g" * 64])
def test_stage_key_is_canonical_bounded_sha256(tmp_path: Path, value: str) -> None:
    ledger = _ledger(tmp_path)
    with pytest.raises(ValueError, match="call_key"):
        ledger.reserve_call("run-1", "gatherer", 100, call_key=value)


def test_guarded_stage_settlement_retains_actual_cents_after_restart(
    tmp_path: Path,
) -> None:
    path = tmp_path / "stage-budget.duckdb"
    ledger = _ledger(tmp_path)
    calls = 0

    def paid_call() -> tuple[str, int]:
        nonlocal calls
        calls += 1
        return "result", 173

    result, balance = ledger.guarded_call(
        "run-1",
        "gatherer",
        250,
        paid_call,
        call_key=STAGE_KEY,
    )
    assert result == "result" and calls == 1
    assert balance.spent_cents == 173
    restarted = BudgetLedger(str(path))
    restarted.ensure_schema()
    exposure = restarted.stage_exposure("run-1", STAGE_KEY)
    assert (exposure.projected_cents, exposure.confirmed_cents) == (250, 173)
    assert (exposure.open_cents, exposure.unknown_cents, exposure.state) == (
        0,
        0,
        "settled",
    )
    with pytest.raises(CallKeyReplay):
        restarted.guarded_call("run-1", "gatherer", 250, paid_call, call_key=STAGE_KEY)
    assert calls == 1


def test_unknown_stage_exposure_reconciles_to_confirmed_actual(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)

    def ambiguous() -> tuple[str, int]:
        raise TimeoutError("provider outcome unknown")

    with pytest.raises(UnknownCallOutcome) as unknown:
        ledger.guarded_call("run-1", "gatherer", 300, ambiguous, call_key=STAGE_KEY)
    exposure = ledger.stage_exposure("run-1", STAGE_KEY)
    assert (exposure.confirmed_cents, exposure.open_cents) == (0, 0)
    assert (exposure.unknown_cents, exposure.state) == (300, "unknown")
    ledger.resolve_unknown(unknown.value.hold.hold_id, 211)
    resolved = ledger.stage_exposure("run-1", STAGE_KEY)
    assert (resolved.projected_cents, resolved.confirmed_cents) == (300, 211)
    assert (resolved.open_cents, resolved.unknown_cents, resolved.state) == (
        0,
        0,
        "settled",
    )


def test_recovery_can_fail_closed_an_open_stage_hold_without_private_api(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    ledger.reserve_call("run-1", "gatherer", 300, call_key=STAGE_KEY)
    unknown = ledger.mark_stage_call_unknown("run-1", STAGE_KEY)
    assert (unknown.state, unknown.unknown_cents) == ("unknown", 300)
    assert ledger.mark_stage_call_unknown("run-1", STAGE_KEY) == unknown
    ledger.resolve_unknown(unknown.hold_id, 211)
    with pytest.raises(ValueError, match="only an open"):
        ledger.mark_stage_call_unknown("run-1", STAGE_KEY)


def test_concurrent_recovery_unknown_transition_is_exactly_idempotent(
    tmp_path: Path,
) -> None:
    path = tmp_path / "stage-budget.duckdb"
    ledger = _ledger(tmp_path)
    ledger.reserve_call("run-1", "gatherer", 300, call_key=STAGE_KEY)
    barrier = threading.Barrier(8)

    def recover(_: int) -> str:
        contender = BudgetLedger(str(path))
        barrier.wait()
        return contender.mark_stage_call_unknown("run-1", STAGE_KEY).state

    with ThreadPoolExecutor(max_workers=8) as pool:
        assert list(pool.map(recover, range(8))) == ["unknown"] * 8
    assert ledger.stage_exposure("run-1", STAGE_KEY).unknown_cents == 300


def test_after_reserve_failure_keeps_ambiguous_checkpoint_hold_open(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    called = False

    def provider() -> tuple[str, int]:
        nonlocal called
        called = True
        return "impossible", 1

    def checkpoint(_hold: object) -> None:
        raise RuntimeError("stage reservation CAS failed")

    with pytest.raises(RuntimeError, match="reservation CAS"):
        ledger.guarded_call(
            "run-1",
            "gatherer",
            300,
            provider,
            call_key=STAGE_KEY,
            after_reserve=checkpoint,
        )
    assert not called
    restarted = BudgetLedger(str(tmp_path / "stage-budget.duckdb"))
    restarted.ensure_schema()
    assert restarted.stage_exposure("run-1", STAGE_KEY).state == "open"


def test_proven_not_dispatched_stage_remains_non_replayable(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)

    def refused() -> tuple[str, int]:
        raise CallNotDispatched("failed before network")

    with pytest.raises(CallNotDispatched):
        ledger.guarded_call("run-1", "gatherer", 200, refused, call_key=STAGE_KEY)
    exposure = ledger.stage_exposure("run-1", STAGE_KEY)
    assert (exposure.confirmed_cents, exposure.open_cents, exposure.unknown_cents) == (
        0,
        0,
        0,
    )
    assert exposure.state == "released"
    with pytest.raises(CallKeyReplay):
        ledger.reserve_call("run-1", "gatherer", 200, call_key=STAGE_KEY)


def test_concurrent_stage_key_reservation_allocates_one_hold(tmp_path: Path) -> None:
    path = tmp_path / "stage-budget.duckdb"
    _ledger(tmp_path)
    barrier = threading.Barrier(12)

    def reserve_once(_: int) -> str:
        contender = BudgetLedger(str(path))
        contender.ensure_schema()
        barrier.wait()
        try:
            contender.reserve_call("run-1", "gatherer", 225, call_key=STAGE_KEY)
        except CallKeyReplay:
            return "replay"
        return "created"

    with ThreadPoolExecutor(max_workers=12) as pool:
        outcomes = list(pool.map(reserve_once, range(12)))
    assert outcomes.count("created") == 1
    assert outcomes.count("replay") == 11
    ledger = BudgetLedger(str(path))
    assert ledger.balance("run-1").held_cents == 225
    assert ledger.stage_exposure("run-1", STAGE_KEY).open_cents == 225
