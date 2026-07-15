from __future__ import annotations

import sqlite3
from dataclasses import replace

import pytest

from substrate.research_spend import (
    BindingConflict,
    IdempotencyConflict,
    LaunchExecutionIntent,
    LaunchOperationIntent,
    LaunchOperationState,
    ResearchSpendLedger,
    RunBinding,
)


def _fixture(tmp_path, *, failure_injector=None):
    ledger = ResearchSpendLedger(tmp_path / "spend.sqlite3", failure_injector=failure_injector)
    ledger.ensure_schema()
    binding = RunBinding(
        run_id="run-launch-1",
        owner_id="owner-1",
        session_id="session-1",
        plan_digest="a" * 64,
        approval_revision=1,
    )
    ledger.create_or_reopen_run("create-launch-run", binding, 500)
    intent = LaunchExecutionIntent(
        execution_id="mle_" + "1" * 48,
        authority_kind="multimedia_research_v1",
        launch_reservation_id="mlr_" + "2" * 48,
        launch_manifest_digest="3" * 64,
        prepared_integrity_digest="4" * 64,
        provider="provider-a",
        model="model-a",
        route_digest="5" * 64,
        pricing_digest="6" * 64,
        workload_digest="7" * 64,
        operation_count=2,
        request_digest="8" * 64,
    )
    operations = tuple(
        LaunchOperationIntent(
            operation_id="mlop_" + str(index + 1) * 48,
            ordinal=index,
            stable_source_id="mrpn_" + str(index + 3) * 48,
            question=f"Question {index}?",
            payload_digest=str(index + 4) * 64,
            provider=intent.provider,
            model=intent.model,
            logical_operation_id="rplo_" + str(index + 5) * 48,
            state=LaunchOperationState.BLOCKED_PROVIDER_INELIGIBLE,
            blocked_reason="bound_provider_route_has_no_eligible_adapter",
        )
        for index in range(2)
    )
    return ledger, binding, intent, operations


def test_manifest_is_atomic_replayable_and_owner_private(tmp_path) -> None:
    ledger, binding, intent, operations = _fixture(tmp_path)
    created, was_created = ledger.materialize_launch_execution(
        "materialize-launch-1", binding, intent, operations
    )
    replay, replay_created = ledger.materialize_launch_execution(
        "materialize-launch-1", binding, intent, operations
    )
    assert was_created is True and replay_created is False
    assert replay == created and created.state == "blocked"
    assert [item.intent.ordinal for item in created.operations] == [0, 1]
    assert ledger.launch_execution_for_run(binding.run_id, "foreign-owner") is None
    assert ledger.integrity_check() == "ok"


def test_manifest_rejects_command_and_provider_route_conflicts(tmp_path) -> None:
    ledger, binding, intent, operations = _fixture(tmp_path)
    ledger.materialize_launch_execution("materialize-launch-1", binding, intent, operations)
    with pytest.raises(IdempotencyConflict):
        ledger.materialize_launch_execution(
            "materialize-launch-1", binding, replace(intent, request_digest="9" * 64), operations
        )
    with pytest.raises(BindingConflict, match="provider route"):
        other = replace(operations[0], provider="provider-b")
        ledger.materialize_launch_execution(
            "materialize-launch-2",
            binding,
            replace(intent, execution_id="mle_" + "9" * 48),
            (other, operations[1]),
        )


def test_manifest_rolls_back_all_rows_on_interrupted_leaf(tmp_path) -> None:
    armed = False

    def fail(name: str) -> None:
        if armed and name == "materialize_launch:after_operation:0":
            raise RuntimeError("interrupted")

    ledger, binding, intent, operations = _fixture(tmp_path, failure_injector=fail)
    armed = True
    with pytest.raises(RuntimeError, match="interrupted"):
        ledger.materialize_launch_execution("materialize-launch-1", binding, intent, operations)
    with sqlite3.connect(tmp_path / "spend.sqlite3") as connection:
        assert (
            connection.execute("SELECT count(*) FROM research_launch_executions").fetchone()[0] == 0
        )
        assert (
            connection.execute("SELECT count(*) FROM research_launch_operations").fetchone()[0] == 0
        )


def test_manifest_tampering_is_detected_by_reads_and_global_check(tmp_path) -> None:
    ledger, binding, intent, operations = _fixture(tmp_path)
    ledger.materialize_launch_execution("materialize-launch-1", binding, intent, operations)
    with sqlite3.connect(tmp_path / "spend.sqlite3") as connection:
        with pytest.raises(sqlite3.IntegrityError, match="operations are immutable"):
            connection.execute(
                "UPDATE research_launch_operations SET question='tampered' WHERE ordinal=0"
            )
        with pytest.raises(sqlite3.IntegrityError, match="executions are immutable"):
            connection.execute("DELETE FROM research_launch_executions")
    assert ledger.launch_execution_for_run(binding.run_id, binding.owner_id) is not None
    assert ledger.integrity_check() == "ok"
