"""Red-proofs: recursive Antiek-bench usage-learn proposals."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.bench_usage_learn_routes import (
    register_bench_usage_learn_routes,
)
from substrate.bench_presentation.usage_learn import propose_next_week_weights


def test_empty_usage_incomplete_no_invented_weights() -> None:
    p = propose_next_week_weights([], week_id="2026-W28")
    assert p.authority == "advisory"
    assert p.incomplete is True
    assert p.task_weights == []
    assert any("no usage" in n for n in p.notes)


def test_failures_upweight_task() -> None:
    p = propose_next_week_weights(
        [
            {"task": "deep_research", "success": False},
            {"task": "deep_research", "success": False},
            {"task": "deep_research", "success": False},
            {"task": "note_taker", "success": True},
            {"task": "note_taker", "success": True},
        ],
        week_id="2026-W28",
    )
    assert p.incomplete is False
    by_task = {t.task: t for t in p.task_weights}
    assert by_task["deep_research"].weight > by_task["note_taker"].weight
    assert by_task["deep_research"].n_failure == 3
    assert abs(sum(t.weight for t in p.task_weights) - 1.0) < 1e-6
    assert "deep_research::edge_cases" in p.suggested_new_tasks


def test_unknown_success_ignored() -> None:
    p = propose_next_week_weights(
        [
            {"task": "reading", "success": None},
            {"task": "reading", "success": True},
        ],
        week_id="w",
    )
    assert p.task_weights
    assert p.task_weights[0].n_success == 1
    assert p.task_weights[0].n_failure == 0


def test_prior_weights_annotate_only_do_not_invent_tasks() -> None:
    p = propose_next_week_weights(
        [{"task": "general", "success": True}],
        prior_weights={"general": 0.4, "deep_research": 0.6},
        week_id="w",
    )
    by_task = {t.task: t for t in p.task_weights}
    assert by_task["general"].prior_weight == 0.4
    # prior-only tasks without usage must not be invented
    assert "deep_research" not in by_task


def test_string_success_does_not_invent_outcome() -> None:
    p = propose_next_week_weights(
        [{"task": "t", "success": "yes"}],  # type: ignore[dict-item]
        week_id="w",
    )
    assert p.incomplete is True
    assert p.task_weights == []


def test_failures_outrank_many_successes() -> None:
    p = propose_next_week_weights(
        [{"task": "failing", "success": False}]
        + [{"task": "winning", "success": True} for _ in range(20)],
        week_id="w",
        min_weight=0.0,
    )
    by_task = {t.task: t for t in p.task_weights}
    assert by_task["failing"].weight > by_task["winning"].weight


def test_weights_sum_exactly_one() -> None:
    p = propose_next_week_weights(
        [{"task": f"t{i}", "success": True} for i in range(6)],
        week_id="w",
        min_weight=0.0,
    )
    total = sum(t.weight for t in p.task_weights)
    assert total == 1.0


def test_weights_sum_exactly_one_many_tasks() -> None:
    """Regression: large N must still sum to binary 1.0 (codex REQUEST-CHANGES)."""
    for n in (7, 31, 301):
        events = []
        for i in range(n):
            events.extend(
                {"task": f"t{i:04d}", "success": False} for _ in range(i % 7)
            )
            events.append({"task": f"t{i:04d}", "success": True})
        p = propose_next_week_weights(events, week_id="w", min_weight=0.0)
        assert sum(t.weight for t in p.task_weights) == 1.0, n


def test_weights_sum_exactly_one_failure_pattern_0_2_4() -> None:
    """Order-dependent float sum regression (codex: failures 0,2,4)."""
    events: list[dict] = []
    for task, n_fail in (("a", 0), ("b", 2), ("c", 4)):
        events.extend({"task": task, "success": False} for _ in range(n_fail))
        events.append({"task": task, "success": True})
    p = propose_next_week_weights(events, week_id="w", min_weight=0.0)
    assert sum(t.weight for t in p.task_weights) == 1.0
    assert all(t.weight >= 0.0 for t in p.task_weights)


def test_weights_nonnegative_large_mass_imbalance() -> None:
    """Regression: residual must not go negative under extreme mass skew."""
    masses = [8074615, 6095105, 5231155, 5172161, 3971338, 2801939, 19]
    events: list[dict] = []
    for i, m in enumerate(masses):
        # mass = n_failure + 1 ⇒ n_failure = m - 1
        events.extend(
            {"task": f"t{i}", "success": False} for _ in range(max(0, m - 1))
        )
        events.append({"task": f"t{i}", "success": True})
    p = propose_next_week_weights(events, week_id="w", min_weight=0.0)
    assert sum(t.weight for t in p.task_weights) == 1.0
    assert all(t.weight >= 0.0 for t in p.task_weights)


def test_prior_with_only_unknown_outcomes_incomplete() -> None:
    p = propose_next_week_weights(
        [{"task": "t", "success": None}],
        prior_weights={"a": 0.5, "b": 0.5},
        week_id="w",
    )
    assert p.incomplete is True
    assert p.task_weights == []


def test_http_usage_learn_route() -> None:
    app = FastAPI()
    register_bench_usage_learn_routes(app)
    client = TestClient(app)
    r = client.post(
        "/settings/antiek-bench/usage-learn",
        json={
            "week_id": "2026-W28",
            "usage_events": [
                {"task": "deep_research", "success": False},
                {"task": "deep_research", "success": False},
                {"task": "note_taker", "success": True},
            ],
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["authority"] == "advisory"
    assert body["incomplete"] is False
    assert abs(sum(t["weight"] for t in body["task_weights"]) - 1.0) < 1e-5
    # empty
    r2 = client.post(
        "/settings/antiek-bench/usage-learn",
        json={"week_id": "x", "usage_events": []},
    )
    assert r2.status_code == 200
    assert r2.json()["incomplete"] is True
    assert r2.json()["task_weights"] == []
    # bool-ish string rejected
    r3 = client.post(
        "/settings/antiek-bench/usage-learn",
        json={"usage_events": [{"task": "t", "success": "yes"}]},
    )
    assert r3.status_code == 422
