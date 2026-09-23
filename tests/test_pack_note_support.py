"""W5 provenance — a pack never presents a generated note as evidence.

``build_session_evidence_pack`` admitted an insight node when its ``chunk_id``
resolved to a real ``chunks`` row, then set ``PackChunk.text`` to the node's
label: the generated note, not the chunk. A remote sandbox names a real
``document_id``, the host funnel grounds the note on that document's chunk,
and the pack handed the synthesizer "The moon is made of green cheese" as a
``direct`` supporting claim citing a chunk about neutral-atom qubits.

A first fix kept the note beside the chunk text when a lexical check said the
chunk supported it. A lexical check treats words as an unordered set, so
"Beta acquired Alpha for cash." passed against "Alpha acquired Beta for
cash." with score 1.0, and swapped figures passed the same way. The platform
has no entailment verifier on this path, so the pack carries no note at all:
every supporting claim is a verbatim excerpt of the chunk it cites. These
tests drive the real remote runner → funnel → pack → Loop 1 context path with
a fake sandbox; no provider is ever called.
"""

from __future__ import annotations

import os

import pytest
from pydantic import ValidationError

from orchestration.loop_one.orchestrator import _investigation_context_from_pack
from orchestration.session_evidence_pack import (
    PackChunk,
    SessionEvidencePackError,
    build_session_evidence_pack,
    parse_session_evidence_pack,
)
from processing.embedding import _reset_default_provider, set_default_embedding_provider
from processing.embedding.embed import HashEmbedding
from runtime.db_lock import connect_read, connect_write
from runtime.remote_exec import RemotePromotionFunnel, RemoteResearchRunner
from runtime.remote_exec.provider import RemoteStepEvent, Sandbox
from runtime.research_runner import BudgetCap, PromotionFunnel, ResearchPlan
from runtime.research_runner.protocol import StepEvent
from substrate.graph.schema import init_database_at_path

_BODY = (
    "Neutral atom qubit error rate suppression improved materially this quarter. "
    "The two-qubit gate error rate for neutral atom systems fell below the 1e-3 "
    "threshold, a scaling milestone for the platform. "
) * 4
_FORGED = "The moon is made of green cheese and was annexed by Luxembourg in 1841."
_HONEST = (
    "Neutral atom two-qubit gate error rate fell below the 1e-3 threshold, "
    "a scaling milestone for the platform."
)


@pytest.fixture
def emb():
    e = HashEmbedding()
    set_default_embedding_provider(e)
    yield e
    _reset_default_provider()


@pytest.fixture
def graph(tmp_path, monkeypatch, emb):
    db = str(tmp_path / "graph.duckdb")
    events = str(tmp_path / "events")
    os.makedirs(events, exist_ok=True)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events)
    init_database_at_path(db)
    _seed(db, emb, [("doc-pd-1", "chunk-pd-1", 0, _BODY)])
    return {"db": db, "events": events}


