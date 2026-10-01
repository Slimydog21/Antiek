"""Taken-down books keep their chunks, but chunk retrieval must not return them."""

from __future__ import annotations

import os

import pytest

from orchestration.loop_one.orchestrator import (
    _keyword_search_chunks,
    _render_chunks_block_for_sub_question,
)
from processing.embedding.embed import (
    HashEmbedding,
    _reset_default_provider,
    set_default_embedding_provider,
)
from runtime.db_lock import connect_write
from substrate.books.takedown import reinstate, take_down
from substrate.graph.retrieval_adapters.turbopuffer import TurbopufferSubstrate
from substrate.graph.retrieval_substrate import DuckDbVssSubstrate
from substrate.graph.schema import init_database_at_path
from substrate.graph.search import search

SENTINEL = "TAKEDOWN-SENTINEL-BODY"
RESTRICTED = "UNTAKEN-RESTRICTED-BODY"
PRIVATE = "SAME-OWNER-PRIVATE-BODY"
FOREIGN = "OTHER-OWNER-PRIVATE-BODY"
OPEN = "OPEN-CONTROL-BODY"
OPEN_TAKEN = "OPEN-CLASS-TAKEN-BODY"
NULL_CLASS = "NULL-CLASS-TAKEN-BODY"
NO_ASSET = "MISSING-ASSET-BODY"
FLAG_FALSE = "FLAG-FALSE-BODY"
FLAG_NULL = "FLAG-NULL-BODY"


@pytest.fixture
def env(tmp_path, monkeypatch):
    db = str(tmp_path / "gate.duckdb")
    events = str(tmp_path / "events")
    os.makedirs(events)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    monkeypatch.delenv("TURBOPUFFER_API_KEY", raising=False)
    monkeypatch.delenv("ANTIEK_TURBOPUFFER_SERVABLE", raising=False)
    monkeypatch.delenv("ANTIEK_TURBOPUFFER_SHADOW_ENABLED", raising=False)
    init_database_at_path(db)
    return db


def _doc(
    con,
    doc_id: str,
    text: str,
    model,
    *,
    content_class,
    owner="__operator__",
    asset: bool | None = False,
):
    con.execute(
        "INSERT INTO documents (document_id, title, source_tier, document_type, "
        "content_class, owner_user_id, raw_text) VALUES (?, ?, 2, 'book', ?, ?, ?)",
        [doc_id, doc_id, content_class, owner, "raw-" + text],
    )
    con.execute(
        "INSERT INTO chunks (chunk_id, document_id, chunk_index, text, embedding) "
        "VALUES (?, ?, 0, ?, ?)",
        [f"chunk-{doc_id}", doc_id, text, model.encode(text)],
    )
    if asset is not None:
        con.execute(
            "INSERT INTO book_assets (document_id, taken_down) VALUES (?, ?)",
            [doc_id, asset],
        )


def _texts(payload) -> str:
    return " ".join(row.get("chunk_text") or "" for row in payload["results"])


def _search(con, model, tag: str, *, owner_user_id: str | None = None):
    return search(
        con, "body", model=model, policy_tag=tag, top_k=20,
        owner_user_id=owner_user_id,
    )


def _seed_corpus(con, model) -> None:
    """Rows whose class gate would still serve them, plus the real takedown."""
    _doc(con, "down", SENTINEL, model, content_class="public_domain", asset=False)
    _doc(
        con, "restricted", RESTRICTED, model, content_class="restricted_pending_opt_in", asset=False
    )
    _doc(con, "mine", PRIVATE, model, content_class="personal_reading", owner="owner-a", asset=False)
    _doc(
        con, "theirs", FOREIGN, model, content_class="personal_reading", owner="other", asset=False
    )
    _doc(con, "open", OPEN, model, content_class="public_domain", asset=False)
    # Stays public_domain. take_down() would rewrite the class, which would
    # let the public class gate hide the row without the takedown predicate.
    _doc(con, "open-taken", OPEN_TAKEN, model, content_class="public_domain", asset=True)
    _doc(con, "null-class", NULL_CLASS, model, content_class=None, asset=True)
    _doc(con, "no-asset", NO_ASSET, model, content_class="public_domain", asset=None)
    _doc(con, "flag-false", FLAG_FALSE, model, content_class="public_domain", asset=False)
    assert take_down(con, "down", reason="rights request") is True
    assert take_down(con, "down", reason="rights request") is False


class _Row:
    def __init__(self, row_id):
        self.id = row_id


class _CandidateBlock:
    # chunk-down is restricted_pending_opt_in after take_down, so the class
    # gate would hide it on a public query. These two stay class-eligible.
    rows = [_Row("chunk-null-class"), _Row("chunk-open-taken"), _Row("chunk-open")]


class _CandidateResponse:
    results = [_CandidateBlock()]


class _CandidateNamespace:
    def multi_query(self, **_kwargs):
        return _CandidateResponse()


def _hydrate_public(con, model, env):
    return TurbopufferSubstrate(
        con,
        model=model,
        api_key="offline",
        namespace=_CandidateNamespace(),
        manifest_dir=os.path.dirname(env),
    ).query("body", top_k=20, policy_tag="attribution_eligible")


def _context_block(model) -> str:
    set_default_embedding_provider(model)
    try:
        return _render_chunks_block_for_sub_question(
            "null-class-taken-body open-class-taken-body open-control-body",
            top_k=20,
            policy_tag="operator_only",
        )
    finally:
        _reset_default_provider()


