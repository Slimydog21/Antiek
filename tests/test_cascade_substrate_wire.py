"""ACV SPR-02 — the flywheel wire regression gate.

The compounding flywheel shipped DEAD in prod because the one user research
entrypoint (``interfaces/research/api/cascade_routes.py`` ``launch`` →
``HostLocalRunner(...)``) constructed the runner with ``retrieval_substrate``
left ``None``, so ``host_local.py``'s ``_maybe_reuse_prior_knowledge`` early-
returned and no ``knowledge.reused`` event ever fired. SPR-02 wired a real
production ``RetrievalSubstrate`` (``build_prod_retrieval_substrate``) into that
construction. These tests are the never-revert guard:

* ``test_launch_constructs_runner_with_non_none_substrate`` — drives the REAL
  launch route and asserts the ``HostLocalRunner`` it builds received a
  non-None ``retrieval_substrate``. This FAILS if the kwarg is removed from
  ``cascade_routes.py`` (the silent-revert this gate exists to catch).

* ``test_factory_returns_none_not_raises_on_unopenable_substrate`` — proves the
  factory's graceful-degradation contract (M2): on ANY failure opening the
  substrate it returns ``None`` (never raises), so a dead substrate degrades to
  a reuse-less research rather than a broken launch.

Mirrors the lightweight ``test_cascade_create_plan_light`` discipline: mount
only ``cascade_router`` + stub the seams, no multi-thousand-line ``create_app``.
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
    tmpdir = tempfile.mkdtemp(prefix="cascade-substrate-wire-")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", os.path.join(tmpdir, "t.duckdb"))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(tmpdir, "events"))
    monkeypatch.setattr(cr, "_embedding_provider", lambda: _StubEmbedding())
    cr._SESSIONS.clear()
    cr._SESSION_TASKS.clear()
    app = FastAPI()
    app.include_router(cascade_router)
    yield TestClient(app)


def _approved_plan(client) -> str:
    """Create + approve a one-leaf plan with an explicit sub-question (no live
    decomposer) and return its root id, ready to launch."""
    r = client.post(
        "/research/plans",
        json={
            "problem": "substrate-wire regression",
            "sub_questions": ["a single minimal sub-question for the wire test"],
            "max_depth": 1,
        },
    )
    assert r.status_code == 200, r.text
    root_id = r.json()["root_node_id"]
    r = client.post(f"/research/plans/{root_id}/approve", json={"approver": "__test__"})
    assert r.status_code == 200, r.text
    return root_id


def test_launch_constructs_runner_with_non_none_substrate(cascade_client, monkeypatch):
    """The real launch path must build HostLocalRunner with a non-None
    retrieval_substrate. FAILS if the ``retrieval_substrate=`` kwarg is dropped
    from cascade_routes.py (silent revert of the flywheel wire)."""
    captured: dict[str, object] = {}

    real_runner_cls = cr.HostLocalRunner

    class _SpyRunner(real_runner_cls):  # type: ignore[misc, valid-type]
        def __init__(self, *args, **kwargs):
            captured["retrieval_substrate"] = kwargs.get("retrieval_substrate", "<<MISSING>>")
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(cr, "HostLocalRunner", _SpyRunner)

    # Make the factory return a sentinel so this test asserts the WIRE (the kwarg
    # is passed through), not the substrate's open() behaviour (covered by the
    # probe + the second test). A truthy sentinel is enough to prove non-None.
    sentinel = object()
    monkeypatch.setattr(cr, "build_prod_retrieval_substrate", lambda: sentinel)

    root_id = _approved_plan(cascade_client)
    r = cascade_client.post(
        f"/research/plans/{root_id}/launch",
        json={"per_research_budget_usd": 1.0, "aggregate_budget_usd": 5.0},
    )
    assert r.status_code == 200, r.text

    assert "retrieval_substrate" in captured, "HostLocalRunner was never constructed"
    assert captured["retrieval_substrate"] != "<<MISSING>>", (
        "launch built HostLocalRunner WITHOUT a retrieval_substrate kwarg — the "
        "flywheel wire reverted; host_local.py:259 would early-return and no "
        "knowledge.reused event would fire (the dead-flywheel defect)"
    )
    assert captured["retrieval_substrate"] is sentinel, (
        "the retrieval_substrate passed to HostLocalRunner was not the value the "
        "prod factory produced"
    )


def test_launch_wires_factory_output(cascade_client, monkeypatch):
    """Belt-and-braces: the kwarg is wired from build_prod_retrieval_substrate()
    specifically (not some other source), so renaming/bypassing the factory
    also trips this gate."""
    calls: list[int] = []
    sentinel = object()

    def _factory():
        calls.append(1)
        return sentinel

    captured: dict[str, object] = {}
    real_runner_cls = cr.HostLocalRunner

    class _SpyRunner(real_runner_cls):  # type: ignore[misc, valid-type]
        def __init__(self, *args, **kwargs):
            captured["sub"] = kwargs.get("retrieval_substrate")
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(cr, "HostLocalRunner", _SpyRunner)
    monkeypatch.setattr(cr, "build_prod_retrieval_substrate", _factory)

    root_id = _approved_plan(cascade_client)
    r = cascade_client.post(
        f"/research/plans/{root_id}/launch",
        json={"per_research_budget_usd": 1.0, "aggregate_budget_usd": 5.0},
    )
    assert r.status_code == 200, r.text
    assert calls == [1], "build_prod_retrieval_substrate() was not called exactly once per launch"
    assert captured["sub"] is sentinel


def test_factory_returns_none_not_raises_on_unopenable_substrate(monkeypatch):
    """M2 graceful-degradation: the factory returns None (never raises) when the
    substrate cannot open, so research continues reuse-less rather than failing.

    We force DuckDbVssSubstrate.open to raise; the factory must swallow it,
    log, and return None."""
    import substrate.graph.retrieval_substrate as rs

    # Point at a real (empty) graph so the existence check + snapshot copy
    # succeed and the failure is forced at the substrate-open step specifically.
    tmpdir = tempfile.mkdtemp(prefix="cascade-wire-factory-")
    db_path = os.path.join(tmpdir, "t.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    from substrate.graph import ensure_initialized

    ensure_initialized(db_path)

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated: vss load failed / model unavailable")

    monkeypatch.setattr(rs.DuckDbVssSubstrate, "open", classmethod(lambda cls, *a, **k: _boom()))

    # Must NOT raise; must return None.
    result = cr.build_prod_retrieval_substrate()
    assert result is None, (
        "build_prod_retrieval_substrate must degrade to None on an unopenable "
        "substrate (reuse disabled), never propagate the exception into the launch"
    )


def test_factory_returns_none_when_db_missing(monkeypatch):
    """A missing graph DB is the most common "reuse disabled" condition (fresh
    box, never ingested). The factory must return None without touching the
    substrate at all."""
    tmpdir = tempfile.mkdtemp(prefix="cascade-wire-missing-")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", os.path.join(tmpdir, "does-not-exist.duckdb"))
    result = cr.build_prod_retrieval_substrate()
    assert result is None
