"""Antiek-bench weekly orchestrator — recursive loop closure."""

from __future__ import annotations

from pathlib import Path

from substrate.antiek_bench.recorder import UsageEvent
from substrate.antiek_bench.runner import RawModelOutput, RunResult
from substrate.antiek_bench.scorer import ScoreVerdict
from substrate.antiek_bench.weekly import (
    WeekEvidence,
    close_week,
    default_laplace_weights,
    iso_week_id,
)


def _result(
    *,
    task: str = "reasoning::two_step",
    candidate: str = "gpt-5.5",
    score: float = 1.0,
    success: bool = True,
    week: str = "2026-W28",
) -> RunResult:
    verdict = ScoreVerdict(
        task_id=task,
        candidate_model_id=candidate,
        method="exact",
        score=score,
        success=success,
        rationale="match",
    )
    return RunResult(
        verdict=verdict,
        raw=RawModelOutput(model_id=candidate, raw_output="C is true.", cost_usd=0.001),
        week_id=week,
    )


def test_iso_week_id_format() -> None:
    from datetime import date

    assert iso_week_id(date(2026, 7, 9)) == "2026-W28"


def test_close_week_records_and_produces_dual_output(tmp_path: Path) -> None:
    ledger = tmp_path / "bench.jsonl"
    evidence = close_week(
        run_results=[_result(), _result(task="code::fix_off_by_one", success=False, score=0.0)],
        ledger_path=ledger,
    )
    assert isinstance(evidence, WeekEvidence)
    assert evidence.week_id == "2026-W28"
    assert len(evidence.view_records) == 2
    assert len(evidence.usage_events) == 2
    assert evidence.n_records == 2
    assert evidence.incomplete is False


def test_close_week_marks_incomplete_with_pending(tmp_path: Path) -> None:
    ledger = tmp_path / "bench.jsonl"
    pending = ScoreVerdict(
        task_id="reading_comprehension::main_claim",
        candidate_model_id="gpt-5.5",
        method="human",
        pending=True,
    )
    evidence = close_week(
        run_results=[
            RunResult(
                verdict=pending,
                raw=RawModelOutput(model_id="gpt-5.5", raw_output="draft"),
                week_id="2026-W28",
            )
        ],
        ledger_path=ledger,
    )
    assert evidence.incomplete is True
    assert evidence.view_records[0].score is None


def test_recursive_loop_weights_sum_to_exactly_one(tmp_path: Path) -> None:
    # The operator's "recursive self-rewriting" edge: this week's failures → next week's weights.
    ledger = tmp_path / "bench.jsonl"
    evidence = close_week(
        run_results=[
            _result(task="reasoning::hard", success=False, score=0.0),
            _result(task="code::easy", success=True, score=1.0),
        ],
        ledger_path=ledger,
    )
    assert evidence.next_week_weights
    total = round(sum(evidence.next_week_weights.values()), 8)
    assert abs(total - 1.0) < 1e-9  # exactly 1.0 (largest-remainder conservation)


def test_failure_driven_weights_upweight_failed_tasks() -> None:
    # More failures → more bench attention next week.
    events = [
        UsageEvent(task="reasoning::always_fails", success=False),
        UsageEvent(task="reasoning::always_fails", success=False),
        UsageEvent(task="code::always_passes", success=True),
    ]
    weights = default_laplace_weights(events=events)
    # reasoning::always_fails should get MORE weight than code::always_passes
    assert weights["reasoning::always_fails"] > weights["code::always_passes"]


def test_pending_events_ignored_in_weights() -> None:
    events = [
        UsageEvent(task="t1", success=None),  # pending — ignored
        UsageEvent(task="t2", success=False),
    ]
    weights = default_laplace_weights(events=events)
    assert "t1" not in weights  # no measured events
    assert "t2" in weights


def test_empty_week_produces_empty_evidence(tmp_path: Path) -> None:
    ledger = tmp_path / "bench.jsonl"
    evidence = close_week(run_results=[], ledger_path=ledger)
    assert evidence.view_records == []
    assert evidence.next_week_weights == {}
    assert evidence.n_records == 0


def test_unauthorized_dispatch_flagged_honestly(tmp_path: Path) -> None:
    # Pure runner results always have live_dispatch_authorized=False; surfaced honestly.
    ledger = tmp_path / "bench.jsonl"
    evidence = close_week(run_results=[_result()], ledger_path=ledger)
    assert evidence.any_unauthorized_dispatch is True


def test_injected_weight_proposer_used(tmp_path: Path) -> None:
    class FixedProposer:
        def propose(
            self,
            *,
            events: list[UsageEvent],
            prior_weights: dict[str, float] | None = None,
        ) -> dict[str, float]:
            return {"custom": 1.0}

    ledger = tmp_path / "bench.jsonl"
    evidence = close_week(
        run_results=[_result()],
        ledger_path=ledger,
        weight_proposer=FixedProposer(),
    )
    assert evidence.next_week_weights == {"custom": 1.0}
