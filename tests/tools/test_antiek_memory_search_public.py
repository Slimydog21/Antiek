"""Rights and ranking checks for the public MCP chunk search."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from runtime.db_lock import connect_read, connect_write
from substrate.graph.retrieval_gate import PERSONAL_ONLY_CONTENT_CLASSES, RESTRICTED_CONTENT_CLASSES
from substrate.graph.schema import init_database_at_path
from substrate.graph.search import search
from tools.antiek_memory.__main__ import PUBLIC_SURFACE_CONTENT_CLASSES, _make_handlers

_TERMS = ("quantum", "bakery", "garden")


class _BagOfWordsEmbedding:
    dimension = len(_TERMS) + 1

    def encode(self, text: str) -> list[float]:
        folded = text.casefold()
        return [float(folded.count(term)) for term in _TERMS] + [0.05]


_CASES = (
    ("pd", "public_domain", "__operator__", "Public domain quantum body"),
    ("upc", "user_public_contribution", "user-b", "User public quantum body"),
    ("oil", "opt_in_licensed", "__operator__", "Licensed quantum body"),
    ("sdo", "source_declared_open", "__operator__", "Open source quantum body"),
    ("r", "restricted_pending_opt_in", "__operator__", "RESTRICTED BODY quantum"),
    ("pr", "personal_reading", "__operator__", "PERSONAL BODY quantum"),
    ("uo", "user_owned", "user-b", "USER OWNED BODY quantum"),
    ("null", None, "__operator__", "NULL RIGHTS BODY quantum"),
    ("td", "public_domain", "__operator__", "TAKEN DOWN BODY quantum"),
)


def _insert_chunk(
    con,
    *,
    name: str,
    content_class: str | None,
    owner: str,
    body: str,
) -> None:
    con.execute(
        "INSERT INTO documents (document_id, title, source_tier, document_type, "
        "content_class, owner_user_id) VALUES (?, ?, 1, 'article', ?, ?)",
        [f"doc-{name}", f"Title {name}", content_class, owner],
    )
    con.execute(
        "INSERT INTO chunks (chunk_id, document_id, chunk_index, text, "
        "embedding, token_count) VALUES (?, ?, 0, ?, ?, 8)",
        [f"chunk-{name}", f"doc-{name}", body, _BagOfWordsEmbedding().encode(body)],
    )


@pytest.fixture
def db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    path = str(tmp_path / "graph.duckdb")
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    init_database_at_path(path)
    with connect_write(path, purpose="seed-search-public") as con:
        for name, content_class, owner, body in _CASES:
            _insert_chunk(
                con, name=name, content_class=content_class, owner=owner, body=body
            )
        con.execute(
            "INSERT INTO book_assets (document_id, taken_down) VALUES (?, TRUE)",
            ["doc-td"],
        )
    return path


def test_search_public_serves_only_public_servable_classes(db_path: str) -> None:
    handlers, _resources = _make_handlers(db_path, embedding_model=_BagOfWordsEmbedding)
    result = handlers["search_public"]({"query": "quantum", "top_k": 50})

    raw = result.content[0]["text"]
    chunks = json.loads(raw)["chunks"]
    assert {chunk["chunk_id"] for chunk in chunks} == {
        "chunk-pd", "chunk-upc", "chunk-oil", "chunk-sdo"
    }
    assert all(chunk["text"].startswith('<antiek:content trusted="false">') for chunk in chunks)
    for body in ("RESTRICTED BODY", "PERSONAL BODY", "USER OWNED BODY", "NULL RIGHTS BODY", "TAKEN DOWN BODY"):
        assert body not in raw


def test_query_matching_nothing_returns_an_honest_empty(db_path: str) -> None:
    handlers, _resources = _make_handlers(db_path, embedding_model=_BagOfWordsEmbedding)
    result = handlers["search_public"]({"query": "zzz-no-such-term", "top_k": 50})

    assert result.is_error is False
    body = json.loads(result.content[0]["text"])
    assert body["query"] == "zzz-no-such-term"
    assert body["chunks"] == []
    assert body["no_match"] is True


def test_non_matching_public_chunk_is_absent(db_path: str) -> None:
    with connect_write(db_path, purpose="seed-nonmatching-public") as con:
        _insert_chunk(
            con, name="unrelated", content_class="public_domain", owner="__operator__",
            body="Mitochondria generate cellular energy.",
        )
    handlers, _resources = _make_handlers(db_path, embedding_model=_BagOfWordsEmbedding)
    result = handlers["search_public"]({"query": "quantum", "top_k": 50})

    assert result.is_error is False
    chunks = json.loads(result.content[0]["text"])["chunks"]
    chunk_ids = {chunk["chunk_id"] for chunk in chunks}
    assert "chunk-pd" in chunk_ids
    assert "chunk-unrelated" not in chunk_ids


@pytest.mark.parametrize("top_k", [0, 51, "5", True])
def test_top_k_out_of_bounds_is_an_error(db_path: str, top_k) -> None:
    handlers, _resources = _make_handlers(db_path, embedding_model=_BagOfWordsEmbedding)
    result = handlers["search_public"]({"query": "quantum", "top_k": top_k})

    assert result.is_error is True
    assert json.loads(result.content[0]["text"])["error"] == (
        "top_k must be an integer between 1 and 50"
    )


def test_search_public_query_changes_the_answer(db_path: str) -> None:
    with connect_write(db_path, purpose="seed-search-public-ranking") as con:
        _insert_chunk(
            con, name="bakery", content_class="public_domain", owner="__operator__",
            body="The bakery makes bread",
        )
        _insert_chunk(
            con, name="garden", content_class="public_domain", owner="__operator__",
            body="The garden grows flowers",
        )
    handlers, _resources = _make_handlers(db_path, embedding_model=_BagOfWordsEmbedding)

    def top_chunk(query: str) -> str:
        result = handlers["search_public"]({"query": query, "top_k": 1})
        return json.loads(result.content[0]["text"])["chunks"][0]["chunk_id"]

    assert top_chunk("bakery") == "chunk-bakery"
    assert top_chunk("garden") == "chunk-garden"


def test_public_surface_allowlist_is_disjoint_from_the_gate() -> None:
    assert {
        "public_domain", "user_public_contribution", "opt_in_licensed", "source_declared_open"
    } == PUBLIC_SURFACE_CONTENT_CLASSES
    assert PUBLIC_SURFACE_CONTENT_CLASSES.isdisjoint(
        RESTRICTED_CONTENT_CLASSES | PERSONAL_ONLY_CONTENT_CLASSES
    )
    assert "user_owned" not in PUBLIC_SURFACE_CONTENT_CLASSES


def test_search_content_classes_none_preserves_legacy_scope(db_path: str) -> None:
    with connect_read(db_path) as con:
        empty = search(
            con, "quantum", model=_BagOfWordsEmbedding(), top_k=50,
            policy_tag="attribution_eligible", content_classes=frozenset(),
        )
        unrestricted = search(
            con, "quantum", model=_BagOfWordsEmbedding(), top_k=50,
            policy_tag="attribution_eligible", content_classes=None,
        )

    assert empty["results"] == []
    assert {"chunk-uo", "chunk-null"} <= {
        hit["chunk_id"] for hit in unrestricted["results"]
    }


def test_search_content_classes_scopes_the_ranking_in_sql(db_path: str) -> None:
    # The MCP handler re-checks each hit, so this pins the SQL scope on its own:
    # search() itself must rank only allowlisted classes (NULL never matches).
    with connect_read(db_path) as con:
        scoped = search(
            con, "quantum", model=_BagOfWordsEmbedding(), top_k=50,
            policy_tag="attribution_eligible",
            content_classes=frozenset({"public_domain", "user_public_contribution"}),
        )

    assert {hit["chunk_id"] for hit in scoped["results"]} == {
        "chunk-pd", "chunk-upc", "chunk-td"
    }
