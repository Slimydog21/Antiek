"""Public book resources enforce document identity and retrieval-time rights."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from runtime.db_lock import connect_write
from substrate.graph.schema import init_database_at_path
from tools.antiek_memory.__main__ import _make_handlers
from tools.antiek_memory.server import AntiekMemoryServer, ResourceContent

BookServer = tuple[
    AntiekMemoryServer, Callable[[str], ResourceContent | None], dict[str, str]
]


@pytest.fixture
def book_server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> BookServer:
    path = str(tmp_path / "books.duckdb")
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    init_database_at_path(path)
    cases = (
        ("restricted", "restricted_pending_opt_in", "pub-1", None, False),
        ("personal", "personal_reading", None, None, False),
        ("taken-down", "public_domain", None, None, True),
        ("null", None, None, None, False),
        ("private", "user_owned", None, None, False),
        ("public", "public_domain", "pub-2", '{"isbn": "0-306-40615-2"}', False),
        ("bad-metadata", "public_domain", None, "{bad json", False),
    )
    markers = {name: f"BODY-{name.upper()}-7f3" for name, *_ in cases}
    with connect_write(path, purpose="seed-book-resources") as con:
        for name, content_class, ip_holder_id, metadata, taken_down in cases:
            document_id = f"doc-{name}"
            con.execute(
                "INSERT INTO documents (document_id, title, source_tier, document_type, "
                "owner_user_id, content_class, ip_holder_id, metadata) "
                "VALUES (?, ?, 1, 'book', ?, ?, ?, ?)",
                [document_id, f"Title {name}", "user-b", content_class, ip_holder_id, metadata],
            )
            con.execute(
                "INSERT INTO chunks (chunk_id, document_id, chunk_index, text) "
                "VALUES (?, ?, 0, ?)",
                [f"chunk-{name}", document_id, markers[name]],
            )
            if taken_down:
                con.execute(
                    "INSERT INTO book_assets (document_id, taken_down) VALUES (?, TRUE)",
                    [document_id],
                )
    _handlers, resource_handler = _make_handlers(path)
    return AntiekMemoryServer(resource_handler=resource_handler), resource_handler, markers


def _read(server: AntiekMemoryServer, uri: str) -> dict[str, Any]:
    response = server.handle_request({
        "jsonrpc": "2.0", "id": 7, "method": "resources/read", "params": {"uri": uri},
    })
    assert response is not None
    return response


@pytest.mark.parametrize(
    ("name", "servability"),
    (
        ("restricted", "restricted"),
        ("personal", "personal_readable"),
        ("taken-down", "taken_down"),
        ("null", "gated_metadata_only"),
    ),
)
def test_withheld_book_returns_licensing_error_without_body_or_holder(
    book_server: BookServer, name: str, servability: str,
) -> None:
    server, _handler, markers = book_server
    uri = f"antiek://books/doc-{name}/chunk-{name}"
    response = _read(server, uri)
    assert response["error"] == {
        "code": -32001,
        "message": "Licensing required",
        "data": {
            "uri": uri,
            "chunk_id": f"chunk-{name}",
            "document_id": f"doc-{name}",
            "title": f"Title {name}",
            "servability": servability,
        },
    }
    wire = json.dumps(response)
    assert markers[name] not in wire
    assert "pub-1" not in wire


def test_private_book_is_not_found(book_server: BookServer) -> None:
    server, handler, markers = book_server
    uri = "antiek://books/doc-private/chunk-private"
    assert handler(uri) is None
    response = _read(server, uri)
    assert response["error"]["code"] == -32602
    assert markers["private"] not in json.dumps(response)


@pytest.mark.parametrize("identifier", ("9780306406157", "doc-public"))
def test_public_book_serves_enveloped_body_with_attribution(
    book_server: BookServer, identifier: str,
) -> None:
    server, _handler, markers = book_server
    uri = f"antiek://books/{identifier}/chunk-public"
    response = _read(server, uri)
    content = response["result"]["contents"][0]
    assert content["uri"] == uri
    assert content["mimeType"] == "application/json"
    assert json.loads(content["text"]) == {
        "chunk_id": "chunk-public",
        "isbn": identifier,
        "document_id": "doc-public",
        "title": "Title public",
        "ip_holder_id": "pub-2",
        "servability": "public_domain",
        "text": f'<antiek:content trusted="false">{markers["public"]}</antiek:content>',
    }


@pytest.mark.parametrize(
    "uri",
    (
        "antiek://books/9781234567897/chunk-public",
        "antiek://books/any-isbn/chunk-public",
        "antiek://books/9780306406157/chunk-bad-metadata",
        "antiek://books/only-one-segment",
        "antiek://books/a/b/c",
    ),
)
def test_mismatched_identity_or_malformed_uri_is_not_found(
    book_server: BookServer, uri: str,
) -> None:
    server, _handler, markers = book_server
    response = _read(server, uri)
    assert response["error"]["code"] == -32602
    assert all(marker not in json.dumps(response) for marker in markers.values())
