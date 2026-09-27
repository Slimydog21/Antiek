"""PA01 owner-document admission on anchored highlights and maps."""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from interfaces.research.api.book_anchor_routes import register_book_anchor_routes
from runtime.db_lock import connect_write
from substrate.books.ingest import register_book
from substrate.graph import ensure_initialized
from substrate.graph.ops import insert_document

BODY = "A private passage that must never become a foreign snippet."
DOC = "private-anchors"


def _client(db: str, monkeypatch, tmp_path) -> TestClient:
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("ANTIEK_RESEARCH_ARTIFACTS_DIR", str(tmp_path / "artifacts"))
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", "owner@example.test")
    ensure_initialized(db)
    with connect_write(db, purpose="pa01-anchor-seed") as con:
        insert_document(
            con, document_id=DOC, source_tier=2, document_type="book",
            title="Private anchors", raw_text=BODY,
            content_class="user_authored_private", owner_user_id="owner-a",
        )
        register_book(con, document_id=DOC, content_class="user_authored_private")
        con.execute(
            "INSERT INTO chunks (chunk_id, document_id, chunk_index, section_path, text, token_count) "
            "VALUES (?, ?, 0, ?, ?, ?)",
            ["private-chunk", DOC, "Page 1", BODY, len(BODY.split())],
        )
    app = FastAPI()

    @app.middleware("http")
    async def test_identity(request: Request, call_next):
        owner = request.headers.get("x-test-owner")
        if owner:
            request.state.user_id = owner
            request.state.auth_method = "antiek_session_cookie"
        return await call_next(request)

    register_book_anchor_routes(app)
    return TestClient(app)


def test_anchor_owner_and_foreign_document_boundary(tmp_path, monkeypatch):
    api = _client(str(tmp_path / "graph.duckdb"), monkeypatch, tmp_path)
    owner = {"x-test-owner": "owner-a"}
    foreign = {"x-test-owner": "owner-b"}
    path = f"/books/{DOC}/anchors"
    created = api.post(path, headers=owner, json={"quote": "private passage", "source": "pin"})
    assert created.status_code == 201, created.text
    anchor_id = created.json()["anchor_id"]
    for method, url, payload in (
        ("post", path, {"quote": "private passage", "source": "pin"}),
        ("get", path, None),
        ("get", f"/books/{DOC}/anchor-map", None),
        ("get", f"/books/{DOC}/anchor-map/owner", None),
    ):
        kwargs = {"headers": foreign}
        if payload is not None:
            kwargs["json"] = payload
        denied = getattr(api, method)(url, **kwargs)
        assert denied.status_code == 404, (method, url, denied.text)
        assert denied.json() == {"detail": "book_not_found"}
    for method, payload in (
        ("patch", {"investigation_id": "investigation-b"}),
        ("delete", None),
    ):
        kwargs = {"headers": foreign}
        if payload is not None:
            kwargs["json"] = payload
        hidden = getattr(api, method)(f"{path}/{anchor_id}", **kwargs)
        absent = getattr(api, method)(f"/books/absent/anchors/{anchor_id}", **kwargs)
        assert hidden.status_code == absent.status_code
        assert hidden.text == absent.text
    own_list = api.get(path, headers=owner)
    assert own_list.status_code == 200 and own_list.json()["count"] == 1
    own_map = api.get(f"/books/{DOC}/anchor-map/owner", headers=owner)
    assert own_map.status_code == 200, own_map.text
    assert own_map.json()["complete"] is True


def test_signed_session_anchor_boundary(tmp_path, monkeypatch):
    from interfaces.research.api.app import create_app
    from substrate.auth import mint_session_cookie

    _client(str(tmp_path / "graph.duckdb"), monkeypatch, tmp_path)
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", "pa01-anchor-session-secret-" + "x" * 48)
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    api = TestClient(create_app(register_wrestling=False, register_providers=False, cors_origins=[]))

    def cookies(owner: str) -> dict[str, str]:
        return {"ANTIEK_SESSION": mint_session_cookie(user_id=owner, email="owner@example.test")}

    path = f"/books/{DOC}/anchors"
    own = api.post(path, cookies=cookies("owner-a"), json={"quote": "private passage", "source": "pin"})
    assert own.status_code == 201, own.text
    foreign = api.post(path, cookies=cookies("owner-b"), json={"quote": "private passage", "source": "pin"})
    assert foreign.status_code == 404
    assert foreign.json() == {"detail": "book_not_found"}
    hidden = api.get(path, cookies=cookies("owner-b"))
    assert hidden.status_code == 404
    assert hidden.json() == {"detail": "book_not_found"}
    anonymous = api.get(path)
    assert anonymous.status_code in {401, 403}
    assert BODY not in anonymous.text
