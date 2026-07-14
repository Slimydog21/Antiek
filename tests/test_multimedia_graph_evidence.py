from __future__ import annotations

import hashlib
from pathlib import Path

import duckdb
import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from interfaces.research.api import multimedia_routes
from interfaces.research.api.multimedia_reconciliation_routes import (
    authenticated_multimedia_policy_tag,
)
from processing.embedding import EmbeddingProvider
from substrate.multimedia.graph_evidence import (
    MultimediaEvidenceSearchRequest,
    MultimediaEvidenceSelection,
    MultimediaGraphEvidence,
)
from substrate.multimedia.read_model import (
    CreateMultimediaDraftRequest,
    MultimediaAssetStore,
)


class StubEmbedding(EmbeddingProvider):
    dimension = 3

    def encode(self, text: str) -> list[float]:
        lower = text.lower()
        return [
            1.0 if "aircraft" in lower else 0.1,
            1.0 if "engine" in lower else 0.1,
            1.0 if "market" in lower else 0.1,
        ]


@pytest.fixture
def graph(tmp_path: Path) -> Path:
    path = tmp_path / "graph.duckdb"
    embedder = StubEmbedding()
    with duckdb.connect(str(path)) as connection:
        connection.execute("DELETE FROM chunks")
        connection.execute("DELETE FROM documents")
        connection.executemany(
            "INSERT INTO documents(document_id,title,source_tier,document_type,owner_user_id) "
            "VALUES (?,?,1,'research',?)",
            [
                ("doc-history", "Aircraft Origins", "owner-1"),
                ("doc-engine", "Engine Systems", "owner-1"),
                ("doc-market", "Market Impact", "owner-1"),
                ("doc-taken", "Withdrawn Aircraft", "owner-1"),
                ("doc-foreign", "Foreign Aircraft", "owner-2"),
            ],
        )
        rows = [
            ("chunk-history", "doc-history", "Early aircraft history began with lightweight structures."),
            ("chunk-engine", "doc-engine", "Engine design and aerodynamic systems changed reliability."),
            ("chunk-market", "doc-market", "The result changed market cost and route economics."),
            ("chunk-taken", "doc-taken", "Aircraft evidence withdrawn after a takedown."),
            ("chunk-foreign", "doc-foreign", "Aircraft engine market secrets from another owner."),
        ]
        connection.executemany(
            "INSERT INTO chunks(chunk_id,document_id,chunk_index,section_path,text,embedding) "
            "VALUES (?,?,0,'Section 1',?,?)",
            [(chunk, document, text, embedder.encode(text)) for chunk, document, text in rows],
        )
        connection.execute(
            "INSERT INTO book_assets(document_id,taken_down,takedown_reason) VALUES ('doc-taken',TRUE,'withdrawn')"
        )
    return path


def _service(graph: Path) -> MultimediaGraphEvidence:
    return MultimediaGraphEvidence(db_path=str(graph), embedding_provider=StubEmbedding())


def test_privileged_search_policy_is_resolved_from_authenticated_request_state() -> None:
    request = Request({"type": "http"})
    request.state.auth_method = "bearer_token"
    request.state.user_id = "owner-1"
    assert authenticated_multimedia_policy_tag(request) == "operator_only"

    unauthenticated = Request({"type": "http"})
    unauthenticated.state.auth_method = "unauthenticated_local"
    unauthenticated.state.user_id = "owner-1"
    with pytest.raises(HTTPException) as exc_info:
        authenticated_multimedia_policy_tag(unauthenticated)
    assert exc_info.value.status_code == 401


def test_search_is_owner_scoped_and_resolve_is_digest_bound(graph: Path) -> None:
    result = _service(graph).search(
        owner_id="owner-1",
        asset_id="mm-1",
        revision_id="rev-1",
        query="aircraft engine market",
        limit=12,
        policy_tag="operator_only",
    )

    assert {candidate.chunk_id for candidate in result.candidates} == {
        "chunk-history",
        "chunk-engine",
        "chunk-market",
    }
    assert "chunk-foreign" not in {candidate.chunk_id for candidate in result.candidates}
    assert "chunk-taken" not in {candidate.chunk_id for candidate in result.candidates}
    selection = tuple(
        MultimediaEvidenceSelection(
            chunk_id=candidate.chunk_id,
            text_sha256=candidate.text_sha256,
        )
        for candidate in result.candidates
    )
    evidence = _service(graph).resolve(selection, owner_id="owner-1")
    assert {item.document_id for item in evidence} == {"doc-history", "doc-engine", "doc-market"}
    with pytest.raises(ValueError, match="unavailable for this owner"):
        _service(graph).resolve(
            (
                MultimediaEvidenceSelection(
                    chunk_id="chunk-taken",
                    text_sha256=hashlib.sha256(
                        b"Aircraft evidence withdrawn after a takedown."
                    ).hexdigest(),
                ),
            ),
            owner_id="owner-1",
        )

    with duckdb.connect(str(graph)) as connection:
        connection.execute("UPDATE chunks SET text='drifted' WHERE chunk_id='chunk-engine'")
    with pytest.raises(ValueError, match="changed after review"):
        _service(graph).resolve(selection, owner_id="owner-1")


