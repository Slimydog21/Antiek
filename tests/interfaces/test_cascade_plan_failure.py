"""create_plan structured failure envelope (DRW honest failure)."""

from __future__ import annotations

import os
import tempfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import interfaces.research.api.cascade_routes as cr
from interfaces.research.api.cascade_routes import cascade_router
from substrate.dispatch.base import ProviderError


class _StubEmbedding:
    dimension = 8

    def encode(self, text: str) -> list[float]:
        return [0.1] * self.dimension


@pytest.fixture
def cascade_client(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="cascade-plan-fail-")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", os.path.join(tmpdir, "t.duckdb"))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(tmpdir, "events"))
    monkeypatch.setattr(cr, "_embedding_provider", lambda: _StubEmbedding())
    cr._SESSIONS.clear()
    cr._SESSION_TASKS.clear()
    app = FastAPI()
    app.include_router(cascade_router)
    yield TestClient(app)


def _detail(resp):
    body = resp.json()
    assert isinstance(body["detail"], dict)
    return body["detail"]


@pytest.mark.parametrize(
    "exc, status, code",
    [
        (
            ProviderError("no backends", provider="<none>", model="<none>", latency_ms=0),
            503,
            "provider_unconfigured",
        ),
        (
            ProviderError("upstream", provider="openrouter", model="m", latency_ms=1),
            502,
            "provider_upstream_error",
        ),
        (TimeoutError(), 504, "timeout"),
        (TypeError("render_full_prompt() takes 0 positional arguments but 1 was given"), 500, "unknown"),
    ],
)
def test_create_plan_emits_classified_envelope(cascade_client, monkeypatch, exc, status, code, caplog):
    import logging

    caplog.set_level(logging.WARNING, logger="interfaces.research.api.cascade_routes")
    def _raise(problem: str, max_depth: int):
        raise exc

    monkeypatch.setattr(cr, "_decompose", _raise)
    resp = cascade_client.post("/research/plans", json={"problem": "P"})
    assert resp.status_code == status, resp.text
    detail = _detail(resp)
    assert detail["code"] == code
    assert "retryable" in detail
    assert "ProviderError" not in resp.text
    assert "TypeError" not in resp.text
    assert "decompose_failed" not in resp.text
    assert any(
        "create_plan decompose failed" in r.message for r in caplog.records
    )


def test_create_plan_happy_path_unchanged(cascade_client, monkeypatch):
    from roles.cascade_planner import SubQuestion, build_plan

    class _Fixed:
        def decompose(self, q, *, context=""):
            return [SubQuestion(question="sub")]

    def _ok(problem: str, max_depth: int):
        return build_plan(problem, decomposer=_Fixed(), max_depth=max_depth)

    monkeypatch.setattr(cr, "_decompose", _ok)
    r = cascade_client.post("/research/plans", json={"problem": "big"})
    assert r.status_code == 200, r.text