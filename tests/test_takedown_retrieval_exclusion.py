"""Taken-down books keep their chunks, but chunk retrieval must not return them."""

from __future__ import annotations

import os

import pytest

from processing.embedding.embed import HashEmbedding
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


def _doc(con, doc_id: str, text: str, model, *, content_class, owner="__operator__",
         asset: bool | None = False):
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


def _search(con, model, tag: str):
    return search(con, "body", model=model, policy_tag=tag, top_k=20)


def test_privileged_search_loses_retained_chunks_after_real_takedown(env):
    model = HashEmbedding(dimension=8)
    with connect_write(env, purpose="test/takedown-seed") as con:
        _doc(con, "down", SENTINEL, model, content_class="public_domain", asset=False)
        _doc(con, "restricted", RESTRICTED, model, content_class="restricted_pending_opt_in", asset=False)
        _doc(con, "mine", PRIVATE, model, content_class="personal_reading", asset=False)
        _doc(con, "theirs", FOREIGN, model, content_class="personal_reading", owner="other", asset=False)
        _doc(con, "open", OPEN, model, content_class="public_domain", asset=False)
        _doc(con, "null-class", NULL_CLASS, model, content_class=None, asset=True)
        _doc(con, "no-asset", NO_ASSET, model, content_class="public_domain", asset=None)
        _doc(con, "flag-false", FLAG_FALSE, model, content_class="public_domain", asset=False)
        assert take_down(con, "down", reason="rights request") is True
        assert take_down(con, "down", reason="rights request") is False
        con.execute("DROP INDEX IF EXISTS idx_book_assets_taken_down")
        con.execute("ALTER TABLE book_assets ALTER COLUMN taken_down DROP NOT NULL")
        _doc(con, "flag-null", FLAG_NULL, model, content_class="public_domain", asset=None)
        con.execute(
            "INSERT INTO book_assets (document_id, taken_down) VALUES ('flag-null', NULL)"
        )
        for tag in ("operator_only", "private_research"):
            found = _texts(_search(con, model, tag))
            assert SENTINEL not in found
            assert RESTRICTED in found
            assert PRIVATE in found
            assert FOREIGN not in found
            assert OPEN in found
            assert NULL_CLASS not in found
            assert NO_ASSET in found
            assert FLAG_FALSE in found
            assert FLAG_NULL in found
        public = _texts(_search(con, model, "attribution_eligible"))
        assert SENTINEL not in public
        assert RESTRICTED not in public
        assert PRIVATE not in public
        assert OPEN in public
        brute = DuckDbVssSubstrate.from_con(con, model=model).query(
            "body", top_k=20, policy_tag="operator_only",
        )
        assert SENTINEL not in _texts(brute)
        substrate = DuckDbVssSubstrate.open(env, model=model)
        try:
            opened = substrate.query("body", top_k=20, policy_tag="private_research")
        finally:
            substrate.close()
        assert SENTINEL not in _texts(opened)
        class _Row:
            def __init__(self, row_id):
                self.id = row_id
        class _Block:
            rows = [_Row("chunk-down"), _Row("chunk-open")]
        class _Response:
            results = [_Block()]
        class _Namespace:
            def multi_query(self, **_kwargs):
                return _Response()
        hydrated = TurbopufferSubstrate(
            con, model=model, api_key="offline", namespace=_Namespace(),
            manifest_dir=os.path.dirname(env),
        ).query("body", top_k=20, policy_tag="attribution_eligible")
        assert SENTINEL not in _texts(hydrated)
        assert OPEN in _texts(hydrated)
        empty = TurbopufferSubstrate(
            con, model=model, api_key="offline",
            namespace=type("NS", (), {"multi_query": lambda self, **_k: type("R", (), {"results": []})()})(),
            manifest_dir=os.path.dirname(env),
        ).query("body", top_k=20, policy_tag="operator_only")
        assert SENTINEL not in _texts(empty)
        assert reinstate(con, "down") is True
        restored = _texts(_search(con, model, "operator_only"))
        assert SENTINEL in restored
        raw = con.execute("SELECT raw_text FROM documents WHERE document_id='down'").fetchone()[0]
        assert raw is None