def test_public_hydration_drops_class_eligible_taken_down_rows(env):
    model = HashEmbedding(dimension=8)
    with connect_write(env, purpose="test/takedown-hydration") as con:
        _seed_corpus(con, model)
        hydrated_text = _texts(_hydrate_public(con, model, env))
        assert NULL_CLASS not in hydrated_text
        assert OPEN_TAKEN not in hydrated_text
        assert OPEN in hydrated_text


def test_loop_one_lexical_fallback_omits_taken_down_rows(env):
    model = HashEmbedding(dimension=8)
    with connect_write(env, purpose="test/takedown-lexical") as con:
        _seed_corpus(con, model)
        lexical = _keyword_search_chunks(
            con,
            ["null-class-taken-body", "open-class-taken-body", "open-control-body"],
            20,
            policy_tag="operator_only",
        )
        lexical_text = " ".join(row["chunk_text"] for row in lexical)
        lexical_ids = " ".join(row["chunk_id"] for row in lexical)
        assert NULL_CLASS not in lexical_text
        assert OPEN_TAKEN not in lexical_text
        assert OPEN in lexical_text
        assert "chunk-null-class" not in lexical_ids
        assert "chunk-open-taken" not in lexical_ids
        assert "chunk-open" in lexical_ids


def test_loop_one_context_omits_taken_down_body_and_citation(env):
    model = HashEmbedding(dimension=8)
    with connect_write(env, purpose="test/takedown-context") as con:
        _seed_corpus(con, model)
    block = _context_block(model)
    assert not block.startswith("(corpus search unavailable")
    assert "### chunk_id: chunk-null-class" not in block
    assert "### chunk_id: chunk-open-taken" not in block
    assert "> " + NULL_CLASS not in block
    assert "> " + OPEN_TAKEN not in block
    assert "### chunk_id: chunk-open" in block
    assert "> " + OPEN in block


def test_privileged_search_loses_retained_chunks_after_real_takedown(env):
    model = HashEmbedding(dimension=8)
    with connect_write(env, purpose="test/takedown-seed") as con:
        _seed_corpus(con, model)
        con.execute("DROP INDEX IF EXISTS idx_book_assets_taken_down")
        con.execute("ALTER TABLE book_assets ALTER COLUMN taken_down DROP NOT NULL")
        _doc(con, "flag-null", FLAG_NULL, model, content_class="public_domain", asset=None)
        con.execute("INSERT INTO book_assets (document_id, taken_down) VALUES ('flag-null', NULL)")
        for tag in ("operator_only", "private_research"):
            found = _texts(_search(con, model, tag, owner_user_id="owner-a"))
            assert SENTINEL not in found
            assert OPEN_TAKEN not in found
            assert NULL_CLASS not in found
            assert RESTRICTED in found
            assert PRIVATE in found
            assert FOREIGN not in found
            assert OPEN in found
            assert NO_ASSET in found
            assert FLAG_FALSE in found
            assert FLAG_NULL in found
        public = _texts(_search(con, model, "attribution_eligible"))
        assert SENTINEL not in public
        assert OPEN_TAKEN not in public
        assert NULL_CLASS not in public
        assert RESTRICTED not in public
        assert PRIVATE not in public
        assert OPEN in public
        assert NO_ASSET in public
        assert FLAG_FALSE in public
        assert FLAG_NULL in public
        brute = DuckDbVssSubstrate.from_con(con, model=model).query(
            "body",
            top_k=20,
            policy_tag="operator_only",
            owner_user_id="owner-a",
        )
        assert SENTINEL not in _texts(brute)
        assert OPEN_TAKEN not in _texts(brute)
        substrate = DuckDbVssSubstrate.open(env, model=model)
        try:
            opened = substrate.query(
                "body", top_k=20, policy_tag="private_research",
                owner_user_id="owner-a",
            )
        finally:
            substrate.close()
        opened_text = _texts(opened)
        observed_engine = (
            "vss-flag-true" if substrate.vss_active else "brute-force-fallback"
        )
        # vss_active only names the path open() selected. HNSW is not measured.
        print(
            f"OBSERVED_VSS_ENGINE={observed_engine} "
            f"vss_active={substrate.vss_active} hnsw_measured=false"
        )
        assert SENTINEL not in opened_text, observed_engine
        assert OPEN_TAKEN not in opened_text, observed_engine
        assert NULL_CLASS not in opened_text, observed_engine
        assert OPEN in opened_text, observed_engine
        hydrated_text = _texts(_hydrate_public(con, model, env))
        assert NULL_CLASS not in hydrated_text
        assert OPEN_TAKEN not in hydrated_text
        assert OPEN in hydrated_text
        empty = TurbopufferSubstrate(
            con,
            model=model,
            api_key="offline",
            namespace=type(
                "NS", (), {"multi_query": lambda self, **_k: type("R", (), {"results": []})()}
            )(),
            manifest_dir=os.path.dirname(env),
        ).query("body", top_k=20, policy_tag="operator_only")
        assert SENTINEL not in _texts(empty)
        assert reinstate(con, "down") is True
        restored = _texts(_search(con, model, "operator_only"))
        assert SENTINEL in restored
        assert OPEN_TAKEN not in restored
        assert NULL_CLASS not in restored
        raw = con.execute("SELECT raw_text FROM documents WHERE document_id='down'").fetchone()[0]
        assert raw is None
