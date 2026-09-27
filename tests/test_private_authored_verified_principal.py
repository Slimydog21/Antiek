"""PA01 private reads require the subject-backed D2 principal at HTTP seams."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from runtime.db_lock import connect_write
from substrate.books.ingest import register_book
from substrate.graph import ensure_initialized
from substrate.graph.ops import insert_document

PRIVATE = "user_authored_private"
BODY_A = "synthetic private body owner A"
BODY_B = "synthetic private body owner B"


def _seed(db: str) -> None:
    from substrate.multi_user.auth import subject_owner_id

    ensure_initialized(db)
    with connect_write(db, purpose="pa01-verified-principal-seed") as con:
        for doc, title, body, owner in (
            (
                "private-a", "Private A", BODY_A,
                subject_owner_id("magic_link", "owner-a@example.test"),
            ),
            (
                "private-b", "Private B", BODY_B,
                subject_owner_id("magic_link", "owner-b@example.test"),
            ),
        ):
            insert_document(
                con,
                document_id=doc,
                source_tier=2,
                document_type="book",
                title=title,
                raw_text=body,
                content_class=PRIVATE,
                owner_user_id=owner,
            )
            register_book(con, document_id=doc, content_class=PRIVATE)
            con.execute(
                "INSERT INTO chunks "
                "(chunk_id,document_id,chunk_index,section_path,text,token_count) "
                "VALUES (?,?,0,?,?,?)",
                [f"{doc}-chunk", doc, "Page 1", body, len(body.split())],
            )


def _api(monkeypatch, tmp_path) -> TestClient:
    db = str(tmp_path / "graph.duckdb")
    _seed(db)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("ANTIEK_RESEARCH_ARTIFACTS_DIR", str(tmp_path / "artifacts"))
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", "pa01-verified-principal-test-" + "x" * 48)
    monkeypatch.setenv(
        "ANTIEK_OPERATOR_EMAIL", "owner-a@example.test,owner-b@example.test"
    )
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    from interfaces.research.api.app import create_app

    return TestClient(
        create_app(register_wrestling=False, register_providers=False, cors_origins=[])
    )


def _cookies(monkeypatch, email: str) -> dict[str, str]:
    from substrate.multi_user.auth import mint_session_cookie

    cookie = mint_session_cookie("magic_link", email, email)
    return {"ANTIEK_SESSION": cookie}


def _owner(email: str) -> str:
    from substrate.multi_user.auth import subject_owner_id

    return subject_owner_id("magic_link", email)


def test_two_subject_owners_read_only_their_private_book_body_and_map(
    monkeypatch, tmp_path
):
    api = _api(monkeypatch, tmp_path)
    a = _cookies(monkeypatch, "owner-a@example.test")
    b = _cookies(monkeypatch, "owner-b@example.test")

    for doc, own_cookie, own_body, foreign_cookie in (
        ("private-a", a, BODY_A, b),
        ("private-b", b, BODY_B, a),
    ):
        detail = api.get(f"/books/{doc}", cookies=own_cookie)
        assert detail.status_code == 200, detail.text
        full_text = api.get(f"/books/{doc}/owner-full-text", cookies=own_cookie)
        assert full_text.status_code == 200, full_text.text
        assert full_text.json()["full_text"] == own_body
        anchor_map = api.get(f"/books/{doc}/anchor-map/owner", cookies=own_cookie)
        assert anchor_map.status_code == 200, anchor_map.text
        assert {c["chunk_id"] for c in anchor_map.json()["chunks"]} == {f"{doc}-chunk"}

        foreign = api.get(f"/books/{doc}/owner-full-text", cookies=foreign_cookie)
        unknown = api.get("/books/absent/owner-full-text", cookies=foreign_cookie)
        assert foreign.status_code == unknown.status_code == 404
        assert foreign.text == unknown.text
        assert own_body not in foreign.text
        foreign_map = api.get(f"/books/{doc}/anchor-map/owner", cookies=foreign_cookie)
        assert foreign_map.status_code == 404
        assert foreign_map.text == unknown.text
        assert own_body not in foreign_map.text

        public_body = api.get(f"/books/{doc}/full-text", cookies=own_cookie)
        public_missing = api.get("/books/absent/full-text", cookies=own_cookie)
        assert public_body.status_code == public_missing.status_code == 404
        assert public_body.text == public_missing.text
        assert own_body not in public_body.text
        public_map = api.get(f"/books/{doc}/anchor-map", cookies=own_cookie)
        map_missing = api.get("/books/absent/anchor-map", cookies=own_cookie)
        assert public_map.status_code == map_missing.status_code == 404
        assert public_map.text == map_missing.text
        assert own_body not in public_map.text


def test_subject_mapping_failure_and_legacy_cookies_never_admit_private_reads(
    monkeypatch, tmp_path
):
    from starlette.requests import Request

    from substrate.auth import mint_session_cookie as mint_legacy_cookie
    from substrate.auth import verify_session_cookie
    from substrate.multi_user.auth import AuthError, resolve_authenticated_principal

    api = _api(monkeypatch, tmp_path)
    legacy = mint_legacy_cookie(
        user_id=_owner("owner-a@example.test"), email="owner-a@example.test"
    )
    mismatch = mint_legacy_cookie(
        user_id=_owner("owner-a@example.test"),
        email="owner-a@example.test",
        provider="magic_link",
        subject="owner-b@example.test",
    )
    sentinel = mint_legacy_cookie(user_id="__operator__", email="owner-a@example.test")
    for cookie in (legacy, mismatch, sentinel):
        assert verify_session_cookie(cookie)
        for path in (
            "/books/private-a",
            "/books/private-a/owner-full-text",
            "/books/private-a/anchor-map/owner",
        ):
            denied = api.get(path, cookies={"ANTIEK_SESSION": cookie})
            assert denied.status_code == 404, (path, denied.text)
            assert BODY_A not in denied.text

    for change in ("alter", "delete"):
        case_dir = tmp_path / change
        case_dir.mkdir()
        case_api = _api(monkeypatch, case_dir)
        a = _cookies(monkeypatch, "owner-a@example.test")["ANTIEK_SESSION"]
        request = Request({
            "type": "http", "method": "GET", "path": "/",
            "headers": [(b"cookie", f"ANTIEK_SESSION={a}".encode())],
        })
        assert verify_session_cookie(a).user_id == _owner("owner-a@example.test")
        assert resolve_authenticated_principal(request).owner_user_id == _owner(
            "owner-a@example.test"
        )
        db = str(case_dir / "graph.duckdb")
        with connect_write(db, purpose=f"pa01-subject-{change}") as con:
            if change == "alter":
                con.execute(
                    "UPDATE auth_subjects SET owner_user_id=? "
                    "WHERE provider='magic_link' AND subject=?",
                    ["user:tampered:owner", "owner-a@example.test"],
                )
            else:
                con.execute(
                    "DELETE FROM auth_subjects WHERE provider='magic_link' AND subject=?",
                    ["owner-a@example.test"],
                )
        assert verify_session_cookie(a).user_id == _owner("owner-a@example.test")
        with pytest.raises(AuthError):
            resolve_authenticated_principal(request)
        for path in (
            "/books/private-a",
            "/books/private-a/owner-full-text",
            "/books/private-a/anchor-map/owner",
            "/books/private-a/anchors",
        ):
            denied = case_api.get(path, cookies={"ANTIEK_SESSION": a})
            assert denied.status_code == 404, (path, denied.text)
            assert BODY_A not in denied.text



def test_owner_anchor_map_uses_one_read_snapshot(monkeypatch, tmp_path):
    import duckdb

    import interfaces.research.api.book_anchor_routes as routes

    api = _api(monkeypatch, tmp_path)
    owner_cookie = _cookies(monkeypatch, "owner-a@example.test")
    db = str(tmp_path / "graph.duckdb")
    # Keep a same-config writer handle alive so connect_read takes its guarded
    # RW fallback; this lets a separate locked writer commit during the route's
    # explicit MVCC read snapshot.
    keeper = duckdb.connect(db)
    original = routes.build_anchor_map
    interleaved: list[str] = []
    replacement = BODY_A + "\nA newly appended section after the served passage."

    def write_between_guard_and_map(con, *, document_id, served_text):
        with connect_write(
            db, purpose="pa01-interleaved-chunk-writer", timeout_s=2
        ) as writer:
            writer.execute(
                "UPDATE documents SET raw_text=? WHERE document_id=?",
                [replacement, document_id],
            )
            writer.execute("DELETE FROM chunks WHERE document_id=?", [document_id])
            writer.execute(
                "INSERT INTO chunks "
                "(chunk_id,document_id,chunk_index,section_path,text,token_count) "
                "VALUES (?,?,0,?,?,?)",
                [
                    "private-a-new-chunk", document_id, "Page 2",
                    BODY_A, len(BODY_A.split()),
                ],
            )
            appended = "A newly appended section after the served passage."
            writer.execute(
                "INSERT INTO chunks "
                "(chunk_id,document_id,chunk_index,section_path,text,token_count) "
                "VALUES (?,?,1,?,?,?)",
                ["private-a-appended-chunk", document_id, "Page 3", appended, len(appended.split())],
            )
        interleaved.append(served_text)
        return original(con, document_id=document_id, served_text=served_text)

    monkeypatch.setattr(routes, "build_anchor_map", write_between_guard_and_map)
    try:
        result = api.get("/books/private-a/anchor-map/owner", cookies=owner_cookie)
    finally:
        keeper.close()
    assert result.status_code == 200, result.text
    assert interleaved == [BODY_A]
    assert {row["chunk_id"] for row in result.json()["chunks"]} == {"private-a-chunk"}
    with connect_write(db, purpose="pa01-interleaved-state-check") as writer:
        assert writer.execute(
            "SELECT raw_text FROM documents WHERE document_id='private-a'"
        ).fetchone() == (replacement,)
        assert writer.execute(
            "SELECT chunk_id FROM chunks WHERE document_id='private-a' ORDER BY chunk_index"
        ).fetchall() == [
            ("private-a-new-chunk",),
            ("private-a-appended-chunk",),
        ]


def test_owner_anchor_map_failure_rolls_back_and_closes(monkeypatch, tmp_path):
    import interfaces.research.api.book_anchor_routes as routes
    import interfaces.research.api.books as books
    import runtime.db_lock

    api = _api(monkeypatch, tmp_path)
    owner_cookie = _cookies(monkeypatch, "owner-a@example.test")
    client = TestClient(api.app, raise_server_exceptions=False)
    original_connect = runtime.db_lock.connect_read
    original_builder = routes.build_anchor_map
    original_serve = books.serve_full_text_guarded
    events: list[str] = []

    class Tracked:
        def __init__(self, con):
            self.con = con

        def execute(self, query, *args):
            if query == "BEGIN TRANSACTION":
                events.append("begin")
            elif query == "ROLLBACK":
                events.append("rollback")
            elif query == "COMMIT":
                events.append("commit")
            return self.con.execute(query, *args)

        def close(self):
            events.append("close")
            self.con.close()

        def __getattr__(self, name):
            return getattr(self.con, name)

    monkeypatch.setattr(
        runtime.db_lock, "connect_read",
        lambda path: Tracked(original_connect(path)),
    )

    def fail(*_args, **_kwargs):
        raise RuntimeError("synthetic map failure")

    for path, patch_target in (
        ("/books/private-a/owner-full-text", books),
        ("/books/private-a/anchor-map/owner", routes),
    ):
        events.clear()
        if patch_target is books:
            monkeypatch.setattr(books, "serve_full_text_guarded", fail)
        else:
            monkeypatch.setattr(routes, "build_anchor_map", fail)
        result = client.get(path, cookies=owner_cookie)
        assert result.status_code == 500, (path, result.text)
        assert events == ["begin", "rollback", "close"]
        monkeypatch.setattr(books, "serve_full_text_guarded", original_serve)
        monkeypatch.setattr(routes, "build_anchor_map", original_builder)
