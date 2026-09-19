from __future__ import annotations

from pathlib import Path

import pytest

from substrate.engagement_spine import (
    HighlightSelection,
    attach_source_references,
    complete_spawn,
    spawn_from_highlight,
)
from substrate.engagement_spine.authority import EngagementAuthority
from substrate.engagement_spine.collective_council import (
    CouncilCallResult,
    CouncilMemberRequest,
    approve_council_plan,
    create_council_preflight,
    get_council_plan,
    run_approved_council,
)
from substrate.engagement_spine.store import InMemoryEngagementStore, authorized_store
from substrate.midnight_oil.budget_ledger import BudgetLedger, CallNotDispatched


def _approved_council(tmp_path: Path, *, member_count: int = 2):
    base = InMemoryEngagementStore()
    store = authorized_store(base, EngagementAuthority("alice"))
    requests = []
    for index in range(member_count):
        spawn = spawn_from_highlight(
            HighlightSelection(
                asset_id=f"paper-{index}",
                selection_text=f"Evidence {index}",
            ),
            store=store,
        )
        attach_source_references(
            spawn.spawn_id, [f"arxiv:1706.0376{index}"], store=store
        )
        complete_spawn(
            spawn.spawn_id,
            store=store,
            output_text=f"Completed analysis {index}",
        )
        requests.append(
            CouncilMemberRequest(spawn.spawn_id, f"critic-{index}", "test/member", 40)
        )
    plan = create_council_preflight(
        store=store,
        collective_id="collective-reviewed",
        shared_prompt="Reconcile these claims without erasing disagreements.",
        members=requests,
        synthesizer_model_id="test/synth",
        synthesizer_projected_max_cents=60,
        approved_ceiling_cents=40 * member_count + 60,
    )
    plan = approve_council_plan(
        plan.plan_id,
        store=store,
        expected_input_sha256=plan.input_sha256,
        approved_ceiling_cents=plan.approved_ceiling_cents,
    )
    ledger = BudgetLedger(str(tmp_path / "budget.duckdb"))
    return base, store, plan, ledger


class _Executor:
    def __init__(self, plan, *, fail_role: str | None = None) -> None:
        self.plan = plan
        self.fail_role = fail_role
        self.calls: list[str] = []

    def execute(self, *, prompt, model_id, role, idempotency_key):
        del prompt, model_id, idempotency_key
        self.calls.append(role)
        if role == self.fail_role:
            raise CallNotDispatched("provably local pre-dispatch failure")
        if role == "synthesizer":
            return CouncilCallResult(
                text="Synthesis preserving the disputed finding.",
                actual_cents=35,
                provider_receipt_id="provider-synth",
                cited_spawn_ids=tuple(member.spawn_id for member in self.plan.members),
                cited_source_ref_ids=tuple(
                    ref for member in self.plan.members for ref in member.source_ref_ids
                ),
            )
        member = next(member for member in self.plan.members if member.role == role)
        return CouncilCallResult(
            text=f"Finding from {role}",
            actual_cents=25,
            provider_receipt_id=f"provider-{role}",
            cited_spawn_ids=(member.spawn_id,),
            cited_source_ref_ids=(member.source_ref_ids[0],),
        )


def test_success_reserves_before_fanout_and_projects_html(tmp_path: Path) -> None:
    base, store, plan, ledger = _approved_council(tmp_path)
    executor = _Executor(plan)

    result = run_approved_council(
        plan.plan_id, store=store, ledger=ledger, executor=executor, max_workers=2
    )

    assert result.state == "complete"
    assert result.spent_cents == 85
    assert result.held_cents == 0
    assert result.html is not None
    assert "No automatic merge or graph promotion performed" in result.html
    assert "Synthesis receipt" in result.html
    assert "provider-synth" in result.html
    assert plan.members[0].spawn_id in result.html
    assert plan.members[0].source_ref_ids[0] in result.html
    assert get_council_plan(plan.plan_id, store=store).state == "complete"
    receipts = [
        row for row in base._docs.values() if row.get("kind") == "council_call_receipt"
    ]
    assert len(receipts) == 3
    assert {row["settlement_state"] for row in receipts} == {"settled"}
    assert not any(row.get("kind") in {"merge_commit", "graph_revision"} for row in base._docs.values())


