from __future__ import annotations

import json
import multiprocessing
from decimal import Decimal
from pathlib import Path

import pytest

from substrate.antiek_bench.live import (
    HardBudget,
    Journal,
    JournalCorruptionError,
    LiveCallRecord,
    LiveCallRunner,
    ProviderResult,
    deterministic_call_id,
)


def _attempt_reservation(path: str, item_id: str, queue: object) -> None:
    journal = Journal(path)
    accepted = journal.reserve_within_cap(
        reservation(item_id=item_id, reserved_usd=Decimal("0.75")), Decimal("1")
    )
    queue.put(accepted)  # type: ignore[attr-defined]


class DirectTimeout:
    def run(self, fn, timeout_s: float):  # type: ignore[no-untyped-def]
        del timeout_s
        return fn()


def reservation(**changes: object) -> LiveCallRecord:
    values = {
        "wedge_id": "2026-w28:suite-v3:model-a:model-b",
        "week_id": "2026-W28",
        "suite_version": "suite-v3",
        "requested_provider": "openai",
        "requested_model": "model-a",
        "task_class": "research",
        "item_id": "item-1",
        "status": "reserved",
        "reserved_usd": Decimal("0.25"),
        "prompt_hash": "sha256:abc",
    }
    values.update(changes)
    return LiveCallRecord(**values)  # type: ignore[arg-type]


def test_identity_is_wedge_scoped() -> None:
    first = deterministic_call_id("wedge", "week-1", "suite-1", "model-a", "item-1")
    assert first == deterministic_call_id("wedge", "week-1", "suite-1", "model-a", "item-1")
    assert first != deterministic_call_id("wedge", "week-2", "suite-1", "model-a", "item-1")
    assert first != deterministic_call_id("wedge", "week-1", "suite-2", "model-a", "item-1")


def test_reservation_and_settlement_round_trip(tmp_path: Path) -> None:
    journal = Journal(tmp_path / "calls.jsonl")
    reserved = reservation()
    journal.append(reserved)
    settled = LiveCallRecord(
        **{
            **reserved.__dict__,
            "status": "ok",
            "cost_usd": Decimal("0.20"),
            "actual_provider": "openai",
            "actual_model": "model-a",
        }
    )
    journal.append(settled)
    assert journal.lookup(reserved.call_id) == settled
    assert len((tmp_path / "calls.jsonl").read_text().splitlines()) == 2


def test_terminal_without_reservation_and_duplicate_phases_are_rejected(tmp_path: Path) -> None:
    journal = Journal(tmp_path / "calls.jsonl")
    reserved = reservation()
    terminal = LiveCallRecord(**{**reserved.__dict__, "status": "failed"})
    with pytest.raises(ValueError, match="requires"):
        journal.append(terminal)
    journal.append(reserved)
    with pytest.raises(ValueError, match="duplicate"):
        journal.append(reserved)
    journal.append(terminal)
    with pytest.raises(ValueError, match="duplicate"):
        journal.append(terminal)


def test_only_incomplete_final_row_is_tolerated(tmp_path: Path) -> None:
    journal = Journal(tmp_path / "calls.jsonl")
    journal.append(reservation())
    with journal.path.open("ab") as handle:
        handle.write(b'{"torn":')
    assert len(journal.replay()) == 1
    second = reservation(item_id="item-2")
    journal.append(second)
    assert set(journal.replay()) == {reservation().call_id, second.call_id}
    journal.path.write_bytes(b'{"bad":true}\n' + journal.path.read_bytes())
    with pytest.raises(JournalCorruptionError, match="row 1"):
        journal.replay()


def test_stored_identity_tampering_is_corruption(tmp_path: Path) -> None:
    path = tmp_path / "calls.jsonl"
    payload = reservation().to_dict()
    payload["call_id"] = "lc_tampered"
    path.write_text(json.dumps(payload) + "\n")
    with pytest.raises(JournalCorruptionError):
        Journal(path).replay()


def test_crash_after_reservation_consumes_budget_and_prevents_redispatch(tmp_path: Path) -> None:
    journal = Journal(tmp_path / "calls.jsonl")
    budget = HardBudget("0.25", journal)
    journal.append(reservation())
    called = False

    def provider() -> ProviderResult:
        nonlocal called
        called = True
        raise AssertionError("must not redispatch")

    result = LiveCallRunner(journal, budget, DirectTimeout()).execute(
        wedge_id="2026-w28:suite-v3:model-a:model-b",
        week_id="2026-W28",
        suite_version="suite-v3",
        requested_provider="openai",
        requested_model="model-a",
        task_class="research",
        item_id="item-1",
        prompt_hash="sha256:abc",
        provider_fn=provider,
        maximum_cost="0.25",
    )
    assert result.status == "reserved"
    assert called is False
    assert budget.available == 0


def test_success_is_reserved_before_dispatch_and_replayed(tmp_path: Path) -> None:
    journal = Journal(tmp_path / "calls.jsonl")
    budget = HardBudget("1", journal)

    def provider() -> ProviderResult:
        assert budget.total_charged == Decimal("0.25")
        return ProviderResult("model-a", 10, 4, Decimal("0.20"), 120, "answer", "openai")

    runner = LiveCallRunner(journal, budget, DirectTimeout())
    kwargs = dict(
        wedge_id="2026-w28:suite-v3:model-a:model-b",
        week_id="2026-W28",
        suite_version="suite-v3",
        requested_provider="openai",
        requested_model="model-a",
        task_class="research",
        item_id="item-1",
        prompt_hash="sha256:abc",
        provider_fn=provider,
        maximum_cost="0.25",
    )
    result = runner.execute(**kwargs)
    assert result.status == "ok"
    assert (
        result.response_hash == "0db52f4076c082518412afd3dd3576e2cb0c63703fd7fed5e23ade60efef31d9"
    )
    assert budget.total_charged == Decimal("0.25")
    assert runner.execute(**kwargs) == result


