"""SR-03 — search ≡ VSS ≡ brute_force ≡ GET /chunks on one seeded graph.

Single fixture DB (public_domain control + personal_reading probe) so surface
parity is proven on identical rows, not independent seeds per path.
"""

from __future__ import annotations

import os
import sys
import tempfile

import pytest
from fastapi.testclient import TestClient

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from runtime.db_lock import connect_read, connect_write
from substrate.graph.ops import insert_chunk, insert_document
from substrate.graph.retrieval_substrate import make_substrate
from substrate.graph.schema import init_database
from substrate.graph.search import search

DOC_PUBLIC = "doc-pd-matrix"
DOC_PERSONAL = "doc-pr-matrix"
QUERY = "quantum optics matrix SR03"


class StubEmbedding:
    dimension = 4

    def encode(self, text: str) -> list[float]:
        h = sum(ord(c) * (i + 1) for i, c in enumerate(text)) or 1
        return [
            float(h % 7) / 7.0,
            float((h >> 3) % 11) / 11.0,
            float((h >> 5) % 13) / 13.0,
            float((h >> 7) % 17) / 17.0,
        ]


@pytest.fixture(scope="module")
def matrix_graph():
    tmp = tempfile.mkdtemp(prefix="antiek-sr03-matrix-")
    db_path = os.path.join(tmp, "graph.duckdb")
    events_dir = os.path.join(tmp, "events")
    os.makedirs(events_dir, exist_ok=True)
    emb = StubEmbedding()
    con = connect_write(db_path, purpose="sr03-matrix-seed")
    try:
        init_database(con)
        chunks: dict[str, str] = {}
        for doc_id, content_class, text in (
            (DOC_PUBLIC, "public_domain", f"{QUERY} public control"),
            (DOC_PERSONAL, "personal_reading", f"{QUERY} personal reading"),
        ):
            insert_document(
                con,
                document_id=doc_id,
                source_tier=2,
                document_type="paper",
                title=f"Title {doc_id}",
                content_class=content_class,
            )
            chunk_id = insert_chunk(
                con,
                document_id=doc_id,
                chunk_index=0,
                text=text,
                token_count=10,
                embedding=emb.encode(text),
            )
            chunks[doc_id] = chunk_id
    finally:
        con.close()
    yield {
        "db_path": db_path,
        "events_dir": events_dir,
        "model": emb,
        "chunks": chunks,
    }


def _doc_ids_from_search(db_path: str, model: StubEmbedding, *, policy_tag: str) -> set[str]:
    con = connect_read(db_path)
    try:
        res = search(
            con,
            QUERY,
            model=model,
            top_k=10,
            policy_tag=policy_tag,
        )
    finally:
        con.close()
    return {r["document_id"] for r in res["results"]}


def _doc_ids_from_substrate(
    db_path: str,
    model: StubEmbedding,
    kind: str,
    *,
    policy_tag: str,
) -> set[str]:
    sub = make_substrate(kind, db_path, model=model)
    try:
        res = sub.query(QUERY, top_k=10, policy_tag=policy_tag)
    finally:
        sub.close()
    return {r["document_id"] for r in res["results"]}


def _get_chunk_client(matrix_graph, monkeypatch):
    import importlib

    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", matrix_graph["db_path"])
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", matrix_graph["events_dir"])
    app_mod = importlib.import_module("interfaces.research.api.app")
    importlib.reload(app_mod)
    app = app_mod.create_app(
        register_wrestling=False,
        register_providers=False,
        cors_origins=[],
    )
    return TestClient(app)


@pytest.mark.parametrize("surface", ["search", "vss", "brute_force"])
def test_attribution_eligible_excludes_personal_reading(matrix_graph, surface):
    """Default policy_tag: public control visible, personal_reading withheld."""
    db_path = matrix_graph["db_path"]
    model = matrix_graph["model"]
    if surface == "search":
        doc_ids = _doc_ids_from_search(
            db_path, model, policy_tag="attribution_eligible",
        )
    else:
        doc_ids = _doc_ids_from_substrate(
            db_path, model, surface, policy_tag="attribution_eligible",
        )
    assert DOC_PUBLIC in doc_ids
    assert DOC_PERSONAL not in doc_ids, (
        f"{surface} leaked personal_reading under attribution_eligible"
    )


@pytest.mark.parametrize("surface", ["search", "vss", "brute_force"])
def test_operator_only_includes_personal_reading(matrix_graph, surface):
    """Privileged policy_tag: personal_reading retrievable on owner path."""
    db_path = matrix_graph["db_path"]
    model = matrix_graph["model"]
    if surface == "search":
        doc_ids = _doc_ids_from_search(
            db_path, model, policy_tag="operator_only",
        )
    else:
        doc_ids = _doc_ids_from_substrate(
            db_path, model, surface, policy_tag="operator_only",
        )
    assert DOC_PERSONAL in doc_ids, (
        f"{surface} withheld personal_reading under operator_only"
    )


def test_get_chunk_personal_reading_withheld(matrix_graph, monkeypatch):
    """GET /chunks mirrors search gate: body withheld for personal_reading."""
    secret = "OWNER private essay SR03 matrix must not leak"
    db_path = matrix_graph["db_path"]
    model = matrix_graph["model"]
    con = connect_write(db_path, purpose="sr03-matrix-chunk-override")
    try:
        chunk_id = insert_chunk(
            con,
            document_id=DOC_PERSONAL,
            chunk_index=1,
            text=secret,
            token_count=10,
            embedding=model.encode(secret),
        )
    finally:
        con.close()
    client = _get_chunk_client(matrix_graph, monkeypatch)
    body = client.get(f"/chunks/{chunk_id}").json()
    assert body["servable"] is False
    assert body["servability"] == "personal_readable"
    assert body["text"] == ""
    assert secret not in body["text"]


def test_get_chunk_public_domain_servable(matrix_graph, monkeypatch):
    """Control: public_domain chunk body still servable via GET /chunks."""
    chunk_id = matrix_graph["chunks"][DOC_PUBLIC]
    client = _get_chunk_client(matrix_graph, monkeypatch)
    body = client.get(f"/chunks/{chunk_id}").json()
    assert body["servable"] is True
    assert body["servability"] is None
    assert QUERY in body["text"]