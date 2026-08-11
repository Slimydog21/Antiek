"""Read SPR-08 — talk-to-book (M2) + corpus search (M1) + meta-reading (M4).

The mechanical gates the sprint demands, kept separate by milestone:

  M2 talk-to-book: answers cite PAGES; the §9.0 gate means a talk-to-book
    answer CANNOT cite a withheld region (its body never enters retrieval); a
    no-extractable-text book fails gracefully (no hallucination).
  M1 corpus search: a typed query returns ranked owned docs; the §9.0 gate
    excludes restricted content.
  M4 meta-reading: the synthesis is OWNED-CORPUS-ONLY (internet-agnostic —
    asserted by tracing retrieval to ``search`` over owned ids, with no
    acquisition / open-web call); HARD length-box (degenerate → rejected with a
    stated bound); a §9.0 withheld region is never cited; the deliverable saves
    as a Read asset through the single-writer funnel.

The dispatch path is exercised with an injected ``DispatchConfig`` + a
registered fake provider so the model call is deterministic and key-free.
"""

from __future__ import annotations

import os
import tempfile

import pytest

from runtime.db_lock import connect_read, connect_write
from substrate.books import ingest as bingest
from substrate.graph.ops import insert_chunk, insert_document
from substrate.graph.schema import init_database

# ---------------------------------------------------------------------------
# Fixtures + helpers
# ---------------------------------------------------------------------------


class StubEmbedding:
    """Deterministic 4-d embedding (matches test_book_corpus_gate.py)."""

    dimension = 4

    def encode(self, text: str) -> list[float]:
        h = sum(ord(c) * (i + 1) for i, c in enumerate(text)) or 1
        return [
            float(h % 7) / 7.0, float((h >> 3) % 11) / 11.0,
            float((h >> 5) % 13) / 13.0, float((h >> 7) % 17) / 17.0,
        ]


class _RecordingProvider:
    """A fake dispatch provider that records its prompts and returns a fixed
    reply, so the dispatch path is deterministic and key-free. Recording the
    prompt lets a test assert WHAT context the model saw (the §9.0 no-leak
    proof: a withheld body must never appear in the prompt)."""

    def __init__(self, reply: str = "A synthesized answer.", name: str = "fake"):
        self.reply = reply
        self.name = name
        self.prompts: list[str] = []

    def call(self, *, model, prompt, max_tokens, temperature):
        from substrate.dispatch import RawProviderResponse

        self.prompts.append(prompt)
        return RawProviderResponse(
            text=self.reply, raw_usage={}, finish_reason="stop", latency_ms=1,
        )

    def normalize_usage(self, raw_usage):
        from substrate.dispatch import NormalizedUsage

        return NormalizedUsage(input_tokens=0, output_tokens=0)


def register_fake(reply: str = "A synthesized answer.") -> _RecordingProvider:
    """Register ONE fake provider under ALL research-tier override names so
    book_qa/meta_reading's provider_override (which resolves from research_tier)
    lands on it whichever tier the caller chose. The shared instance records
    every prompt.

    The claude-less research-tier map (#309) resolves fast→zai / deep→
    zai_reasoning (GLM-5.2, thinking off / on); 'deepseek' is the config
    primary (no-override fallback). All override aliases share the SAME
    prompt log so a test can assert "no model dispatch" regardless of tier."""
    from substrate.dispatch.router import register_provider

    deep = _RecordingProvider(reply, name="deepseek")
    register_provider(deep)
    # The claude-less override names (zai / zai_reasoning) + the legacy
    # 'xiaomi' alias all share the SAME prompt log.
    for override_name in ("zai", "zai_reasoning", "xiaomi"):
        twin = _RecordingProvider(reply, name=override_name)
        twin.prompts = deep.prompts
        register_provider(twin)
    return deep


