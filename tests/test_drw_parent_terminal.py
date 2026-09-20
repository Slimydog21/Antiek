"""SPR-DRL-09 M3 — parent-terminal observability for DRW cascade sessions.

The defect this guards (cycle-2 tribunal): ``_run_to_completion`` used to wrap
the synthesis tail in a bare ``except Exception: pass``. A session whose Loop 1
synthesis tail RAISED would silently never reach ``DeepResearchComplete`` — the
operator would see green per-leaf states + cost and never learn the session is
split-brained. The fix CAPTURES the failure (records ``synthesis_tail_error`` on
the session + emits a durable audit trail), keeps the background task non-fatal,
and surfaces ``deep_research_complete`` + ``synthesis_tail_error`` in
``session_status``.

These tests are hermetic: the synthesis tail is mocked via
``set_synthesis_tail_runner`` (no live keys, no real model). The REAL Path-A
convergence that makes ``is_deep_research_complete()`` truly True end-to-end is
covered separately by ``test_cascade_convergence.py``; here we mock that single
check on the happy path because M3 is about the *observability wiring*, not
re-proving convergence.

Steelman of "best-effort swallow is fine, leave it": background completion runs
detached from any request, so a raise there can't return an HTTP 500 — swallowing
keeps the event loop alive, which is a real invariant (§16). REJECTED: keeping the
loop alive does NOT require throwing the information away. A silent terminal
failure is precisely the split-brain the ANT-DRL programme exists to prevent —
"the loop didn't crash" and "the operator can see the synthesis failed" are
independent properties, and we owe both. Capture-then-record satisfies the
non-fatal invariant while making the failure observable.
"""

from __future__ import annotations

import hashlib
import logging
import os
import tempfile

import pytest
from starlette.requests import Request

import interfaces.research.api.cascade_routes as cr
from orchestration.cascade_session import (
    SYNTHESIS_TAIL_FAILED,
    CascadeSession,
    Leaf,
    reconstruct_session,
)
from processing.embedding import _reset_default_provider, set_default_embedding_provider
from roles.cascade_planner import SubQuestion, approve_plan, build_plan, persist_tree
from roles.cascade_planner.persist import load_tree
from runtime.research_runner import (
    HostLocalRunner,
    PromotionFunnel,
    make_demo_loop,
)
from substrate.event_log import trajectory
from substrate.graph.schema import init_database_at_path

# --------------------------------------------------------------------------
# Hermetic fixtures (mirrors tests/test_cascade_session.py — no live keys)
# --------------------------------------------------------------------------


class _FakeEmbedding:
    dimension = 8

    def encode(self, text: str) -> list[float]:
        d = hashlib.sha256(text.encode()).digest()
        return [b / 255.0 for b in d[: self.dimension]]


def _request() -> Request:
    return Request({"type": "http", "method": "GET", "path": "/", "headers": []})


class _Dec:
    def __init__(self, subs: list[str]) -> None:
        self._subs = subs

    def decompose(self, q: str, *, context: str = ""):
        return [SubQuestion(question=s) for s in self._subs]


@pytest.fixture(autouse=True)
def _emb():
    set_default_embedding_provider(_FakeEmbedding())
    yield
    _reset_default_provider()


@pytest.fixture(autouse=True)
def _restore_runner():
    """Each test wires its own tail runner; never leak it across tests."""
    saved = cr._SYNTHESIS_TAIL_RUNNER
    yield
    cr.set_synthesis_tail_runner(saved)


@pytest.fixture
def env(monkeypatch):
    d = tempfile.mkdtemp()
    db = os.path.join(d, "g.duckdb")
    ev = os.path.join(d, "events")
    os.makedirs(ev, exist_ok=True)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", ev)
    import substrate.graph.insight_question as iq

    monkeypatch.setattr(iq, "graph_db_path", lambda: db)
    init_database_at_path(db)
    return {"db": db, "events": ev}


def _approved_plan(env, subs=("sub one",), session_id="session-1"):
    tree = build_plan("the problem", decomposer=_Dec(list(subs))).tree
    root_id = persist_tree(
        tree, investigation_id=session_id,
        embedding_provider=_FakeEmbedding(), db_path=env["db"],
    )
    approve_plan(root_id, approver="operator",
                 investigation_id=session_id, db_path=env["db"])
    loaded = load_tree(root_id, db_path=env["db"])
    leaves = [
        Leaf(investigation_id=f"{session_id}-leaf-{i}", sub_question=c.question,
             question_node_id=c.graph_node_id)
        for i, c in enumerate(loaded.root.children)
    ]
    return root_id, leaves


def _make_session(env, session_id="session-1"):
    funnel = PromotionFunnel(db_path=env["db"], embedding_provider=_FakeEmbedding())
    runner = HostLocalRunner(
        make_demo_loop(steps=1, emit_note=True),
        events_dir=env["events"],
        seal_on_complete=False,
        on_emit=funnel.submit,
    )
    return CascadeSession(session_id, runner=runner, funnel=funnel,
                          events_dir=env["events"], db_path=env["db"])


async def _drain(session: CascadeSession):
    return [ev async for ev in session.stream()]


