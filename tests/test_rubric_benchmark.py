"""
Smoke tests for the inline-rubric latency benchmark.

We do NOT run the full 500-sample benchmark in pytest (that's a 60ms+
operation on a cold-cache CI worker; multiplied across 200+ test files
the cost compounds). Instead these tests cover:

- the fixture generator is deterministic on its seed;
- the scorer accepts the SimpleNamespace payloads the corpus produces;
- the BenchmarkResult dataclass holds the expected fields;
- ``--check-regression`` exits 0 when current ≈ baseline;
- ``--check-regression`` exits 2 on a synthetic regression injected
  into a temp baseline file;
- the percentile helper matches numpy semantics on the edge cases
  (single element, two elements, exact-fence values).

The real benchmark runs as a CI step (see ``.github/workflows/ci.yml``,
``Inline-rubric latency`` step) not as a pytest test.

Spec: ~/specs/antiek-hashimoto-engineering/sprint-e7-craft-benchmark.html
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmarks import fixtures, rubric_latency
from substrate.synthesis_rubric.scorer import score_synthesis


# ---------------------------------------------------------------------------
# Fixture generator determinism
# ---------------------------------------------------------------------------


def test_corpus_is_deterministic_on_default_seed() -> None:
    a = fixtures.build_corpus()
    b = fixtures.build_corpus()
    # We cannot compare SimpleNamespace by ``==`` (it compares by id), so
    # compare the materialised attrs that the scorer reads.
    assert len(a) == len(b) == fixtures.FIXTURE_COUNT
    for x, y in zip(a, b):
        assert x.conviction_level == y.conviction_level
        assert x.implicit_recommendation == y.implicit_recommendation
        assert len(x.thesis_components) == len(y.thesis_components)
        for cx, cy in zip(x.thesis_components, y.thesis_components):
            assert cx.claim == cy.claim
            assert cx.supporting_chunk_ids == cy.supporting_chunk_ids


def test_corpus_exercises_cross_product() -> None:
    """At least one fixture with each rubric outcome dimension."""
    corpus = fixtures.build_corpus()
    convictions = {f.conviction_level for f in corpus}
    citation_densities = {
        sum(1 for c in f.thesis_components if c.supporting_chunk_ids) / max(1, len(f.thesis_components))
        for f in corpus
    }
    constraints = {f.constraint_compliance.hard_constraints_satisfied for f in corpus}
    recommendations = {f.implicit_recommendation for f in corpus}
    assert len(convictions) >= 3, f"need varied conviction; got {convictions}"
    assert len(citation_densities) >= 3, "need varied citation density"
    assert constraints == {True, False}, "need both compliant and non-compliant"
    assert "insufficient_evidence" in recommendations, "need the floor case"
    assert "ship_thesis" in recommendations, "need the happy path"


def test_corpus_summary_count_matches() -> None:
    summary = fixtures.serialize_corpus_summary()
    assert summary["fixture_count"] == fixtures.FIXTURE_COUNT
    # voice_good + voice_sloppy must sum to fixture_count.
    rd = summary["recipe_distribution"]
    assert rd["voice_good"] + rd["voice_sloppy"] == fixtures.FIXTURE_COUNT
    assert rd["constraint_satisfied"] + rd["constraint_violated"] == fixtures.FIXTURE_COUNT


# ---------------------------------------------------------------------------
# Scorer accepts the corpus
# ---------------------------------------------------------------------------


def test_scorer_runs_on_every_fixture() -> None:
    """The scorer's duck-typed reads must succeed on every payload."""
    corpus = fixtures.build_corpus()
    for f in corpus:
        result = score_synthesis(f)
        assert 0.0 <= result.composite <= 1.0
        assert 0.0 <= result.voice_style <= 1.0


def test_scorer_floors_insufficient_evidence() -> None:
    """``implicit_recommendation == 'insufficient_evidence'`` must
    floor the composite at ``INSUFFICIENT_EVIDENCE_FLOOR``. This protects
    the §14.4 0.5 gate from being passed by sub-component noise on a
    payload the synthesizer itself declined to commit to."""
    corpus = fixtures.build_corpus()
    floored = [f for f in corpus if f.implicit_recommendation == "insufficient_evidence"]
    assert floored, "test corpus needs at least one insufficient_evidence fixture"
    for f in floored:
        result = score_synthesis(f)
        from substrate.synthesis_rubric.scorer import INSUFFICIENT_EVIDENCE_FLOOR

        assert result.composite <= INSUFFICIENT_EVIDENCE_FLOOR + 1e-9