def _config_for(role: str):
    """A minimal DispatchConfig routing ``role`` to a 'deepseek' primary, so a
    no-override call still has a registered backend and the research-tier
    override (zai/zai_reasoning) is also registered. (book_qa/meta_reading pass
    provider_override; this config is the base the router starts from.)"""
    from substrate.dispatch import DispatchConfig, TierConfig

    tier = TierConfig(
        name="synthesis", provider="deepseek", model="m",
        max_tokens=64, temperature=0.2, context_budget_tokens=1000,
    )
    return DispatchConfig(role_tiers={role: "synthesis"}, tiers={"synthesis": tier})


@pytest.fixture(autouse=True)
def _clean_registry():
    """Isolate the provider registry per test (no cross-test leakage)."""
    from substrate.dispatch.router import reset_provider_registry

    reset_provider_registry()
    yield
    reset_provider_registry()


@pytest.fixture
def db(monkeypatch):
    tmp = tempfile.mkdtemp(prefix="antiek-spr08-")
    db_path = os.path.join(tmp, "graph.duckdb")
    events_dir = os.path.join(tmp, "events")
    os.makedirs(events_dir, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events_dir)
    con = connect_write(db_path, purpose="spr08-test")
    init_database(con)
    con.close()
    return db_path


def _book_with_pages(
    db_path, document_id, *, content_class="public_domain", title="A Book",
    pages=(("Page 1", "the body of page one about quantum mechanics"),
           ("Page 2", "page two discusses entanglement and superposition")),
    with_chunks=True,
):
    """A registered book whose chunks carry ``Page N`` section_paths — the
    realistic shape that makes a citation resolve to a reader page."""
    con = connect_write(db_path, purpose="insert")
    insert_document(
        con, document_id=document_id, source_tier=2, document_type="book",
        title=title, author="Author", raw_text="full body " * 80,
    )
    if with_chunks:
        for i, (section, text) in enumerate(pages):
            insert_chunk(
                con, document_id=document_id, chunk_index=i, text=text,
                section_path=section, token_count=len(text.split()),
                embedding=StubEmbedding().encode(text),
            )
    con.close()
    con = connect_write(db_path, purpose="register")
    try:
        bingest.register_book(con, document_id=document_id, content_class=content_class)
    finally:
        con.close()


def _restricted_book(db_path, document_id, *, title="Restricted"):
    """A restricted book (content_class restricted_pending_opt_in) WITH chunks
    that mention a unique probe term — so a test can prove the §9.0 gate keeps
    those chunks out of retrieval (the body never reaches the model)."""
    con = connect_write(db_path, purpose="insert")
    insert_document(
        con, document_id=document_id, source_tier=2, document_type="book",
        title=title, author="Author", raw_text="SECRET RESTRICTED BODY " * 50,
    )
    insert_chunk(
        con, document_id=document_id, chunk_index=0,
        text="WITHHELDSECRET quantum passage that must never be cited",
        section_path="Page 1", token_count=8,
        embedding=StubEmbedding().encode("WITHHELDSECRET quantum passage"),
    )
    con.close()
    con = connect_write(db_path, purpose="register")
    try:
        bingest.register_book(
            con, document_id=document_id,
            content_class="restricted_pending_opt_in",
            provenance="aggregated, unknown rights",
        )
    finally:
        con.close()


# ---------------------------------------------------------------------------
# M2 — talk-to-book: page citations + §9.0 no-leak + no-extractable-text
# ---------------------------------------------------------------------------


def test_talk_to_book_answer_cites_pages(db):
    from substrate.books.book_qa import answer_book_question

    _book_with_pages(db, "doc-talk")
    register_fake("Page one covers quantum mechanics.")
    con = connect_read(db)
    try:
        result = answer_book_question(
            con, document_id="doc-talk", question="what is on page one?",
            model=StubEmbedding(), investigation_id="read-doc-talk",
            config=_config_for("user_agent"),
        )
    finally:
        con.close()
    assert result.grounded is True
    assert result.citations, "a grounded answer must cite the chunks it used"
    # The citations resolve to reader pages (section_path 'Page N' → N-1).
    resolved = [c for c in result.citations if c.page_resolved]
    assert resolved, "at least one citation should resolve to a page"
    assert all(c.page_index is not None for c in resolved)
    assert {c.page_index for c in resolved} <= {0, 1}  # Page 1/2 → index 0/1