def test_pre_dispatch_member_failure_is_attributed_and_unused_budget_released(
    tmp_path: Path,
) -> None:
    _base, store, plan, ledger = _approved_council(tmp_path)
    executor = _Executor(plan, fail_role="critic-1")

    result = run_approved_council(
        plan.plan_id, store=store, ledger=ledger, executor=executor
    )

    assert result.state == "complete"
    assert [receipt.state for receipt in result.member_receipts] == [
        "complete",
        "not_dispatched",
    ]
    assert result.spent_cents == 60
    assert result.held_cents == 0
    assert executor.calls.count("synthesizer") == 1


def test_provider_return_is_durable_before_failed_settlement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base, store, plan, ledger = _approved_council(tmp_path, member_count=1)
    executor = _Executor(plan)

    def fail_settlement(*_args, **_kwargs):
        raise RuntimeError("simulated settlement persistence failure")

    monkeypatch.setattr(ledger, "settle", fail_settlement)
    result = run_approved_council(
        plan.plan_id, store=store, ledger=ledger, executor=executor
    )

    assert result.state == "unknown"
    assert result.held_cents == 40
    assert executor.calls == ["critic-0"]
    receipt = next(
        row for row in base._docs.values() if row.get("kind") == "council_call_receipt"
    )
    assert receipt["settlement_state"] == "provider_returned"
    assert receipt["provider_receipt_id"] == "provider-critic-0"
    assert receipt["output_text"] == "Finding from critic-0"


def test_replay_of_terminal_plan_dispatches_nothing(tmp_path: Path) -> None:
    _base, store, plan, ledger = _approved_council(tmp_path, member_count=1)
    executor = _Executor(plan)
    run_approved_council(plan.plan_id, store=store, ledger=ledger, executor=executor)
    calls = list(executor.calls)

    with pytest.raises(ValueError, match="not approved"):
        run_approved_council(plan.plan_id, store=store, ledger=ledger, executor=executor)
    assert executor.calls == calls


def test_initial_result_persistence_failure_leaves_plan_retryable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _base, store, plan, ledger = _approved_council(tmp_path, member_count=1)
    executor = _Executor(plan)
    original_put = type(store).put_document
    failed = False

    def fail_first_result(self, document_id, row):
        nonlocal failed
        if row.get("kind") == "council_result" and not failed:
            failed = True
            raise OSError("simulated result-store outage")
        return original_put(self, document_id, row)

    monkeypatch.setattr(type(store), "put_document", fail_first_result)
    with pytest.raises(OSError, match="result-store outage"):
        run_approved_council(
            plan.plan_id, store=store, ledger=ledger, executor=executor
        )
    assert get_council_plan(plan.plan_id, store=store).state == "approved"
    assert executor.calls == []

    result = run_approved_council(
        plan.plan_id, store=store, ledger=ledger, executor=executor
    )
    assert result.state == "complete"


def test_post_settlement_checkpoint_failure_is_visible_not_redispatched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _base, store, plan, ledger = _approved_council(tmp_path, member_count=1)
    executor = _Executor(plan)
    original_put = type(store).put_document

    def reject_settled_marker(self, document_id, row):
        if (
            row.get("kind") == "council_call_receipt"
            and row.get("settlement_state") == "settled"
        ):
            raise OSError("simulated audit-marker outage")
        return original_put(self, document_id, row)

    monkeypatch.setattr(type(store), "put_document", reject_settled_marker)
    result = run_approved_council(
        plan.plan_id, store=store, ledger=ledger, executor=executor
    )

    assert result.state == "complete"
    assert result.spent_cents == 60
    assert result.held_cents == 0
    assert result.member_receipts[0].error_type == "SettlementCheckpointUpdateFailed"
    assert result.synthesizer_receipt.error_type == "SettlementCheckpointUpdateFailed"
    assert executor.calls == ["critic-0", "synthesizer"]