def _seed(db: str, emb: HashEmbedding, rows: list[tuple[str, str, int, str]]) -> None:
    con = connect_write(db, purpose="seed")
    try:
        con.execute("BEGIN")
        for doc_id, chunk_id, idx, text in rows:
            if not con.execute(
                "SELECT 1 FROM documents WHERE document_id = ?", [doc_id]
            ).fetchone():
                con.execute(
                    "INSERT INTO documents (document_id, title, source_tier, "
                    "document_type, content_class) VALUES (?, ?, 1, 'paper', "
                    "'public_domain')",
                    [doc_id, doc_id],
                )
            con.execute(
                "INSERT INTO chunks (chunk_id, document_id, chunk_index, text, "
                "embedding, token_count) VALUES (?, ?, ?, ?, ?, ?)",
                [chunk_id, doc_id, idx, text, emb.encode(text), len(text) // 4],
            )
        con.execute("COMMIT")
    finally:
        con.close()


def _chunk_text(db: str, chunk_id: str) -> str:
    con = connect_read(db)
    try:
        return str(con.execute(
            "SELECT text FROM chunks WHERE chunk_id = ?", [chunk_id]
        ).fetchone()[0])
    finally:
        con.close()


def _node_chunk(db: str, nid: str) -> str | None:
    import json

    con = connect_read(db)
    try:
        meta = con.execute(
            "SELECT metadata FROM nodes WHERE node_id = ?", [nid]
        ).fetchone()[0]
    finally:
        con.close()
    return json.loads(meta).get("chunk_id")


class _NoteSandbox:
    name = "fake-sandbox"

    def __init__(self, text: str, data: dict):
        self._text = text
        self._data = data

    def probe(self) -> None:
        return None

    async def provision(self, plan):
        return Sandbox(sandbox_id="sbx-" + plan.investigation_id,
                       investigation_id=plan.investigation_id)

    async def run(self, sandbox, plan):
        yield RemoteStepEvent(seq=1, kind="note", text=self._text,
                              provider=self.name, data=dict(self._data))

    async def steer(self, sandbox, command) -> None:
        return None

    async def teardown(self, sandbox) -> None:
        return None


async def _remote_note(graph: dict, emb, iid: str, text: str, data: dict) -> str:
    funnel = RemotePromotionFunnel(db_path=graph["db"], embedding_provider=emb)
    await funnel.start()
    runner = RemoteResearchRunner(
        _NoteSandbox(text, data), events_dir=graph["events"],
        outbox_db_path=graph["db"], seal_on_complete=False, on_emit=funnel.submit,
    )
    h = await runner.start(iid, ResearchPlan(iid, "q?", budget=BudgetCap(cost_usd=1.0)))
    _ = [e async for e in runner.stream(h)]
    await runner.join()
    await funnel.drain_and_stop()
    assert funnel.errors == []
    assert funnel.promoted_insights == 1
    return funnel.promoted_node_ids[0]


def _presented_text(ctx) -> str:
    return "\n".join(
        [e.answer for e in ctx.evidence]
        + [c.claim for e in ctx.evidence for c in e.supporting_claims]
    )


def _assert_only_source_text_presented(pack, ctx, db: str, note: str) -> None:
    """Every chunk and every claim the synthesizer sees is the substrate's own
    text: pack text is the chunk row, each claim is a verbatim excerpt of the
    chunk it cites, and the generated note appears nowhere."""
    for c in pack.chunks:
        assert c.text == _chunk_text(db, c.chunk_id)
    claims = [c for e in ctx.evidence for c in e.supporting_claims]
    assert claims, "the real source chunk stays admissible as verbatim evidence"
    for claim in claims:
        assert claim.evidence_type == "direct"
        assert claim.claim in _chunk_text(db, claim.chunk_ids[0])
        assert "verbatim excerpt" in claim.confidence_basis
    assert note not in _presented_text(ctx)
    assert all("note" not in c.model_dump() for c in pack.chunks)


# Nearest variants of a generated note. Each shares its source's words; the
# reversal and the swapped figures use no word the source lacks, so a
# bag-of-words check scores them as fully supported.
_DEAL_BODY = (
    "Alpha acquired Beta for cash. The deal closed in March after a long review. "
    "Revenue was 12 million in 2023 and 30 million in 2024, the filing shows. "
) * 4
_REVERSED = "Beta acquired Alpha for cash."
_NUMBERS_SWAPPED = "Revenue was 30 million in 2023 and 12 million in 2024."
_APPENDED = _HONEST + " The moon is made of green cheese."
_STOPWORD_FLIP = (
    "Neutral atom two-qubit gate error rate fell over the 1e-3 threshold."
)

_NOTES = [
    pytest.param("doc-pd-1", _FORGED, id="forged"),
    pytest.param("doc-deal", _REVERSED, id="reversed-relationship"),
    pytest.param("doc-deal", _NUMBERS_SWAPPED, id="reassigned-numbers"),
    pytest.param("doc-pd-1", _APPENDED, id="appended-forgery"),
    pytest.param("doc-pd-1", _STOPWORD_FLIP, id="stopword-flip"),
    pytest.param("doc-pd-1", _HONEST, id="honest-paraphrase"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("doc_id, note", _NOTES)
async def test_remote_note_is_never_presented_as_evidence(graph, emb, doc_id, note):
    """Codex repros: a remote note naming a real document is grounded on that
    document's chunk by the funnel. Whatever the note says, including a
    reversed relationship or reassigned figures built only from the source's
    own words, the pack and the synthesis context carry the chunk's text and
    never the note."""
    _seed(graph["db"], emb, [("doc-deal", "chunk-deal-1", 0, _DEAL_BODY)])
    await _remote_note(graph, emb, "inv-note", note, {"document_id": doc_id})

    pack = build_session_evidence_pack(
        "session-note", events_dir=graph["events"], db_path=graph["db"],
        researches=[("inv-note", "sub")],
    )
    assert {c.document_id for c in pack.chunks} == {doc_id}
    ctx = _investigation_context_from_pack(pack)
    _assert_only_source_text_presented(pack, ctx, graph["db"], note)


def test_builder_ignores_a_stored_groundedness_score(graph, emb):
    """Sibling entrypoint: a node written straight through ``promote_insight``
    (backfill, ``min_groundedness=None``) with a real chunk and a self-asserted
    0.99 score still yields only the chunk's text."""
    from substrate.graph.insight_question import promote_insight

    promote_insight(
        text=_FORGED, investigation_id="leaf-direct",
        source_document_id="doc-pd-1", chunk_id="chunk-pd-1",
        metadata={"groundedness_score": 0.99}, embedding_provider=emb,
    )
    pack = build_session_evidence_pack(
        "session-direct", events_dir=graph["events"], db_path=graph["db"],
        researches=[("leaf-direct", "sub")],
    )
    assert [(c.chunk_id, c.text) for c in pack.chunks] == [("chunk-pd-1", _BODY)]
    ctx = _investigation_context_from_pack(pack)
    _assert_only_source_text_presented(pack, ctx, graph["db"], _FORGED)


def test_notes_citing_one_chunk_yield_one_excerpt(graph, emb):
    """With the note gone, two notes of one leaf citing the same chunk would
    hand the synthesizer the same excerpt twice as two supporting claims. The
    pack keeps one chunk per (leaf, chunk)."""
    from substrate.graph.insight_question import promote_insight

    for text in (_HONEST, _STOPWORD_FLIP):
        promote_insight(
            text=text, investigation_id="leaf-dup",
            source_document_id="doc-pd-1", chunk_id="chunk-pd-1",
            embedding_provider=emb,
        )
    pack = build_session_evidence_pack(
        "session-dup", events_dir=graph["events"], db_path=graph["db"],
        researches=[("leaf-dup", "sub")],
    )
    assert [c.chunk_id for c in pack.chunks] == ["chunk-pd-1"]
    ctx = _investigation_context_from_pack(pack)
    assert len(ctx.evidence[0].supporting_claims) == 1


def test_pack_refuses_a_chunk_carrying_a_note():
    """No parse or build path can put a generated note into a pack: the chunk
    model has no such field, so a pack dict carrying one is refused."""
    with pytest.raises(SessionEvidencePackError, match="note"):
        parse_session_evidence_pack({
            "schema_version": 2, "session_id": "s", "problem_question": "q",
            "chunks": [{
                "chunk_id": "chunk-pd-1", "document_id": "doc-pd-1",
                "ip_holder_id": None, "text": _BODY, "note": _HONEST,
                "source_investigation_id": "leaf", "sub_question": "sq",
            }],
            "documents": [{"document_id": "doc-pd-1", "title": "d",
                           "ip_holder_id": None}],
            "leaf_investigation_ids": ["leaf"],
        })
    with pytest.raises(ValidationError, match="note"):
        PackChunk(
            chunk_id="chunk-pd-1", document_id="doc-pd-1", text=_BODY,
            note=_HONEST, source_investigation_id="leaf", sub_question="sq",
        )


def test_schema_v1_pack_is_refused():
    """A v1 pack's ``text`` is the generated note; reading it as source text
    is the defect, so v1 no longer parses."""
    with pytest.raises(SessionEvidencePackError, match="unsupported schema_version"):
        parse_session_evidence_pack({
            "schema_version": 1, "session_id": "s", "problem_question": "q",
            "chunks": [], "documents": [], "leaf_investigation_ids": [],
        })


@pytest.mark.asyncio
async def test_funnel_cites_the_supporting_chunk_not_the_longest(graph, emb):
    """Funnel sibling: the note cites the substantive chunk that supports it.
    The document's longest chunk says something else; citing it (the old
    ``ORDER BY length DESC``) put an unrelated excerpt in the pack for every
    note on that document."""
    longest = (
        "Trapped ion systems demonstrated long coherence times across a larger "
        "register this year, with sympathetic cooling keeping motional heating low. "
    ) * 8
    _seed(graph["db"], emb, [("doc-pd-1", "chunk-pd-1b", 1, longest)])
    assert len(longest) > len(_BODY)

    funnel = PromotionFunnel(db_path=graph["db"], embedding_provider=emb)
    await funnel.start()
    await funnel.submit(StepEvent("inv-cite", 0, "note", text=_HONEST,
                                  data={"document_id": "doc-pd-1"}))
    await funnel.drain_and_stop()
    assert funnel.errors == []
    assert _node_chunk(graph["db"], funnel.promoted_node_ids[0]) == "chunk-pd-1"

    pack = build_session_evidence_pack(
        "session-cite", events_dir=graph["events"], db_path=graph["db"],
        researches=[("inv-cite", "sub")],
    )
    assert [(c.chunk_id, c.text) for c in pack.chunks] == [("chunk-pd-1", _BODY)]
