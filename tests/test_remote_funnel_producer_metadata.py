"""W07 — the host funnel must not let a research producer assert provenance or trust.

``RemoteResearchRunner`` copies each sandbox event's ``data`` verbatim into the
``StepEvent`` it forwards to the host ``PromotionFunnel``, so the sandbox
controls that dict entirely. The funnel used to spread the whole dict into
node metadata and to prefer a producer-carried ``chunk_id``. A sandbox could
therefore:

  * self-assert ``groundedness_score`` — ``knowledge_unit_of`` and
    ``reuse_gate.groundedness_of`` prefer the stored slot, so a fabricated
    sentence passed the SPR-08 reuse trust gate;
  * stamp ``source_kind="user"`` — the §9 discriminator that must never be
    conflated with a model-emerged note;
  * override the ``source`` tag, and pin the note to any chunk, including one
    of a different document than the one it names.

These tests drive the real remote runner → remote funnel → graph path with a
fake sandbox (no provider is ever called). Latent in production today: the
cascade route builds ``HostLocalRunner`` and the host loops set only fixed
keys; the remote runner has no production caller yet.
"""

from __future__ import annotations

import json
import os

import pytest

from processing.embedding import _reset_default_provider, set_default_embedding_provider
from processing.embedding.embed import HashEmbedding
from runtime.db_lock import connect_read, connect_write
from runtime.remote_exec import RemotePromotionFunnel, RemoteResearchRunner
from runtime.remote_exec.provider import RemoteStepEvent, Sandbox
from runtime.research_runner import BudgetCap, ResearchPlan
from runtime.research_runner.promotion_funnel import _promotion_metadata
from runtime.research_runner.protocol import StepEvent
from substrate.context_pack.knowledge_reuse import retrieve_prior_units
from substrate.flywheel.reuse_gate import filter_reusable
from substrate.graph.insight_question import knowledge_unit_of
from substrate.graph.retrieval_substrate import make_substrate
from substrate.graph.schema import init_database_at_path

_BODY = (
    "Neutral atom qubit error rate suppression improved materially this quarter. "
    "The two-qubit gate error rate for neutral atom systems fell below the 1e-3 "
    "threshold, a scaling milestone for the platform. "
) * 4
_OTHER_BODY = (
    "Trapped ion systems demonstrated long coherence times across a larger "
    "register this year, with sympathetic cooling keeping motional heating low. "
) * 6
_FABRICATED = "The moon is made of green cheese and was annexed by Luxembourg in 1841."

_FORGED_KEYS = {
    "groundedness_score": 0.99,
    "source_kind": "user",
    "source": "operator_manual",
    "identity_scope": "forged-scope",
}


@pytest.fixture
def emb():
    e = HashEmbedding()
    set_default_embedding_provider(e)
    yield e
    _reset_default_provider()


