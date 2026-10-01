"""The book HTTP schema exports the canonical servability vocabulary."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api import books as book_api
from substrate.books.model import BookAsset
from substrate.books.servability import ServabilityStatus
from substrate.books.serve import ServeResult


def _mounted_book_app() -> FastAPI:
    app = FastAPI()
    book_api.register_book_routes(app)
    return app


def _resolve_ref(document: dict, node: dict) -> dict:
    ref = node.get("$ref")
    if ref is None:
        return node
    prefix = "#/components/schemas/"
    assert ref.startswith(prefix)
    return document["components"]["schemas"][ref.removeprefix(prefix)]


def _property_schema(document: dict, model_name: str, property_name: str) -> dict:
    schemas = document["components"]["schemas"]

    def find(node: dict) -> dict | None:
        node = _resolve_ref(document, node)
        properties = node.get("properties", {})
        if property_name in properties:
            return properties[property_name]
        for branch in node.get("allOf", []):
            found = find(branch)
            if found is not None:
                return found
        return None

    result = find(schemas[model_name])
    assert result is not None, f"{model_name}.{property_name} is absent from OpenAPI"
    return result


def _assert_exact_enum_schema(document: dict, node: dict, values: list[str]) -> None:
    schema = _resolve_ref(document, node)
    assert schema.get("type") == "string"
    assert schema.get("enum") == values
    assert not any(key in schema for key in ("anyOf", "oneOf", "allOf"))


def _asset_for(status: ServabilityStatus) -> BookAsset:
    content_class, taken_down = {
        ServabilityStatus.PUBLIC_DOMAIN: ("public_domain", False),
        ServabilityStatus.PLATFORM_AUTHORED: ("user_owned", False),
        ServabilityStatus.PUBLISHER_OPTED_IN: ("opt_in_licensed", False),
        ServabilityStatus.SOURCE_DECLARED_OPEN: ("source_declared_open", False),
        ServabilityStatus.GATED_METADATA_ONLY: ("restricted_pending_opt_in", False),
        ServabilityStatus.TAKEN_DOWN: ("public_domain", True),
        ServabilityStatus.PERSONAL_READABLE: ("personal_reading", False),
        ServabilityStatus.PRIVATE_AUTHORED: ("user_authored_private", False),
    }[status]
    return BookAsset(
        document_id="synthetic-book",
        title="Synthetic title",
        author="Synthetic author",
        content_class=content_class,
        ip_holder_id=None,
        page_count=1,
        pagination_scheme="pdf_page",
        cover_uri=None,
        toc=[],
        provenance=None,
        license_basis=None,
        taken_down=taken_down,
        taken_down_at=None,
        takedown_reason=None,
        pre_takedown_content_class=None,
    )


def test_mounted_book_openapi_uses_the_canonical_servability_enum():
    document = _mounted_book_app().openapi()
    canonical_values = [status.value for status in ServabilityStatus]
    fields = {
        "BookSummary": False,
        "BookDetail": False,
        "BookImportResponse": False,
        "BookHtmlPublishJobOut": False,
        "SpinResearchResponse": False,
        "FullTextResponse": True,
    }

    for model_name, nullable in fields.items():
        property_schema = _property_schema(document, model_name, "servability")
        if nullable:
            schema = _resolve_ref(document, property_schema)
            branches = schema.get("anyOf")
            assert isinstance(branches, list) and len(branches) == 2
            resolved_branches = [_resolve_ref(document, branch) for branch in branches]
            null_branches = [branch for branch in resolved_branches if branch.get("type") == "null"]
            enum_branches = [branch for branch in resolved_branches if branch.get("type") != "null"]
            assert len(null_branches) == 1
            assert len(enum_branches) == 1
            _assert_exact_enum_schema(document, enum_branches[0], canonical_values)
        else:
            _assert_exact_enum_schema(document, property_schema, canonical_values)


def test_book_response_serialization_preserves_all_canonical_wire_values():
    for status in ServabilityStatus:
        asset = _asset_for(status)
        summary = book_api.BookSummary.from_asset(asset)
        detail = book_api.BookDetail.from_asset(asset)

        assert summary.model_dump(mode="json")["servability"] == status.value
        assert detail.model_dump(mode="json")["servability"] == status.value


def test_mounted_book_routes_serialize_enum_status_and_nullable_full_text(
    monkeypatch,
    tmp_path,
):
    import duckdb

    from substrate import graph

    asset = _asset_for(ServabilityStatus.PERSONAL_READABLE)
    db_path = str(tmp_path / "synthetic-books.duckdb")
    with duckdb.connect(db_path) as con:
        con.execute(
            "CREATE TABLE documents "
            "(document_id VARCHAR, content_class VARCHAR, owner_user_id VARCHAR)"
        )
        con.execute(
            "CREATE TABLE book_assets "
            "(document_id VARCHAR, pre_takedown_content_class VARCHAR, taken_down BOOLEAN)"
        )
        con.execute(
            "INSERT INTO documents VALUES (?, ?, NULL)",
            [asset.document_id, asset.content_class],
        )
        con.execute("INSERT INTO book_assets VALUES (?, NULL, FALSE)", [asset.document_id])
    monkeypatch.setattr(book_api, "_resolve_db_path", lambda: db_path)
    monkeypatch.setattr(graph, "default_db_path", lambda: db_path)

    def list_assets(_con, *, owner_user_id, status):
        assert owner_user_id is None
        assert status == "all"
        return [asset]

    monkeypatch.setattr(book_api, "list_discoverable_book_assets", list_assets)
    result = ServeResult(
        document_id="synthetic-book",
        found=True,
        servability=None,
        servable=False,
        full_text=None,
        snippet="Synthetic metadata only",
        title="Synthetic title",
        author="Synthetic author",
        reason="gated_metadata_only",
    )
    monkeypatch.setattr(book_api, "serve_full_text_guarded", lambda *_args, **_kwargs: result)
    monkeypatch.setattr(book_api, "_prefer_reader_html_body", lambda _con, _doc, value, **_: value)
    monkeypatch.setattr(book_api, "_record_arxiv_serve_audit", lambda *_args: None)

    client = TestClient(_mounted_book_app())
    listed = client.get("/books?status=all")
    assert listed.status_code == 200
    assert listed.json()["books"][0]["servability"] == ServabilityStatus.PERSONAL_READABLE.value

    full_text = client.get("/books/synthetic-book/full-text")
    assert full_text.status_code == 200
    assert full_text.json()["servability"] is None
