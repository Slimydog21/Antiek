"""SPR-DRL-09 — pack doc-url-* fidelity + parent terminal observability."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
from dataclasses import dataclass
from types import ModuleType
from typing import List, Optional

import httpx
import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from acquisition.search.parallel import ParallelClient
from orchestration.cascade_session import CascadeSession, Leaf
from orchestration.session_evidence_pack import build_session_evidence_pack
from processing.embedding import _reset_default_provider, set_default_embedding_provider
from roles.cascade_planner import SubQuestion, approve_plan, build_plan, persist_tree
from roles.cascade_planner.persist import load_tree
from runtime.research_runner import (
    HostLocalRunner,
    PromotionFunnel,
    make_parallel_gather_loop,
)
from runtime.research_runner.promotion_funnel import _promotion_metadata
from runtime.research_runner.protocol import StepEvent
from substrate.event_log import trajectory
from substrate.graph.schema import init_database_at_path
from substrate.legal_gate import PermissiveLegalGate


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


def _mock_parallel_client(responses: List[dict]) -> ParallelClient:
    it = iter(responses)
    last = [None]

    def handler(request: httpx.Request) -> httpx.Response:
        try:
            body = next(it)
            last[0] = body
        except StopIteration:
            body = last[0] or {"results": []}
        return httpx.Response(200, json=body)

    return ParallelClient(
        api_key="test-key",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=lambda _s: None,
    )


def _parallel_result(url: str) -> dict:
    return {"url": url, "title": "T", "excerpts": ["excerpt"]}


@pytest.fixture(autouse=True)
def _emb():
    set_default_embedding_provider(_FakeEmbedding())
    yield
    _reset_default_provider()


@pytest.fixture
def env(tmp_path, monkeypatch):
    events_dir = tmp_path / "events"
    events_dir.mkdir()
    db = tmp_path / "g.duckdb"
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(events_dir))
    monkeypatch.setenv("PARALLEL_API_KEY", "test-key")
    monkeypatch.setenv("ANTIEK_LEGAL_GATE_PLACEHOLDER_ACKED", "1")
    import substrate.graph.insight_question as iq

    monkeypatch.setattr(iq, "graph_db_path", lambda: str(db))
    init_database_at_path(str(db))
    return {"db": str(db), "events": str(events_dir)}


def test_promotion_metadata_maps_document_id_to_source_document_id():
    ev = StepEvent(
        "leaf-1",
        1,
        "note",
        text="ingested doc",
        data={"document_id": "doc-url-abc123", "gather_mode": "parallel"},
    )
    meta = _promotion_metadata(ev)
    assert meta["source_document_id"] == "doc-url-abc123"


@pytest.mark.asyncio
async def test_parallel_gather_pack_uses_doc_url_not_placeholder(env, monkeypatch):
    @dataclass(frozen=True)
    class FakeIngestResult:
        document_id: str
        final_url: str = ""
        chunk_ids: tuple = ()
        node_ids: tuple = ()
        document_loaded_event_id: Optional[str] = None
        chunks_written: int = 1
        skipped_reason: Optional[str] = None
        title: Optional[str] = None
        author: Optional[str] = None

    seq = {"n": 0}

    def fake_ingest(url, **kwargs):
        seq["n"] += 1
        return FakeIngestResult(document_id=f"doc-url-pack{seq['n']:02d}")

    mod = ModuleType("acquisition.urls.adapter")
    mod.ingest_url = fake_ingest
    monkeypatch.setitem(sys.modules, "acquisition.urls.adapter", mod)

    cli = _mock_parallel_client([
        {
            "search_id": "s1",
            "results": [
                _parallel_result("https://example.com/one"),
                _parallel_result("https://example.com/two"),
            ],
        }
    ])
    gate = PermissiveLegalGate(_bypass_acknowledgment=True)
    loop_fn = make_parallel_gather_loop(
        top_k=2,
        client=cli,
        legal_gate=gate,
        db_path=env["db"],
        events_dir=env["events"],
    )

    tree = build_plan("pack fidelity problem", decomposer=_Dec(["sub q"])).tree
    root_id = persist_tree(
        tree,
        investigation_id="session-pack",
        embedding_provider=_FakeEmbedding(),
        db_path=env["db"],
    )
    approve_plan(
        root_id,
        approver="operator",
        investigation_id="session-pack",
        db_path=env["db"],
    )
    loaded = load_tree(root_id, db_path=env["db"])
    leaves = [
        Leaf(
            investigation_id="leaf-pack-0",
            sub_question=c.question,
            question_node_id=c.graph_node_id,
        )
        for c in loaded.root.children
    ]

    funnel = PromotionFunnel(db_path=env["db"], embedding_provider=_FakeEmbedding())
    runner = HostLocalRunner(
        loop_fn,
        events_dir=env["events"],
        seal_on_complete=False,
        on_emit=funnel.submit,
    )
    session = CascadeSession(
        "session-pack",
        runner=runner,
        funnel=funnel,
        events_dir=env["events"],
        db_path=env["db"],
    )
    await session.launch(root_id, leaves)
    _ = [ev async for ev in session.stream()]
    await session.join_and_merge()

    pack = session.build_evidence_pack(plan_root_node_id=root_id)
    assert len(pack.chunks) >= 1
    assert all(c.document_id.startswith("doc-url-") for c in pack.chunks)
    assert not any(c.document_id.startswith("doc-gather-") for c in pack.chunks)

    rebuilt = build_session_evidence_pack(
        "session-pack",
        events_dir=env["events"],
        db_path=env["db"],
        researches=[("leaf-pack-0", "sub q")],
        plan_root_node_id=root_id,
    )
    assert rebuilt.content_hash == pack.content_hash


@pytest.mark.asyncio
async def test_synthesis_tail_error_surfaces_in_completion_status(env):
    funnel = PromotionFunnel(db_path=env["db"], embedding_provider=_FakeEmbedding())
    runner = HostLocalRunner(
        make_parallel_gather_loop(
            top_k=0,
            client=_mock_parallel_client([{"search_id": "s", "results": []}]),
            legal_gate=PermissiveLegalGate(_bypass_acknowledgment=True),
            db_path=env["db"],
            events_dir=env["events"],
        ),
        events_dir=env["events"],
        seal_on_complete=False,
        on_emit=funnel.submit,
    )
    session = CascadeSession(
        "session-err",
        runner=runner,
        funnel=funnel,
        events_dir=env["events"],
        db_path=env["db"],
    )
    tree = build_plan("err", decomposer=_Dec(["q"])).tree
    root_id = persist_tree(
        tree,
        investigation_id="session-err",
        embedding_provider=_FakeEmbedding(),
        db_path=env["db"],
    )
    approve_plan(root_id, approver="op", investigation_id="session-err", db_path=env["db"])
    loaded = load_tree(root_id, db_path=env["db"])
    leaves = [
        Leaf(investigation_id="leaf-err-0", sub_question=c.question)
        for c in loaded.root.children
    ]
    await session.launch(root_id, leaves)
    _ = [ev async for ev in session.stream()]
    await session.join_and_merge()

    session._synthesis_tail_attempted = True
    session.record_synthesis_tail_error("RuntimeError: synthesis exploded")

    status = session.completion_status()
    assert status["gather_complete"] is True
    assert status["deep_research_complete"] is False
    assert status["synthesis_tail_error"] == "RuntimeError: synthesis exploded"

    events = trajectory("session-err", events_dir=env["events"])
    assert any(e.get("action_type") == "cascade.synthesis_tail_failed" for e in events)