# ---------------------------------------------------------------------------
# Percentile helper
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "samples,q,expected",
    [
        ([1.0], 50, 1.0),
        ([1.0], 95, 1.0),
        ([1.0, 2.0], 50, 1.5),
        ([1.0, 2.0, 3.0, 4.0, 5.0], 50, 3.0),
        ([1.0, 2.0, 3.0, 4.0, 5.0], 100, 5.0),
        ([1.0, 2.0, 3.0, 4.0, 5.0], 0, 1.0),
    ],
)
def test_percentile_basic(samples, q, expected) -> None:
    assert rubric_latency._percentile(sorted(samples), q) == pytest.approx(expected)


# ---------------------------------------------------------------------------
# Tiny benchmark + CI gate behavior
# ---------------------------------------------------------------------------


def test_benchmark_runs_tiny_sample_and_returns_result() -> None:
    """A 10-warmup + 20-sample benchmark must succeed and produce
    plausible numbers in pytest-time-budget (well under 1s)."""
    result = rubric_latency.run_benchmark(samples=20, warmup=10)
    assert result.samples == 20
    assert result.warmup == 10
    assert result.p50_us > 0
    assert result.p95_us >= result.p50_us
    assert result.p99_us >= result.p95_us
    assert result.max_us >= result.p99_us


def test_check_regression_passes_on_synthetic_match(tmp_path, monkeypatch) -> None:
    """Synthesize a baseline that matches current; check_regression must say so."""
    # Run a tiny benchmark to get a real result.
    result = rubric_latency.run_benchmark(samples=20, warmup=10)
    baseline_file = tmp_path / "baseline.json"
    baseline_file.write_text(
        json.dumps(
            {
                "result": {
                    "p95_us": result.p95_us,
                    "p50_us": result.p50_us,
                    "p99_us": result.p99_us,
                    "max_us": result.max_us,
                    "mean_us": result.mean_us,
                    "samples": result.samples,
                    "warmup": result.warmup,
                    "corpus_size": result.corpus_size,
                    "git_sha": "test",
                    "captured_at": "test",
                },
                "corpus_summary": {},
                "notes": "synthetic baseline for test",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(rubric_latency, "BASELINE_FILE", baseline_file)
    regressed, message = rubric_latency._check_regression(result, threshold_pct=10.0)
    assert not regressed, message
    assert "within tolerance" in message or "IMPROVED" in message


def test_check_regression_flags_synthetic_regression(tmp_path, monkeypatch) -> None:
    """Baseline at 100us, current at 200us → 100% regression → exit 2."""
    result = rubric_latency.BenchmarkResult(
        p50_us=100.0,
        p95_us=200.0,
        p99_us=210.0,
        max_us=220.0,
        mean_us=120.0,
        samples=500,
        warmup=10,
        corpus_size=100,
        git_sha="test",
        captured_at="test",
    )
    baseline_file = tmp_path / "baseline.json"
    baseline_file.write_text(
        json.dumps(
            {
                "result": {
                    "p95_us": 100.0,
                    "p50_us": 50.0,
                    "p99_us": 110.0,
                    "max_us": 120.0,
                    "mean_us": 60.0,
                    "samples": 500,
                    "warmup": 10,
                    "corpus_size": 100,
                    "git_sha": "test",
                    "captured_at": "test",
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(rubric_latency, "BASELINE_FILE", baseline_file)
    regressed, message = rubric_latency._check_regression(result, threshold_pct=10.0)
    assert regressed
    assert "REGRESSED" in message
    assert "+100.0%" in message


def test_check_regression_handles_missing_baseline(tmp_path, monkeypatch) -> None:
    """Missing baseline.json: not a regression — message says so."""
    result = rubric_latency.run_benchmark(samples=20, warmup=10)
    monkeypatch.setattr(rubric_latency, "BASELINE_FILE", tmp_path / "absent.json")
    regressed, message = rubric_latency._check_regression(result, threshold_pct=10.0)
    assert not regressed
    assert "no baseline" in message
    assert "--update-baseline" in message


# ---------------------------------------------------------------------------
# Baseline file shape (so a future maintainer reading it knows what's there)
# ---------------------------------------------------------------------------


def test_committed_baseline_has_required_fields() -> None:
    """The on-disk baseline.json must carry git_sha + captured_at +
    corpus_summary so the lock is recoverable."""
    baseline_file = Path(__file__).resolve().parent.parent / "benchmarks" / "baseline.json"
    assert baseline_file.exists(), (
        "benchmarks/baseline.json missing — run "
        "`python -m benchmarks.rubric_latency --update-baseline` to mint."
    )
    data = json.loads(baseline_file.read_text(encoding="utf-8"))
    assert "result" in data
    assert "corpus_summary" in data
    r = data["result"]
    for field in ("p50_us", "p95_us", "p99_us", "samples", "git_sha", "captured_at"):
        assert field in r, f"baseline result missing {field!r}"
    assert r["samples"] >= 100, "baseline should be a real run, not a smoke fixture"
