from __future__ import annotations

from substrate.engagement_spine.collective_council import (
    council_result_sha256,
    run_approved_council,
)
from substrate.engagement_spine.council_reconciliation import reconcile_council_hold
from tests.test_collective_council_execution import _approved_council, _Executor


def test_checkpointed_unknown_is_reconciled_without_redispatch(
    tmp_path, monkeypatch
) -> None:
    base, store, plan, ledger = _approved_council(tmp_path, member_count=1)
    executor = _Executor(plan)
    original_settle = ledger.settle

    def fail_settlement(*_args, **_kwargs):
        raise RuntimeError("simulated settlement failure")

    monkeypatch.setattr(ledger, "settle", fail_settlement)
    execution = run_approved_council(
        plan.plan_id, store=store, ledger=ledger, executor=executor
    )
    monkeypatch.setattr(ledger, "settle", original_settle)
    result = store.get_document(execution.result_id)
    unknown = result["member_receipts"][0]

    receipt = reconcile_council_hold(
        store=store,
        ledger=ledger,
        plan_id=plan.plan_id,
        result_id=execution.result_id,
        expected_result_sha256=council_result_sha256(result),
        role=unknown["role"],
        hold_id=unknown["hold_id"],
        actual_cents=25,
    )
    replay = reconcile_council_hold(
        store=store,
        ledger=ledger,
        plan_id=plan.plan_id,
        result_id=execution.result_id,
        expected_result_sha256=receipt["expected_result_sha256"],
        role=unknown["role"],
        hold_id=receipt["hold_id"],
        actual_cents=25,
    )

    assert replay == receipt
    assert receipt["terminal_council_state"] == "failed"
    assert receipt["balance"]["spent_cents"] == 25
    assert receipt["balance"]["held_cents"] == 0
    assert executor.calls == ["critic-0"]
    final = store.get_document(execution.result_id)
    assert final["state"] == "failed"
    assert final["member_receipts"][0]["state"] == "complete"
    checkpoint = next(
        row for row in base._docs.values() if row.get("kind") == "council_call_receipt"
    )
    assert checkpoint["settlement_state"] == "reconciled"


def test_unknown_without_output_remains_visibly_attributed(tmp_path) -> None:
    _base, store, plan, ledger = _approved_council(tmp_path, member_count=1)

    class LostResponseExecutor:
        def execute(self, **_kwargs):
            raise TimeoutError("provider response lost")

    execution = run_approved_council(
        plan.plan_id,
        store=store,
        ledger=ledger,
        executor=LostResponseExecutor(),
    )
    result = store.get_document(execution.result_id)
    unknown = result["member_receipts"][0]
    receipt = reconcile_council_hold(
        store=store,
        ledger=ledger,
        plan_id=plan.plan_id,
        result_id=execution.result_id,
        expected_result_sha256=council_result_sha256(result),
        role=unknown["role"],
        hold_id=unknown["hold_id"],
        actual_cents=10,
    )

    assert receipt["terminal_council_state"] == "failed"
    final = store.get_document(execution.result_id)
    assert final["member_receipts"][0]["state"] == "reconciled_without_output"
    assert final["member_receipts"][0]["actual_cents"] == 10
    assert final["html"] is None
