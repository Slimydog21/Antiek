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


def test_prior_weights_recorded() -> None:
    p = propose_next_week_weights(
        [{"task": "general", "success": True}],
        prior_weights={"general": 0.4, "deep_research": 0.6},
        week_id="w",
    )
    by_task = {t.task: t for t in p.task_weights}
    assert by_task["general"].prior_weight == 0.4
    # deep_research present from prior even without usage
    assert "deep_research" in by_task


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
