"""SPR-DRL-05 — SessionEvidencePack schema + builder gates."""

from __future__ import annotations

import asyncio
import hashlib
import os
import tempfile

import pytest

from orchestration.cascade_session import CascadeSession, Leaf
from orchestration.session_evidence_pack import (
    PackChunk,
    PackDocument,
    SessionEvidencePack,
    SessionEvidencePackError,
    build_session_evidence_pack,
    compute_content_hash,
    parse_session_evidence_pack,
)
from runtime.research_runner import HostLocalRunner, PromotionFunnel, make_contract_gather_stub
from roles.cascade_planner import approve_plan, build_plan, persist_tree, SubQuestion
from roles.cascade_planner.persist import load_tree
from substrate.graph.schema import init_database_at_path
from processing.embedding import set_default_embedding_provider, _reset_default_provider


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


def test_invalid_pack_rejects_unknown_document():
    with pytest.raises(SessionEvidencePackError, match="unknown document"):
        parse_session_evidence_pack({
            "schema_version": 1,
            "session_id": "session-1",
            "problem_question": "q",
            "chunks": [{
                "chunk_id": "c1",
                "document_id": "missing-doc",
                "ip_holder_id": None,
                "text": "t",
                "source_investigation_id": "leaf-0",
                "sub_question": "sq",
            }],
            "documents": [],
            "leaf_investigation_ids": ["leaf-0"],
            "content_hash": "deadbeef",
        })


def test_empty_pack_valid_with_zero_chunks():
    pack = SessionEvidencePack(
        session_id="session-empty",
        problem_question="the problem",
        chunks=[],
        documents=[],
        leaf_investigation_ids=[],
    )
    assert pack.content_hash
    assert pack.chunks == []


def test_content_hash_stable_across_rebuild():
    chunks = [
        PackChunk(
            chunk_id="chunk-a",
            document_id="doc-1",
            ip_holder_id=None,
            text="alpha",
            source_investigation_id="leaf-0",
            sub_question="sub a",
        ),
    ]
    docs = [PackDocument(document_id="doc-1", title="Doc 1", ip_holder_id=None)]
    h1 = compute_content_hash(
        session_id="s1",
        problem_question="problem",
        chunks=chunks,
        documents=docs,
        leaf_investigation_ids=["leaf-0"],
    )
    h2 = compute_content_hash(
        session_id="s1",
        problem_question="problem",
        chunks=chunks,
        documents=docs,
        leaf_investigation_ids=["leaf-0"],
    )
    assert h1 == h2


@pytest.mark.asyncio
async def test_builder_from_hermetic_jsonl(env):
    """Hermetic cascade gather → pack with provenance-linked chunks."""
    tree = build_plan("the problem", decomposer=_Dec(["sub one"])).tree
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
            investigation_id="leaf-0",
            sub_question=c.question,
            question_node_id=c.graph_node_id,
        )
        for c in loaded.root.children
    ]

    funnel = PromotionFunnel(db_path=env["db"], embedding_provider=_FakeEmbedding())
    runner = HostLocalRunner(
        make_contract_gather_stub(steps=1, cost_per_step=0.01),
        events_dir=env["events"],
        seal_on_complete=False,
        on_emit=funnel.submit,
    )
    session = CascadeSession(
        "session-1",
        runner=runner,
        funnel=funnel,
        events_dir=env["events"],
        db_path=env["db"],
    )
    await session.launch(root_id, leaves)
    _ = [ev async for ev in session.stream()]
    await session.join_and_merge()

    pack = session.build_evidence_pack(plan_root_node_id=root_id)
    assert pack.session_id == "session-1"
    assert pack.problem_question == "the problem"
    assert pack.leaf_investigation_ids == ["leaf-0"]
    assert len(pack.chunks) >= 1
    assert len(pack.documents) >= 1
    for chunk in pack.chunks:
        assert any(d.document_id == chunk.document_id for d in pack.documents)
        doc = next(d for d in pack.documents if d.document_id == chunk.document_id)
        assert chunk.ip_holder_id == doc.ip_holder_id

    rebuilt = build_session_evidence_pack(
        "session-1",
        events_dir=env["events"],
        db_path=env["db"],
        researches=[("leaf-0", "sub one")],
        plan_root_node_id=root_id,
    )
    assert rebuilt.content_hash == pack.content_hash