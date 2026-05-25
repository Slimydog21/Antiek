"""DRW — the real Exa→Browserbase browse loop.

Tests the loop LOGIC against deterministic stub providers (the network-bound
real providers rely on the Exa/Browserbase adapters' own tests): search →
fetch → distil → emit, with steer checkpoints, within-run dedup, thin/failed
source handling, and budget cost reporting; plus a runner-integration check
that the emitted notes reach the graph through the SPR-06 funnel.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import tempfile

import pytest

from runtime.research_runner import (
    BudgetManager, HostLocalRunner, PromotionFunnel, ResearchPlan,
)
from runtime.research_runner.browse_loop import FetchedContent, SearchResult, make_browse_loop
from runtime.research_runner.host_local import LoopContext
from runtime.research_runner.protocol import StopResearch
from roles.note_taker.distill import Distillation, DistilledQuestion
from roles.note_taker.parser import ExtractedNote
from substrate.graph.schema import init_database_at_path
from runtime.db_lock import connect_read
from processing.embedding import set_default_embedding_provider, _reset_default_provider


class _FakeEmbedding:
    dimension = 8

    def encode(self, text: str) -> list[float]:
        d = hashlib.sha256(text.encode()).digest()
        return [b / 255.0 for b in d[: self.dimension]]


class FakeDistiller:
    def __init__(self, insights, questions):
        self._i, self._q = insights, questions

    def distill(self, text, *, source_event_ids=(), context=""):
        return Distillation(
            insights=[ExtractedNote(note_id=f"n{i}", text=t, confidence="moderate", source_event_ids=("ev",))
                      for i, t in enumerate(self._i)],
            questions=[DistilledQuestion(text=q) for q in self._q],
        )


def _search(results):
    return lambda query, limit: list(results)[:limit]


def _fetch(text_by_url, cost=0.02):
    def _f(url):
        t = text_by_url.get(url, "")
        return FetchedContent(text=t, cost_usd=cost, ok=bool(t))
    return _f


def _ctx(sub_question="the question"):
    return LoopContext(ResearchPlan(investigation_id="inv-0", sub_question=sub_question), BudgetManager())


# --------------------------------------------------------------------------
# Core loop logic
# --------------------------------------------------------------------------


async def test_loop_searches_fetches_and_distils():
    results = [SearchResult(url="u1", title="Source One"), SearchResult(url="u2", title="Source Two")]
    fetch = _fetch({"u1": "Long content about GPU economics. " * 10, "u2": "More substantive content here. " * 10})
    loop = make_browse_loop(search=_search(results), fetch=fetch,
                            distiller=FakeDistiller(["GPUs gate scale."], ["What is the moat?"]),
                            top_k=5, min_chars=10)
    events = [ev async for ev in loop(_ctx())]
    kinds = [e.kind for e in events]
    assert kinds[0] == "plan"
    assert any(e.kind == "step" and "searched" in e.text for e in events)
    assert sum(1 for e in events if e.kind == "step" and e.text.startswith("read")) == 2
    assert any(e.kind == "note" for e in events)
    assert any(e.kind == "question" for e in events)
    # notes carry their source url for provenance
    note = next(e for e in events if e.kind == "note")
    assert note.data.get("source_url") in {"u1", "u2"}


async def test_loop_dedups_within_run():
    results = [SearchResult(url="u1"), SearchResult(url="u2")]
    fetch = _fetch({"u1": "content " * 20, "u2": "other " * 20})
    # Same insight distilled from BOTH sources → emitted once.
    loop = make_browse_loop(search=_search(results), fetch=fetch,
                            distiller=FakeDistiller(["The one insight."], []), top_k=5, min_chars=5)
    notes = [e for e in [ev async for ev in loop(_ctx())] if e.kind == "note"]
    assert len(notes) == 1


async def test_loop_skips_thin_and_handles_fetch_failure():
    def fetch(url):
        if url == "u_thin":
            return FetchedContent(text="hi", cost_usd=0.0, ok=True)   # below min_chars
        if url == "u_fail":
            raise RuntimeError("network down")
        return FetchedContent(text="Plenty of real content here. " * 10, cost_usd=0.02, ok=True)
    results = [SearchResult(url="u_thin"), SearchResult(url="u_fail"), SearchResult(url="u_ok", title="OK")]
    loop = make_browse_loop(search=_search(results), fetch=fetch,
                            distiller=FakeDistiller(["insight"], []), top_k=5, min_chars=50)
    events = [ev async for ev in loop(_ctx())]
    assert any("thin/empty" in e.text for e in events)
    assert any("fetch failed" in e.text for e in events)
    # only the OK source produced a read step + a note
    assert sum(1 for e in events if e.text.startswith("read")) == 1
    assert sum(1 for e in events if e.kind == "note") == 1


async def test_loop_stops_at_checkpoint():
    loop = make_browse_loop(search=_search([SearchResult(url="u1")]),
                            fetch=_fetch({"u1": "x " * 50}),
                            distiller=FakeDistiller(["i"], []), min_chars=5)
    ctx = _ctx()
    ctx.request_stop()                       # stop before the loop spends anything
    collected = []
    with pytest.raises(StopResearch):
        async for ev in loop(ctx):
            collected.append(ev)
    # the plan event is emitted before the first checkpoint; then it stops
    assert collected and collected[0].kind == "plan"
    assert all(e.kind != "note" for e in collected)   # never reached fetching


async def test_loop_reports_search_and_fetch_cost():
    results = [SearchResult(url="u1", cost_usd=0.005), SearchResult(url="u2", cost_usd=0.005)]
    fetch = _fetch({"u1": "content " * 20, "u2": "content2 " * 20}, cost=0.02)
    loop = make_browse_loop(search=_search(results), fetch=fetch,
                            distiller=FakeDistiller([], []), top_k=5, min_chars=5)
    events = [ev async for ev in loop(_ctx())]
    total = sum(e.cost_usd for e in events)
    # search (0.005 + 0.005) + 2 fetches (0.02 each) = 0.05
    assert total == pytest.approx(0.05)


# --------------------------------------------------------------------------
# Runner integration — emitted notes reach the graph via the funnel
# --------------------------------------------------------------------------


@pytest.fixture
def graph_env(monkeypatch):
    set_default_embedding_provider(_FakeEmbedding())
    d = tempfile.mkdtemp()
    db = os.path.join(d, "g.duckdb")
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(d, "events"))
    import substrate.graph.insight_question as iq
    monkeypatch.setattr(iq, "graph_db_path", lambda: db)
    init_database_at_path(db)
    yield {"db": db}
    _reset_default_provider()


async def test_browse_loop_through_runner_promotes_notes(graph_env):
    results = [SearchResult(url="u1", title="S1"), SearchResult(url="u2", title="S2")]
    fetch = _fetch({"u1": "content one " * 20, "u2": "content two " * 20})
    loop = make_browse_loop(search=_search(results), fetch=fetch,
                            distiller=FakeDistiller(["Insight A.", "Insight B."], ["Q1?"]),
                            top_k=5, min_chars=5)
    funnel = PromotionFunnel(db_path=graph_env["db"], embedding_provider=_FakeEmbedding())
    await funnel.start()   # the worker must run before notes are submitted (else drain hangs)
    runner = HostLocalRunner(loop, budget=BudgetManager(), on_emit=funnel.submit, seal_on_complete=False)
    handle = await runner.start("inv-browse", ResearchPlan(investigation_id="inv-browse", sub_question="q"))
    _ = [ev async for ev in runner.stream(handle)]
    await runner.join()
    await funnel.drain_and_stop()
    assert funnel.errors == []
    con = connect_read(graph_env["db"])
    try:
        insights = con.execute("SELECT count(*) FROM nodes WHERE node_type='insight'").fetchone()[0]
        questions = con.execute("SELECT count(*) FROM nodes WHERE node_type='question'").fetchone()[0]
    finally:
        con.close()
    assert insights == 2 and questions == 1   # distilled across sources, deduped, promoted
