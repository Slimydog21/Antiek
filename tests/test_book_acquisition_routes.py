from __future__ import annotations

import ast
import io
import zipfile
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from interfaces.research.api.book_acquisition_routes import (
    EPUB_MEDIA_TYPE,
    PurchaseIntentRequest,
    create_book_acquisition_router,
)
from runtime.db_lock import connect_write
from substrate.graph.schema import init_database

KEY = b"book-acquisition-api-test-key-32-bytes"


def _epub(body: str = "Compressors raise the pressure of incoming air.") -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        archive.writestr("mimetype", EPUB_MEDIA_TYPE)
        archive.writestr(
            "META-INF/container.xml",
            '<?xml version="1.0"?><container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0"><rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>',
        )
        archive.writestr(
            "OEBPS/content.opf",
            '<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" xmlns:dc="http://purl.org/dc/elements/1.1/" version="3.0"><metadata><dc:title>Jet Engines</dc:title><dc:creator>A. Researcher</dc:creator></metadata><manifest><item id="c1" href="c1.xhtml" media-type="application/xhtml+xml"/></manifest><spine><itemref idref="c1"/></spine></package>',
        )
        archive.writestr(
            "OEBPS/c1.xhtml",
            f"<html><body><h1>Compression</h1><p>{body}</p></body></html>",
        )
    return out.getvalue()


def _hostile_epub() -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        archive.writestr("mimetype", EPUB_MEDIA_TYPE)
        archive.writestr("../escape.xhtml", "<html><body>escape</body></html>")
    return out.getvalue()


def _client(tmp_path: Path, *, max_epub_bytes: int = 1024 * 1024) -> tuple[TestClient, Path]:
    db_path = tmp_path / "books.duckdb"
    with connect_write(str(db_path), purpose="book-acquisition-api-test-init") as con:
        init_database(con)

    app = FastAPI()

    @app.middleware("http")
    async def test_identity(request: Request, call_next):  # type: ignore[no-untyped-def]
        if request.headers.get("x-test-auth") == "yes":
            request.state.auth_method = "bearer_token"
            request.state.user_id = request.headers.get("x-test-user", "alice")
        return await call_next(request)

    app.include_router(
        create_book_acquisition_router(
            db_path=str(db_path),
            signing_key=KEY,
            max_epub_bytes=max_epub_bytes,
        )
    )
    return TestClient(app), db_path


def _auth_headers(user: str = "alice") -> dict[str, str]:
    return {"x-test-auth": "yes", "x-test-user": user}


