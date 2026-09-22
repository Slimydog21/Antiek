"""MCP ``search_personal`` — the caller's owner and the caller's query (SPR-11 T2).

Before this task the handler bound a hardcoded pseudo-owner and never used the
query: every caller got the first N chunks of one storage sentinel in document
order. These tests pin the three properties the published manifest promises:
the query changes the answer, the owner bounds the answer, and a request that
proves no owner gets an error rather than someone's chunks.

The embedding model is a deterministic bag-of-words stub injected through the
same factory seam production fills with sentence-transformers, so the ranking
path exercised here is the real ``substrate.graph.search.search``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from runtime.db_lock import connect_write
from substrate.graph.schema import init_database_at_path
from tools.antiek_memory.__main__ import _make_handlers
from tools.antiek_memory.server import AntiekMemoryServer

_TERMS = ("quantum", "bakery", "garden")


class _BagOfWordsEmbedding:
    """One dimension per vocabulary term plus a constant so no vector is zero."""

    dimension = len(_TERMS) + 1

    def encode(self, text: str) -> list[float]:
        folded = text.casefold()
        return [float(folded.count(term)) for term in _TERMS] + [0.05]


_CORPUS = {
    "owner-a": [
        ("chunk-a-quantum", "Quantum error correction notes from the reading group."),
        ("chunk-a-bakery", "The village bakery ledger for the spring season."),
        ("chunk-a-garden", "Garden soil records and planting dates."),
    ],
    "owner-b": [
        ("chunk-b-quantum", "Quantum annealing benchmarks, second pass."),
        ("chunk-b-bakery", "Bakery supplier invoices and flour prices."),
    ],
}


@pytest.fixture
def db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    path = str(tmp_path / "graph.duckdb")
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    init_database_at_path(path)
    embed = _BagOfWordsEmbedding()
    with connect_write(path, purpose="seed-search-personal") as con:
        for owner, chunks in _CORPUS.items():
            document_id = f"doc-{owner}"
            con.execute(
                "INSERT INTO documents (document_id, title, source_tier, document_type, "
                "owner_user_id) VALUES (?, ?, 1, 'article', ?)",
                [document_id, f"Library of {owner}", owner],
            )
            for index, (chunk_id, text) in enumerate(chunks):
                con.execute(
                    "INSERT INTO chunks (chunk_id, document_id, chunk_index, text, "
                    "embedding, token_count) VALUES (?, ?, ?, ?, ?, 8)",
                    [chunk_id, document_id, index, text, embed.encode(text)],
                )
    return path


@pytest.fixture
def search_personal(db_path: str):
    handlers, _resources = _make_handlers(db_path, embedding_model=_BagOfWordsEmbedding)
    return handlers["search_personal"]


def _chunk_ids(result) -> set[str]:
    body = json.loads(result.content[0]["text"])
    return {chunk["chunk_id"] for chunk in body["chunks"]}


def test_two_queries_for_one_owner_return_different_chunk_sets(search_personal) -> None:
    auth = {"user_id": "owner-a"}
    quantum = search_personal({"query": "quantum", "top_k": 1}, auth_context=auth)
    bakery = search_personal({"query": "bakery", "top_k": 1}, auth_context=auth)

    assert quantum.is_error is False and bakery.is_error is False
    assert _chunk_ids(quantum) == {"chunk-a-quantum"}
    assert _chunk_ids(bakery) == {"chunk-a-bakery"}
    assert _chunk_ids(quantum) != _chunk_ids(bakery)


def test_two_owners_return_disjoint_chunk_sets(search_personal) -> None:
    owner_a = search_personal({"query": "quantum bakery", "top_k": 10}, auth_context={"user_id": "owner-a"})
    owner_b = search_personal({"query": "quantum bakery", "top_k": 10}, auth_context={"user_id": "owner-b"})

    ids_a, ids_b = _chunk_ids(owner_a), _chunk_ids(owner_b)
    assert ids_a == {"chunk-a-quantum", "chunk-a-bakery", "chunk-a-garden"}
    assert ids_b == {"chunk-b-quantum", "chunk-b-bakery"}
    assert ids_a.isdisjoint(ids_b)
    for chunk in json.loads(owner_a.content[0]["text"])["chunks"]:
        assert chunk["owner_user_id"] == "owner-a"
        assert chunk["text"] in dict(_CORPUS["owner-a"]).values()


def test_missing_auth_context_is_an_error_with_zero_chunks(search_personal) -> None:
    result = search_personal({"query": "quantum", "top_k": 10})

    assert result.is_error is True
    body = json.loads(result.content[0]["text"])
    assert body["chunks"] == []
    assert body["query"] == "quantum"
    assert "auth_context" in body["error"]


@pytest.mark.parametrize(
    "auth_context",
    [None, {}, {"user_id": ""}, {"user_id": "   "}, {"user_id": 7}, {"scopes": ["memory"]},
     {"user_id": "__operator__"}, {"user_id": "shared"}, {"user_id": "Service"}],
)
def test_unproven_or_shared_identity_fails_closed(search_personal, auth_context) -> None:
    result = search_personal({"query": "quantum"}, auth_context=auth_context)

    assert result.is_error is True
    assert json.loads(result.content[0]["text"])["chunks"] == []


def test_owner_with_no_documents_gets_an_honest_empty_answer(db_path: str) -> None:
    def _never() -> _BagOfWordsEmbedding:
        raise AssertionError("no documents in scope must not load the embedding model")

    handlers, _resources = _make_handlers(db_path, embedding_model=_never)
    result = handlers["search_personal"]({"query": "quantum"}, auth_context={"user_id": "owner-c"})

    assert result.is_error is False
    assert _chunk_ids(result) == set()


def test_server_threads_transport_auth_context_and_ignores_argument_claims(db_path: str) -> None:
    handlers, resources = _make_handlers(db_path, embedding_model=_BagOfWordsEmbedding)
    server = AntiekMemoryServer(handler_fns=handlers, resource_handler=resources)

    def call(params: dict) -> dict:
        response = server.handle_request(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": params}
        )
        assert response is not None
        return response["result"]

    # A self-asserted owner inside ``arguments`` proves nothing: error, no chunks.
    forged = call({
        "name": "search_personal",
        "arguments": {"query": "quantum", "auth_context": {"user_id": "owner-a"}},
    })
    assert forged["isError"] is True
    assert json.loads(forged["content"][0]["text"])["chunks"] == []

    # The transport-level field is the one that counts.
    genuine = call({
        "name": "search_personal",
        "arguments": {"query": "quantum", "top_k": 1},
        "auth_context": {"user_id": "owner-a"},
    })
    assert genuine["isError"] is False
    body = json.loads(genuine["content"][0]["text"])
    assert [chunk["chunk_id"] for chunk in body["chunks"]] == ["chunk-a-quantum"]
