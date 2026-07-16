from __future__ import annotations

# ruff: noqa: F811 - imported fixture names are intentionally injected by pytest.
import json
from contextlib import suppress

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_canonical_aggregate_projection import completed_parent  # noqa: F401

from interfaces.research.api.canonical_twin_reader_routes import (
    CanonicalTwinReaderRouteRuntime,
    canonical_twin_reader_router,
    get_canonical_twin_reader_runtime,
    register_canonical_twin_reader_routes,
)
from runtime.db_lock import connect_write
from substrate.graph.schema import init_database
from substrate.twin_recursion import (
    CanonicalTwinReader,
    CanonicalTwinReaderNotFound,
    SourceRevision,
    TwinRecursionLedger,
    publish_canonical_twin,
)


def _published(completed_parent):
    asset, manifest, registry, completions, _, _, _, tmp_path = completed_parent
    ledger = TwinRecursionLedger(tmp_path / "reader-twins.sqlite3")
    snapshot = ledger.apply_paid_aggregate(
        SourceRevision("acct", asset),
        manifest=manifest,
        completions=completions,
        registry=registry,
    )
    graph = connect_write(str(tmp_path / "reader.duckdb"), purpose="test_twin_reader")
    init_database(graph)
    result = publish_canonical_twin(graph, ledger, binding_id=snapshot.binding_id)
    return asset, ledger, snapshot, graph, result


def test_owner_navigates_exact_source_to_sanitized_advisory_view(completed_parent) -> None:
    asset, ledger, snapshot, graph, result = _published(completed_parent)
    try:
        view = CanonicalTwinReader(graph, ledger).read_by_source(
            owner_id="acct", source_asset_id=asset.asset_id, source_hash=snapshot.source_hash
        )
        assert view.document_id == result.document_id
        assert view.source_asset_id == asset.asset_id
        assert view.authority == "advisory" and view.shareable is False
        assert "verify against sources" in view.authority_label
        assert "<!doctype" not in view.html_fragment.lower()
        assert "<script" not in view.html_fragment.lower()
        assert "Insight parent" in view.html_fragment
    finally:
        graph.close()


@pytest.mark.parametrize("owner", ["other-account", "", " acct "])
def test_wrong_or_malformed_owner_gets_uniform_not_found(completed_parent, owner: str) -> None:
    asset, ledger, snapshot, graph, _ = _published(completed_parent)
    try:
        with pytest.raises((CanonicalTwinReaderNotFound, ValueError)):
            CanonicalTwinReader(graph, ledger).read_by_source(
                owner_id=owner, source_asset_id=asset.asset_id, source_hash=snapshot.source_hash
            )
    finally:
        graph.close()


def test_substituted_html_and_extra_chunk_fail_closed(completed_parent) -> None:
    asset, ledger, snapshot, graph, result = _published(completed_parent)
    try:
        graph.execute(
            "UPDATE documents SET raw_text=? WHERE document_id=?",
            ["<img src=x onerror=alert(1)><script>alert(1)</script>", result.document_id],
        )
        graph.execute(
            "INSERT INTO chunks(chunk_id,document_id,chunk_index,text,token_count) "
            "VALUES ('reader-forged-extra',?,1,'forged',0)",
            [result.document_id],
        )
        with pytest.raises(CanonicalTwinReaderNotFound, match="unavailable"):
            CanonicalTwinReader(graph, ledger).read_by_source(
                owner_id="acct", source_asset_id=asset.asset_id, source_hash=snapshot.source_hash
            )
    finally:
        graph.close()


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("source_tier", 4),
        ("investigation_id", "forged-investigation"),
        ("twin_source_envelope", "{}"),
        ("source_uri", "antiek:twin-binding:forged"),
    ],
)
def test_any_publication_owned_document_substitution_fails_closed(
    completed_parent, column: str, value: object
) -> None:
    asset, ledger, snapshot, graph, result = _published(completed_parent)
    try:
        chunk = graph.execute(
            "SELECT chunk_id,chunk_index,section_path,text,token_count FROM chunks "
            "WHERE document_id=?",
            [result.document_id],
        ).fetchone()
        graph.execute("DELETE FROM chunks WHERE document_id=?", [result.document_id])
        graph.execute(f"UPDATE documents SET {column}=? WHERE document_id=?", [value, result.document_id])
        graph.execute(
            "INSERT INTO chunks(chunk_id,document_id,chunk_index,section_path,text,token_count) "
            "VALUES (?,?,?,?,?,?)",
            [chunk[0], result.document_id, *chunk[1:]],
        )
        with pytest.raises(CanonicalTwinReaderNotFound):
            CanonicalTwinReader(graph, ledger).read_by_source(
                owner_id="acct", source_asset_id=asset.asset_id, source_hash=snapshot.source_hash
            )
    finally:
        graph.close()


