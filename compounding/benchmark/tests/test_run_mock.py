"""AFF SPR-09 M6 — the end-to-end mock run produces an honest artifact.

The fast version runs the benchmark with small ``n`` and few resamples over the
real frozen set, driving the real demo loop through measure→aggregate→validity,
and asserts the artifact shape + the honest demo-loop null (delta ≈ 0). The full
n=20 / 10k-resample run is marked ``slow`` (≈2 min) and excluded from the fast CI
suite; the committed artifact at ``results/spr09_run.json`` is its output.
"""

from __future__ import annotations

import os

import pytest

from compounding.benchmark.question_set import load_question_set
from compounding.benchmark.run import RESULTS_PATH, read_git_sha, run_benchmark
from compounding.benchmark.validity import HEADLINE_METRIC, VALIDITY_VALID


@pytest.fixture
def dirs(tmp_path):
    return os.path.join(tmp_path, "events"), os.path.join(tmp_path, "graphs")


def test_mock_run_reports_honest_null(dirs):
    """The demo loop is reuse-blind, so the headline token_cost_usd delta is 0
    (no dispatch.call cost differs) — the honest null, reported verbatim. The
    artifact carries a signed delta + finite CI for every metric."""
    events_dir, graphs_dir = dirs
    qs = load_question_set()
    result = run_benchmark(qs, events_dir=events_dir, graphs_dir=graphs_dir, n=3, resamples=500)

    assert result.mock_run is True
    assert result.frozen_sha == qs.frozen_sha
    assert result.n == 3

    # Every metric has a signed delta and a finite ci_low <= ci_high.
    for m in result.headline.metrics:
        assert m.ci_low <= m.ci_high
    token = result.headline.metric(HEADLINE_METRIC)
    assert token.delta == 0.0, "the reuse-blind demo loop must report a 0 token-cost delta"
    assert token.ci_low == 0.0 and token.ci_high == 0.0


def test_mock_run_validity_and_comparisons(dirs):
    """The mock run carries a validity verdict and all four §2 comparisons
    (headline, internal-probe-separate, partial, control)."""
    events_dir, graphs_dir = dirs
    qs = load_question_set()
    result = run_benchmark(qs, events_dir=events_dir, graphs_dir=graphs_dir, n=3, resamples=500)

    labels = {c.label for c in result.comparisons}
    assert "warm_vs_cold_high_overlap" in labels
    assert "warm_vs_cold_internal_probe" in labels   # reported SEPARATELY (§2 de-pool)
    assert "warm_vs_cold_partial" in labels
    assert "irrelevant_vs_cold_control" in labels
    # The control is flat (0) and within tolerance → valid (degenerate mock case).
    assert result.validity == VALIDITY_VALID


def test_committed_artifact_is_honest():
    """The committed artifact (results/spr09_run.json) is the mock-run output:
    mock_run true, a validity verdict, the frozen sha, and an honest (≈0)
    headline delta. git_sha is a documented placeholder until the orchestrator's
    commit re-stamps it."""
    import json

    if not os.path.exists(RESULTS_PATH):
        pytest.skip("artifact not yet generated (produced by `python -m compounding.benchmark.run`)")
    with open(RESULTS_PATH, encoding="utf-8") as f:
        art = json.load(f)
    assert art["mock_run"] is True
    assert art["frozen_sha"] == load_question_set().frozen_sha
    assert "validity" in art and art["validity"] in ("valid", "underpowered", "invalid")
    assert art["metrics"], "the artifact must carry a flat metrics list for the jq gate"
    headline_cost = next(m for m in art["metrics"] if m["metric"] == HEADLINE_METRIC)
    assert headline_cost["delta"] == 0.0  # the honest demo-loop null


def test_read_git_sha_returns_string():
    sha = read_git_sha()
    assert isinstance(sha, str) and sha


@pytest.mark.slow
def test_full_mock_run_n20(tmp_path):
    """The full n=20 / 10k-resample run over the whole frozen set. Slow (≈2 min);
    excluded from the fast CI suite. This is the command that produces the
    committed artifact."""
    qs = load_question_set()
    result = run_benchmark(
        qs,
        events_dir=os.path.join(tmp_path, "ev"),
        graphs_dir=os.path.join(tmp_path, "gr"),
        n=20,
    )
    assert result.n == 20
    assert result.headline.metric(HEADLINE_METRIC).delta == 0.0
