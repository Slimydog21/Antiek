"""Red-proofs: Antiek-bench weekly presentation (injected records only)."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.bench_view_routes import register_bench_view_routes
from substrate.bench_presentation.view import present_weekly_bench


def test_empty_week_incomplete_no_invented_scores() -> None:
    view = present_weekly_bench([], week_id="2026-W28")
    assert view.week_id == "2026-W28"
    assert view.authority == "advisory"
    assert view.best_by_task == {}
    assert view.scores == []
    assert view.incomplete is True
    assert any("no runs" in n for n in view.notes)


def test_best_by_task_from_measured_scores() -> None:
    view = present_weekly_bench(
        [
            {"task": "deep_research", "model_id": "flash", "score": 0.4, "n_runs": 2},
            {"task": "deep_research", "model_id": "thinker", "score": 0.9, "n_runs": 2},
            {"task": "note_taker", "model_id": "flash", "score": 0.85, "n_runs": 1},
            {"task": "note_taker", "model_id": "thinker", "score": 0.5, "n_runs": 1},
        ],
        week_id="2026-W28",
    )
    assert view.best_by_task["deep_research"] == "thinker"
    assert view.best_by_task["note_taker"] == "flash"
    assert view.incomplete is False


def test_null_score_marks_incomplete_and_skips_best() -> None:
    view = present_weekly_bench(
        [
            {"task": "reading", "model_id": "a", "score": None},
            {"task": "reading", "model_id": "b", "score": 0.7},
        ],
        week_id="2026-W01",
    )
    assert view.incomplete is True
    assert view.best_by_task["reading"] == "b"
    nulls = [s for s in view.scores if s.score is None]
    assert len(nulls) == 1


def test_tie_breaks_stable_by_model_id() -> None:
    view = present_weekly_bench(
        [
            {"task": "general", "model_id": "zeta", "score": 0.5},
            {"task": "general", "model_id": "alpha", "score": 0.5},
        ],
        week_id="w",
    )
    assert view.best_by_task["general"] == "alpha"


def test_bool_score_is_not_measured() -> None:
    view = present_weekly_bench(
        [{"task": "t", "model_id": "m", "score": False}],  # type: ignore[dict-item]
        week_id="w",
    )
    assert view.scores[0].score is None
    assert view.best_by_task == {}
    assert view.incomplete is True


def test_http_weekly_route() -> None:
    app = FastAPI()
    register_bench_view_routes(app)
    client = TestClient(app)
    r = client.post(
        "/settings/antiek-bench/weekly",
        json={
            "week_id": "2026-W28",
            "records": [
                {"task": "deep_research", "model_id": "m1", "score": 0.8},
                {"task": "deep_research", "model_id": "m2", "score": 0.6},
            ],
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["authority"] == "advisory"
    assert body["best_by_task"]["deep_research"] == "m1"
    # empty
    r2 = client.post("/settings/antiek-bench/weekly", json={"week_id": "x", "records": []})
    assert r2.status_code == 200
    assert r2.json()["incomplete"] is True
    assert r2.json()["best_by_task"] == {}
    # bool must not become score 0.0
    r3 = client.post(
        "/settings/antiek-bench/weekly",
        json={
            "week_id": "w",
            "records": [{"task": "t", "model_id": "m", "score": False}],
        },
    )
    # strict pydantic may 422, or pure path treats as unmeasured
    if r3.status_code == 200:
        body3 = r3.json()
        assert body3["best_by_task"] == {}
        assert body3["scores"][0]["score"] is None
    else:
        assert r3.status_code == 422
