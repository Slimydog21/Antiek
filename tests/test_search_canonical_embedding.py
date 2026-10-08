"""Canonical ingestion/query identity with real private SQL and authenticated HTTP.

The dependency control supplies deterministic vectors, not pretrained-model proof.
The Linux cold-child control separately uses real MiniLM weights and these ports.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
from processing.embedding import (
    HashEmbedding,
    SentenceTransformerEmbedding,
    embedding_provider_fingerprint,
)
from runtime.db_lock import connect_read, connect_write
from substrate.auth import mint_session_cookie
from substrate.graph import insert_chunk, insert_document
from substrate.graph.search import SentenceTransformerEmbedding as QueryEmbedding
from substrate.graph.search import search


@pytest.fixture
def model_dependency(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    calls: list[tuple[str, str]] = []

    class ControlledEncoder:
        max_seq_length = 256
        tokenizer = None

        def __init__(self, name: str, *, device: str) -> None:
            calls.append((name, device))

        def get_sentence_embedding_dimension(self) -> int:
            return 384

        def encode(self, texts: list[str]) -> list[list[float]]:
            return [[1.0, *([0.0] * 383)] for _ in texts]

    dependency = ModuleType("sentence_transformers")
    dependency.SentenceTransformer = ControlledEncoder  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "sentence_transformers", dependency)
    monkeypatch.setitem(
        sys.modules, "torch",
        SimpleNamespace(backends=SimpleNamespace(mkldnn=SimpleNamespace(enabled=True))),
    )
    return calls


def _store(provider: Any, *, unresolved: bool = False) -> None:
    body = "A reading note preserves the evidence behind a historical claim."
    with connect_write(os.environ["ANTIEK_DUCKDB_PATH"], purpose="canonical-search-control") as con:
        insert_document(
            con, document_id="canonical-control", title="Reading evidence control",
            source_tier=4, document_type="article", content_class="user_owned",
            owner_user_id="__operator__", raw_text=body,
        )
        insert_chunk(
            con, document_id="canonical-control", chunk_index=0,
            text=body, section_path="Page 2", embedding=provider.encode(body),
            embedding_provider=provider,
        )
        if unresolved:
            text = "This second note has no resolved page anchor."
            insert_chunk(
                con, document_id="canonical-control", chunk_index=1,
                text=text, section_path="Unresolved section", embedding=provider.encode(text),
                embedding_provider=provider,
            )


def _stored_vectors_and_metadata() -> tuple[list[Any], list[Any]]:
    con = connect_read(os.environ["ANTIEK_DUCKDB_PATH"])
    try:
        return (
            con.execute("SELECT chunk_id, embedding FROM chunks ORDER BY chunk_id").fetchall(),
            con.execute("SELECT * FROM embeddings_meta ORDER BY chunk_id").fetchall(),
        )
    finally:
        con.close()


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    monkeypatch.delenv("ANTIEK_AUTH_MODE", raising=False)
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", "canonical-search@example.invalid")
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", "synthetic-canonical-search-control-secret")
    monkeypatch.setenv("ANTIEK_PUBLIC_SIGNUP_ENABLED", "0")
    app = create_app(
        register_wrestling=False, register_providers=False,
        cors_origins=["https://antiek.ai"],
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        client.cookies.set(
            "ANTIEK_SESSION",
            mint_session_cookie(user_id="__operator__", email="canonical-search@example.invalid"),
        )
        assert client.get("/auth/me").status_code == 200
        yield client


def test_ingestion_metadata_is_accepted_by_the_query_encoder(model_dependency: list[Any]) -> None:
    producer = SentenceTransformerEmbedding()
    _store(producer)
    before = _stored_vectors_and_metadata()
    query = QueryEmbedding()
    con = connect_read(os.environ["ANTIEK_DUCKDB_PATH"])
    try:
        result = search(con, "historical evidence", model=query, policy_tag="private_research")
    finally:
        con.close()
    assert [row["document_id"] for row in result["results"]] == ["canonical-control"]
    assert embedding_provider_fingerprint(query) == embedding_provider_fingerprint(producer)
    assert QueryEmbedding is SentenceTransformerEmbedding
    assert model_dependency == [("all-MiniLM-L6-v2", "cpu")] * 2
    assert _stored_vectors_and_metadata() == before


@pytest.mark.parametrize("different_identity", ["model", "provider", "hash"])
def test_equal_dimensions_do_not_admit_a_different_identity(
    model_dependency: list[Any], different_identity: str,
) -> None:
    class OtherProvider:
        provider_name = "different-provider"
        model_name = "all-MiniLM-L6-v2"
        dimension = 384

        def encode(self, _text: str) -> list[float]:
            return [1.0, *([0.0] * 383)]

    producer = {
        "model": lambda: SentenceTransformerEmbedding("different-model"),
        "provider": OtherProvider,
        "hash": lambda: HashEmbedding(dimension=384),
    }[different_identity]()
    _store(producer)
    before = _stored_vectors_and_metadata()
    con = connect_read(os.environ["ANTIEK_DUCKDB_PATH"])
    try:
        with pytest.raises(ValueError) as failure:
            search(con, "historical evidence", model=QueryEmbedding(), policy_tag="private_research")
    finally:
        con.close()
    assert type(failure.value).__name__ == "EmbeddingCompatibilityError"
    assert _stored_vectors_and_metadata() == before


def test_authenticated_http_returns_actual_ingested_hits_and_page_resolution(
    client: TestClient, model_dependency: list[Any],
) -> None:
    _store(SentenceTransformerEmbedding(), unresolved=True)
    before = _stored_vectors_and_metadata()
    response = client.get("/corpus/search?q=historical%20evidence", headers={"Origin": "https://antiek.ai"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["query"] == "historical evidence" and body["count"] == 2
    hits = {hit["snippet"]: hit for hit in body["hits"]}
    assert {hit["document_id"] for hit in hits.values()} == {"canonical-control"}
    assert hits["A reading note preserves the evidence behind a historical claim."]["page_index"] == 1
    assert hits["A reading note preserves the evidence behind a historical claim."]["page_resolved"] is True
    assert hits["This second note has no resolved page anchor."]["page_index"] is None
    assert hits["This second note has no resolved page anchor."]["page_resolved"] is False
    assert response.headers["access-control-allow-origin"] == "https://antiek.ai"
    assert _stored_vectors_and_metadata() == before


@pytest.mark.parametrize("origin", ["https://antiek.ai", "https://unallowed.invalid", None])
def test_real_incompatible_metadata_is_an_opaque_503_with_cors(
    client: TestClient, model_dependency: list[Any], origin: str | None,
) -> None:
    _store(SentenceTransformerEmbedding("private-model-identity"))
    before = _stored_vectors_and_metadata()
    headers = {} if origin is None else {"Origin": origin}
    response = client.get("/corpus/search?q=historical%20evidence", headers=headers)
    assert response.status_code == 503
    assert response.json() == {"detail": "embedding_incompatible"}
    assert "private-model-identity" not in response.text
    assert "hits" not in response.json()
    if origin == "https://antiek.ai":
        assert response.headers["access-control-allow-origin"] == origin
    else:
        assert "access-control-allow-origin" not in response.headers
    assert _stored_vectors_and_metadata() == before


def test_unrelated_search_value_error_is_not_disguised_as_compatibility(
    client: TestClient, model_dependency: list[Any], monkeypatch: pytest.MonkeyPatch,
) -> None:
    from importlib import import_module

    def fail(*_args: Any, **_kwargs: Any) -> None:
        raise ValueError("unrelated-query-defect")

    monkeypatch.setattr(import_module("substrate.graph.search"), "search", fail)
    assert client.get("/corpus/search?q=control").status_code == 500