def test_talk_to_book_cannot_cite_withheld_region(db):
    """THE §9.0 no-leak test. A restricted book's chunk mentions the probe term
    WITHHELDSECRET; a talk-to-book turn must never retrieve it, so the body
    never reaches the model prompt and never appears in a citation."""
    from substrate.books.book_qa import answer_book_question

    _restricted_book(db, "doc-withheld")
    provider = register_fake("(no grounding)")
    con = connect_read(db)
    try:
        result = answer_book_question(
            con, document_id="doc-withheld",
            question="quantum passage about entanglement",
            model=StubEmbedding(), investigation_id="read-doc-withheld",
            config=_config_for("user_agent"),
        )
    finally:
        con.close()
    # The restricted chunk is gated out of retrieval → no context → ungrounded
    # honest answer, NO model dispatch (the body never reaches a prompt).
    assert result.grounded is False
    assert result.citations == []
    assert provider.prompts == [], "a withheld book must not dispatch a model at all"
    # Belt-and-braces: even if a prompt had been built, the body must not be in it.
    assert all("WITHHELDSECRET" not in p for p in provider.prompts)


def test_talk_to_book_no_extractable_text_fails_gracefully(db):
    """A scanned-image PDF has no chunks. The turn returns an honest 'no
    readable text' answer WITHOUT dispatching a model (no hallucination)."""
    from substrate.books.book_qa import answer_book_question

    _book_with_pages(db, "doc-scanned", with_chunks=False)
    provider = register_fake("should never be called")
    con = connect_read(db)
    try:
        def _must_not_dispatch(_prompt: str):
            raise AssertionError("no-context owner selection must not dispatch")

        result = answer_book_question(
            con, document_id="doc-scanned", question="what is this about?",
            model=StubEmbedding(), investigation_id="read-doc-scanned",
            config=_config_for("user_agent"),
            authorized_dispatch=_must_not_dispatch,
        )
    finally:
        con.close()
    assert result.grounded is False
    assert result.citations == []
    assert "readable text" in result.answer.lower()
    assert provider.prompts == [], "no chunks ⇒ no model dispatch (no hallucination)"


def test_talk_to_book_approximate_page_is_labelled(db):
    """A chunk whose section_path is a chapter title (not 'Page N') must NOT
    claim an exact page — page_resolved is False, page_index is None."""
    from substrate.books.book_qa import answer_book_question

    _book_with_pages(
        db, "doc-chapter",
        pages=(("Chapter One: Foundations", "quantum mechanics overview text"),),
    )
    register_fake("An answer.")
    con = connect_read(db)
    try:
        result = answer_book_question(
            con, document_id="doc-chapter", question="overview?",
            model=StubEmbedding(), investigation_id="read-doc-chapter",
            config=_config_for("user_agent"),
        )
    finally:
        con.close()
    assert result.citations
    assert all(not c.page_resolved and c.page_index is None for c in result.citations)


# ---------------------------------------------------------------------------
# M1 — corpus search
# ---------------------------------------------------------------------------


@pytest.fixture
def client(db):
    from fastapi.testclient import TestClient

    from interfaces.research.api.app import create_app

    # register_providers=False so no real keyed provider is wired; our tests
    # register a fake provider explicitly where a dispatch is exercised.
    app = create_app(register_wrestling=False, register_providers=False, cors_origins=[])
    return TestClient(app)


def test_corpus_search_returns_ranked_owned_docs(db, client, monkeypatch):
    """A typed query returns owned-corpus hits. The embedding model is the
    deterministic stub (monkeypatched onto SentenceTransformerEmbedding)."""
    import sys

    monkeypatch.setattr(
        sys.modules["substrate.graph.search"], "SentenceTransformerEmbedding",
        lambda: StubEmbedding(),
    )
    _book_with_pages(db, "doc-cs-1", title="Quantum Book")
    res = client.get("/corpus/search", params={"q": "quantum mechanics"})
    assert res.status_code == 200
    body = res.json()
    assert body["count"] >= 1
    ids = {h["document_id"] for h in body["hits"]}
    assert "doc-cs-1" in ids
    # A hit anchored to 'Page N' resolves a page; the snippet is bounded.
    assert any(h["page_resolved"] for h in body["hits"])


