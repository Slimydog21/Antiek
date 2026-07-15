from __future__ import annotations

import zipfile
from io import BytesIO
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api import books as books_api
from runtime.db_lock import connect_read, connect_write
from substrate.graph.schema import init_database


def _epub() -> bytes:
    container = (
        '<?xml version="1.0"?>'
        '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
        '<rootfiles><rootfile full-path="OEBPS/content.opf"/></rootfiles>'
        '</container>'
    )
    opf = (
        '<?xml version="1.0"?>'
        '<package xmlns="http://www.idpf.org/2007/opf">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        '<dc:title>Imported Fixture</dc:title><dc:creator>Fixture Author</dc:creator>'
        '</metadata><manifest><item id="chapter" href="chapter.xhtml" '
        'media-type="application/xhtml+xml"/></manifest>'
        '<spine><itemref idref="chapter"/></spine></package>'
    )
    chapter = (
        '<html><body><h1>Opening</h1><p>Readable imported prose.</p>'
        '<img src="https://tracker.invalid/pixel" alt="cover"></body></html>'
    )
    output = BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("mimetype", "application/epub+zip")
        archive.writestr("META-INF/container.xml", container)
        archive.writestr("OEBPS/content.opf", opf)
        archive.writestr("OEBPS/chapter.xhtml", chapter)
    return output.getvalue()


def _client(tmp_path: Path, monkeypatch) -> tuple[TestClient, str]:
    db = str(tmp_path / "graph.duckdb")
    writer = connect_write(db, purpose="test/book-import-api/schema")
    try:
        init_database(writer)
    finally:
        writer.close()
    monkeypatch.setattr(books_api, "_resolve_db_path", lambda: db)
    monkeypatch.setenv("ANTIEK_EVENTS_DIR", str(tmp_path / "events"))
    app = FastAPI()
    books_api.register_book_routes(app)
    return TestClient(app), db


def test_epub_import_is_reachable_and_owner_only_by_default(tmp_path: Path, monkeypatch) -> None:
    client, db = _client(tmp_path, monkeypatch)
    response = client.post(
        "/books/import/epub",
        content=_epub(),
        headers={"content-type": "application/epub+zip"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["content_class"] == "personal_reading"
    assert body["source_format"] == "epub"
    assert body["content_format"] == "html"
    assert body["chunk_count"] > 0

    con = connect_read(db)
    try:
        stored = con.execute(
            "SELECT raw_text, content_class FROM documents WHERE document_id = ?",
            [body["document_id"]],
        ).fetchone()
    finally:
        con.close()
    assert stored is not None
    assert stored[1] == "personal_reading"
    assert "tracker.invalid" not in stored[0]
    assert 'alt="cover"' in stored[0]

    # The same authenticated-owner resolver used by research/context reads
    # admits personal-reading bytes without claiming they are public/servable.
    monkeypatch.setattr(
        books_api, "_owner_read_policy_tag", lambda _request: books_api._OWNER_READ_POLICY_TAG
    )
    full_text = client.get(f"/books/{body['document_id']}/owner-full-text")
    assert full_text.status_code == 200
    assert full_text.json()["servable"] is False
    assert full_text.json()["reason"] == "owner_personal_reading"
    assert full_text.json()["ad_eligible"] is False
    assert full_text.json()["content_format"] == "html"
    assert "Readable imported prose" in full_text.json()["full_text"]

    public = client.get(f"/books/{body['document_id']}/full-text")
    assert public.status_code == 200
    assert public.json()["full_text"] is None


def test_epub_import_replay_is_idempotent(tmp_path: Path, monkeypatch) -> None:
    client, _ = _client(tmp_path, monkeypatch)
    kwargs = {
        "content": _epub(),
        "headers": {"content-type": "application/epub+zip"},
    }
    first = client.post("/books/import/epub", **kwargs)
    second = client.post("/books/import/epub", **kwargs)
    assert first.status_code == second.status_code == 201
    assert first.json()["document_id"] == second.json()["document_id"]
    assert first.json()["was_new"] is True
    assert second.json()["was_new"] is False


def test_epub_import_rejects_bad_media_empty_and_oversized(
    tmp_path: Path, monkeypatch
) -> None:
    client, _ = _client(tmp_path, monkeypatch)
    assert client.post(
        "/books/import/epub", content=_epub(), headers={"content-type": "text/plain"}
    ).status_code == 415
    assert client.post(
        "/books/import/epub", content=b"", headers={"content-type": "application/epub+zip"}
    ).status_code == 400
    oversized = client.post(
        "/books/import/epub",
        content=b"x",
        headers={
            "content-type": "application/epub+zip",
            "content-length": str(97 * 1024 * 1024),
        },
    )
    assert oversized.status_code == 413


def test_owner_only_import_cannot_mint_external_rights_holder(
    tmp_path: Path, monkeypatch
) -> None:
    client, _ = _client(tmp_path, monkeypatch)
    response = client.post(
        "/books/import/epub?content_class=personal_reading&rights_holder_name=Publisher",
        content=_epub(),
        headers={"content-type": "application/epub+zip"},
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "owner_only_import_cannot_create_rights_holder"


def test_malformed_epub_returns_bounded_machine_reason(tmp_path: Path, monkeypatch) -> None:
    client, db = _client(tmp_path, monkeypatch)
    response = client.post(
        "/books/import/epub",
        content=b"not-an-epub secret payload",
        headers={"content-type": "application/epub+zip"},
    )
    assert response.status_code == 422
    assert response.json() == {"detail": "not_an_epub"}
    assert "secret" not in response.text
    con = connect_read(db)
    try:
        assert con.execute("SELECT COUNT(*) FROM documents").fetchone() == (0,)
    finally:
        con.close()