# --------------------------------------------------------------------------
# (a) A raising synthesis tail is CAPTURED, audited, and NON-FATAL.
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_synthesis_tail_failure_captured_not_swallowed(env, caplog):
    root_id, leaves = _approved_plan(env)
    session = _make_session(env)
    await session.launch(root_id, leaves)
    await _drain(session)

    async def _boom(_session, _pack):
        raise RuntimeError("synthesis tail exploded")

    cr.set_synthesis_tail_runner(_boom)

    # _run_to_completion must NOT propagate — the background task is non-fatal.
    with caplog.at_level(logging.ERROR, logger="orchestration.cascade_session"):
        await cr._run_to_completion(session)  # no raise == non-fatal

    # Captured on the session (not swallowed).
    assert session.synthesis_tail_error is not None
    assert "RuntimeError" in session.synthesis_tail_error
    assert "synthesis tail exploded" in session.synthesis_tail_error

    # Audit trail #1: a structured ERROR log record exists (caplog), naming the
    # failing stage (SPR-DRL-09 sharpen: the message is stage-aware so a
    # join/merge failure isn't mislabeled as a synthesis-tail one).
    assert any(
        rec.levelno >= logging.ERROR
        and "completion failed at stage=synthesis_tail" in rec.getMessage()
        for rec in caplog.records
    ), "expected a stage-aware logger.exception audit record for the synthesis-tail failure"

    # Audit trail #2: a durable event on the session's own trajectory, so the
    # from-event-log status path can reconstruct it after eviction/restart.
    rows = trajectory(session.session_id, events_dir=env["events"])
    failed = [r for r in rows if r.get("action_type") == SYNTHESIS_TAIL_FAILED]
    assert failed, "expected a cascade.synthesis_tail.failed audit event"
    assert "synthesis tail exploded" in failed[-1]["payload"]["error"]

    # The terminal contract is now observably failed: not DeepResearchComplete,
    # error surfaced.
    terminal = session.terminal_status()
    assert terminal["deep_research_complete"] is False
    assert "synthesis tail exploded" in terminal["synthesis_tail_error"]

    # And the recovered (from-event-log) view honestly surfaces the same error.
    rec = reconstruct_session(session.session_id, events_dir=env["events"])
    assert rec.synthesis_tail_error is not None
    assert "synthesis tail exploded" in rec.synthesis_tail_error


# --------------------------------------------------------------------------
# (b) session_status exposes deep_research_complete=False + the error string.
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_session_status_exposes_failed_synthesis_tail(env):
    root_id, leaves = _approved_plan(env)
    session = _make_session(env)
    await session.launch(root_id, leaves)
    await _drain(session)

    async def _boom(_session, _pack):
        raise ValueError("tail blew up in status path")

    cr.set_synthesis_tail_runner(_boom)
    await cr._run_to_completion(session)

    # Register in the live registry so session_status takes the live branch.
    cr._SESSIONS[session.session_id] = session
    try:
        resp = await cr.session_status(session.session_id, _request())
    finally:
        cr._SESSIONS.pop(session.session_id, None)

    assert resp["live"] is True
    assert resp["deep_research_complete"] is False
    assert resp["synthesis_tail_error"] is not None
    assert "tail blew up in status path" in resp["synthesis_tail_error"]


# --------------------------------------------------------------------------
# (c) Happy path: a succeeding tail → deep_research_complete=True, error None.
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_session_status_happy_path_no_error(env, monkeypatch):
    root_id, leaves = _approved_plan(env)
    session = _make_session(env)
    await session.launch(root_id, leaves)
    await _drain(session)

    ran = {"called": False}

    async def _ok(_session, _pack):
        ran["called"] = True  # a tail that succeeds

    cr.set_synthesis_tail_runner(_ok)
    await cr._run_to_completion(session)

    assert ran["called"] is True
    assert session.synthesis_tail_error is None

    # The REAL end-to-end DeepResearchComplete (phases 6-9 + terminal event) is
    # proven hermetically in test_cascade_convergence.py with a live broadcaster.
    # Here we mock the single check to assert the observability WIRING: a clean
    # run surfaces deep_research_complete=True / synthesis_tail_error=None.
    monkeypatch.setattr(session, "is_deep_research_complete", lambda: True)

    cr._SESSIONS[session.session_id] = session
    try:
        resp = await cr.session_status(session.session_id, _request())
    finally:
        cr._SESSIONS.pop(session.session_id, None)

    assert resp["deep_research_complete"] is True
    assert resp["synthesis_tail_error"] is None
    # No audit event on the happy path.
    rows = trajectory(session.session_id, events_dir=env["events"])
    assert not [r for r in rows if r.get("action_type") == SYNTHESIS_TAIL_FAILED]


# --------------------------------------------------------------------------
# Guard: no synthesis runner wired (prod default) → no spurious error.
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_tail_runner_is_clean(env):
    root_id, leaves = _approved_plan(env)
    session = _make_session(env)
    await session.launch(root_id, leaves)
    await _drain(session)

    cr.set_synthesis_tail_runner(None)
    await cr._run_to_completion(session)  # join_and_merge only

    assert session.synthesis_tail_error is None
    assert session.terminal_status()["synthesis_tail_error"] is None
