from __future__ import annotations

import contextlib
import multiprocessing
from collections.abc import Iterator, Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from acquisition.search.exa.paid_dispatch import PaidSearchEnvelope, authorize_paid_search
from substrate.midnight_oil.budget_ledger import BudgetLedger


def _envelope(**changes: Any) -> PaidSearchEnvelope:
    base = PaidSearchEnvelope(
        run_id="run-1",
        role="researcher",
        owner_id="owner-1",
        approved_brief_hash="a" * 64,
        investigation_id="inv-1",
        query="café AI",
        endpoint_version="search-v1",
        parameters={"numResults": 10, "contents": {"text": True}},
        domains=("EXAMPLE.org", "arxiv.org"),
        projected_max_cents=75,
        currency="usd",
        catalog_version="exa-prices-2026-07",
        policy_version="policy-v1",
    )
    return replace(base, **changes)


def _ledger(path: Path) -> BudgetLedger:
    ledger = BudgetLedger(str(path))
    ledger.ensure_schema()
    with contextlib.suppress(ValueError):
        ledger.reserve("run-1", 300, {"researcher": 300})
    return ledger


def _race(path: str, queue: multiprocessing.Queue[tuple[str, str]], query: str = "café AI") -> None:
    try:
        op = authorize_paid_search(BudgetLedger(path), _envelope(query=query))
        queue.put(("ok", op.hold_id))
    except Exception as exc:  # pragma: no cover - child diagnostic
        queue.put(("error", repr(exc)))


def test_canonical_identity_is_explicit_and_bounded() -> None:
    left = _envelope(
        query="cafe\u0301 AI",
        domains=("arxiv.org", "example.ORG"),
        parameters={"contents": {"text": True}, "numResults": 10},
    )
    assert left.request_hash == _envelope().request_hash
    assert left.operation_id == _envelope().operation_id
    assert _envelope(domains=None).request_hash != _envelope(domains=()).request_hash
    assert _envelope(operation_version="exa-search-operation-v2").request_hash != left.request_hash
    with pytest.raises(ValueError, match="floats"):
        _ = _envelope(parameters={"score": 1.0}).request_hash
    with pytest.raises(ValueError, match="duplicate domains"):
        _ = _envelope(domains=("EXAMPLE.org", "example.org")).request_hash
    with pytest.raises(ValueError, match="65536"):
        _envelope(parameters={f"field-{index}": "x" * 8_000 for index in range(9)})


def test_envelope_snapshots_a_mutable_mapping_once() -> None:
    parameters: dict[str, Any] = {"numResults": 10}
    envelope = _envelope(parameters=parameters)
    before = (envelope.request_hash, envelope.operation_id)
    parameters["numResults"] = 100
    parameters["new"] = True
    assert (envelope.request_hash, envelope.operation_id) == before
    assert envelope.canonical_object()["parameters"] == {"numResults": 10}

    class Stateful(Mapping[str, object]):
        def __len__(self) -> int:
            return 2

        def __iter__(self) -> Iterator[str]:
            return iter(("only",))

        def __getitem__(self, key: str) -> object:
            return 1

        def items(self) -> Any:
            return [("only", 1)]

    with pytest.raises(ValueError, match="stateful"):
        _envelope(parameters=Stateful())


def test_atomic_authority_replay_and_hostile_reuse(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path / "db.duckdb")
    first = authorize_paid_search(ledger, _envelope())
    assert first.state == "PENDING"
    assert authorize_paid_search(ledger, _envelope()) == first
    assert ledger.balance("run-1").held_cents == 75
    with ledger._coordinator.acquire_write_context("test") as ctx:  # noqa: SLF001
        assert ctx.execute("SELECT count(*) FROM midnight_oil_call_holds").fetchone() == (1,)
    # Same operation identity cannot be rebound to changed authority.
    with ledger._coordinator.acquire_write_context("test") as ctx:  # noqa: SLF001
        ctx.execute(
            "UPDATE paid_dispatch_operations SET owner_id='attacker' WHERE operation_id=?",
            [first.operation_id],
        )
    with pytest.raises(RuntimeError, match="conflicts"):
        authorize_paid_search(ledger, _envelope())
    assert ledger.balance("run-1").held_cents == 75


