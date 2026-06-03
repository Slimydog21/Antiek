"""ACV SPR-06 — the reuse-CONSUMING benchmark run reports a REAL negative delta.

The companion to ``test_run_mock.py`` (which proves the DEMO loop's honest null).
This drives ``run_benchmark(loop_kind="consuming")`` over the real frozen set and
asserts the headline ``token_cost_usd`` delta is strictly NEGATIVE with a CI
upper bound below zero — the warm arm genuinely does less work because the
reuse-consuming loop short-circuits the sub-questions the pack covers — WHILE the
irrelevant-vs-cold control stays flat (the §2 validity gate still holds). This is
the measurement the keystone caveat said only a reuse-consuming loop could
produce.

These run against the CONSUMING loop; ``test_run_mock.py`` / ``test_harness.py``
run against the DEMO loop. Both must hold: the demo loop's null is honest, the
consuming loop's saving is real — and neither is faked.
"""

from __future__ import annotations

import os

import pytest

from compounding.benchmark.question_set import load_question_set
from compounding.benchmark.run import run_benchmark
from compounding.benchmark.validity import HEADLINE_METRIC, VALIDITY_VALID


@pytest.fixture
def dirs(tmp_path):
    return os.path.join(tmp_path, "events"), os.path.join(tmp_path, "graphs")


def test_consuming_run_reports_strictly_negative_delta(dirs):
    """The reuse-consuming benchmark's headline token_cost_usd delta is strictly
    negative AND its bootstrap CI upper bound is below zero — a real saving beyond
    the floor, not noise and not a clamp."""
    events_dir, graphs_dir = dirs
    qs = load_question_set()
    result = run_benchmark(
        qs, events_dir=events_dir, graphs_dir=graphs_dir,
        n=3, resamples=500, loop_kind="consuming",
    )
    assert result.loop_kind == "consuming"
    token = result.headline.metric(HEADLINE_METRIC)
    assert token.delta < 0.0, f"warm must be cheaper on the consuming loop, got {token.delta}"
    assert token.ci_high < 0.0, (
        f"the CI upper bound must be below 0 (saving beyond the floor), got "
        f"[{token.ci_low}, {token.ci_high}]"
    )


def test_consuming_run_control_stays_flat(dirs):
    """The irrelevant-vs-cold control stays flat on the consuming loop (off-topic
    units share no salient tokens with the questions → cover nothing → no
    saving), so the validity gate still passes — the saving is RELEVANCE, not
    graph-presence."""
    events_dir, graphs_dir = dirs
    qs = load_question_set()
    result = run_benchmark(
        qs, events_dir=events_dir, graphs_dir=graphs_dir,
        n=3, resamples=500, loop_kind="consuming",
    )
    control = next(c for c in result.comparisons if c.label == "irrelevant_vs_cold_control")
    ctrl = control.metric(HEADLINE_METRIC)
    assert ctrl.delta == 0.0, f"the irrelevant control must stay flat, got {ctrl.delta}"
    assert result.validity == VALIDITY_VALID


def test_consuming_run_is_not_the_demo_null(dirs):
    """Sanity that the consuming loop is doing something the demo loop is NOT: the
    same run on the demo loop reports a 0 delta, the consuming loop reports < 0.
    The demo loop's null and the consuming loop's saving are BOTH true."""
    events_dir, graphs_dir = dirs
    qs = load_question_set()
    demo = run_benchmark(
        qs, events_dir=os.path.join(events_dir, "demo"),
        graphs_dir=os.path.join(graphs_dir, "demo"), n=3, resamples=300, loop_kind="demo",
    )
    consuming = run_benchmark(
        qs, events_dir=os.path.join(events_dir, "cons"),
        graphs_dir=os.path.join(graphs_dir, "cons"), n=3, resamples=300, loop_kind="consuming",
    )
    assert demo.headline.metric(HEADLINE_METRIC).delta == 0.0
    assert consuming.headline.metric(HEADLINE_METRIC).delta < 0.0
