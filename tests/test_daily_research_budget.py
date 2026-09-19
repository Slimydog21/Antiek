from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from substrate.dispatch.daily_research_budget import (
    DailyResearchBudgetExceeded,
    DailyResearchBudgetInvalid,
    hold_daily_research_budget,
    read_daily_research_budget,
    release_daily_research_budget,
    settle_daily_research_budget,
)
from substrate.investigation_tenancy import InvestigationAuthority
from substrate.schemas import InvestigationStartRequestedPayload

NOW = datetime(2026, 7, 17, tzinfo=UTC)


def _hold(root, hold_id: str, amount: str = "0.75"):
    return hold_daily_research_budget(
        account_id="alice",
        hold_id=hold_id,
        cap_usd="1.00",
        amount_usd=amount,
        now=NOW,
        root=root,
    )


def test_concurrent_holds_cannot_reuse_one_daily_balance(tmp_path) -> None:
    ids = ("a" * 64, "b" * 64)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(_hold, tmp_path, hold_id) for hold_id in ids]
    outcomes = []
    for future in futures:
        try:
            outcomes.append(future.result().held_cents)
        except DailyResearchBudgetExceeded:
            outcomes.append("refused")
    assert sorted(outcomes, key=str) == [75, "refused"]
    assert (
        read_daily_research_budget(
            account_id="alice", cap_usd="1.00", now=NOW, root=tmp_path
        ).remaining_cents
        == 25
    )


def test_hold_replay_settle_release_and_account_isolation(tmp_path) -> None:
    held = _hold(tmp_path, "a" * 64)
    assert held.held_cents == 75
    assert _hold(tmp_path, "a" * 64) == held
    settled = settle_daily_research_budget(
        account_id="alice",
        hold_id="a" * 64,
        cap_usd="1.00",
        amount_usd="0.75",
        actual_usd="0.20",
        now=NOW,
        root=tmp_path,
    )
    assert (settled.held_cents, settled.settled_cents, settled.remaining_cents) == (0, 20, 80)
    assert (
        settle_daily_research_budget(
            account_id="alice",
            hold_id="a" * 64,
            cap_usd="1.00",
            amount_usd="0.75",
            actual_usd="0.20",
            now=NOW,
            root=tmp_path,
        )
        == settled
    )
    assert (
        read_daily_research_budget(
            account_id="bob", cap_usd="1.00", now=NOW, root=tmp_path
        ).remaining_cents
        == 100
    )
    with pytest.raises(DailyResearchBudgetInvalid, match="terminal"):
        release_daily_research_budget(
            account_id="alice",
            hold_id="a" * 64,
            cap_usd="1.00",
            amount_usd="0.75",
            now=NOW,
            root=tmp_path,
        )


def test_release_returns_capacity_and_conflicts_fail_closed(tmp_path) -> None:
    _hold(tmp_path, "a" * 64)
    released = release_daily_research_budget(
        account_id="alice",
        hold_id="a" * 64,
        cap_usd="1.00",
        amount_usd="0.75",
        now=NOW,
        root=tmp_path,
    )
    assert released.remaining_cents == 100
    assert (
        release_daily_research_budget(
            account_id="alice",
            hold_id="a" * 64,
            cap_usd="1.00",
            amount_usd="0.75",
            now=NOW,
            root=tmp_path,
        )
        == released
    )
    with pytest.raises(DailyResearchBudgetInvalid, match="another amount"):
        _hold(tmp_path, "a" * 64, "0.50")


def test_released_pre_start_hold_can_be_reacquired_but_settled_hold_cannot(
    tmp_path,
) -> None:
    _hold(tmp_path, "a" * 64)
    release_daily_research_budget(
        account_id="alice",
        hold_id="a" * 64,
        cap_usd="1.00",
        amount_usd="0.75",
        now=NOW,
        root=tmp_path,
    )
    reacquired = _hold(tmp_path, "a" * 64)
    assert (reacquired.held_cents, reacquired.remaining_cents) == (75, 25)
    settle_daily_research_budget(
        account_id="alice",
        hold_id="a" * 64,
        cap_usd="1.00",
        amount_usd="0.75",
        actual_usd="0.20",
        now=NOW,
        root=tmp_path,
    )
    with pytest.raises(DailyResearchBudgetInvalid, match="already terminal"):
        _hold(tmp_path, "a" * 64)


def test_terminal_reconciliation_retains_unknown_calls_then_settles(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ANTIEK_HOME", str(tmp_path))
    monkeypatch.setenv("ANTIEK_OPERATOR_BUDGET_USD", "1.00")
    hold_daily_research_budget(
        account_id="alice",
        hold_id="a" * 64,
        cap_usd="1.00",
        amount_usd="0.75",
        now=datetime.now(UTC),
    )
    request = SimpleNamespace(
        research_quote_id="a" * 64,
        research_daily_budget_hold_id="a" * 64,
        research_daily_budget_date_stamp=datetime.now(UTC).strftime("%Y%m%d"),
        research_daily_budget_cap_usd=1.0,
        approved_run_ceiling_usd=0.75,
    )
    reservation = {
        "action_type": "research.call_reserved",
        "payload": {"reservation_id": "reservation", "projected_max_cost_usd": 0.5},
    }
    rows = [reservation]
    monkeypatch.setattr(
        "orchestration.loop_one.orchestrator.trajectory_authorized", lambda _authority: rows
    )
    from orchestration.loop_one.orchestrator import _reconcile_daily_research_hold

    authority = InvestigationAuthority("alice", "child")
    assert _reconcile_daily_research_hold(request, authority) is False
    assert read_daily_research_budget(account_id="alice", cap_usd="1.00").held_cents == 75
    rows.append(
        {
            "action_type": "research.call_settled",
            "payload": {
                "action_type": "research.call_settled",
                "reservation_id": "reservation",
                "actual_cost_usd": 0.201,
            },
        }
    )
    # Recovery uses the cap persisted on the start receipt, not mutable config.
    monkeypatch.setenv("ANTIEK_OPERATOR_BUDGET_USD", "0.50")
    assert _reconcile_daily_research_hold(request, authority) is True
    snapshot = read_daily_research_budget(account_id="alice", cap_usd="1.00")
    assert (snapshot.held_cents, snapshot.settled_cents, snapshot.remaining_cents) == (
        0,
        21,
        79,
    )


def test_explicit_ledger_date_is_validated_and_recovers_original_day(tmp_path) -> None:
    held = hold_daily_research_budget(
        account_id="alice",
        hold_id="c" * 64,
        cap_usd="1.00",
        amount_usd="0.25",
        date_stamp="20260717",
        root=tmp_path,
    )
    assert held.date_stamp == "20260717"
    assert (
        read_daily_research_budget(
            account_id="alice",
            cap_usd="1.00",
            date_stamp="20260717",
            root=tmp_path,
        ).held_cents
        == 25
    )
    with pytest.raises(DailyResearchBudgetInvalid, match="date stamp"):
        read_daily_research_budget(
            account_id="alice",
            cap_usd="1.00",
            date_stamp="20260231",
            root=tmp_path,
        )
    with pytest.raises(DailyResearchBudgetInvalid, match="either now or date_stamp"):
        read_daily_research_budget(
            account_id="alice",
            cap_usd="1.00",
            now=NOW,
            date_stamp="20260717",
            root=tmp_path,
        )


def test_daily_start_authority_is_complete_and_bound_to_quote() -> None:
    with pytest.raises(ValueError, match="daily budget authority must be complete"):
        InvestigationStartRequestedPayload(
            question="What is true?",
            research_daily_budget_hold_id="d" * 64,
        )
