from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import cast

import pytest

from runtime.db_lock import LockedConnection
from substrate.midnight_oil import (
    ADAPTER_KEYS,
    MidnightOilExecutionRequest,
    MidnightOilRequest,
    execute_midnight_oil,
    preflight_midnight_oil,
)
from substrate.midnight_oil.seams import (
    ALL_SEAMS,
    RETRIEVAL_REQUIRES_RESERVATION,
    Balance,
    MidnightOilSeams,
    NotAuthorized,
    NullBudgetReservationProvider,
    NullControlLedgerAuditRollback,
    NullFinalHtmlArtifactWriter,
    NullGraphMutationWriter,
    NullModelProviderRouteExecutor,
    NullOperatorLiveDispatchEnablement,
    NullRetrievalExecutorSourceReceipts,
    OperatorSpendNotAuthorized,
    ReservedBalance,
    RetrievalResult,
    SeamOrderingViolation,
)


def test_seam_catalog_exactly_matches_closed_adapter_keys() -> None:
    keys = [seam.adapter_key for seam in ALL_SEAMS]

    assert len(keys) == 7
    assert len(keys) == len(set(keys))
    assert set(keys) == set(ADAPTER_KEYS)


def test_null_budget_adapter_never_reserves_or_debits() -> None:
    adapter = NullBudgetReservationProvider()

    with pytest.raises(NotAuthorized, match="reservation"):
        adapter.reserve("run-1", 1000)
    with pytest.raises(NotAuthorized, match="debit"):
        adapter.debit("run-1", 1)


def test_null_provider_adapter_never_calls_a_model() -> None:
    adapter = NullModelProviderRouteExecutor()

    with pytest.raises(OperatorSpendNotAuthorized):
        adapter.execute(
            "prompt",
            "planner",
            investigation_id="investigation-1",
            budget=Balance(
                run_id="run-1",
                ceiling_cents=1000,
                spent_cents=0,
                held_cents=0,
                remaining_cents=1000,
                status="reserved",
            ),
        )


def test_null_retrieval_is_falsey_empty_and_explicitly_blocked() -> None:
    result = NullRetrievalExecutorSourceReceipts().retrieve("query", ("arxiv",))

    assert result.receipts == ()
    assert result.blocked_reason == "retrieval adapter is not implemented"
    assert not result


def test_null_write_and_ledger_adapters_never_manufacture_success() -> None:
    graph = NullGraphMutationWriter()
    artifact = NullFinalHtmlArtifactWriter()
    ledger = NullControlLedgerAuditRollback()

    with pytest.raises(NotAuthorized, match="graph"):
        graph.commit_asset(
            cast(LockedConnection, object()),
            "<article></article>",
            "<aside></aside>",
            investigation_id="investigation-1",
        )
    with pytest.raises(NotAuthorized, match="artifact"):
        artifact.write(object())
    with pytest.raises(NotAuthorized, match="ledger"):
        ledger.rollback_receipt("ledger-1")


def test_null_operator_gate_is_closed() -> None:
    adapter = NullOperatorLiveDispatchEnablement()

    assert adapter.is_authorized("run-1") is False
    assert adapter.authorization() is None


class _BudgetAdapter:
    adapter_key = "budget_reservation_provider"

    def reserve(
        self,
        run_id: str,
        approved_ceiling_cents: int,
        role_budgets: Mapping[str, int] | None = None,
    ) -> ReservedBalance:
        return ReservedBalance(
            run_id=run_id,
            ceiling_cents=approved_ceiling_cents,
            spent_cents=0,
            held_cents=0,
            remaining_cents=approved_ceiling_cents,
            status="reserved",
        )

    def debit(
        self, run_id: str, amount_cents: int, role: str | None = None
    ) -> Balance:
        return Balance(
            run_id=run_id,
            ceiling_cents=amount_cents,
            spent_cents=amount_cents,
            held_cents=0,
            remaining_cents=0,
            status="exhausted",
        )


class _RetrievalAdapter:
    adapter_key = "retrieval_executor_source_receipts"

    def retrieve(self, query: str, source_policy: tuple[str, ...]) -> RetrievalResult:
        return RetrievalResult(blocked_reason="test adapter intentionally empty")


def test_retrieval_before_budget_reservation_raises_exact_invariant() -> None:
    seams = MidnightOilSeams(budget=_BudgetAdapter(), retrieval=_RetrievalAdapter())

    with pytest.raises(SeamOrderingViolation, match=RETRIEVAL_REQUIRES_RESERVATION):
        seams.retrieve("run-1", "query", ("arxiv",))

    seams.reserve("run-1", 1000)
    result = seams.retrieve("run-1", "query", ("arxiv",))
    assert not result


def test_synthetic_runner_accepts_bundle_without_invoking_any_seam() -> None:
    preflight = preflight_midnight_oil(
        MidnightOilRequest(
            goal="Prove the synthetic DI boundary stays inert.",
            work_minutes=60,
            price_ceiling_usd=Decimal("10.00"),
            route_mode="auto_balanced",
            source_policy=["arxiv"],
            operator_acknowledged_spend=True,
        )
    )
    assert preflight.launch_packet is not None
    assert preflight.approval_receipt is not None
    assert preflight.runner_handoff is not None
    assert preflight.applied_run_receipt is not None
    request = MidnightOilExecutionRequest(
        launch_packet=preflight.launch_packet,
        approval_receipt=preflight.approval_receipt,
        runner_handoff=preflight.runner_handoff,
        applied_run_receipt=preflight.applied_run_receipt,
        role_plans=preflight.role_plans,
    )

    receipt = execute_midnight_oil(request, seams=MidnightOilSeams())

    assert receipt.execution_mode == "synthetic"
    assert receipt.actual_cost_usd == 0.0
    assert receipt.persisted is False