def test_budget_rejects_before_provider_and_negative_estimate(tmp_path: Path) -> None:
    journal = Journal(tmp_path / "calls.jsonl")
    budget = HardBudget("0.10", journal)
    with pytest.raises(ValueError, match="non-negative"):
        budget.can_start("-0.01")
    with pytest.raises(ValueError, match="budget exceeded"):
        LiveCallRunner(journal, budget, DirectTimeout()).execute(
            wedge_id="w",
            week_id="week",
            suite_version="suite",
            requested_provider="p",
            requested_model="m",
            task_class="t",
            item_id="i",
            prompt_hash="h",
            provider_fn=lambda: pytest.fail("must not call"),
            maximum_cost="0.11",
        )


def test_concurrent_admission_cannot_exceed_cap(tmp_path: Path) -> None:
    context = multiprocessing.get_context("spawn")
    queue = context.Queue()
    path = str(tmp_path / "calls.jsonl")
    workers = [
        context.Process(target=_attempt_reservation, args=(path, f"item-{index}", queue))
        for index in range(2)
    ]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=10)
        assert worker.exitcode == 0
    assert sorted(queue.get(timeout=1) for _ in workers) == [False, True]
    assert HardBudget("1", Journal(path)).total_charged == Decimal("0.75")


def test_failure_text_and_response_are_never_persisted(tmp_path: Path) -> None:
    journal = Journal(tmp_path / "calls.jsonl")
    runner = LiveCallRunner(journal, HardBudget("1", journal), DirectTimeout())

    def provider() -> ProviderResult:
        raise RuntimeError(
            "private-sentinel and sk-ABCDEF123456 Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.payload"
        )

    result = runner.execute(
        wedge_id="w",
        week_id="week",
        suite_version="suite",
        requested_provider="p",
        requested_model="m",
        task_class="t",
        item_id="i",
        prompt_hash="h",
        provider_fn=provider,
        maximum_cost="0.1",
    )
    persisted = journal.path.read_text()
    assert result.status == "failed"
    assert "private-sentinel" not in persisted
    assert "sk-ABCDEF123456" not in persisted
    assert "eyJhbGciOiJIUzI1NiJ9" not in persisted
    assert result.failure_text == "provider call failed"


def test_timeout_remains_conservatively_charged(tmp_path: Path) -> None:
    class Timeout:
        def run(self, fn, timeout_s: float):  # type: ignore[no-untyped-def]
            del fn, timeout_s
            raise TimeoutError

    journal = Journal(tmp_path / "calls.jsonl")
    budget = HardBudget("0.5", journal)
    result = LiveCallRunner(journal, budget, Timeout()).execute(
        wedge_id="w",
        week_id="week",
        suite_version="suite",
        requested_provider="p",
        requested_model="m",
        task_class="t",
        item_id="i",
        prompt_hash="h",
        provider_fn=lambda: pytest.fail("not called"),
        maximum_cost="0.3",
    )
    assert result.status == "timeout"
    assert budget.total_charged == Decimal("0.3")


def test_provider_cost_above_enforced_maximum_fails_closed(tmp_path: Path) -> None:
    journal = Journal(tmp_path / "calls.jsonl")
    result = LiveCallRunner(journal, HardBudget("1", journal), DirectTimeout()).execute(
        wedge_id="w",
        week_id="week",
        suite_version="suite",
        requested_provider="p",
        requested_model="m",
        task_class="t",
        item_id="i",
        prompt_hash="h",
        provider_fn=lambda: ProviderResult("m", 1, 1, Decimal("0.2"), 1),
        maximum_cost="0.1",
    )
    assert result.status == "failed"
    assert result.failure_text == "provider measurement contract breached"
    # Never hide the actual bill merely to make the cap appear intact.
    assert result.cost_usd == Decimal("0.2")
    assert HardBudget("1", journal).total_charged == Decimal("0.2")


def test_attribution_and_route_receipt_are_persisted(tmp_path: Path) -> None:
    journal = Journal(tmp_path / "calls.jsonl")
    result = LiveCallRunner(journal, HardBudget("1", journal), DirectTimeout()).execute(
        wedge_id="w",
        week_id="week",
        suite_version="suite",
        requested_provider="openai",
        requested_model="model-a",
        task_class="wrestle",
        item_id="i",
        prompt_hash="sha256:prompt",
        provider_fn=lambda: ProviderResult(
            "model-a",
            10,
            5,
            Decimal("0.05"),
            12,
            "answer",
            "openai",
            "evt_dispatch_123",
        ),
        maximum_cost="0.1",
    )
    assert result.status == "ok"
    assert result.route_receipt_id == "evt_dispatch_123"
    assert journal.lookup(result.call_id) == result


def test_cross_model_fallback_contamination_fails_with_actual_bill(tmp_path: Path) -> None:
    journal = Journal(tmp_path / "calls.jsonl")
    result = LiveCallRunner(journal, HardBudget("1", journal), DirectTimeout()).execute(
        wedge_id="w",
        week_id="week",
        suite_version="suite",
        requested_provider="provider-a",
        requested_model="model-a",
        task_class="distill",
        item_id="i",
        prompt_hash="h",
        provider_fn=lambda: ProviderResult(
            "model-b", 1, 1, Decimal("0.04"), 3, provider_id="provider-b"
        ),
        maximum_cost="0.1",
    )
    assert result.status == "failed"
    assert result.actual_provider == "provider-b"
    assert result.actual_model == "model-b"
    assert result.cost_usd == Decimal("0.04")
    assert result.failure_text == "provider measurement contract breached"