def test_corpus_search_excludes_restricted_content(db, client, monkeypatch):
    """The §9.0 gate: a restricted book is never in corpus-search results."""
    import sys

    monkeypatch.setattr(
        sys.modules["substrate.graph.search"], "SentenceTransformerEmbedding",
        lambda: StubEmbedding(),
    )
    _restricted_book(db, "doc-cs-restricted", title="Restricted Quantum")
    res = client.get("/corpus/search", params={"q": "quantum passage entanglement"})
    body = res.json()
    ids = {h["document_id"] for h in body["hits"]}
    assert "doc-cs-restricted" not in ids
    assert all("WITHHELDSECRET" not in h["snippet"] for h in body["hits"])


def test_corpus_search_empty_query_returns_empty(db, client):
    res = client.get("/corpus/search", params={"q": "   "})
    assert res.status_code == 200
    assert res.json()["count"] == 0


# ---------------------------------------------------------------------------
# M4 — meta-reading: owned-corpus-only, hard length-box, §9.0, saves
# ---------------------------------------------------------------------------


def test_meta_reading_is_owned_corpus_only(db):
    """The synthesis draws ONLY on owned docs — its corpus_document_ids are
    exactly the owned servable set, and the retrieved context is from those
    docs. (Internet-agnosticism is structural: retrieval is search() over owned
    ids; there is no acquisition/open-web path on this code path.)"""
    from substrate.books.meta_reading import generate_meta_reading

    _book_with_pages(db, "doc-mr-1", title="Owned Quantum")
    register_fake("A synthesis over owned books.")
    con = connect_read(db)
    try:
        deliverable = generate_meta_reading(
            con, prompt="quantum themes", unit="pages", amount=1,
            model=StubEmbedding(), investigation_id="read-meta-x",
            config=_config_for("synthesizer"),
        )
    finally:
        con.close()
    assert deliverable.empty is False
    assert deliverable.corpus_document_ids == ["doc-mr-1"]
    assert deliverable.citations
    assert all(c.document_id == "doc-mr-1" for c in deliverable.citations)


def test_meta_reading_never_cites_withheld_region(db):
    """A restricted book in the corpus must never appear in the synthesis'
    citations OR its retrieved context (§9.0 gate). The owned set is servable-
    only, AND the gate excludes restricted content at retrieval — defense in
    depth."""
    from substrate.books.meta_reading import generate_meta_reading

    _book_with_pages(db, "doc-mr-ok", title="Owned OK")
    _restricted_book(db, "doc-mr-restricted")
    provider = register_fake("Synthesis.")
    con = connect_read(db)
    try:
        deliverable = generate_meta_reading(
            con, prompt="quantum passage entanglement", unit="pages", amount=1,
            model=StubEmbedding(), investigation_id="read-meta-y",
            config=_config_for("synthesizer"),
        )
    finally:
        con.close()
    cited_docs = {c.document_id for c in deliverable.citations}
    assert "doc-mr-restricted" not in cited_docs
    assert "doc-mr-restricted" not in deliverable.corpus_document_ids
    assert all("WITHHELDSECRET" not in p for p in provider.prompts)


def test_meta_reading_empty_corpus_is_honest(db):
    """No owned books ⇒ an honest empty deliverable, no dispatch, no fabricated
    report."""
    from substrate.books.meta_reading import generate_meta_reading

    provider = register_fake("should not be called")
    con = connect_read(db)
    try:
        deliverable = generate_meta_reading(
            con, prompt="anything", unit="pages", amount=1,
            model=StubEmbedding(), investigation_id="read-meta-empty",
            config=_config_for("synthesizer"),
        )
    finally:
        con.close()
    assert deliverable.empty is True
    assert deliverable.report == ""
    assert deliverable.citations == []
    assert provider.prompts == []