def test_frozen_edges_fencing_success_and_terminal_projection(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path / "db.duckdb")
    op = authorize_paid_search(ledger, _envelope())
    op = ledger.transition_paid_operation(
        op.operation_id, expected_state="PENDING", next_state="CLAIMED"
    )
    assert op.fencing_token == 1
    with pytest.raises(RuntimeError, match="fencing"):
        ledger.transition_paid_operation(
            op.operation_id, expected_state="CLAIMED", next_state="SENDING", fencing_token=0
        )
    op = ledger.transition_paid_operation(
        op.operation_id, expected_state="CLAIMED", next_state="SENDING", fencing_token=1
    )
    for hostile_ref in ("artifact://", "artifact:sha256:", "artifact:sha256:" + "B" * 64):
        with pytest.raises(ValueError, match="artifact ref|SHA-256"):
            ledger.transition_paid_operation(
                op.operation_id,
                expected_state="SENDING",
                next_state="RESPONSE_RECORDED",
                fencing_token=1,
                response_ref=hostile_ref,
            )
    op = ledger.transition_paid_operation(
        op.operation_id,
        expected_state="SENDING",
        next_state="RESPONSE_RECORDED",
        fencing_token=1,
        response_ref="artifact:sha256:" + "b" * 64,
    )
    op = ledger.transition_paid_operation(
        op.operation_id,
        expected_state="RESPONSE_RECORDED",
        next_state="SUCCEEDED",
        fencing_token=1,
        success_ref="artifact:sha256:" + "c" * 64,
        actual_cents=40,
    )
    assert ledger.balance("run-1").spent_cents == 40
    op = ledger.transition_paid_operation(
        op.operation_id, expected_state="SUCCEEDED", next_state="PROJECTED", fencing_token=1
    )
    with pytest.raises(ValueError, match="terminal"):
        ledger.transition_paid_operation(
            op.operation_id, expected_state="PROJECTED", next_state="PENDING", fencing_token=1
        )


def test_cross_run_hold_tamper_fails_before_settlement(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path / "tamper.duckdb")
    ledger.reserve("run-2", 300, {"researcher": 300})
    operation = authorize_paid_search(ledger, _envelope())
    operation = ledger.transition_paid_operation(
        operation.operation_id, expected_state="PENDING", next_state="CLAIMED"
    )
    operation = ledger.transition_paid_operation(
        operation.operation_id,
        expected_state="CLAIMED",
        next_state="SENDING",
        fencing_token=operation.fencing_token,
    )
    operation = ledger.transition_paid_operation(
        operation.operation_id,
        expected_state="SENDING",
        next_state="RESPONSE_RECORDED",
        fencing_token=operation.fencing_token,
        response_ref="artifact:sha256:" + "b" * 64,
    )
    with ledger._coordinator.acquire_write_context("hostile-test") as ctx:  # noqa: SLF001
        ctx.execute(
            "UPDATE midnight_oil_call_holds SET run_id='run-2' WHERE hold_id=?",
            [operation.hold_id],
        )
    with pytest.raises(RuntimeError, match="canonical hold binding"):
        ledger.transition_paid_operation(
            operation.operation_id,
            expected_state="RESPONSE_RECORDED",
            next_state="SUCCEEDED",
            fencing_token=operation.fencing_token,
            success_ref="artifact:sha256:" + "c" * 64,
            actual_cents=40,
        )
    assert ledger.balance("run-1").spent_cents == 0
    assert ledger.balance("run-1").held_cents == 75
    assert ledger.balance("run-2").spent_cents == 0
    assert ledger.balance("run-2").held_cents == 0


def test_persisted_state_requires_coherent_fencing_generation(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path / "fence-tamper.duckdb")
    operation = authorize_paid_search(ledger, _envelope())
    with ledger._coordinator.acquire_write_context("hostile-test") as ctx:  # noqa: SLF001
        ctx.execute(
            "UPDATE paid_dispatch_operations SET fencing_token=1 WHERE operation_id=?",
            [operation.operation_id],
        )
    with pytest.raises(RuntimeError, match="pending.*fencing"):
        ledger.paid_operation(operation.operation_id)
    with ledger._coordinator.acquire_write_context("hostile-test") as ctx:  # noqa: SLF001
        ctx.execute(
            "UPDATE paid_dispatch_operations SET state='CLAIMED', fencing_token=0 "
            "WHERE operation_id=?",
            [operation.operation_id],
        )
    with pytest.raises(RuntimeError, match="requires a fencing token"):
        ledger.paid_operation(operation.operation_id)


def test_released_row_cannot_hide_stranded_held_balance(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path / "balance-tamper.duckdb")
    operation = authorize_paid_search(ledger, _envelope())
    operation = ledger.transition_paid_operation(
        operation.operation_id,
        expected_state="PENDING",
        next_state="REJECTED_PRE_DISPATCH",
    )
    operation = ledger.transition_paid_operation(
        operation.operation_id,
        expected_state="REJECTED_PRE_DISPATCH",
        next_state="RELEASED",
        fencing_token=0,
    )
    with ledger._coordinator.acquire_write_context("hostile-test") as ctx:  # noqa: SLF001
        ctx.execute("UPDATE midnight_oil_reservations SET held_cents=5 WHERE run_id='run-1'")
        ctx.execute(
            "UPDATE midnight_oil_role_budgets SET held_cents=5 "
            "WHERE run_id='run-1' AND role='researcher'"
        )
    with pytest.raises(RuntimeError, match="held balances"):
        ledger.paid_operation(operation.operation_id)