def test_grounded_draft_is_a_separate_parent_linked_asset(graph: Path, tmp_path: Path) -> None:
    store = MultimediaAssetStore(tmp_path / "assets")
    parent = store.create_draft(
        CreateMultimediaDraftRequest(
            topic="aircraft engine market",
            target_minutes=20,
            source_scope="owned corpus",
        ),
        owner_id="owner-1",
    )
    found = _service(graph).search(
        owner_id="owner-1",
        asset_id=parent.asset.asset_id,
        revision_id=parent.asset.revision_id,
        query="aircraft engine market",
        limit=12,
        policy_tag="operator_only",
    )
    evidence = _service(graph).resolve(
        tuple(
            MultimediaEvidenceSelection(chunk_id=item.chunk_id, text_sha256=item.text_sha256)
            for item in found.candidates
        ),
        owner_id="owner-1",
    )
    grounded = store.create_grounded_draft(
        parent.asset.asset_id,
        expected_parent_revision_id=parent.asset.revision_id,
        evidence=evidence,
        owner_id="owner-1",
    )

    assert grounded.asset.asset_id != parent.asset.asset_id
    assert grounded.asset.parent_asset_id == parent.asset.asset_id
    assert grounded.derived_from_revision_id == parent.asset.revision_id
    assert grounded.asset.status == "planned"
    assert grounded.plan.request.source_scope == "owned corpus"
    assert grounded.plan.request.sources == ()
    assert len(grounded.plan.unsourced_line_ids) < len(parent.plan.unsourced_line_ids)
    assert store.get(parent.asset.asset_id, owner_id="owner-1") == parent
    with pytest.raises(ValueError, match="stale"):
        store.create_grounded_draft(
            parent.asset.asset_id,
            expected_parent_revision_id="rev-stale",
            evidence=evidence,
            owner_id="owner-1",
        )
    with pytest.raises(ValueError, match="bounded unique"):
        store.create_grounded_draft(
            parent.asset.asset_id,
            expected_parent_revision_id=parent.asset.revision_id,
            evidence=(evidence[0], evidence[0]),
            owner_id="owner-1",
        )


def test_http_search_review_and_ground_round_trip(graph: Path, tmp_path: Path, monkeypatch) -> None:
    store = MultimediaAssetStore(tmp_path / "assets")
    monkeypatch.setattr(multimedia_routes, "_STORE", store)
    app = FastAPI()

    @app.middleware("http")
    async def identity(request: Request, call_next):  # type: ignore[no-untyped-def]
        request.state.auth_method = "bearer_token"
        request.state.user_id = "owner-1"
        return await call_next(request)

    multimedia_routes.register_multimedia_routes(app)
    app.dependency_overrides[multimedia_routes.get_multimedia_evidence_runtime] = lambda: (
        multimedia_routes.MultimediaEvidenceRuntime(
            db_path=str(graph), embedding_provider_factory=StubEmbedding
        )
    )
    client = TestClient(app)
    created = client.post(
        "/multimedia/assets",
        json={"topic": "aircraft engine market", "target_minutes": 20, "source_scope": "owned corpus"},
    )
    assert created.status_code == 201
    parent = created.json()
    found = client.post(
        f"/multimedia/assets/{parent['asset']['asset_id']}/evidence-search",
        json={"expected_revision_id": "rev-1", "limit": 12},
    )
    assert found.status_code == 200
    candidates = found.json()["candidates"]
    grounded = client.post(
        f"/multimedia/assets/{parent['asset']['asset_id']}/grounded-drafts",
        json={
            "expected_parent_revision_id": "rev-1",
            "selections": [
                {"chunk_id": row["chunk_id"], "text_sha256": row["text_sha256"]}
                for row in candidates
            ],
        },
    )
    assert grounded.status_code == 201
    body = grounded.json()
    assert body["asset"]["parent_asset_id"] == parent["asset"]["asset_id"]
    citation_documents = {
        citation["document_id"]
        for line in body["plan"]["script_lines"]
        for citation in line["citations"]
    }
    assert citation_documents <= {"doc-history", "doc-engine", "doc-market"}
    assert citation_documents


    stale = client.post(
        f"/multimedia/assets/{parent['asset']['asset_id']}/evidence-search",
        json=MultimediaEvidenceSearchRequest(expected_revision_id="rev-stale").model_dump(),
    )
    assert stale.status_code == 409
    assert hashlib.sha256(b"drifted").hexdigest() not in {row["text_sha256"] for row in candidates}

    long_draft = client.post(
        "/multimedia/assets",
        json={"topic": "aircraft " * 700, "target_minutes": 20},
    )
    assert long_draft.status_code == 201
    long_search = client.post(
        f"/multimedia/assets/{long_draft.json()['asset']['asset_id']}/evidence-search",
        json={"expected_revision_id": "rev-1", "limit": 1},
    )
    assert long_search.status_code == 200
    assert 0 < len(long_search.json()["query"]) <= 4096
