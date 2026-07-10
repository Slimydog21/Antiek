"""W0 deep-research eval harness: dataset, determinism, degradation red-proof,
comparability fail-closed, NOT_MEASURED honesty, bench bridge, journal."""

from __future__ import annotations

import dataclasses
import json
import math
from pathlib import Path

import pytest

import substrate.deep_research_eval as dre
from substrate.deep_research_eval import (
    AXES,
    EXPECTED_QUERY_COUNT,
    JUDGE_MODEL_ID,
    QUERIES_V1_SHA256,
    RUBRIC_VERSION,
    DatasetValidationError,
    EvalJournalCorruptionError,
    EvalRun,
    EvalRunJournal,
    IncompleteRunError,
    NotComparableError,
    Query,
    QueryDataset,
    RegressionThresholds,
    ResearchReport,
    SourceRef,
    compare_runs,
    deep_research_bench_record,
    default_dataset_path,
    load_dataset,
    run_eval,
)

# Private-import in tests is deliberate: the unpinned-digest sentinel is
# test-only and intentionally NOT part of the package's public surface.
from substrate.deep_research_eval.dataset import _TEST_ONLY_UNPINNED_DIGEST

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
    assert dataset.content_digest == QUERIES_V1_SHA256
    assert dataset.dataset_key == f"deep_research_eval_v1@1.0.0+{QUERIES_V1_SHA256}"

    # Structural validation fails closed on a mutated copy (frozen file itself
    # untouched; digest pin bypassed with the test-only sentinel so the
    # "exactly 20" invariant is exercised independently of the content pin).
    data = json.loads(default_dataset_path().read_text(encoding="utf-8"))
    data["queries"] = data["queries"][:19]
    truncated = tmp_path / "queries_truncated.json"
    truncated.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(DatasetValidationError, match="exactly 20"):
        load_dataset(truncated, expected_sha256=_TEST_ONLY_UNPINNED_DIGEST)


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
        f"deep_research_eval_v1@1.0.0+{QUERIES_V1_SHA256}",
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
        ("dataset_content_digest", "0" * 64),
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
    assert record["suite_version"] == healthy_run.comparability_key[0]
    assert record["suite_version"].endswith(f"+{QUERIES_V1_SHA256}")
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


# 8. Tamper-evidence: forged aggregates/completeness refuse deserialization.
def test_from_dict_rejects_forged_aggregates(
    dataset: QueryDataset, healthy_run: EvalRun
) -> None:
    forgeries: tuple[tuple[str, object], ...] = (
        ("mean_judge_score", 999.0),
        ("mean_coverage_hit_rate", 0.0),
        ("measured_count", 3),
        ("complete", False),
    )
    for field, forged_value in forgeries:
        data = healthy_run.to_dict()
        data[field] = forged_value
        with pytest.raises(ValueError, match="aggregates"):
            EvalRun.from_dict(data)

    forged_axes = healthy_run.to_dict()
    forged_axes["mean_axis_scores"]["completeness"] = 1.0
    with pytest.raises(ValueError, match="aggregates"):
        EvalRun.from_dict(forged_axes)

    # Forging complete=true onto an incomplete run must also refuse — this is
    # the laundering path into deep_research_bench_record.
    incomplete = run_eval(
        dataset, healthy_provider, malformed_judge, run_id_seed=SEED, week_id=WEEK_CANDIDATE
    )
    laundered = incomplete.to_dict()
    laundered["complete"] = True
    with pytest.raises(ValueError, match="aggregates"):
        EvalRun.from_dict(laundered)

    # Honest round-trip still deserializes.
    assert EvalRun.from_dict(healthy_run.to_dict()) == healthy_run


# 9. Tamper-evidence: out-of-range/NaN per-score values refuse deserialization.
def test_from_dict_rejects_out_of_range_score_values(healthy_run: EvalRun) -> None:
    for bad_value in (999.0, math.nan, math.inf, -0.1, True, "0.9"):
        data = healthy_run.to_dict()
        data["scores"][0]["judge_scores"]["completeness"] = bad_value
        with pytest.raises(ValueError):
            EvalRun.from_dict(data)
    data = healthy_run.to_dict()
    data["scores"][0]["coverage_hit_rate"] = 2.0
    with pytest.raises(ValueError, match="coverage_hit_rate"):
        EvalRun.from_dict(data)


# 10. NaN/negative/inf thresholds must refuse, never fail open to COMPARABLE.
def test_thresholds_must_be_finite_and_nonnegative(
    dataset: QueryDataset, healthy_run: EvalRun
) -> None:
    degraded = run_eval(
        dataset, degraded_provider, fixed_judge, run_id_seed=SEED, week_id=WEEK_CANDIDATE
    )
    bad_thresholds = (
        RegressionThresholds(max_judge_score_drop=math.nan, max_coverage_drop=math.nan),
        RegressionThresholds(max_judge_score_drop=-0.1, max_coverage_drop=0.1),
        RegressionThresholds(max_judge_score_drop=0.05, max_coverage_drop=math.inf),
    )
    for thresholds in bad_thresholds:
        with pytest.raises(ValueError, match="finite and non-negative"):
            compare_runs(healthy_run, degraded, thresholds)


