"""W5 provenance — a pack chunk never certifies text its chunk does not contain.

``build_session_evidence_pack`` admitted an insight node when its ``chunk_id``
resolved to a real ``chunks`` row, then set ``PackChunk.text`` to the node's
label: the generated note, not the chunk. A remote sandbox names a real
``document_id``, the host funnel grounds the note on that document's chunk,
and the pack handed the synthesizer "The moon is made of green cheese" as a
``direct`` supporting claim citing a chunk about neutral-atom qubits.

The pack now carries the chunk's own substrate text as ``text`` and the
generated note, separately, as ``note`` only when the cited chunk supports it
at the groundedness bar (re-scored at build time, never read from metadata).
The funnel cites the substantive chunk that best supports a note instead of
the longest one. These tests drive the real remote runner → funnel → pack →
Loop 1 context path with a fake sandbox; no provider is ever called.
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


@pytest.mark.asyncio
async def test_forged_remote_note_is_not_certified_by_a_real_chunk(graph, emb):
    """Codex repro: a forged remote note naming a real document is grounded on
    that document's chunk by the funnel. The pack cites the chunk; its text
    must be the chunk's substrate text, the forged note must not ride along,
    and nothing the synthesizer is shown may carry the forged sentence."""
    await _remote_note(graph, emb, "inv-forged", _FORGED, {"document_id": "doc-pd-1"})

    pack = build_session_evidence_pack(
        "session-forged", events_dir=graph["events"], db_path=graph["db"],
        researches=[("inv-forged", "neutral atom error rates")],
    )
    assert pack.chunks, "the real source chunk stays admissible as verbatim evidence"
    for c in pack.chunks:
        assert c.text == _chunk_text(graph["db"], c.chunk_id)
        assert "green cheese" not in c.text
        assert c.note is None

    ctx = _investigation_context_from_pack(pack)
    assert "green cheese" not in _presented_text(ctx)
    for ev in ctx.evidence:
        for claim in ev.supporting_claims:
            assert claim.claim in _chunk_text(graph["db"], claim.chunk_ids[0])


@pytest.mark.asyncio
async def test_supported_remote_note_is_presented_beside_its_source_text(graph, emb):
    """An honest note the cited chunk supports is presented as the claim, and
    the source text stays in its own field, so the two are never conflated."""
    await _remote_note(graph, emb, "inv-honest", _HONEST, {"document_id": "doc-pd-1"})

    pack = build_session_evidence_pack(
        "session-honest", events_dir=graph["events"], db_path=graph["db"],
        researches=[("inv-honest", "neutral atom error rates")],
    )
    assert [(c.chunk_id, c.note) for c in pack.chunks] == [("chunk-pd-1", _HONEST)]
    assert pack.chunks[0].text == _BODY

    ctx = _investigation_context_from_pack(pack)
    [ev] = ctx.evidence
    assert [c.claim for c in ev.supporting_claims] == [_HONEST]
    # A generated restatement is typed "inferred"; only source text is direct.
    assert ev.supporting_claims[0].evidence_type == "inferred"
    assert _BODY[:200] in ev.answer


# Nearest variants of the forged note: each clears the lexical groundedness
# bar on its own (asserted below), so a bar-only check presents it.
_APPENDED = _HONEST + " The moon is made of green cheese."
_STOPWORD_FLIP = (
    "Neutral atom two-qubit gate error rate fell over the 1e-3 threshold."
)


@pytest.mark.parametrize("note", [_APPENDED, _STOPWORD_FLIP])
def test_note_that_clears_the_bar_but_adds_words_is_not_presented(graph, emb, note):
    """An honest prefix with an invented sentence appended, or a meaning flip
    through a stopword the bar ignores (below -> over), scores at or above the
    groundedness bar. Neither is presented: the chunk stays a verbatim
    excerpt and the synthesizer never sees the note."""
    from orchestration.session_evidence_pack import note_support
    from substrate.eval.groundedness import DEFAULT_SUPPORTED_THRESHOLD
    from substrate.graph.insight_question import promote_insight

    assert note_support(note, _BODY) >= DEFAULT_SUPPORTED_THRESHOLD
    promote_insight(
        text=note, investigation_id="leaf-variant",
        source_document_id="doc-pd-1", chunk_id="chunk-pd-1",
        embedding_provider=emb,
    )
    pack = build_session_evidence_pack(
        "session-variant", events_dir=graph["events"], db_path=graph["db"],
        researches=[("leaf-variant", "sub")],
    )
    assert [(c.chunk_id, c.text, c.note) for c in pack.chunks] == [
        ("chunk-pd-1", _BODY, None),
    ]
    ctx = _investigation_context_from_pack(pack)
    presented = _presented_text(ctx)
    assert "green cheese" not in presented
    assert "fell over" not in presented
    [claim] = ctx.evidence[0].supporting_claims
    assert claim.evidence_type == "direct"
    assert claim.claim in _BODY
    with pytest.raises(ValidationError, match="not supported"):
        PackChunk(
            chunk_id="chunk-pd-1", document_id="doc-pd-1", text=_BODY,
            note=note, source_investigation_id="leaf", sub_question="sq",
        )


def test_builder_rescores_and_ignores_a_stored_groundedness_score(graph, emb):
    """Sibling entrypoint: a node written straight through ``promote_insight``
    (backfill, ``min_groundedness=None``) with a real chunk and a self-asserted
    0.99 score. The builder re-scores the note against the chunk text."""
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
    assert [(c.chunk_id, c.text, c.note) for c in pack.chunks] == [
        ("chunk-pd-1", _BODY, None),
    ]


def test_pack_chunk_rejects_a_note_its_text_does_not_support():
    """The model itself refuses a chunk presenting an unsupported note, so a
    pack parsed or built by any other path cannot conflate the two."""
    with pytest.raises(ValidationError, match="not supported"):
        PackChunk(
            chunk_id="chunk-pd-1", document_id="doc-pd-1", text=_BODY,
            note=_FORGED, source_investigation_id="leaf", sub_question="sq",
        )
    ok = PackChunk(
        chunk_id="chunk-pd-1", document_id="doc-pd-1", text=_BODY,
        note=_HONEST, source_investigation_id="leaf", sub_question="sq",
    )
    assert ok.note == _HONEST


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
    ``ORDER BY length DESC``) left an honest note unpresentable and pinned
    every note to whatever that chunk said."""
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
    assert [(c.chunk_id, c.note) for c in pack.chunks] == [("chunk-pd-1", _HONEST)]