def test_pre_send_release_and_post_send_unknown_rules(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path / "db.duckdb")
    op = authorize_paid_search(ledger, _envelope())
    op = ledger.transition_paid_operation(
        op.operation_id, expected_state="PENDING", next_state="REJECTED_PRE_DISPATCH"
    )
    op = ledger.transition_paid_operation(
        op.operation_id,
        expected_state="REJECTED_PRE_DISPATCH",
        next_state="RELEASED",
        fencing_token=0,
    )
    assert op.state == "RELEASED" and ledger.balance("run-1").held_cents == 0

    second = authorize_paid_search(ledger, _envelope(query="another"))
    second = ledger.transition_paid_operation(
        second.operation_id, expected_state="PENDING", next_state="CLAIMED"
    )
    second = ledger.transition_paid_operation(
        second.operation_id, expected_state="CLAIMED", next_state="SENDING", fencing_token=1
    )
    second = ledger.transition_paid_operation(
        second.operation_id, expected_state="SENDING", next_state="OUTCOME_UNKNOWN", fencing_token=1
    )
    assert ledger.balance("run-1").held_cents == 75
    with pytest.raises(ValueError, match="authenticated accounting"):
        ledger.annotate_paid_operation_zero_charge(
            second.operation_id, evidence_ref="artifact:sha256:" + "d" * 64, fencing_token=1
        )
    assert ledger.balance("run-1").held_cents == 75
    with pytest.raises(ValueError, match="terminal"):
        ledger.transition_paid_operation(
            second.operation_id,
            expected_state="OUTCOME_UNKNOWN",
            next_state="CLAIMED",
            fencing_token=1,
        )
    second = ledger.annotate_paid_operation_zero_charge(
        second.operation_id,
        evidence_ref="accounting://authenticated/sha256/" + "d" * 64,
        fencing_token=1,
    )
    assert second.state == "OUTCOME_UNKNOWN"
    assert second.zero_charge_evidence_ref == "accounting://authenticated/sha256/" + "d" * 64
    assert ledger.balance("run-1").held_cents == 0
    assert (
        ledger.annotate_paid_operation_zero_charge(
            second.operation_id,
            evidence_ref="accounting://authenticated/sha256/" + "d" * 64,
            fencing_token=1,
        )
        == second
    )
    with pytest.raises(RuntimeError, match="immutable"):
        ledger.annotate_paid_operation_zero_charge(
            second.operation_id,
            evidence_ref="accounting://authenticated/sha256/" + "e" * 64,
            fencing_token=1,
        )


def test_reopen_quarantines_a_sending_crash_prefix_without_releasing(tmp_path: Path) -> None:
    path = tmp_path / "reopen.duckdb"
    ledger = _ledger(path)
    operation = authorize_paid_search(ledger, _envelope())
    operation = ledger.transition_paid_operation(
        operation.operation_id, expected_state="PENDING", next_state="CLAIMED"
    )
    ledger.transition_paid_operation(
        operation.operation_id,
        expected_state="CLAIMED",
        next_state="SENDING",
        fencing_token=operation.fencing_token,
    )
    recovered = BudgetLedger(str(path)).quarantine_incomplete_paid_operation(operation.operation_id)
    assert recovered.state == "OUTCOME_UNKNOWN"
    assert BudgetLedger(str(path)).balance("run-1").held_cents == 75
    assert (
        BudgetLedger(str(path)).quarantine_incomplete_paid_operation(operation.operation_id)
        == recovered
    )


def test_real_process_race_reopen_and_utc_rollover_independence(tmp_path: Path) -> None:
    path = tmp_path / "race.duckdb"
    _ledger(path)
    context = multiprocessing.get_context("spawn")
    queue: multiprocessing.Queue[tuple[str, str]] = context.Queue()
    processes = [context.Process(target=_race, args=(str(path), queue)) for _ in range(6)]
    for process in processes:
        process.start()
    for process in processes:
        process.join(20)
        assert process.exitcode == 0
    outcomes = [queue.get(timeout=3) for _ in processes]
    assert {kind for kind, _ in outcomes} == {"ok"}
    assert len({hold for _, hold in outcomes}) == 1
    reopened = BudgetLedger(str(path)).paid_operation(_envelope().operation_id)
    assert reopened is not None and reopened.state == "PENDING"
    assert BudgetLedger(str(path)).balance("run-1").held_cents == 75
    # No wall-clock/day field participates in identity or hold retention.
    assert reopened.hold_id == BudgetLedger.paid_operation_hold_id(
        reopened.operation_id, 75, "USD", "exa-prices-2026-07", "policy-v1"
    )


def test_distinct_operations_racing_never_alias(tmp_path: Path) -> None:
    path = tmp_path / "distinct.duckdb"
    _ledger(path)
    context = multiprocessing.get_context("spawn")
    queue: multiprocessing.Queue[tuple[str, str]] = context.Queue()
    processes = [
        context.Process(target=_race, args=(str(path), queue, f"query-{index}"))
        for index in range(4)
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(20)
        assert process.exitcode == 0
    outcomes = [queue.get(timeout=3) for _ in processes]
    assert {kind for kind, _ in outcomes} == {"ok"}
    assert len({hold for _, hold in outcomes}) == 4
    assert BudgetLedger(str(path)).balance("run-1").held_cents == 300