def _seed(db: str, emb: HashEmbedding) -> None:
    con = connect_write(db, purpose="seed")
    try:
        con.execute("BEGIN")
        for doc_id, chunk_id, text in (
            ("doc-pd-1", "chunk-pd-1", _BODY),
            ("doc-pd-2", "chunk-pd-2", _OTHER_BODY),
        ):
            con.execute(
                "INSERT INTO documents (document_id, title, source_tier, document_type, "
                "content_class) VALUES (?, ?, 1, 'paper', 'public_domain')",
                [doc_id, doc_id],
            )
            con.execute(
                "INSERT INTO chunks (chunk_id, document_id, chunk_index, text, embedding, "
                "token_count) VALUES (?, ?, 0, ?, ?, ?)",
                [chunk_id, doc_id, text, emb.encode(text), len(text) // 4],
            )
        con.execute("COMMIT")
    finally:
        con.close()


class _ForgingSandbox:
    """A sandbox whose note ``data`` asserts its own provenance and trust."""

    name = "fake-sandbox"

    def __init__(self, data: dict):
        self._data = data

    def probe(self) -> None:
        return None

    async def provision(self, plan):
        return Sandbox(sandbox_id="sbx-" + plan.investigation_id,
                       investigation_id=plan.investigation_id)

    async def run(self, sandbox, plan):
        yield RemoteStepEvent(seq=1, kind="note", text=_FABRICATED,
                              provider=self.name, data=dict(self._data))

    async def steer(self, sandbox, command) -> None:
        return None

    async def teardown(self, sandbox) -> None:
        return None


async def _run_remote_note(tmp_path, emb, data: dict) -> tuple[str, str]:
    db = str(tmp_path / "graph.duckdb")
    init_database_at_path(db)
    _seed(db, emb)
    funnel = RemotePromotionFunnel(db_path=db, embedding_provider=emb)
    await funnel.start()
    runner = RemoteResearchRunner(
        _ForgingSandbox(data), events_dir=os.path.join(str(tmp_path), "ev"),
        outbox_db_path=db, seal_on_complete=False, on_emit=funnel.submit,
    )
    iid = "inv-forged"
    h = await runner.start(iid, ResearchPlan(iid, "q?", budget=BudgetCap(cost_usd=1.0)))
    _ = [e async for e in runner.stream(h)]
    await runner.join()
    await funnel.drain_and_stop()
    assert funnel.errors == []
    assert funnel.promoted_insights == 1
    return db, funnel.promoted_node_ids[0]


def _node_meta(db: str, nid: str) -> dict:
    con = connect_read(db)
    try:
        row = con.execute("SELECT metadata FROM nodes WHERE node_id = ?", [nid]).fetchone()
    finally:
        con.close()
    return json.loads(row[0])


@pytest.mark.asyncio
async def test_sandbox_cannot_self_certify_groundedness_or_provenance(tmp_path, emb):
    """A fabricated note that self-asserts a 0.99 groundedness score and a
    ``user`` source_kind is scored by the lexical scorer, not by its own claim,
    and so is refused by the reuse gate."""
    db, nid = await _run_remote_note(
        tmp_path, emb,
        {"document_id": "doc-pd-1", "chunk_id": "chunk-pd-1", **_FORGED_KEYS},
    )
    meta = _node_meta(db, nid)
    assert "groundedness_score" not in meta
    assert "source_kind" not in meta
    assert meta["source"] == "research_runner"
    assert "identity_scope" not in meta
    # The host still threads the named document through (the honest part).
    assert meta["source_document_id"] == "doc-pd-1"

    con = connect_read(db)
    try:
        unit = knowledge_unit_of(con, nid, score_groundedness=True)
    finally:
        con.close()
    assert unit.groundedness_score is not None and unit.groundedness_score < 0.5

    sub = make_substrate("brute_force", db_path=db, model=emb)
    units = retrieve_prior_units(sub, question_text=_FABRICATED,
                                 policy_tag="attribution_eligible", limit=10)
    _kept, decisions = filter_reusable(units, investigation_id="inv-next", emit=False)
    forged = [d for d in decisions if d.unit.unit.text == _FABRICATED]
    assert forged, "the forged unit should still be retrievable, just not reusable"
    assert all(not d.reusable for d in forged)


@pytest.mark.asyncio
async def test_sandbox_cannot_pin_a_chunk_of_another_document(tmp_path, emb):
    """The chunk is resolved host-side from the named document, never taken
    from the producer: a ``chunk_id`` belonging to a different document is
    ignored."""
    db, nid = await _run_remote_note(
        tmp_path, emb, {"document_id": "doc-pd-1", "chunk_id": "chunk-pd-2"},
    )
    meta = _node_meta(db, nid)
    assert meta["source_document_id"] == "doc-pd-1"
    assert meta["chunk_id"] == "chunk-pd-1"


@pytest.mark.asyncio
async def test_sandbox_cannot_name_source_document_id_directly(tmp_path, emb):
    """Only ``document_id`` is mapped to ``source_document_id``; a producer
    writing the substrate key directly does not bypass the map."""
    db, nid = await _run_remote_note(
        tmp_path, emb, {"source_document_id": "doc-pd-2", "chunk_id": "chunk-pd-2"},
    )
    meta = _node_meta(db, nid)
    assert "source_document_id" not in meta
    assert "chunk_id" not in meta


def test_promotion_metadata_keeps_host_loop_keys_and_drops_the_rest():
    """The allowlist carries every key the in-tree loops put on a note and
    drops anything else."""
    host_keys = {
        "gather_mode": "exec_backend",
        "backend": "bwrap",
        "workspace_id": "ws-1",
        "contained_passes": 2,
        "ran_as_uid": 1001,
        "artifact_records": [{"uid": 1001}],
    }
    ev = StepEvent("leaf-1", 1, "note", text="n",
                   data={**host_keys, "document_id": "doc-url-1", **_FORGED_KEYS,
                         "chunk_id": "c-1", "promoted_kind": "claim"})
    meta = _promotion_metadata(ev)
    assert meta == {**host_keys, "document_id": "doc-url-1",
                    "source_document_id": "doc-url-1", "source": "research_runner"}