def _intent(client: TestClient, *, user: str = "alice") -> dict[str, object]:
    response = client.post(
        "/book-acquisition/intents",
        headers=_auth_headers(user),
        json={
            "title": "Jet Engines",
            "author": "A. Researcher",
            "store": "publisher.example",
            "max_price_usd_cents": 3000,
            "desired_format": "epub",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _authorize(
    client: TestClient,
    intent_receipt_id: str,
    *,
    user: str = "alice",
    decision: str = "authorized",
) -> dict[str, object]:
    response = client.post(
        f"/book-acquisition/intents/{intent_receipt_id}/authorization",
        headers=_auth_headers(user),
        json={
            "decision": decision,
            "authorized_price_ceiling_usd_cents": (2500 if decision == "authorized" else 0),
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_authenticated_intent_authorization_and_port_round_trip(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    intent = _intent(client)
    authorization = _authorize(client, str(intent["intent_receipt_id"]))
    assert authorization["purchase_occurred"] is False
    epub = _epub()

    response = client.post(
        f"/book-acquisition/authorizations/{authorization['authorization_receipt_id']}/port",
        headers={**_auth_headers(), "content-type": EPUB_MEDIA_TYPE},
        content=epub,
    )
    assert response.status_code == 200, response.text
    port = response.json()
    assert port["reader_route"] == f"/read/{port['document_id']}"
    assert port["content_class"] == "personal_reading"
    assert port["servability"] == "personal_readable"
    assert port["was_new"] is True
    assert "signing_key" not in response.text

    replay = client.post(
        f"/book-acquisition/authorizations/{authorization['authorization_receipt_id']}/port",
        headers={**_auth_headers(), "content-type": EPUB_MEDIA_TYPE},
        content=epub,
    )
    assert replay.status_code == 200
    assert replay.json()["port_receipt_id"] == port["port_receipt_id"]
    assert replay.json()["was_new"] is False


def test_routes_require_server_authenticated_operator(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    response = client.post(
        "/book-acquisition/intents",
        json={
            "title": "Jet Engines",
            "author": "A. Researcher",
            "store": "publisher.example",
            "max_price_usd_cents": 3000,
        },
    )
    assert response.status_code == 401


def test_money_fields_reject_coerced_strings_floats_and_booleans(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    base = {
        "title": "Jet Engines",
        "author": "A. Researcher",
        "store": "publisher.example",
    }
    for invalid in ("3000", 3000.0, True, 2**100):
        response = client.post(
            "/book-acquisition/intents",
            headers=_auth_headers(),
            json={**base, "max_price_usd_cents": invalid},
        )
        assert response.status_code == 422

    intent = _intent(client)
    for invalid in ("2500", 2500.0, True, 2**100):
        response = client.post(
            f"/book-acquisition/intents/{intent['intent_receipt_id']}/authorization",
            headers=_auth_headers(),
            json={
                "decision": "authorized",
                "authorized_price_ceiling_usd_cents": invalid,
            },
        )
        assert response.status_code == 422


def test_cross_operator_and_denied_authorization_fail_before_port(tmp_path: Path) -> None:
    client, db_path = _client(tmp_path)
    intent = _intent(client)
    wrong_operator = client.post(
        f"/book-acquisition/intents/{intent['intent_receipt_id']}/authorization",
        headers=_auth_headers("bob"),
        json={
            "decision": "authorized",
            "authorized_price_ceiling_usd_cents": 2500,
        },
    )
    assert wrong_operator.status_code == 403

    denied = _authorize(
        client,
        str(intent["intent_receipt_id"]),
        decision="denied",
    )
    port = client.post(
        f"/book-acquisition/authorizations/{denied['authorization_receipt_id']}/port",
        headers={**_auth_headers(), "content-type": EPUB_MEDIA_TYPE},
        content=_epub(),
    )
    assert port.status_code == 403
    with connect_write(str(db_path), purpose="book-acquisition-api-test-count") as con:
        assert con.execute("SELECT COUNT(*) FROM documents").fetchone() == (0,)
        assert con.execute("SELECT COUNT(*) FROM book_authorized_ports").fetchone() == (0,)


def test_port_requires_epub_media_type_and_bounded_nonempty_bytes(tmp_path: Path) -> None:
    epub = _epub()
    client, _ = _client(tmp_path, max_epub_bytes=len(epub) - 1)
    intent = _intent(client)
    authorization = _authorize(client, str(intent["intent_receipt_id"]))
    route = f"/book-acquisition/authorizations/{authorization['authorization_receipt_id']}/port"

    wrong_type = client.post(
        route,
        headers={**_auth_headers(), "content-type": "application/json"},
        content=epub,
    )
    assert wrong_type.status_code == 415

    oversized = client.post(
        route,
        headers={**_auth_headers(), "content-type": EPUB_MEDIA_TYPE},
        content=epub,
    )
    assert oversized.status_code == 413

    empty_root = tmp_path / "empty"
    empty_root.mkdir()
    empty_client, _ = _client(empty_root)
    empty_intent = _intent(empty_client)
    empty_auth = _authorize(empty_client, str(empty_intent["intent_receipt_id"]))
    empty = empty_client.post(
        f"/book-acquisition/authorizations/{empty_auth['authorization_receipt_id']}/port",
        headers={**_auth_headers(), "content-type": EPUB_MEDIA_TYPE},
        content=b"",
    )
    assert empty.status_code == 422


def test_port_rejects_invalid_and_hostile_epubs_as_client_input(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    intent = _intent(client)
    authorization = _authorize(client, str(intent["intent_receipt_id"]))
    route = f"/book-acquisition/authorizations/{authorization['authorization_receipt_id']}/port"

    for epub_bytes, reason in (
        (b"not a zip", "not_an_epub"),
        (_hostile_epub(), "path_traversal"),
    ):
        response = client.post(
            route,
            headers={**_auth_headers(), "content-type": EPUB_MEDIA_TYPE},
            content=epub_bytes,
        )
        assert response.status_code == 422
        assert reason in response.json()["detail"]


def test_router_has_no_payment_network_path_or_client_secret_surface() -> None:
    source_path = (
        Path(__file__).parents[1] / "interfaces" / "research" / "api" / "book_acquisition_routes.py"
    )
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".", 1)[0])
    assert imported_roots.isdisjoint(
        {"httpx", "requests", "urllib", "socket", "subprocess", "pathlib"}
    )
    request_fields = set(PurchaseIntentRequest.model_fields)
    assert request_fields.isdisjoint(
        {"signing_key", "api_key", "url", "path", "payment_method", "checkout"}
    )
