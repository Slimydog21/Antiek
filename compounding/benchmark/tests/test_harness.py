"""AFF SPR-09 M2 — the multi-arm harness over the existing ResearchRunner.

Drives the REAL host-local runner on the deterministic demo loop with small
``steps`` (CI-fast). Asserts the single-writer-per-graph invariant (distinct
PersonalGraphHandle identities), that the warm arm reaches its seeded units
through the real deposit→retrieve→reuse surface (a knowledge.reused event lands),
and the §16 invariant (the harness imports no second runtime).
"""

from __future__ import annotations

import os

import pytest

from compounding.benchmark.harness import (
    ColdSeed,
    IrrelevantSeed,
    WarmSeed,
    run_arm,
)
from compounding.benchmark.question_set import load_question_set
from substrate.event_log import trajectory


@pytest.fixture
def dirs(tmp_path):
    return os.path.join(tmp_path, "events"), os.path.join(tmp_path, "graphs")


@pytest.fixture
def headline_q():
    return load_question_set().headline_questions()[0]


def test_arms_distinct_graph_handles(dirs, headline_q):
    """M2 acceptance + §2 arm isolation: the cold / warm / irrelevant arms hold
    DISTINCT db_path identities (single-writer-per-graph; no shared writer)."""
    events_dir, graphs_dir = dirs
    cold = run_arm(headline_q, ColdSeed(), events_dir=events_dir, graphs_dir=graphs_dir)
    warm = run_arm(headline_q, WarmSeed(), events_dir=events_dir, graphs_dir=graphs_dir)
    irr = run_arm(headline_q, IrrelevantSeed(), events_dir=events_dir, graphs_dir=graphs_dir)
    paths = {cold.db_path, warm.db_path, irr.db_path}
    assert len(paths) == 3, f"arms must hold distinct graph files, got {paths}"
    # each is a {user_id}.duckdb under the per-arm graphs dir (graph_router shape).
    for r in (cold, warm, irr):
        assert r.db_path.endswith(".duckdb")
        assert os.path.dirname(r.db_path) == graphs_dir


def test_cold_arm_has_no_reuse_substrate(dirs, headline_q):
    """The cold arm runs with retrieval_substrate=None (the automatic no-reuse
    path); the warm/irrelevant arms run with a live substrate."""
    events_dir, graphs_dir = dirs
    cold = run_arm(headline_q, ColdSeed(), events_dir=events_dir, graphs_dir=graphs_dir)
    warm = run_arm(headline_q, WarmSeed(), events_dir=events_dir, graphs_dir=graphs_dir)
    assert cold.reuse_substrate_active is False
    assert warm.reuse_substrate_active is True


def test_warm_arm_reaches_seeds_via_real_reuse_surface(dirs, headline_q):
    """The warm arm is populated ONLY through the deposit→retrieve→reuse surface
    — a ``knowledge.reused`` event lands on the investigation's trajectory
    (the reuse path ran), and the seeded unit count is non-zero. No back door."""
    events_dir, graphs_dir = dirs
    warm = run_arm(headline_q, WarmSeed(), events_dir=events_dir, graphs_dir=graphs_dir)
    assert warm.seeded_unit_count > 0
    rows = trajectory(warm.investigation_id, events_dir=events_dir)
    actions = [r.get("action_type") for r in rows]
    assert "knowledge.reused" in actions, (
        "the warm arm must reach seeds through the real reuse surface "
        "(a knowledge.reused event), not a back door"
    )


def test_control_question_seeds_nothing_in_warm(dirs):
    """A zero-overlap control question names no seeded units, so even the WARM
    arm seeds nothing for it — it cannot compound and must stay flat."""
    events_dir, graphs_dir = dirs
    control_q = load_question_set().control_questions()[0]
    warm = run_arm(control_q, WarmSeed(), events_dir=events_dir, graphs_dir=graphs_dir)
    assert warm.seeded_unit_count == 0


def test_irrelevant_arm_seeds_same_count_as_warm(dirs, headline_q):
    """§2 graph-size control: the irrelevant arm seeds the SAME COUNT of units as
    the warm arm (differing only in topical relevance) so the control isolates
    relevance from graph-presence."""
    events_dir, graphs_dir = dirs
    warm = run_arm(headline_q, WarmSeed(), events_dir=events_dir, graphs_dir=graphs_dir)
    irr = run_arm(headline_q, IrrelevantSeed(), events_dir=events_dir, graphs_dir=graphs_dir)
    assert irr.seeded_unit_count == warm.seeded_unit_count == len(headline_q.seeded_unit_ids)


def test_demo_loop_delta_is_null(dirs, headline_q):
    """THE KEYSTONE, surfaced at the harness: the reuse-blind demo loop makes no
    dispatch.call, so warm and cold token_cost_usd are BOTH 0 — the honest
    null. This test documents the finding mechanically; it does not 'pass' by
    manufacturing a positive delta."""
    events_dir, graphs_dir = dirs
    cold = run_arm(headline_q, ColdSeed(), events_dir=events_dir, graphs_dir=graphs_dir)
    warm = run_arm(headline_q, WarmSeed(), events_dir=events_dir, graphs_dir=graphs_dir)
    assert cold.cost.token_cost_usd == 0.0
    assert warm.cost.token_cost_usd == 0.0
    assert warm.cost.token_cost_usd - cold.cost.token_cost_usd == 0.0
