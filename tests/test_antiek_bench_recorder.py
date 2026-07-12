"""Antiek-bench recorder — tamper-evident dual-output ledger (§10 invariants #1,#6,#7)."""

from __future__ import annotations

import json

import pytest

from substrate.antiek_bench.recorder import (
    GENESIS_HASH,
    LedgerCorruption,
    UsageEvent,
    ViewRecord,
    append_to_ledger,
    read_ledger,
    record_verdict,
    week_incomplete,
    week_usage_events,
    week_view_records,
)
from substrate.antiek_bench.scorer import HumanScorer, ScoreVerdict
from substrate.antiek_bench.task_registry import BenchTask


def _exact_task(expected: str = "C is true.") -> BenchTask:
    return BenchTask(
        task_id="reasoning::two_step",
        family="reasoning",
        prompt="p",
        scoring="exact",
        expected=expected,
    )


def _scored_verdict(*, candidate: str = "gpt-5.5", score: float = 1.0, success: bool = True) -> ScoreVerdict:
    return ScoreVerdict(
        task_id="reasoning::two_step",
        candidate_model_id=candidate,
        method="exact",
        score=score,
        success=success,
        rationale="match",
    )


# --- dual output (frozen §2 contract shapes) ------------------------------ #


def test_one_verdict_produces_both_view_record_and_usage_event() -> None:
    verdict = _scored_verdict()
    record = record_verdict(verdict, week_id="2026-W28")
    assert isinstance(record.view_record, ViewRecord)
    assert isinstance(record.usage_event, UsageEvent)
    # view record matches the frozen shape
    assert record.view_record.task == "reasoning::two_step"
    assert record.view_record.model_id == "gpt-5.5"
    assert record.view_record.score == 1.0
    assert record.view_record.n_runs == 1
    # usage event matches the frozen shape
    assert record.usage_event.task == "reasoning::two_step"
    assert record.usage_event.success is True


def test_failed_run_carries_success_false() -> None:
    verdict = _scored_verdict(success=False, score=0.0)
    record = record_verdict(verdict, week_id="2026-W28")
    assert record.usage_event.success is False
    assert record.view_record.score == 0.0


def test_pending_verdict_yields_null_score_and_success() -> None:
    # Invariant: pending → score=None, success=None (nothing invented).
    task = BenchTask(
        task_id="reading_comprehension::main_claim",
        family="reading_comprehension",
        prompt="p",
        scoring="human",
    )
    pending = HumanScorer().pending(task=task, candidate_model_id="gpt-5.5")
    record = record_verdict(pending, week_id="2026-W28")
    assert record.view_record.score is None
    assert record.usage_event.success is None
    assert record.pending is True


# --- tamper-evident hash chain -------------------------------------------- #


def test_first_record_chains_from_genesis() -> None:
    record = record_verdict(_scored_verdict(), week_id="2026-W28")
    assert record.prev_hash == GENESIS_HASH
    assert len(record.record_hash) == 64  # sha256 hex


def test_append_chains_records_correctly(tmp_path) -> None:  # type: ignore[no-untyped-def]
    ledger = tmp_path / "bench.jsonl"
    r1 = append_to_ledger(
        record_verdict(_scored_verdict(candidate="m1"), week_id="2026-W28"),
        ledger_path=ledger,
    )
    r2 = append_to_ledger(
        record_verdict(_scored_verdict(candidate="m2"), week_id="2026-W28"),
        ledger_path=ledger,
    )
    assert r1.prev_hash == GENESIS_HASH
    assert r2.prev_hash == r1.record_hash
    # re-read verifies the chain
    loaded = read_ledger(ledger)
    assert len(loaded) == 2
    assert loaded[1].prev_hash == loaded[0].record_hash


def test_tampered_payload_detected(tmp_path) -> None:  # type: ignore[no-untyped-def]
    # Invariant #6: chain break / tamper → LedgerCorruption, never silent recovery.
    ledger = tmp_path / "bench.jsonl"
    append_to_ledger(
        record_verdict(_scored_verdict(), week_id="2026-W28"),
        ledger_path=ledger,
    )
    # Corrupt the score in the persisted record.
    lines = ledger.read_text(encoding="utf-8").splitlines()
    obj = json.loads(lines[0])
    obj["score"] = 0.0  # was 1.0 — this changes the payload but not the hash
    lines[0] = json.dumps(obj)
    ledger.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(LedgerCorruption, match="record_hash mismatch"):
        read_ledger(ledger)


def test_broken_chain_detected(tmp_path) -> None:  # type: ignore[no-untyped-def]
    ledger = tmp_path / "bench.jsonl"
    append_to_ledger(
        record_verdict(_scored_verdict(), week_id="2026-W28"),
        ledger_path=ledger,
    )
    # Corrupt the prev_hash of a second record to simulate chain break.
    lines = ledger.read_text(encoding="utf-8").splitlines()
    obj = json.loads(lines[0])
    obj["prev_hash"] = "WRONG"
    lines[0] = json.dumps(obj)
    ledger.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(LedgerCorruption, match="hash chain broken"):
        read_ledger(ledger)


def test_absent_ledger_is_empty_not_corrupt(tmp_path) -> None:  # type: ignore[no-untyped-def]
    ledger = tmp_path / "nonexistent.jsonl"
    assert read_ledger(ledger) == []


# --- secrets redaction ---------------------------------------------------- #


def test_secret_token_in_payload_rejected() -> None:
    # Invariant: no api_key/raw_prompt in any persisted record.
    verdict = ScoreVerdict(
        task_id="t",
        candidate_model_id="sk-secret-key",  # contains 'sk-'
        method="exact",
        score=1.0,
        success=True,
        rationale="api_key should not appear",
    )
    with pytest.raises(ValueError, match="forbidden sensitive token"):
        record_verdict(verdict, week_id="2026-W28")


# --- week queries + incomplete ------------------------------------------- #


def test_week_views_and_events_filter_by_week(tmp_path) -> None:  # type: ignore[no-untyped-def]
    ledger = tmp_path / "bench.jsonl"
    for week in ("2026-W28", "2026-W29"):
        append_to_ledger(
            record_verdict(_scored_verdict(), week_id=week),
            ledger_path=ledger,
        )
    assert len(week_view_records(ledger, week_id="2026-W28")) == 1
    assert len(week_usage_events(ledger, week_id="2026-W29")) == 1


def test_week_incomplete_with_pending_record(tmp_path) -> None:  # type: ignore[no-untyped-def]
    ledger = tmp_path / "bench.jsonl"
    task = BenchTask(
        task_id="reading_comprehension::main_claim",
        family="reading_comprehension",
        prompt="p",
        scoring="human",
    )
    append_to_ledger(
        record_verdict(
            HumanScorer().pending(task=task, candidate_model_id="gpt-5.5"),
            week_id="2026-W28",
        ),
        ledger_path=ledger,
    )
    assert week_incomplete(ledger, week_id="2026-W28") is True


def test_week_complete_when_all_scored(tmp_path) -> None:  # type: ignore[no-untyped-def]
    ledger = tmp_path / "bench.jsonl"
    append_to_ledger(
        record_verdict(_scored_verdict(), week_id="2026-W28"),
        ledger_path=ledger,
    )
    assert week_incomplete(ledger, week_id="2026-W28") is False
    assert week_incomplete(ledger, week_id="2026-W99") is True  # no records
