"""Archive-to-HTML evidence using the real scratch database and resolver.

The current resolver collapses the thesis into one document-grounded claim;
these tests do not establish chunk-level attribution or persisted export denial.
Both the light route and the full application's signed-cookie boundary are exercised.
"""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.synthesis_artifact import (
    register_synthesis_artifact_routes,
    resolve_synthesis_export,
)
from middleware.archive import ArchiveInputs, archive_synthesis_via_db
from runtime.db_lock import connect_read, connect_write
from services.html_projection.gate import assert_script_free
from services.html_projection.island import extract_island
from substrate.graph import default_db_path


@pytest.fixture
def archived_synthesis(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[str, str]:
    # tests/conftest.py provides a fresh copy of the canonical schema per test.
    db_path = default_db_path()
    assert Path(db_path).resolve().is_relative_to(tmp_path.resolve())
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("ANTIEK_RESEARCH_ARTIFACTS_DIR", str(tmp_path / "artifacts"))
    with connect_write(db_path, purpose="test-synthesis-export-seed") as con:
        for document_id, rights, title, passage in (
            ("doc-public", "public_domain", "Public evidence", "PUBLIC_SOURCE_PASSAGE"),
            ("doc-private", "personal_reading", "Private evidence", "PRIVATE_SOURCE_PASSAGE"),
        ):
            con.execute(
                "INSERT INTO documents "
                "(document_id, title, source_tier, document_type, content_class, raw_text) "
                "VALUES (?, ?, 1, 'paper', ?, ?)",
                [document_id, title, rights, passage],
            )
            con.execute(
                "INSERT INTO chunks "
                "(chunk_id, document_id, chunk_index, text, token_count) "
                "VALUES (?, ?, 0, ?, 1)",
                [f"chunk-{document_id}", document_id, passage],
            )
        synthesis_id = archive_synthesis_via_db(
            con,
            ArchiveInputs(
                target_question="What does the mixed evidence support?",
                synthesis_timestamp=datetime(2026, 9, 20, tzinfo=UTC),
                status="passed",
                implicit_recommendation="conditional",
                thesis_text="An authored conclusion from mixed evidence.",
                evidence=[
                    {"claim": "First evidence claim", "chunk_id": "chunk-doc-public"},
                    {"claim": "Second evidence claim", "chunk_id": "chunk-doc-private"},
                ],
                chunk_ids=("chunk-doc-public", "chunk-doc-private"),
                document_ids=("doc-public", "doc-private"),
            ),
            investigation_id="inv-export-database",
            synthesis_id="syn-export-database",
        )
    return db_path, synthesis_id


def test_real_resolver_preserves_document_rights_but_not_per_claim_evidence(
    archived_synthesis: tuple[str, str],
) -> None:
    db_path, synthesis_id = archived_synthesis
    export = resolve_synthesis_export(synthesis_id, db_path=db_path)
    assert export is not None
    assert len(export.claims) == 1
    assert export.claims[0].statement == "An authored conclusion from mixed evidence."
    sources = {source.document_id: source for source in export.claims[0].sources}
    assert set(sources) == {"doc-public", "doc-private"}
    assert sources["doc-public"].content_class == "public_domain"
    assert sources["doc-private"].content_class == "personal_reading"
    assert sources["doc-public"].servable is True
    assert sources["doc-private"].servable is False
    assert all(source.chunk_text is None for source in sources.values())
    assert {source.locator for source in sources.values()} == {
        "/read/doc-public", "/read/doc-private",
    }


def test_query_html_route_exports_archived_synthesis_without_source_passages(
    archived_synthesis: tuple[str, str],
) -> None:
    _, synthesis_id = archived_synthesis
    app = FastAPI()
    register_synthesis_artifact_routes(app)
    with TestClient(app) as client:
        response = client.get(f"/api/syntheses/{synthesis_id}/artifact?format=html")
    assert response.status_code == 200
    assert "attachment" in response.headers["content-disposition"]
    assert_script_free(response.text)
    assert "An authored conclusion from mixed evidence." in response.text
    assert "Public evidence" in response.text
    assert "Private evidence" in response.text
    assert "cite-only" in response.text
    assert "PUBLIC_SOURCE_PASSAGE" not in response.text
    assert "PRIVATE_SOURCE_PASSAGE" not in response.text
    model = extract_island(response.text)
    assert model["metadata"]["synthesis_id"] == synthesis_id
    # "Complete" currently means document links, not resolved claim/chunk spans.
    assert model["metadata"]["provenance"] == {
        "fully_sourced": 1, "total": 1, "complete": True,
    }
    assert {edge["to_document_id"] for edge in model["edges"]} == {
        "doc-public", "doc-private",
    }


def test_current_schema_has_no_persisted_synthesis_export_restriction(
    archived_synthesis: tuple[str, str],
) -> None:
    db_path, synthesis_id = archived_synthesis
    con = connect_read(db_path)
    try:
        columns = {
            row[0] for row in con.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'syntheses'"
            ).fetchall()
        }
    finally:
        con.close()
    assert {"synthesis_id", "status", "thesis_text"} <= columns
    assert columns.isdisjoint({
        "restricted", "restriction_reason", "visibility", "export_allowed",
        "export_restricted",
    }), "A new row-level export policy needs resolver coverage before this evidence changes."
    export = resolve_synthesis_export(synthesis_id, db_path=db_path)
    assert export is not None
    assert export.restricted is False
    assert export.restriction_reason is None


def test_full_app_signed_operator_cookie_exports_real_archived_synthesis(
    archived_synthesis: tuple[str, str], monkeypatch: pytest.MonkeyPatch,
) -> None:
    from secrets import token_urlsafe

    from interfaces.research.api.app import create_app
    from substrate.auth import mint_session_cookie

    _, synthesis_id = archived_synthesis
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    monkeypatch.delenv("ANTIEK_OPERATOR_SERVICE_TOKEN_CLIENT_ID", raising=False)
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", "operator@example.test")
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", token_urlsafe(32))
    with TestClient(create_app(
        register_wrestling=False, register_providers=False, cors_origins=[],
    )) as client:
        url = f"/api/syntheses/{synthesis_id}/artifact?format=html"
        assert client.get(url).status_code == 401
        client.cookies.set("ANTIEK_SESSION", mint_session_cookie(
            user_id="__operator__", email="operator@example.test",
        ))
        response = client.get(url)
    assert response.status_code == 200
    assert_script_free(response.text)
    assert "An authored conclusion from mixed evidence." in response.text
    assert "Public evidence" in response.text
    assert "Private evidence" in response.text
    assert "cite-only" in response.text
    assert "PRIVATE_SOURCE_PASSAGE" not in response.text
    assert "PUBLIC_SOURCE_PASSAGE" not in response.text
    assert extract_island(response.text)["metadata"]["synthesis_id"] == synthesis_id