def test_malformed_metadata_and_duplicate_source_match_fail_closed(completed_parent) -> None:
    asset, ledger, snapshot, graph, result = _published(completed_parent)
    try:
        original = graph.execute(
            "SELECT metadata FROM documents WHERE document_id=?", [result.document_id]
        ).fetchone()[0]
        graph.execute(
            "UPDATE documents SET metadata='not-json' WHERE document_id=?", [result.document_id]
        )
        reader = CanonicalTwinReader(graph, ledger)
        with pytest.raises(CanonicalTwinReaderNotFound):
            reader.read_by_source(
                owner_id="acct", source_asset_id=asset.asset_id, source_hash=snapshot.source_hash
            )
        graph.execute("UPDATE documents SET metadata=? WHERE document_id=?", [original, result.document_id])
        metadata = json.loads(original)
        graph.execute(
            "INSERT INTO documents(document_id,source_tier,document_type,title,raw_text,metadata,"
            "content_class,owner_user_id) VALUES ('duplicate-twin',5,'canonical_twin','duplicate',"
            "'duplicate',?,'personal_reading','acct')",
            [json.dumps(metadata)],
        )
        with pytest.raises(CanonicalTwinReaderNotFound):
            reader.read_by_source(
                owner_id="acct", source_asset_id=asset.asset_id, source_hash=snapshot.source_hash
            )
    finally:
        graph.close()


def test_http_surface_requires_authenticated_owner_and_is_private(completed_parent) -> None:
    asset, ledger, snapshot, graph, _ = _published(completed_parent)
    db_path = str(
        graph.execute(
            "SELECT path FROM duckdb_databases() WHERE database_name=current_database()"
        ).fetchone()[0]
    )
    try:
        graph.close()
        unauthenticated_app = FastAPI()
        unauthenticated_app.include_router(canonical_twin_reader_router)
        unauthenticated_app.dependency_overrides[get_canonical_twin_reader_runtime] = lambda: (
            CanonicalTwinReaderRouteRuntime(db_path, ledger)
        )
        unauthenticated = TestClient(unauthenticated_app).get(
            f"/reader/sources/{asset.asset_id}/canonical-twin",
            params={"source_hash": snapshot.source_hash},
        )
        assert unauthenticated.status_code == 401
        assert unauthenticated.headers["cache-control"] == "private, no-store"
        assert unauthenticated.headers["x-content-type-options"] == "nosniff"

        authenticated_app = FastAPI()

        @authenticated_app.middleware("http")
        async def authenticated(request, call_next):
            request.state.auth_method = "bearer_token"
            request.state.user_id = "acct"
            return await call_next(request)

        register_canonical_twin_reader_routes(
            authenticated_app,
            db_path=db_path,
            ledger_path=str(ledger.path),
        )
        configured_runtime = authenticated_app.dependency_overrides[
            get_canonical_twin_reader_runtime
        ]()
        assert configured_runtime.ledger._read_only is True
        response = TestClient(authenticated_app).get(
            f"/reader/sources/{asset.asset_id}/canonical-twin",
            params={"source_hash": snapshot.source_hash},
        )
        assert response.status_code == 200
        assert response.json()["authority"] == "advisory"
        assert response.json()["shareable"] is False
        assert response.headers["cache-control"] == "private, no-store"
        assert response.headers["x-content-type-options"] == "nosniff"
        method_denied = TestClient(authenticated_app).post(
            f"/reader/sources/{asset.asset_id}/canonical-twin",
            params={"source_hash": snapshot.source_hash},
        )
        assert method_denied.status_code == 405
        assert method_denied.headers["cache-control"] == "private, no-store"
        missing_route = TestClient(authenticated_app).get("/reader/sources/missing/private-path")
        assert missing_route.status_code == 404
        assert missing_route.headers["cache-control"] == "private, no-store"
    finally:
        with suppress(Exception):
            graph.close()