def test_meta_reading_endpoint_rejects_degenerate_length(db, client, monkeypatch):
    """0-minute / above-cap requests are rejected with a STATED bound (422),
    never silently clamped."""
    import sys

    monkeypatch.setattr(
        sys.modules["substrate.graph.search"], "SentenceTransformerEmbedding",
        lambda: StubEmbedding(),
    )
    zero = client.post("/corpus/meta-reading", json={
        "prompt": "x", "length_unit": "minutes", "length_amount": 0,
    })
    # pydantic ge=1 on the request OR the substrate bound — either way refused.
    assert zero.status_code in (422,)
    huge = client.post("/corpus/meta-reading", json={
        "prompt": "x", "length_unit": "pages", "length_amount": 9999,
    })
    assert huge.status_code == 422
    assert "capped" in huge.json()["detail"].lower()


def test_meta_reading_endpoint_saves_asset_through_funnel(db, client, monkeypatch):
    """The deliverable is persisted as substrate truth: a
    read.meta_reading.generated event lands in the trajectory (single-writer
    funnel), re-openable later. NOT a side-store."""
    import sys

    from substrate.event_log import trajectory

    monkeypatch.setattr(
        sys.modules["substrate.graph.search"], "SentenceTransformerEmbedding",
        lambda: StubEmbedding(),
    )
    _book_with_pages(db, "doc-mr-save", title="Saveable")
    register_fake("Saved synthesis.")

    res = client.post("/corpus/meta-reading", json={
        "prompt": "quantum themes", "length_unit": "pages", "length_amount": 1,
        "corpus_scope": "hard",
    })
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["empty"] is False
    assert body["asset_id"].startswith("mr-")
    assert body["corpus_document_ids"] == ["doc-mr-save"]
    assert body["word_budget"] == 300  # 1 page × 300 words

    inv = f"read-meta-{body['asset_id']}"
    events = trajectory(inv)
    saved = [e for e in events if e.get("action_type") == "read.meta_reading.generated"]
    assert len(saved) == 1, "deliverable must be saved through the single-writer funnel"
    assert saved[0]["payload"]["asset_id"] == body["asset_id"]
    assert saved[0]["payload"]["corpus_scope"] == "hard"


# ---------------------------------------------------------------------------
# search() multi-doc scope — the seam meta-reading depends on
# ---------------------------------------------------------------------------


def test_search_document_ids_scopes_to_the_set(db):
    """``search(document_ids=[a, b])`` returns chunks from ONLY those docs in
    one gated query — the owned-corpus IN-clause meta-reading relies on."""
    from substrate.graph.search import search

    _book_with_pages(db, "doc-in-a", title="A")
    _book_with_pages(db, "doc-in-b", title="B")
    _book_with_pages(db, "doc-in-c", title="C")
    con = connect_read(db)
    try:
        res = search(
            con, "quantum", model=StubEmbedding(), top_k=50,
            document_ids=["doc-in-a", "doc-in-b"],
        )
    finally:
        con.close()
    docs = {r["document_id"] for r in res["results"]}
    assert docs <= {"doc-in-a", "doc-in-b"}
    assert "doc-in-c" not in docs


def test_search_empty_document_ids_returns_nothing(db):
    """An EXPLICITLY-empty owned set returns no results — never the whole
    corpus (the owned-corpus scope must not silently widen)."""
    from substrate.graph.search import search

    _book_with_pages(db, "doc-empty-scope", title="X")
    con = connect_read(db)
    try:
        res = search(con, "quantum", model=StubEmbedding(), top_k=50, document_ids=[])
    finally:
        con.close()
    assert res["results"] == []


def test_search_excludes_restricted_in_document_ids_scope(db):
    """The §9.0 gate applies inside the IN-clause too: a restricted doc named
    in the set is still excluded."""
    from substrate.graph.search import search

    _book_with_pages(db, "doc-scope-ok", title="OK")
    _restricted_book(db, "doc-scope-restricted")
    con = connect_read(db)
    try:
        res = search(
            con, "quantum passage", model=StubEmbedding(), top_k=50,
            document_ids=["doc-scope-ok", "doc-scope-restricted"],
        )
    finally:
        con.close()
    docs = {r["document_id"] for r in res["results"]}
    assert "doc-scope-restricted" not in docs
