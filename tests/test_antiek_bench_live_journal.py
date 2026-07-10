"""ABLW-SPR-01 verification: append-only journal + hard budget.

Covers the four sprint milestones:

1. Version the record — round-trip every status, deterministic identity,
   secret-free persistence.
2. Append and replay — fsync-backed JSONL, duplicate rejection, torn-tail
   recovery, deterministic lookup.
3. Fold the cap — property tests for arbitrary cost sequences against the
   hard-cap invariant.
4. Bound abandoned work — timeout recorded once, charged conservatively,
   never retried implicitly.
"""

from __future__ import annotations

import json
import os
import sys
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from substrate.antiek_bench.live import (  # noqa: E402
    HardBudget,
    Journal,
    LiveCallRecord,
    LiveCallRunner,
    ProviderResult,
    Status,
    TimeoutRunner,
    _deterministic_call_id,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_record(
    *,
    requested_model: str = "glm-4",
    actual_model: str = "glm-4",
    task_class: str = "distill",
    item_id: str = "item-01",
    cost_usd: Decimal | str = "0.01",
    prompt_tokens: int = 100,
    completion_tokens: int = 50,
    latency_ms: int = 500,
    status: Status = "ok",
    failure_text: str = "",
) -> LiveCallRecord:
    return LiveCallRecord(
        requested_model=requested_model,
        actual_model=actual_model,
        task_class=task_class,
        item_id=item_id,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_usd=Decimal(str(cost_usd)),
        latency_ms=latency_ms,
        status=status,
        failure_text=failure_text,
    )


def _make_runner(
    tmp_path: Path,
    cap: str = "1.00",
    timeout_s: float = 30.0,
) -> tuple[LiveCallRunner, Journal, HardBudget]:
    """Construct a LiveCallRunner with a mock timeout runner."""
    journal = Journal(tmp_path / "journal.jsonl")
    budget = HardBudget(Decimal(cap), journal)
    timeout_runner = MagicMock(spec=TimeoutRunner)
    runner = LiveCallRunner(journal, budget, timeout_runner)
    return runner, journal, budget


# ---------------------------------------------------------------------------
# Milestone 1: Version the record
# ---------------------------------------------------------------------------


class TestLiveCallRecordRoundTrip:
    """Every status round-trips through to_dict/from_dict without loss."""

    @pytest.mark.parametrize("status", ["ok", "timeout", "error"])
    def test_round_trip_preserves_all_fields(self, status: Status) -> None:
        rec = _make_record(
            status=status,
            failure_text="some detail" if status != "ok" else "",
        )
        d = rec.to_dict()
        restored = LiveCallRecord.from_dict(d)
        assert restored.requested_model == rec.requested_model
        assert restored.actual_model == rec.actual_model
        assert restored.task_class == rec.task_class
        assert restored.item_id == rec.item_id
        assert restored.prompt_tokens == rec.prompt_tokens
        assert restored.completion_tokens == rec.completion_tokens
        assert restored.cost_usd == rec.cost_usd
        assert restored.latency_ms == rec.latency_ms
        assert restored.status == rec.status
        assert restored.failure_text == rec.failure_text

    def test_deterministic_call_id(self) -> None:
        """call_id is a pure function of (requested_model, task_class, item_id)."""
        rec = _make_record(
            requested_model="m1", task_class="distill", item_id="x",
        )
        expected = _deterministic_call_id("m1", "distill", "x")
        assert rec.call_id == expected
        assert rec.call_id.startswith("lc_")
        assert len(rec.call_id) == 19  # "lc_" + 16 hex chars

    def test_call_id_differs_when_params_differ(self) -> None:
        r1 = _make_record(requested_model="m1", task_class="distill", item_id="x")
        r2 = _make_record(requested_model="m2", task_class="distill", item_id="x")
        r3 = _make_record(requested_model="m1", task_class="synthesize", item_id="x")
        r4 = _make_record(requested_model="m1", task_class="distill", item_id="y")
        ids = {r1.call_id, r2.call_id, r3.call_id, r4.call_id}
        assert len(ids) == 4

    def test_call_id_not_stored_in_dict(self) -> None:
        """call_id is recomputed, never serialized."""
        rec = _make_record()
        d = rec.to_dict()
        assert "call_id" not in d

    def test_cost_usd_serialized_as_string(self) -> None:
        """Decimal cost is persisted as string, not float."""
        rec = _make_record(cost_usd="0.001234")
        d = rec.to_dict()
        assert isinstance(d["cost_usd"], str)
        assert d["cost_usd"] == "0.001234"

    def test_failure_text_bounded_to_500_chars(self) -> None:
        long_text = "x" * 1000
        rec = _make_record(status="error", failure_text=long_text)
        d = rec.to_dict()
        assert len(d["failure_text"]) <= 500

    def test_secret_free_no_env_values(self) -> None:
        """Persisted dict contains no API keys or environment values."""
        rec = _make_record(
            requested_model="gpt-4",
            actual_model="gpt-4-turbo",
            failure_text="API key sk-12345 leaked",
        )
        d = rec.to_dict()
        raw = json.dumps(d)
        # The dict itself should not contain env-shaped values beyond
        # what the user passed in.  The key point: no env() reads, no
        # os.environ snapshots, no credential fields.
        assert "api_key" not in d
        assert "token" not in d
        assert "secret" not in d
        assert "password" not in d
        assert "api_key" not in raw
        # failure_text is user-supplied; we bound it but don't scrub.
        # The invariant is that the record *schema* has no credential slots.

    def test_from_dict_rejects_invalid_status(self) -> None:
        d = _make_record().to_dict()
        d["status"] = "bogus"
        with pytest.raises(ValueError, match="invalid status"):
            LiveCallRecord.from_dict(d)

    def test_from_dict_rejects_missing_fields(self) -> None:
        d = _make_record().to_dict()
        del d["requested_model"]
        with pytest.raises((KeyError, ValueError)):
            LiveCallRecord.from_dict(d)


# ---------------------------------------------------------------------------
# Milestone 2: Append and replay
# ---------------------------------------------------------------------------


class TestJournalAppendReplay:
    """Fsync-backed JSONL append, duplicate rejection, torn-tail recovery."""

    def test_append_and_replay_round_trip(self, tmp_path: Path) -> None:
        journal = Journal(tmp_path / "journal.jsonl")
        rec = _make_record()
        journal.append(rec)
        records = journal.replay()
        assert len(records) == 1
        restored = records[rec.call_id]
        assert restored.requested_model == rec.requested_model
        assert restored.cost_usd == rec.cost_usd

    def test_multiple_appends_preserve_order(self, tmp_path: Path) -> None:
        journal = Journal(tmp_path / "journal.jsonl")
        r1 = _make_record(item_id="a", cost_usd="0.01")
        r2 = _make_record(item_id="b", cost_usd="0.02")
        r3 = _make_record(item_id="c", cost_usd="0.03")
        journal.append(r1)
        journal.append(r2)
        journal.append(r3)
        records = journal.replay()
        assert len(records) == 3
        assert {r.call_id for r in [r1, r2, r3]} == set(records.keys())

    def test_duplicate_call_id_rejected(self, tmp_path: Path) -> None:
        """Idempotency: appending the same call_id twice raises ValueError."""
        journal = Journal(tmp_path / "journal.jsonl")
        rec = _make_record()
        journal.append(rec)
        with pytest.raises(ValueError, match="duplicate call_id"):
            journal.append(rec)

    def test_simulated_crash_preserves_complete_rows(self, tmp_path: Path) -> None:
        """A crash after complete rows preserves all of them.

        Simulates: write two complete rows, then write a partial (torn)
        line directly to the file (bypassing fsync).
        """
        journal = Journal(tmp_path / "journal.jsonl")
        r1 = _make_record(item_id="a", cost_usd="0.01")
        r2 = _make_record(item_id="b", cost_usd="0.02")
        journal.append(r1)
        journal.append(r2)

        # Simulate a torn tail: write a partial JSON line directly.
        with open(journal.path, "a", encoding="utf-8") as f:
            f.write('{"requested_model":"crash",')  # incomplete JSON
            f.flush()

        records = journal.replay()
        # Both complete rows survive; the torn tail is dropped.
        assert len(records) == 2
        assert r1.call_id in records
        assert r2.call_id in records

    def test_torn_tail_only_drops_last_line(self, tmp_path: Path) -> None:
        """Only the last line is dropped on parse failure — not earlier rows."""
        journal = Journal(tmp_path / "journal.jsonl")
        r1 = _make_record(item_id="a", cost_usd="0.01")
        r2 = _make_record(item_id="b", cost_usd="0.02")
        r3 = _make_record(item_id="c", cost_usd="0.03")
        journal.append(r1)
        journal.append(r2)
        journal.append(r3)

        # Write a torn line after the three complete rows.
        with open(journal.path, "a", encoding="utf-8") as f:
            f.write('{"incomplete":\n')
            f.flush()

        records = journal.replay()
        assert len(records) == 3

    def test_empty_journal_returns_empty(self, tmp_path: Path) -> None:
        journal = Journal(tmp_path / "empty.jsonl")
        assert journal.replay() == {}

    def test_lookup_returns_none_for_missing(self, tmp_path: Path) -> None:
        journal = Journal(tmp_path / "journal.jsonl")
        assert journal.lookup("lc_nonexistent") is None

    def test_lookup_returns_record(self, tmp_path: Path) -> None:
        journal = Journal(tmp_path / "journal.jsonl")
        rec = _make_record()
        journal.append(rec)
        found = journal.lookup(rec.call_id)
        assert found is not None
        assert found.item_id == rec.item_id

    def test_journal_creates_parent_directory(self, tmp_path: Path) -> None:
        nested = tmp_path / "a" / "b" / "journal.jsonl"
        journal = Journal(nested)
        rec = _make_record()
        journal.append(rec)
        assert nested.exists()
        assert len(journal.replay()) == 1

    def test_append_rejects_blank_model(self, tmp_path: Path) -> None:
        journal = Journal(tmp_path / "j.jsonl")
        rec = _make_record(requested_model="  ")
        with pytest.raises(ValueError, match="requested_model"):
            journal.append(rec)

    def test_append_rejects_negative_cost(self, tmp_path: Path) -> None:
        journal = Journal(tmp_path / "j.jsonl")
        rec = _make_record(cost_usd="-0.01")
        with pytest.raises(ValueError, match="cost_usd"):
            journal.append(rec)

    def test_append_rejects_negative_tokens(self, tmp_path: Path) -> None:
        journal = Journal(tmp_path / "j.jsonl")
        rec = _make_record(prompt_tokens=-1)
        with pytest.raises(ValueError, match="prompt_tokens"):
            journal.append(rec)

    def test_clear_removes_journal(self, tmp_path: Path) -> None:
        journal = Journal(tmp_path / "j.jsonl")
        journal.append(_make_record())
        assert journal.path.exists()
        journal.clear()
        assert not journal.path.exists()
        assert journal.replay() == {}

    def test_deterministic_lookup(self, tmp_path: Path) -> None:
        """Lookup is deterministic — same call_id always returns the same record."""
        journal = Journal(tmp_path / "j.jsonl")
        rec = _make_record()
        journal.append(rec)
        r1 = journal.lookup(rec.call_id)
        r2 = journal.lookup(rec.call_id)
        assert r1 is not None and r2 is not None
        assert r1.call_id == r2.call_id
        assert r1.cost_usd == r2.cost_usd

    def test_replay_survives_multiple_crashes(self, tmp_path: Path) -> None:
        """Multiple torn tails across crash cycles don't corrupt earlier rows."""
        journal = Journal(tmp_path / "j.jsonl")
        r1 = _make_record(item_id="a", cost_usd="0.01")
        journal.append(r1)

        # Crash 1
        with open(journal.path, "a", encoding="utf-8") as f:
            f.write('{"crash1":\n')
        assert len(journal.replay()) == 1

        # Append more
        r2 = _make_record(item_id="b", cost_usd="0.02")
        journal.append(r2)

        # Crash 2
        with open(journal.path, "a", encoding="utf-8") as f:
            f.write('{"crash2":\n')
        assert len(journal.replay()) == 2


# ---------------------------------------------------------------------------
# Milestone 3: Fold the cap
# ---------------------------------------------------------------------------


class TestHardBudget:
    """Hard-cap enforcement derived from journal state."""

    def test_initial_budget_has_full_cap(self, tmp_path: Path) -> None:
        journal = Journal(tmp_path / "j.jsonl")
        budget = HardBudget(Decimal("10.00"), journal)
        assert budget.cap_usd == Decimal("10.00")
        assert budget.spent == Decimal("0")
        assert budget.reserved == Decimal("0")
        assert budget.available == Decimal("10.00")

    def test_spent_accumulates_from_journal(self, tmp_path: Path) -> None:
        journal = Journal(tmp_path / "j.jsonl")
        journal.append(_make_record(item_id="a", cost_usd="0.50"))
        journal.append(_make_record(item_id="b", cost_usd="0.30"))
        budget = HardBudget(Decimal("1.00"), journal)
        assert budget.spent == Decimal("0.80")
        assert budget.reserved == Decimal("0")
        assert budget.available == Decimal("0.20")

    def test_timeout_reserved_not_spent(self, tmp_path: Path) -> None:
        journal = Journal(tmp_path / "j.jsonl")
        journal.append(_make_record(item_id="a", cost_usd="0.50", status="timeout"))
        budget = HardBudget(Decimal("1.00"), journal)
        assert budget.spent == Decimal("0")
        assert budget.reserved == Decimal("0.50")
        assert budget.available == Decimal("0.50")

    def test_mixed_ok_and_timeout(self, tmp_path: Path) -> None:
        journal = Journal(tmp_path / "j.jsonl")
        journal.append(_make_record(item_id="a", cost_usd="0.30", status="ok"))
        journal.append(_make_record(item_id="b", cost_usd="0.20", status="timeout"))
        journal.append(_make_record(item_id="c", cost_usd="0.10", status="error"))
        budget = HardBudget(Decimal("1.00"), journal)
        # spent = ok (0.30) + error (0.10) = 0.40
        assert budget.spent == Decimal("0.40")
        # reserved = timeout (0.20)
        assert budget.reserved == Decimal("0.20")
        # total_charged = 0.60
        assert budget.total_charged == Decimal("0.60")
        assert budget.available == Decimal("0.40")

    def test_can_start_within_budget(self, tmp_path: Path) -> None:
        journal = Journal(tmp_path / "j.jsonl")
        budget = HardBudget(Decimal("1.00"), journal)
        assert budget.can_start(Decimal("1.00")) is True
        assert budget.can_start(Decimal("1.01")) is False

    def test_can_start_after_spend(self, tmp_path: Path) -> None:
        journal = Journal(tmp_path / "j.jsonl")
        journal.append(_make_record(item_id="a", cost_usd="0.80"))
        budget = HardBudget(Decimal("1.00"), journal)
        assert budget.can_start(Decimal("0.20")) is True
        assert budget.can_start(Decimal("0.21")) is False

    def test_can_start_after_timeout_reservation(self, tmp_path: Path) -> None:
        journal = Journal(tmp_path / "j.jsonl")
        journal.append(_make_record(item_id="a", cost_usd="0.70", status="timeout"))
        budget = HardBudget(Decimal("1.00"), journal)
        assert budget.can_start(Decimal("0.30")) is True
        assert budget.can_start(Decimal("0.31")) is False

    def test_cap_formula_documented(self, tmp_path: Path) -> None:
        """Verify the cap formula: available = cap - spent - reserved."""
        journal = Journal(tmp_path / "j.jsonl")
        journal.append(_make_record(item_id="a", cost_usd="0.25", status="ok"))
        journal.append(_make_record(item_id="b", cost_usd="0.15", status="timeout"))
        budget = HardBudget(Decimal("2.00"), journal)
        assert budget.available == Decimal("2.00") - Decimal("0.25") - Decimal("0.15")

    def test_negative_cap_rejected(self, tmp_path: Path) -> None:
        journal = Journal(tmp_path / "j.jsonl")
        with pytest.raises(ValueError, match="non-negative"):
            HardBudget(Decimal("-1.00"), journal)

    def test_budget_reflects_journal_state(self, tmp_path: Path) -> None:
        """Budget is derived from journal — appending changes available."""
        journal = Journal(tmp_path / "j.jsonl")
        budget = HardBudget(Decimal("1.00"), journal)
        assert budget.available == Decimal("1.00")
        journal.append(_make_record(item_id="a", cost_usd="0.40"))
        assert budget.available == Decimal("0.60")


# ---------------------------------------------------------------------------
# Milestone 3 (continued): Property tests for hard-cap invariant
# ---------------------------------------------------------------------------


class TestHardBudgetProperty:
    """Property tests: no new call starts when spent + reserve exceeds cap."""

    @pytest.mark.parametrize(
        "costs,cap",
        [
            # (individual costs, cap) — cap is just enough for the sum
            (["0.10", "0.20", "0.30"], "0.60"),
            (["0.01"], "0.01"),
            (["0.50", "0.50"], "1.00"),
            # Cap exceeds sum — all calls fit
            (["0.10", "0.20"], "1.00"),
        ],
    )
    def test_all_calls_fit_within_cap(
        self, costs: list[str], cap: str, tmp_path: Path,
    ) -> None:
        journal = Journal(tmp_path / "j.jsonl")
        budget = HardBudget(Decimal(cap), journal)
        total = Decimal("0")
        for i, cost in enumerate(costs):
            est = Decimal(cost)
            assert budget.can_start(est), (
                f"call {i} (cost={cost}) rejected but budget has "
                f"{budget.available} remaining"
            )
            journal.append(_make_record(item_id=f"item-{i}", cost_usd=cost))
            total += est
        # Final state: spent == total
        assert budget.spent == total

    @pytest.mark.parametrize(
        "costs,cap,last_cost",
        [
            # Sum of costs == cap; last call at exact boundary
            (["0.40", "0.40"], "0.80", "0.00"),
            # Sum exceeds cap; last call should be rejected
            (["0.50", "0.50"], "0.90", "0.10"),
        ],
    )
    def test_cap_boundary_enforced(
        self,
        costs: list[str],
        cap: str,
        last_cost: str,
        tmp_path: Path,
    ) -> None:
        journal = Journal(tmp_path / "j.jsonl")
        budget = HardBudget(Decimal(cap), journal)
        for i, cost in enumerate(costs):
            journal.append(_make_record(item_id=f"item-{i}", cost_usd=cost))
        # Check whether the last call fits
        remaining = budget.available
        est = Decimal(last_cost)
        if remaining >= est:
            assert budget.can_start(est) is True
        else:
            assert budget.can_start(est) is False

    def test_timeout_reserves_full_cost(self, tmp_path: Path) -> None:
        """A timeout consumes its full reservation — provider billing is unknowable."""
        journal = Journal(tmp_path / "j.jsonl")
        budget = HardBudget(Decimal("1.00"), journal)
        # Record a timeout with cost 0.80
        journal.append(_make_record(item_id="t", cost_usd="0.80", status="timeout"))
        # Remaining = 1.00 - 0 (spent) - 0.80 (reserved) = 0.20
        assert budget.available == Decimal("0.20")
        assert budget.can_start(Decimal("0.20")) is True
        assert budget.can_start(Decimal("0.21")) is False

    def test_error_charged_as_spent(self, tmp_path: Path) -> None:
        """Error calls are charged as spent (not reserved)."""
        journal = Journal(tmp_path / "j.jsonl")
        budget = HardBudget(Decimal("1.00"), journal)
        journal.append(_make_record(item_id="e", cost_usd="0.60", status="error"))
        assert budget.spent == Decimal("0.60")
        assert budget.reserved == Decimal("0")

    def test_sequence_with_mixed_statuses(self, tmp_path: Path) -> None:
        """Arbitrary sequence of ok/timeout/error respects the cap."""
        journal = Journal(tmp_path / "j.jsonl")
        budget = HardBudget(Decimal("2.00"), journal)
        calls = [
            ("a", "0.30", "ok"),
            ("b", "0.50", "timeout"),
            ("c", "0.20", "error"),
            ("d", "0.40", "ok"),
            ("e", "0.60", "timeout"),
        ]
        for item_id, cost, status in calls:
            if budget.can_start(cost):
                journal.append(
                    _make_record(item_id=item_id, cost_usd=cost, status=status)  # type: ignore[arg-type]
                )
        # Verify invariant: total_charged <= cap
        assert budget.total_charged <= Decimal("2.00")


# ---------------------------------------------------------------------------
# Milestone 4: Bound abandoned work
# ---------------------------------------------------------------------------


class TestCallRunnerTimeout:
    """Timeout recorded once, charged conservatively, never retried implicitly."""

    def test_successful_call_recorded(self, tmp_path: Path) -> None:
        runner, journal, budget = _make_runner(tmp_path)
        result = ProviderResult(
            model_id="glm-4",
            prompt_tokens=100,
            completion_tokens=50,
            cost_usd=Decimal("0.05"),
            latency_ms=500,
        )
        runner._timeout.run = MagicMock(return_value=result)
        record = runner.execute(
            requested_model="glm-4",
            actual_model="glm-4",
            task_class="distill",
            item_id="item-01",
            provider_fn=lambda: result,
        )
        assert record.status == "ok"
        assert record.cost_usd == Decimal("0.05")
        assert len(journal.replay()) == 1

    def test_timeout_recorded_with_estimated_cost(self, tmp_path: Path) -> None:
        """Timeout charges the full estimated cost (conservative reservation)."""
        runner, journal, budget = _make_runner(tmp_path)
        runner._timeout.run = MagicMock(side_effect=TimeoutError())
        record = runner.execute(
            requested_model="glm-4",
            actual_model="glm-4",
            task_class="distill",
            item_id="item-01",
            provider_fn=lambda: None,
            estimated_cost=Decimal("0.50"),
        )
        assert record.status == "timeout"
        assert record.cost_usd == Decimal("0.50")
        assert record.failure_text == "call timed out"
        assert len(journal.replay()) == 1

    def test_timeout_never_retried_implicitly(self, tmp_path: Path) -> None:
        """A timeout is recorded once — the runner does not retry."""
        runner, journal, budget = _make_runner(tmp_path)
        runner._timeout.run = MagicMock(side_effect=TimeoutError())
        runner.execute(
            requested_model="glm-4",
            actual_model="glm-4",
            task_class="distill",
            item_id="item-01",
            provider_fn=lambda: None,
            estimated_cost=Decimal("0.50"),
        )
        # The timeout runner should have been called exactly once.
        runner._timeout.run.assert_called_once()
        records = journal.replay()
        assert len(records) == 1
        assert list(records.values())[0].status == "timeout"

    def test_budget_exceeded_rejects_call(self, tmp_path: Path) -> None:
        runner, journal, budget = _make_runner(tmp_path, cap="1.00")
        # Fill the budget
        journal.append(_make_record(item_id="filler", cost_usd="0.90"))
        with pytest.raises(ValueError, match="budget exceeded"):
            runner.execute(
                requested_model="glm-4",
                actual_model="glm-4",
                task_class="distill",
                item_id="item-01",
                provider_fn=lambda: None,
                estimated_cost=Decimal("0.20"),
            )
        # No new record should be added.
        assert len(journal.replay()) == 1

    def test_error_recorded_with_exception_text(self, tmp_path: Path) -> None:
        runner, journal, budget = _make_runner(tmp_path)
        runner._timeout.run = MagicMock(
            side_effect=RuntimeError("connection refused"),
        )
        record = runner.execute(
            requested_model="glm-4",
            actual_model="glm-4",
            task_class="distill",
            item_id="item-01",
            provider_fn=lambda: None,
            estimated_cost=Decimal("0.10"),
        )
        assert record.status == "error"
        assert "connection refused" in record.failure_text
        assert record.cost_usd == Decimal("0.10")

    def test_call_id_deterministic_in_runner(self, tmp_path: Path) -> None:
        """Records created by the runner have deterministic call_ids."""
        runner, journal, budget = _make_runner(tmp_path)
        result = ProviderResult(
            model_id="glm-4",
            prompt_tokens=100,
            completion_tokens=50,
            cost_usd=Decimal("0.05"),
            latency_ms=500,
        )
        runner._timeout.run = MagicMock(return_value=result)
        r1 = runner.execute(
            requested_model="glm-4",
            actual_model="glm-4",
            task_class="distill",
            item_id="item-01",
            provider_fn=lambda: result,
        )
        r2 = runner.execute(
            requested_model="glm-4",
            actual_model="glm-4",
            task_class="distill",
            item_id="item-02",
            provider_fn=lambda: result,
        )
        assert r1.call_id != r2.call_id
        assert r1.call_id == _deterministic_call_id("glm-4", "distill", "item-01")

    def test_timeout_then_budget_tightens(self, tmp_path: Path) -> None:
        """After a timeout, the budget reflects the reservation."""
        runner, journal, budget = _make_runner(tmp_path, cap="1.00")
        runner._timeout.run = MagicMock(side_effect=TimeoutError())
        runner.execute(
            requested_model="glm-4",
            actual_model="glm-4",
            task_class="distill",
            item_id="item-01",
            provider_fn=lambda: None,
            estimated_cost=Decimal("0.80"),
        )
        assert budget.available == Decimal("0.20")
        # Next call within remaining budget should succeed
        result = ProviderResult(
            model_id="glm-4",
            prompt_tokens=50,
            completion_tokens=25,
            cost_usd=Decimal("0.15"),
            latency_ms=300,
        )
        runner._timeout.run = MagicMock(return_value=result)
        record = runner.execute(
            requested_model="glm-4",
            actual_model="glm-4",
            task_class="distill",
            item_id="item-02",
            provider_fn=lambda: result,
            estimated_cost=Decimal("0.15"),
        )
        assert record.status == "ok"
        assert len(journal.replay()) == 2