# 11. Journal: blank middle row raises; torn tail stays tolerated.
def test_journal_blank_middle_row_raises_torn_tail_tolerated(
    healthy_run: EvalRun, tmp_path: Path
) -> None:
    path = tmp_path / "blank_middle.jsonl"
    journal = EvalRunJournal(path)
    journal.append(healthy_run)
    with path.open("ab") as fh:
        fh.write(b"\n")
    journal.append(healthy_run)
    with pytest.raises(EvalJournalCorruptionError, match="blank"):
        journal.read_all()

    torn_path = tmp_path / "torn_tail.jsonl"
    torn_journal = EvalRunJournal(torn_path)
    torn_journal.append(healthy_run)
    with torn_path.open("ab") as fh:
        fh.write(b'{"torn":')  # crash mid-append: unterminated final line
    assert torn_journal.read_all() == (healthy_run,)


# 12. Tamper-evidence: per-score identity tamper breaks the deterministic run_id.
def test_tampered_score_identity_breaks_run_id(healthy_run: EvalRun) -> None:
    data = healthy_run.to_dict()
    data["scores"][0]["query_id"] = "drq-999"  # aggregates unchanged, identity not
    with pytest.raises(ValueError, match="run_id"):
        EvalRun.from_dict(data)


# 13. Dataset content pin: same-version content edit fails closed.
def test_dataset_digest_pin(tmp_path: Path) -> None:
    data = json.loads(default_dataset_path().read_text(encoding="utf-8"))
    data["curation_note"] = "tampered without a version bump"
    tampered = tmp_path / "queries_tampered.json"
    tampered.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(DatasetValidationError, match="digest mismatch"):
        load_dataset(tampered)
    # Test-only escape hatch still applies full structural validation.
    variant = load_dataset(tampered, expected_sha256=_TEST_ONLY_UNPINNED_DIGEST)
    assert len(variant.queries) == EXPECTED_QUERY_COUNT


# 14. Tamper-evidence: forged hit_anchors break the deterministic run_id.
def test_tampered_hit_anchors_break_run_id(healthy_run: EvalRun) -> None:
    data = healthy_run.to_dict()
    # coverage_hit_rate untouched, so aggregates still agree — identity must not.
    data["scores"][0]["hit_anchors"] = ["forged anchor"]
    with pytest.raises(ValueError, match="run_id"):
        EvalRun.from_dict(data)


# 15. Content digest is in the comparability key: an altered same-version
# dataset loaded via the unpinned path can never be compared against the
# genuine frozen set — the identity difference is structural, not documented.
def test_unpinned_variant_gets_different_comparability_key(
    dataset: QueryDataset, healthy_run: EvalRun, tmp_path: Path
) -> None:
    data = json.loads(default_dataset_path().read_text(encoding="utf-8"))
    data["queries"][0]["expected_coverage"] = ["weakened anchor set"]
    variant_path = tmp_path / "queries_variant.json"
    variant_path.write_text(json.dumps(data), encoding="utf-8")
    variant = load_dataset(variant_path, expected_sha256=_TEST_ONLY_UNPINNED_DIGEST)

    assert variant.dataset_id == dataset.dataset_id
    assert variant.version == dataset.version  # same id@version...
    assert variant.content_digest != dataset.content_digest
    assert variant.dataset_key != dataset.dataset_key  # ...different identity

    variant_run = run_eval(
        variant, healthy_provider, fixed_judge, run_id_seed=SEED, week_id=WEEK_CANDIDATE
    )
    assert variant_run.comparability_key != healthy_run.comparability_key
    with pytest.raises(NotComparableError) as excinfo:
        compare_runs(healthy_run, variant_run)
    assert excinfo.value.verdict.verdict == "NOT_COMPARABLE"
    # And the variant run still round-trips through tamper-evident deserialization.
    assert EvalRun.from_dict(variant_run.to_dict()) == variant_run


# 16. The unpinned-digest sentinel is not part of the public package surface.
def test_unpinned_sentinel_not_exported() -> None:
    assert "UNPINNED_DIGEST_TEST_ONLY" not in dre.__all__
    assert not hasattr(dre, "UNPINNED_DIGEST_TEST_ONLY")
    assert "_TEST_ONLY_UNPINNED_DIGEST" not in dre.__all__
    assert not hasattr(dre, "_TEST_ONLY_UNPINNED_DIGEST")
