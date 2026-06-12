"""ANT-DRL P-13 — cascade_session reconstruct + DeepResearchComplete guard.

Hermetic gates for PLATFORM_EXEC_MATRIX row P-13 and split-brain negative
coverage paired with P-12.
"""

from __future__ import annotations

import hashlib
import os
import tempfile

import pytest

from orchestration.cascade_session import CascadeSession, Leaf, reconstruct_session
from processing.embedding import _reset_default_provider, set_default_embedding_provider
from roles.cascade_planner import (
    SubQuestion,
    approve_plan,
    build_plan,
    persist_tree,
)
from roles.cascade_planner.persist import load_tree
from runtime.research_runner import (
    HostLocalRunner,
    PromotionFunnel,
    RunState,
    make_demo_loop,
)
from substrate.graph.schema import init_database_at_path


class _FakeEmbedding:
    dimension = 8

    def encode(self, text: str) -> list[float]:
        d = hashlib.sha256(text.encode()).digest()
        return [b / 255.0 for b in d[: self.dimension]]


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


def _approved_plan(env, subs=("sub one", "sub two")):
    tree = build_plan("the problem", decomposer=_Dec(list(subs))).tree
    root_id = persist_tree(
        tree,
        investigation_id="session-1",
        embedding_provider=_FakeEmbedding(),
        db_path=env["db"],
    )
    approve_plan(
        root_id,
        approver="operator",
        investigation_id="session-1",
        db_path=env["db"],
    )
    loaded = load_tree(root_id, db_path=env["db"])
    leaves = [
        Leaf(
            investigation_id=f"leaf-{i}",
            sub_question=c.question,
            question_node_id=c.graph_node_id,
        )
        for i, c in enumerate(loaded.root.children)
    ]
    return root_id, leaves


def _make_session(env):
    funnel = PromotionFunnel(db_path=env["db"], embedding_provider=_FakeEmbedding())
    runner = HostLocalRunner(
        make_demo_loop(steps=2, emit_note=True),
        events_dir=env["events"],
        seal_on_complete=False,
        on_emit=funnel.submit,
    )
    return CascadeSession(
        "session-1",
        runner=runner,
        funnel=funnel,
        events_dir=env["events"],
        db_path=env["db"],
    )


async def _drain(session: CascadeSession):
    return [ev async for ev in session.stream()]


@pytest.mark.asyncio
async def test_session_reconstructs_from_event_log(env):
    """P-13: membership + terminal state recoverable from JSONL alone."""
    root_id, leaves = _approved_plan(env, subs=["a", "b", "c"])
    session = _make_session(env)
    await session.launch(root_id, leaves)
    await _drain(session)
    await session.join_and_merge()

    recovery = reconstruct_session("session-1", events_dir=env["events"])
    assert {r.investigation_id for r in recovery.researches} == {
        "leaf-0",
        "leaf-1",
        "leaf-2",
    }
    assert recovery.all_terminal
    assert all(r.state == RunState.DONE.value for r in recovery.researches)


@pytest.mark.asyncio
async def test_demo_loop_runner_complete_is_not_deep_research_complete(env):
    """Split-brain guard: runner DONE without synthesis fails P-12/P-13 pair."""
    root_id, leaves = _approved_plan(env, subs=["a"])
    session = _make_session(env)
    await session.launch(root_id, leaves)
    await _drain(session)

    assert session.is_complete()
    assert not session.is_deep_research_complete()