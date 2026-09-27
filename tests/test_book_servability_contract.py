"""The book HTTP schema exports the canonical servability vocabulary."""

from __future__ import annotations

from types import SimpleNamespace

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


def _enum_values(document: dict, node: dict) -> list[str]:
    node = _resolve_ref(document, node)
    if "enum" in node:
        return node["enum"]
    for key in ("anyOf", "oneOf", "allOf"):
        for branch in node.get(key, []):
            values = _enum_values(document, branch)
            if values:
                return values
    return []


def _allows_null(document: dict, node: dict) -> bool:
    node = _resolve_ref(document, node)
    if node.get("type") == "null":
        return True
    return any(
        _allows_null(document, branch)
        for key in ("anyOf", "oneOf", "allOf")
        for branch in node.get(key, [])
    )


def _asset_for(status: ServabilityStatus) -> BookAsset:
    content_class, taken_down = {
        ServabilityStatus.PUBLIC_DOMAIN: ("public_domain", False),
        ServabilityStatus.PLATFORM_AUTHORED: ("user_owned", False),
        ServabilityStatus.PUBLISHER_OPTED_IN: ("opt_in_licensed", False),
        ServabilityStatus.SOURCE_DECLARED_OPEN: ("source_declared_open", False),
        ServabilityStatus.GATED_METADATA_ONLY: ("restricted_pending_opt_in", False),
        ServabilityStatus.TAKEN_DOWN: ("public_domain", True),
        ServabilityStatus.PERSONAL_READABLE: ("personal_reading", False),
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
        assert _enum_values(document, property_schema) == canonical_values
        assert _allows_null(document, property_schema) is nullable


def test_book_response_serialization_preserves_all_seven_wire_values():
    for status in ServabilityStatus:
        asset = _asset_for(status)
        summary = book_api.BookSummary.from_asset(asset)
        detail = book_api.BookDetail.from_asset(asset)

        assert summary.model_dump(mode="json")["servability"] == status.value
        assert detail.model_dump(mode="json")["servability"] == status.value


def test_mounted_book_routes_serialize_enum_status_and_nullable_full_text(
    monkeypatch,
):
    from runtime import db_lock

    asset = _asset_for(ServabilityStatus.PERSONAL_READABLE)
    monkeypatch.setattr(book_api, "_resolve_db_path", lambda: "/synthetic/books.duckdb")
    monkeypatch.setattr(
        db_lock,
        "connect_read",
        lambda *_args, **_kwargs: SimpleNamespace(close=lambda: None),
    )
    monkeypatch.setattr(
        book_api,
        "list_book_assets",
        lambda _con, *, servable_only: [asset],
    )
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
