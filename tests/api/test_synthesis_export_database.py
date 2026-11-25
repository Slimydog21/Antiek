"""Archive-to-HTML evidence using the real scratch database and resolver.

The fixture follows production's typed thesis/evidence archive and chunk-only pins.
Missing or legacy provenance cannot become a complete claim/chunk/document chain.
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
from substrate.schemas import (
    ConstraintCompliance,
    EvidenceRetrieveDeliveredPayload,
    SupportingClaim,
    SynthesizeDeliveredPayload,
    ThesisComponent,
)


@pytest.fixture
def archived_synthesis(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[str, str]:
    # tests/conftest.py provides a fresh copy of the canonical schema per test.
    db_path = default_db_path()
    assert Path(db_path).resolve().is_relative_to(tmp_path.resolve())
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("ANTIEK_RESEARCH_ARTIFACTS_DIR", str(tmp_path / "artifacts"))
    monkeypatch.setenv("ANTIEK_FRONTEND_BASE_URL", "https://reader.example.test")
    monkeypatch.delenv("ANTIEK_PUBLIC_BASE_URL", raising=False)
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
                thesis=SynthesizeDeliveredPayload(
                    thesis_summary="An authored conclusion from mixed evidence.",
                    implicit_recommendation="conditional",
                    thesis_components=[
                        ThesisComponent(claim="The public-source claim.", confidence="high",
                                        supporting_chunk_ids=["chunk-doc-public"]),
                        ThesisComponent(claim="The private-source claim.", confidence="moderate",
                                        supporting_chunk_ids=["chunk-doc-private"]),
                    ],
                    constraint_compliance=ConstraintCompliance(
                        hard_constraints_satisfied=True,
                    ),
                ).model_dump(mode="json"),
                evidence=[EvidenceRetrieveDeliveredPayload(
                    sub_question="What does each source establish?",
                    answer="Two source-specific findings.",
                    supporting_claims=[
                        SupportingClaim(
                            claim=f"Evidence from {document_id}", evidence_type="direct",
                            chunk_ids=[f"chunk-{document_id}"], confidence="high",
                            confidence_basis="The cited passage states the finding.",
                        ) for document_id in ("doc-public", "doc-private")
                    ],
                ).model_dump(mode="json")],
                chunk_ids=("chunk-doc-public", "chunk-doc-private"),
            ),
            investigation_id="inv-export-database",
            synthesis_id="syn-export-database",
        )
    return db_path, synthesis_id


def test_real_resolver_maps_each_archived_claim_to_its_chunk_without_document_pins(
    archived_synthesis: tuple[str, str],
) -> None:
    db_path, synthesis_id = archived_synthesis
    export = resolve_synthesis_export(synthesis_id, db_path=db_path)
    assert export is not None
    assert [claim.statement for claim in export.claims] == [
        "The public-source claim.", "The private-source claim.",
    ]
    assert [[source.chunk_id for source in claim.sources] for claim in export.claims] == [
        ["chunk-doc-public"], ["chunk-doc-private"],
    ]
    assert all(claim.fully_sourced for claim in export.claims)
    sources = {source.document_id: source for claim in export.claims for source in claim.sources}
    assert set(sources) == {"doc-public", "doc-private"}
    assert sources["doc-public"].content_class == "public_domain"
    assert sources["doc-private"].content_class == "personal_reading"
    assert sources["doc-public"].servable is True
    assert sources["doc-private"].servable is False
    assert sources["doc-public"].chunk_text == "PUBLIC_SOURCE_PASSAGE"
    assert {source.locator for source in sources.values()} == {
        "https://reader.example.test/read/doc-public",
        "https://reader.example.test/read/doc-private",
    }
    con = connect_read(db_path)
    try:
        count_row = con.execute(
            "SELECT count(*) FROM synthesis_substrate_manifest "
            "WHERE synthesis_id = ? AND entity_kind = 'document'", [synthesis_id],
        ).fetchone()
        assert count_row is not None and count_row[0] == 0
    finally:
        con.close()


def test_query_html_route_embeds_public_passage_and_withholds_private_passage(
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
    assert "PUBLIC_SOURCE_PASSAGE" in response.text
    assert "PRIVATE_SOURCE_PASSAGE" not in response.text
    model = extract_island(response.text)
    assert model["metadata"]["synthesis_id"] == synthesis_id
    assert model["metadata"]["provenance"] == {
        "fully_sourced": 2, "total": 2, "complete": True,
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
    assert "PUBLIC_SOURCE_PASSAGE" in response.text
    assert extract_island(response.text)["metadata"]["synthesis_id"] == synthesis_id


@pytest.mark.parametrize(
    "thesis,document_ids,expected_ids",
    [
        pytest.param(
            {"thesis_components": [{"claim": "Partially sourced claim.",
                                     "supporting_chunk_ids": ["chunk-doc-public", "missing-chunk"]}]},
            (), ["chunk-doc-public", "missing-chunk"], id="known-and-missing-citation",
        ),
        pytest.param(None, ("doc-public",), [None], id="document-only-legacy"),
        pytest.param(["not-a-thesis-object"], ("doc-public",), [None], id="malformed-thesis"),
        pytest.param(
            {"thesis_components": [
                {"claim": "Valid component.", "supporting_chunk_ids": ["chunk-doc-public"]},
                "invalid-component",
            ]}, (), [], id="invalid-component-cannot-disappear",
        ),
        pytest.param(
            {"thesis_components": [{"claim": "Null citation field.",
                                     "supporting_chunk_ids": None}]},
            (), [None], id="null-citation-field",
        ),
        pytest.param(
            {"thesis_components": [{"claim": "Scalar citation field.",
                                     "supporting_chunk_ids": "chunk-doc-public"}]},
            (), [None], id="nonlist-citation-field",
        ),
        pytest.param(
            {"thesis_components": [{"claim": "Known and malformed citation.",
                                     "supporting_chunk_ids": ["chunk-doc-public", None]}]},
            (), ["chunk-doc-public", None], id="known-and-malformed-citation",
        ),
        pytest.param(
            {"thesis_components": [{"claim": "An analogy-grounded claim.",
                                     "supporting_chunk_ids": [], "supporting_path_indices": [0]}]},
            (), [], id="analogy-only",
        ),
    ],
)
def test_incomplete_archived_provenance_stays_incomplete_in_real_html_route(
    archived_synthesis: tuple[str, str], thesis: object, document_ids: tuple[str, ...],
    expected_ids: list[str | None],
) -> None:
    db_path, _ = archived_synthesis
    with connect_write(db_path, purpose="test-incomplete-synthesis-export") as con:
        synthesis_id = archive_synthesis_via_db(
            con,
            ArchiveInputs(
                target_question="Is this claim fully sourced?",
                synthesis_timestamp=datetime(2026, 9, 20, tzinfo=UTC),
                status="passed", implicit_recommendation="conditional",
                thesis_text="A retained authored summary.", thesis=thesis,
                chunk_ids=("chunk-doc-public",), document_ids=document_ids,
            ),
            investigation_id="inv-incomplete", synthesis_id="syn-incomplete",
        )
    export = resolve_synthesis_export(synthesis_id, db_path=db_path)
    assert export is not None
    assert len(export.claims) == 1
    assert export.claims[0].fully_sourced is False
    assert [source.chunk_id for source in export.claims[0].sources] == expected_ids
    app = FastAPI()
    register_synthesis_artifact_routes(app)
    with TestClient(app) as client:
        response = client.get(f"/api/syntheses/{synthesis_id}/artifact?format=html")
    assert response.status_code == 200
    assert "Provenance incomplete" in response.text
    assert "A retained authored summary." in response.text
    assert extract_island(response.text)["metadata"]["provenance"] == {
        "fully_sourced": 0, "total": 1, "complete": False,
    }


@pytest.mark.parametrize("limit", [
    "_MAX_COMPONENTS", "_MAX_CITATIONS", "_MAX_THESIS_CHARS", "_MAX_CITATION_ID_LENGTH",
])
def test_over_bound_thesis_falls_back_instead_of_claiming_partial_completeness(
    archived_synthesis: tuple[str, str], monkeypatch: pytest.MonkeyPatch, limit: str,
) -> None:
    from interfaces.research.api import synthesis_artifact

    _, synthesis_id = archived_synthesis
    monkeypatch.setattr(synthesis_artifact, limit, 1)
    app = FastAPI()
    register_synthesis_artifact_routes(app)
    with TestClient(app) as client:
        response = client.get(f"/api/syntheses/{synthesis_id}/artifact?format=html")
    assert response.status_code == 200
    assert "An authored conclusion from mixed evidence." in response.text
    assert "Provenance incomplete" in response.text
    assert "PUBLIC_SOURCE_PASSAGE" not in response.text
    assert "PRIVATE_SOURCE_PASSAGE" not in response.text
    assert extract_island(response.text)["metadata"]["provenance"] == {
        "fully_sourced": 0, "total": 1, "complete": False,
    }


@pytest.mark.parametrize(
    "frontend,public,expected",
    [
        ("https://frontend.example.test", "", "https://frontend.example.test"),
        ("", "https://public.example.test", "https://public.example.test"),
        ("https://frontend.example.test", "https://public.example.test", "https://frontend.example.test"),
        ("http://localhost:8080/", "", "http://localhost:8080"),
        ("http://127.0.0.1:8080", "", "http://127.0.0.1:8080"),
        ("https://reader.cafe", "", "https://reader.cafe"),
        ("http://[::1]:8080/", "", "http://[::1]:8080"),
    ],
)
def test_real_resolver_uses_configured_reader_origin(
    archived_synthesis: tuple[str, str], monkeypatch: pytest.MonkeyPatch,
    frontend: str, public: str, expected: str,
) -> None:
    monkeypatch.setenv("ANTIEK_FRONTEND_BASE_URL", frontend)
    monkeypatch.setenv("ANTIEK_PUBLIC_BASE_URL", public)
    db_path, synthesis_id = archived_synthesis
    export = resolve_synthesis_export(synthesis_id, db_path=db_path)
    assert export is not None
    assert {source.locator for claim in export.claims for source in claim.sources} == {
        f"{expected}/read/doc-public", f"{expected}/read/doc-private",
    }


@pytest.mark.parametrize(
    "frontend",
    [None, "/relative", "javascript:alert(1)", "https://user:pass@reader.example.test",
     "https://reader.example.test/subpath", "https://reader.example.test?redirect=evil",
     "https://reader.example.test#fragment", "https://reader.example.test:bad",
     "https://reader.\nexample.test", "https://reader..example.test",
     "https://-reader.example.test", "http://999.1.2.3",
     "https://reader.example.test\\@evil.test", "https://reader.example.test:99999",
     "https://read%65r.example.test", "http://0x7f.1", "http://0x7f000001",
     "http://0177.0.0.1", "http://reader.123", "http://0X7F000001.", "http://0x"],
)
def test_unavailable_reader_origin_keeps_visible_unclickable_references(
    archived_synthesis: tuple[str, str], monkeypatch: pytest.MonkeyPatch,
    frontend: str | None,
) -> None:
    if frontend is None:
        monkeypatch.delenv("ANTIEK_FRONTEND_BASE_URL", raising=False)
        monkeypatch.delenv("ANTIEK_PUBLIC_BASE_URL", raising=False)
    else:
        monkeypatch.setenv("ANTIEK_FRONTEND_BASE_URL", frontend)
        # An explicitly invalid preferred origin must not silently use another host.
        monkeypatch.setenv("ANTIEK_PUBLIC_BASE_URL", "https://fallback.example.test")
    db_path, synthesis_id = archived_synthesis
    export = resolve_synthesis_export(synthesis_id, db_path=db_path)
    assert export is not None
    assert all(source.locator is None for claim in export.claims for source in claim.sources)
    app = FastAPI()
    register_synthesis_artifact_routes(app)
    with TestClient(app) as client:
        response = client.get(f"/api/syntheses/{synthesis_id}/artifact?format=html")
    assert response.status_code == 200
    assert "reader link unavailable" in response.text
    assert "doc-public" in response.text and "Public evidence" in response.text
    assert "doc-private" in response.text and "Private evidence" in response.text
    assert 'href="/read/' not in response.text
    assert 'href="file:' not in response.text
    model = extract_island(response.text)
    cites = [node["attrs"] for node in model["content"] if node["type"] == "antiek_cite_link"]
    assert len(cites) == 2
    assert all("target_url" not in cite for cite in cites)
    assert_script_free(response.text)


@pytest.mark.parametrize("suffix", ["artifact.html", "artifact?format=html"])
def test_both_real_html_routes_keep_configured_links_despite_spoofed_headers(
    archived_synthesis: tuple[str, str], suffix: str,
) -> None:
    _, synthesis_id = archived_synthesis
    app = FastAPI()
    register_synthesis_artifact_routes(app)
    with TestClient(app) as client:
        response = client.get(f"/api/syntheses/{synthesis_id}/{suffix}", headers={
            "Host": "host.attacker.test",
            "Origin": "https://origin.attacker.test",
            "X-Forwarded-Host": "forwarded.attacker.test",
            "X-Forwarded-Proto": "http",
            "Forwarded": "host=forwarded.attacker.test;proto=http",
        })
    assert response.status_code == 200
    model = extract_island(response.text)
    targets = {
        node["attrs"]["target_url"] for node in model["content"]
        if node["type"] == "antiek_cite_link"
    }
    assert targets == {
        "https://reader.example.test/read/doc-public",
        "https://reader.example.test/read/doc-private",
    }
    assert all(f'href="{target}"' in response.text for target in targets)
    assert "attacker.test" not in response.text
    assert "PUBLIC_SOURCE_PASSAGE" in response.text
    assert "PRIVATE_SOURCE_PASSAGE" not in response.text
    assert_script_free(response.text)


@pytest.mark.parametrize(
    "document_id,encoded",
    [("a/b", "a%2Fb"), ("a?b", "a%3Fb"), ("a#b", "a%23b"),
     ("a b", "a%20b"), ("café", "caf%C3%A9"), ("%2e%2e", "%252e%252e"),
     (".", None), ("..", None), ("", None)],
)
def test_reader_locator_keeps_document_identity_in_one_path_segment(
    document_id: str, encoded: str | None,
) -> None:
    from interfaces.research.api.synthesis_artifact import _reader_locator

    origin = "https://reader.example.test"
    expected = None if encoded is None else f"{origin}/read/{encoded}"
    assert _reader_locator(origin, document_id) == expected


def test_invalid_public_origin_without_frontend_has_no_reader_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from interfaces.research.api.synthesis_artifact import _reader_origin

    monkeypatch.setenv("ANTIEK_FRONTEND_BASE_URL", "")
    monkeypatch.setenv("ANTIEK_PUBLIC_BASE_URL", "https://reader.example.test:99999")
    assert _reader_origin() is None
