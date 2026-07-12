"""Antiek-bench routes — read/propose surface, offline + budget-honest."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("ANTIEK_HOME", str(tmp_path))
    monkeypatch.setenv("ANTIEK_BENCH_DIR", str(tmp_path / "antiek_bench"))
    monkeypatch.delenv("ANTIEK_OPERATOR_BUDGET_USD", raising=False)
    monkeypatch.delenv("ANTIEK_DAEMON_HOURLY_BUDGET_USD", raising=False)
    from interfaces.research.api.app import create_app

    app = create_app()
    app.state.registered_providers = {"zai", "deepseek"}
    from interfaces.research.api.antiek_bench_routes import register_antiek_bench_routes

    register_antiek_bench_routes(app)
    with TestClient(app) as c:
        yield c


# --- GET /antiek-bench/tasks --------------------------------------------- #


def test_tasks_lists_default_registry(client: TestClient) -> None:
    resp = client.get("/antiek-bench/tasks")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["count"] >= 6
    assert len(body["tasks"]) == body["count"]
    assert "reasoning" in body["families"]
    task_ids = [t["task_id"] for t in body["tasks"]]
    assert all("::" in tid for tid in task_ids)  # family::slug convention


def test_task_row_has_prompt_preview_not_full_prompt(client: TestClient) -> None:
    resp = client.get("/antiek-bench/tasks")
    for task in resp.json()["tasks"]:
        assert len(task["prompt_preview"]) <= 200


# --- GET /antiek-bench/week/{week_id} ------------------------------------ #


def test_week_absent_ledger_is_incomplete_not_error(client: TestClient) -> None:
    resp = client.get("/antiek-bench/week/2026-W28")
    assert resp.status_code == 200
    body = resp.json()
    assert body["incomplete"] is True
    assert body["view_records"] == []
    assert body["n_records"] == 0


# --- POST /antiek-bench/runs/propose ------------------------------------- #


def test_propose_unknown_task_returns_400(client: TestClient) -> None:
    # Fail-closed: unknown task → 404, not a silent empty proposal.
    resp = client.post(
        "/antiek-bench/runs/propose",
        json={"task_id": "nonexistent::task"},
    )
    assert resp.status_code == 404


def test_propose_never_authorizes_dispatch(client: TestClient) -> None:
    resp = client.post(
        "/antiek-bench/runs/propose",
        json={"task_id": "reasoning::two_step_inference"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["live_dispatch_authorized"] is False
    assert body["task_id"] == "reasoning::two_step_inference"


def test_propose_surfaces_would_exceed_budget(client: TestClient) -> None:
    resp = client.post(
        "/antiek-bench/runs/propose",
        json={"task_id": "reasoning::two_step_inference"},
    )
    body = resp.json()
    # would_exceed_budget is surfaced (bool or None when pricing unknown)
    assert "would_exceed_budget" in body
    assert "cost_estimate" in body


def test_propose_notes_pricing_unknown(client: TestClient) -> None:
    # Without a real dispatch config, pricing is unknown → honest note.
    resp = client.post(
        "/antiek-bench/runs/propose",
        json={"task_id": "code::fix_off_by_one"},
    )
    body = resp.json()
    if not body["cost_estimate"]["pricing_known"]:
        assert any("pricing unknown" in n for n in body["notes"])
