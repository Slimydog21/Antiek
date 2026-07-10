"""W0 deep-research eval harness: dataset, determinism, degradation red-proof,
comparability fail-closed, NOT_MEASURED honesty, bench bridge, journal."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from substrate.deep_research_eval import (
    AXES,
    EXPECTED_QUERY_COUNT,
    JUDGE_MODEL_ID,
    RUBRIC_VERSION,
    DatasetValidationError,
    EvalRun,
    EvalRunJournal,
    IncompleteRunError,
    NotComparableError,
    Query,
    QueryDataset,
    ResearchReport,
    SourceRef,
    compare_runs,
    deep_research_bench_record,
    default_dataset_path,
    load_dataset,
    run_eval,
)

WEEK_BASELINE = "2026-W27"
WEEK_CANDIDATE = "2026-W28"
SEED = "w0-test-seed"


def healthy_provider(query: Query) -> ResearchReport:
    """Stub provider that addresses every coverage anchor and cites sources."""
    answer = (
        f"Findings for {query.query_id}: "
        + " ".join(query.expected_coverage)
        + " — full grounded analysis."
    )
    sources = tuple(
        SourceRef(url=f"https://example.org/{query.query_id}/{i}", title=f"source {i}")
        for i in range(3)
    )
    return ResearchReport(
        answer_text=answer, sources=sources, tool_calls=8, tokens_in=4000, tokens_out=1200
    )


def degraded_provider(query: Query) -> ResearchReport:
    """Deliberately degraded: drops sources, truncates the answer so coverage
    anchors are missed (the W0 done-bar degradation)."""
    return ResearchReport(
        answer_text="no findings.", sources=(), tool_calls=1, tokens_in=100, tokens_out=10
    )


def fixed_judge(prompt: str) -> str:
    return json.dumps({axis: 0.9 for axis in AXES})


def malformed_judge(prompt: str) -> str:
    return "sure! the report scores about 0.9 overall {not json"


@pytest.fixture(scope="module")
def dataset() -> QueryDataset:
    return load_dataset()


@pytest.fixture(scope="module")
def healthy_run(dataset: QueryDataset) -> EvalRun:
    return run_eval(
        dataset, healthy_provider, fixed_judge, run_id_seed=SEED, week_id=WEEK_BASELINE
    )


# 1. Dataset loads + validates.
def test_dataset_loads_20_frozen_unique(dataset: QueryDataset, tmp_path: Path) -> None:
    assert len(dataset.queries) == EXPECTED_QUERY_COUNT == 20
    ids = [q.query_id for q in dataset.queries]
    assert len(set(ids)) == 20
    assert dataset.frozen is True
    assert dataset.version == "1.0.0"
    assert dataset.dataset_id == "deep_research_eval_v1"
    assert all(q.expected_coverage for q in dataset.queries)
    assert dataset.dataset_key == "deep_research_eval_v1@1.0.0"

    # Validation fails closed on a mutated copy (frozen file itself untouched).
    data = json.loads(default_dataset_path().read_text(encoding="utf-8"))
    data["queries"] = data["queries"][:19]
    truncated = tmp_path / "queries_truncated.json"
    truncated.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(DatasetValidationError, match="exactly 20"):
        load_dataset(truncated)


# 2. Deterministic run: same stubs → identical run_id + scores.
def test_deterministic_run(dataset: QueryDataset, healthy_run: EvalRun) -> None:
    rerun = run_eval(
        dataset, healthy_provider, fixed_judge, run_id_seed=SEED, week_id=WEEK_BASELINE
    )
    assert rerun.run_id == healthy_run.run_id
    assert rerun.scores == healthy_run.scores
    assert rerun == healthy_run
    assert healthy_run.run_id.startswith("dre_")
    assert healthy_run.complete is True
    assert healthy_run.mean_coverage_hit_rate == 1.0
    assert healthy_run.comparability_key == (
        "deep_research_eval_v1@1.0.0",
        RUBRIC_VERSION,
        JUDGE_MODEL_ID,
    )


# 3. Degradation red-proof (W0 done-bar).
def test_degraded_provider_detected_as_regression(
    dataset: QueryDataset, healthy_run: EvalRun
) -> None:
    degraded = run_eval(
        dataset, degraded_provider, fixed_judge, run_id_seed=SEED, week_id=WEEK_CANDIDATE
    )
    verdict = compare_runs(healthy_run, degraded)
    assert verdict.verdict == "REGRESSION"
    assert verdict.coverage_delta == -1.0
    assert any("coverage_hit_rate" in reason for reason in verdict.reasons)

    healthy_next_week = run_eval(
        dataset, healthy_provider, fixed_judge, run_id_seed=SEED, week_id=WEEK_CANDIDATE
    )
    assert compare_runs(healthy_run, healthy_next_week).verdict == "COMPARABLE"


# 4. Comparability fail-closed: different keys REFUSE, never a silent comparison.
def test_comparability_key_mismatch_refuses(healthy_run: EvalRun) -> None:
    for field, value in (
        ("rubric_version", "9.9.9"),
        ("judge_model_id", "other/judge-model"),
        ("dataset_version", "2.0.0"),
    ):
        candidate = dataclasses.replace(healthy_run, **{field: value})
        with pytest.raises(NotComparableError) as excinfo:
            compare_runs(healthy_run, candidate)
        assert excinfo.value.verdict.verdict == "NOT_COMPARABLE"
        assert "comparability keys differ" in str(excinfo.value)


# 5. Malformed judge → NOT_MEASURED, run incomplete, regression refused.
def test_malformed_judge_fails_closed(dataset: QueryDataset, healthy_run: EvalRun) -> None:
    unmeasured = run_eval(
        dataset, healthy_provider, malformed_judge, run_id_seed=SEED, week_id=WEEK_CANDIDATE
    )
    assert all(s.status == "NOT_MEASURED" for s in unmeasured.scores)
    assert all(s.judge_scores is None for s in unmeasured.scores)
    assert unmeasured.measured_count == 0
    assert unmeasured.complete is False

    # Partial judge failure also marks the aggregate incomplete.
    def flaky_judge(prompt: str) -> str:
        if "drq-010" in prompt or "sandbox isolation" in prompt:
            return "{broken"
        return fixed_judge(prompt)

    partial = run_eval(
        dataset, healthy_provider, flaky_judge, run_id_seed=SEED, week_id=WEEK_CANDIDATE
    )
    assert partial.complete is False
    assert 0 < partial.measured_count < len(partial.scores)

    for candidate in (unmeasured, partial):
        with pytest.raises(NotComparableError) as excinfo:
            compare_runs(healthy_run, candidate)
        assert excinfo.value.verdict.verdict == "NOT_COMPARABLE"
        assert "incomplete" in str(excinfo.value)


# 6. bench_bridge record shape.
def test_bench_bridge_record_shape(dataset: QueryDataset, healthy_run: EvalRun) -> None:
    record = deep_research_bench_record(healthy_run)
    assert record["by_task"] == "deep_research"
    assert record["by_task_class"] == {"deep_research": healthy_run.mean_judge_score}
    assert record["run_id"] == healthy_run.run_id
    assert record["week_id"] == WEEK_BASELINE
    assert record["suite_version"] == "deep_research_eval_v1@1.0.0"
    assert record["mean_score"] == healthy_run.mean_judge_score
    assert record["comparability_key"] == list(healthy_run.comparability_key)
    assert set(record["by_axis"]) == set(AXES)
    assert record["query_count"] == 20 and record["measured_count"] == 20
    # html-free: v1 has no UI, the record must not claim an html view.
    assert "html" not in json.dumps(record).lower()

    incomplete = run_eval(
        dataset, healthy_provider, malformed_judge, run_id_seed=SEED, week_id=WEEK_CANDIDATE
    )
    with pytest.raises(IncompleteRunError):
        deep_research_bench_record(incomplete)


# 7. Journal round-trip: append two runs, read back, order preserved.
def test_journal_round_trip(
    dataset: QueryDataset, healthy_run: EvalRun, tmp_path: Path
) -> None:
    journal = EvalRunJournal(tmp_path / "eval_runs.jsonl")
    degraded = run_eval(
        dataset, degraded_provider, fixed_judge, run_id_seed=SEED, week_id=WEEK_CANDIDATE
    )
    journal.append(healthy_run)
    journal.append(degraded)
    replayed = journal.read_all()
    assert replayed == (healthy_run, degraded)
    assert [r.run_id for r in replayed] == [healthy_run.run_id, degraded.run_id]
