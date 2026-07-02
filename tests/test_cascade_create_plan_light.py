"""ANT-H2V — create_plan transport without full ``create_app``.

The DRW ``test_cascade_api`` client fixture imports ``app.py`` (multi-thousand-line
factory). That is correct for journey tests but unsuitable as a *canonical*
contract gate: collection + startup contend with zombie pytest processes and can
hang for minutes.

These tests mount only ``cascade_router`` and stub persistence seams.
"""

from __future__ import annotations

import os
import tempfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import interfaces.research.api.cascade_routes as cr
from interfaces.research.api.cascade_routes import cascade_router


class _StubEmbedding:
    dimension = 8

    def encode(self, text: str) -> list[float]:
        return [0.1] * self.dimension


@pytest.fixture
def cascade_client(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="cascade-plan-light-")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", os.path.join(tmpdir, "t.duckdb"))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(tmpdir, "events"))
    monkeypatch.setattr(cr, "_embedding_provider", lambda: _StubEmbedding())
    cr._SESSIONS.clear()
    cr._SESSION_TASKS.clear()
    app = FastAPI()
    app.include_router(cascade_router)
    yield TestClient(app)


def test_create_plan_auto_decompose_without_sub_questions(cascade_client, monkeypatch):
    from roles.cascade_planner import SubQuestion, build_plan

    class _FixedDecomposer:
        def decompose(self, q, *, context=""):
            return [
                SubQuestion(question="focused sub one"),
                SubQuestion(question="focused sub two"),
            ]

    def _hermetic_decompose(problem: str, max_depth: int):
        return build_plan(problem, decomposer=_FixedDecomposer(), max_depth=max_depth)

    monkeypatch.setattr(cr, "_decompose", _hermetic_decompose)
    r = cascade_client.post("/research/plans", json={"problem": "big problem"})
    assert r.status_code == 200, r.text
    assert len(r.json()["tree"]["root"]["children"]) == 2


def test_create_plan_decompose_failed_returns_structured_unknown(cascade_client, monkeypatch):
    def _boom(problem: str, max_depth: int):
        raise TypeError(
            "render_full_prompt() takes 0 positional arguments but 1 was given",
        )

    monkeypatch.setattr(cr, "_decompose", _boom)
    r = cascade_client.post("/research/plans", json={"problem": "P"})
    assert r.status_code == 500, r.text
    detail = r.json()["detail"]
    assert detail["code"] == "unknown"
    assert "TypeError" not in r.text