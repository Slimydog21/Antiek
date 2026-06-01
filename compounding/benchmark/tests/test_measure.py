"""AFF SPR-09 M3 — cost-to-resolve measurement over a synthetic trajectory.

Feeds a trajectory of KNOWN events (in the exact ``substrate.event_log.trajectory``
row shape: action_type / payload / emitted_at) and asserts the measurement
returns the EXACT expected counts. The synthetic trajectory is the right altitude
— it isolates the arithmetic of the measurement from the (reuse-blind) demo loop,
so a wrong sum is caught here regardless of what any loop produces.
"""

from __future__ import annotations

from compounding.benchmark.measure import measure_trajectory


def _row(action_type, *, payload=None, emitted_at="2026-05-31T10:00:00Z"):
    return {"action_type": action_type, "payload": payload or {}, "emitted_at": emitted_at,
            "event_id": "evt-x"}


def _dispatch(cost, *, inp=100, out=50, latency=200, at="2026-05-31T10:00:00Z"):
    return _row("dispatch.call", payload={
        "cost_usd": cost, "input_tokens": inp, "output_tokens": out, "latency_ms": latency,
    }, emitted_at=at)


def test_exact_counts_from_known_trajectory():
    """M3 acceptance: the six fields are summed/counted exactly off the rows."""
    rows = [
        _dispatch(0.10, inp=100, out=50, latency=200, at="2026-05-31T10:00:00Z"),
        _dispatch(0.20, inp=300, out=120, latency=400, at="2026-05-31T10:00:01Z"),
        _row("connector.delivered", emitted_at="2026-05-31T10:00:01Z"),
        _row("evidence.retrieve.delivered", emitted_at="2026-05-31T10:00:01Z"),
        _row("connector.delivered", emitted_at="2026-05-31T10:00:02Z"),
        _row("graph.node.inserted", payload={"node_id": "n-1"}, emitted_at="2026-05-31T10:00:02Z"),
        _row("graph.node.inserted", payload={"node_id": "n-2"}, emitted_at="2026-05-31T10:00:03Z"),
        # an event we don't measure — must be ignored.
        _row("investigation.completed", emitted_at="2026-05-31T10:00:03Z"),
    ]
    m = measure_trajectory(rows)
    assert m.token_cost_usd == 0.30
    assert m.input_tokens == 400
    assert m.output_tokens == 170
    assert m.sources_fetched == 3       # 2 connector + 1 evidence
    assert m.novel_insight_yield == 2   # n-1, n-2 both novel (no seed)
    assert m.redundant_rederivations == 0
    assert m.dispatch_calls == 2
    assert m.summed_latency_ms == 600
    # wall_ms = span 10:00:00 → 10:00:03 = 3000 ms
    assert m.wall_ms == 3000.0


def test_redundant_rederivation_against_seed():
    """A graph.node.inserted whose node_id is already SEEDED is a re-derivation
    the warm graph should have short-circuited — content-addressed id collision.
    Counted as redundant, NOT as novel yield."""
    rows = [
        _row("graph.node.inserted", payload={"node_id": "seeded-A"}),  # re-derived
        _row("graph.node.inserted", payload={"node_id": "fresh-B"}),   # genuinely novel
        _row("graph.node.inserted", payload={"node_id": "seeded-C"}),  # re-derived
    ]
    m = measure_trajectory(rows, seeded_node_ids=["seeded-A", "seeded-C", "seeded-unused"])
    assert m.novel_insight_yield == 1            # only fresh-B
    assert m.redundant_rederivations == 2        # seeded-A, seeded-C


def test_no_cost_when_no_dispatch_calls():
    """The honest mock-path shape: a trajectory with NO dispatch.call events has
    token_cost_usd == 0 (the demo loop makes no provider calls). This is the
    keystone null, surfaced at the measurement layer."""
    rows = [
        _row("investigation.start_requested", emitted_at="2026-05-31T10:00:00Z"),
        _row("knowledge.reused", emitted_at="2026-05-31T10:00:00Z"),
        _row("investigation.completed", emitted_at="2026-05-31T10:00:00Z"),
    ]
    m = measure_trajectory(rows)
    assert m.token_cost_usd == 0.0
    assert m.dispatch_calls == 0
    assert m.sources_fetched == 0


def test_empty_trajectory_is_all_zero():
    m = measure_trajectory([])
    assert m.token_cost_usd == 0.0
    assert m.wall_ms == 0.0
    assert m.novel_insight_yield == 0
