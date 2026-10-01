"""Owner-bound metadata discovery through the mounted HTTP application."""

from __future__ import annotations

import duckdb
import pytest
from fastapi.testclient import TestClient

from runtime.db_lock import connect_read, connect_write
from substrate.books.model import list_discoverable_book_assets
from substrate.graph.schema import init_database
from substrate.multi_user.auth import mint_session_cookie, subject_owner_id

ALICE = "alice-discovery@example.test"
BOB = "bob-discovery@example.test"
SECRET = "discovery-synthetic-secret-" + "x" * 40


def _client(monkeypatch: pytest.MonkeyPatch, db_path: str) -> TestClient:
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", SECRET)
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", f"{ALICE},{BOB}")
    monkeypatch.setenv("ANTIEK_COOKIE_INSECURE", "1")
    monkeypatch.setenv("ANTIEK_EMAIL_PROVIDER", "mock")
    from interfaces.research.api.app import create_app

    return TestClient(create_app(register_wrestling=False, register_providers=False))


def _cookie(email: str) -> dict[str, str]:
    return {"ANTIEK_SESSION": mint_session_cookie("magic_link", email, email)}


def _seed(db_path: str, *, bulk: bool = False) -> dict[str, str]:
    owners = {email: subject_owner_id("magic_link", email) for email in (ALICE, BOB)}
    con = connect_write(db_path, purpose="discovery-synthetic-seed")
    try:
        init_database(con)
        records = [
            ("public", "public_domain", "__operator__", False),
            ("legacy", None, "__operator__", False),
            ("user-owned", "user_owned", "__operator__", False),
            ("contribution", "user_public_contribution", "__operator__", False),
            ("private-a", "user_authored_private", owners[ALICE], False),
            ("personal-a", "personal_reading", owners[ALICE], False),
            ("private-b", "user_authored_private", owners[BOB], False),
            ("personal-b", "personal_reading", owners[BOB], False),
            ("taken", "restricted_pending_opt_in", "__operator__", True),
            ("unknown", "unknown_class", "__operator__", False),
        ]
        if bulk:
            records.extend(
                (f"z-denied-{i:04d}", "user_authored_private", owners[BOB], False)
                for i in range(1100)
            )
            records.extend(
                (f"a-admitted-{i:04d}", "public_domain", "__operator__", False)
                for i in range(1210)
            )
        con.executemany(
            "INSERT INTO documents (document_id, source_tier, document_type, title, "
            "author, content_class, owner_user_id) VALUES (?, 2, 'book', ?, 'Synthetic', ?, ?)",
            [(doc, doc, content_class, owner) for doc, content_class, owner, _ in records],
        )
        con.executemany(
            "INSERT INTO book_assets (document_id, taken_down, pre_takedown_content_class) "
            "VALUES (?, ?, ?)",
            [(doc, taken, "public_domain" if taken else None)
             for doc, _, _, taken in records],
        )
    finally:
        con.close()
    return owners


@pytest.fixture
def catalog(monkeypatch: pytest.MonkeyPatch, tmp_path):
    db_path = str(tmp_path / "catalog.duckdb")
    monkeypatch.setenv("ANTIEK_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("ANTIEK_PASSKEY_STORE", str(tmp_path / "passkeys.json"))
    owners = _seed(db_path)
    return _client(monkeypatch, db_path), db_path, owners


def _ids(response, field: str) -> set[str]:
    assert response.status_code == 200, response.text
    return {item["document_id"] for item in response.json()[field]}


def _assert_unavailable(response, path: str) -> None:
    assert response.status_code == 503, response.text
    detail = response.json()["detail"]
    if path == "/documents":
        assert detail == {"error": {
            "code": "read_unavailable",
            "message": (
                "The underlying store could not be read. This is "
                "NOT a statement that no records exist."
            ),
        }}
    else:
        assert detail == "read_unavailable"


@pytest.mark.parametrize("path,field", [
    ("/documents", "documents"), ("/books?status=all", "books"),
    ("/library?filter=all", "works"),
])
def test_signed_principals_see_own_and_shared_metadata_only(catalog, path, field):
    client, _, _ = catalog
    for email, own, foreign in (
        (ALICE, {"private-a", "personal-a"}, {"private-b", "personal-b"}),
        (BOB, {"private-b", "personal-b"}, {"private-a", "personal-a"}),
    ):
        ids = _ids(client.get(path, cookies=_cookie(email)), field)
        assert own | {"public", "legacy", "user-owned", "contribution"} <= ids
        assert not ids & (foreign | {"unknown", "taken"})


def test_status_is_applied_before_book_limit(catalog):
    client, db_path, owners = catalog
    with connect_read(db_path) as con:
        assert {asset.document_id for asset in list_discoverable_book_assets(
            con, owner_user_id=owners[ALICE], status="servable",
        )} == {"public", "user-owned", "contribution"}
        assert {asset.document_id for asset in list_discoverable_book_assets(
            con, owner_user_id=owners[ALICE], status="gated",
        )} == {"legacy", "private-a", "personal-a"}
    assert _ids(client.get("/books?status=gated", cookies=_cookie(ALICE)), "books") == {
        "legacy", "private-a", "personal-a",
    }


def test_gated_book_page_survives_newer_public_cap_and_orders_ties(catalog):
    client, db_path, owners = catalog
    con = connect_write(db_path, purpose="discovery-gated-pagination")
    try:
        con.execute("UPDATE book_assets SET created_at = TIMESTAMP '2020-01-01 00:00:00'")
        con.executemany(
            "INSERT INTO documents (document_id, source_tier, document_type, "
            "title, content_class) VALUES (?, 2, 'book', ?, 'public_domain')",
            [(f"new-public-{i:03d}", f"new-public-{i:03d}") for i in range(210)],
        )
        con.executemany(
            "INSERT INTO book_assets (document_id, created_at) "
            "VALUES (?, TIMESTAMP '2025-01-01 00:00:00')",
            [(f"new-public-{i:03d}",) for i in range(210)],
        )
    finally:
        con.close()
    assert _ids(client.get("/books?status=gated", cookies=_cookie(ALICE)), "books") == {
        "legacy", "private-a", "personal-a",
    }
    with connect_read(db_path) as con:
        pages = [list_discoverable_book_assets(
            con, owner_user_id=owners[ALICE], status="gated", limit=1, offset=offset,
        )[0].document_id for offset in range(3)]
    assert pages == ["private-a", "personal-a", "legacy"]


def test_document_limit_skips_newer_foreign_private(catalog):
    client, db_path, owners = catalog
    con = connect_write(db_path, purpose="discovery-document-page")
    try:
        con.executemany(
            "INSERT INTO documents (document_id, source_tier, document_type, "
            "title, content_class, owner_user_id) VALUES (?, 2, 'book', ?, ?, ?)",
            [
                ("zy-public", "zy-public", "public_domain", "__operator__"),
                ("zz-foreign", "zz-foreign", "user_authored_private", owners[BOB]),
            ],
        )
    finally:
        con.close()
    assert _ids(client.get("/documents?limit=1", cookies=_cookie(ALICE)),
                "documents") == {"zy-public"}


def test_large_mixed_catalog_paginates_after_visibility(monkeypatch, tmp_path):
    db_path = str(tmp_path / "large.duckdb")
    monkeypatch.setenv("ANTIEK_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("ANTIEK_PASSKEY_STORE", str(tmp_path / "passkeys.json"))
    _seed(db_path, bulk=True)
    client = _client(monkeypatch, db_path)
    cookie = _cookie(ALICE)
    books = client.get("/books", cookies=cookie)
    assert books.status_code == 200, books.text
    assert books.json()["count"] == 200
    assert len({item["document_id"] for item in books.json()["books"]}) == 200
    assert all(item["document_id"] != "z-denied-0000" for item in books.json()["books"])
    page = client.get("/library?filter=all&page=7&page_size=200", cookies=cookie)
    assert page.status_code == 200, page.text
    assert page.json()["total"] == 1216
    assert len(page.json()["works"]) == 16
    assert not any(item["document_id"].startswith("z-denied") for item in page.json()["works"])
    assert "a-admitted-0000" in _ids(
        client.get("/library?filter=all&search=a-admitted-0000", cookies=cookie), "works",
    )
    assert _ids(client.get("/documents?limit=2000", cookies=cookie), "documents") == {
        "public", "legacy", "user-owned", "contribution", "private-a", "personal-a",
        *(f"a-admitted-{i:04d}" for i in range(1210)),
    }


@pytest.mark.parametrize("tables", [(), ("documents",), ("book_assets",)])
def test_only_empty_main_schema_is_honest_empty(monkeypatch, tmp_path, tables):
    db_path = str(tmp_path / "state.duckdb")
    monkeypatch.setenv("ANTIEK_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("ANTIEK_PASSKEY_STORE", str(tmp_path / "passkeys.json"))
    con = duckdb.connect(db_path)
    try:
        for table in tables:
            con.execute(f"CREATE TABLE {table} (document_id TEXT)")
    finally:
        con.close()
    client = _client(monkeypatch, db_path)
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", "")
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", "")
    for path, field in (("/documents", "documents"), ("/books", "books"), ("/library", "works")):
        response = client.get(path)
        if not tables:
            assert response.status_code == 200, response.text
            assert response.json()[field] == []
        else:
            _assert_unavailable(response, path)


def test_incomplete_columns_and_open_failure_are_unavailable(monkeypatch, tmp_path):
    db_path = str(tmp_path / "broken.duckdb")
    monkeypatch.setenv("ANTIEK_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("ANTIEK_PASSKEY_STORE", str(tmp_path / "passkeys.json"))
    con = duckdb.connect(db_path)
    try:
        con.execute("CREATE TABLE documents (document_id TEXT)")
        con.execute("CREATE TABLE book_assets (document_id TEXT)")
    finally:
        con.close()
    client = _client(monkeypatch, db_path)
    cookie = _cookie(ALICE)
    for path in ("/documents", "/books", "/library"):
        _assert_unavailable(client.get(path, cookies=cookie), path)
    missing_path = tmp_path / "absent.duckdb"
    assert not missing_path.exists()
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(missing_path))
    for path in ("/documents", "/books", "/library"):
        _assert_unavailable(client.get(path, cookies=cookie), path)
        assert not missing_path.exists()


def test_document_materialization_failure_is_unavailable_then_valid_row_reads(
    monkeypatch, tmp_path,
):
    db_path = str(tmp_path / "malformed-row.duckdb")
    monkeypatch.setenv("ANTIEK_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("ANTIEK_PASSKEY_STORE", str(tmp_path / "passkeys.json"))
    con = duckdb.connect(db_path)
    try:
        con.execute(
            "CREATE TABLE documents (document_id TEXT, title TEXT, source_uri TEXT, "
            "document_type TEXT, source_tier TEXT, investigation_id TEXT, "
            "content_class TEXT, ip_holder_id TEXT, owner_user_id TEXT)"
        )
        con.execute("CREATE TABLE book_assets (document_id TEXT, taken_down BOOLEAN)")
        con.executemany(
            "INSERT INTO documents (document_id, title, document_type, source_tier, "
            "content_class, owner_user_id) VALUES (?, ?, 'book', ?, 'public_domain', ?)",
            [
                ("good", "Good synthetic row", "2", "__operator__"),
                ("bad", "Bad synthetic row", "not-an-integer", "__operator__"),
            ],
        )
    finally:
        con.close()
    client = _client(monkeypatch, db_path)
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", "")
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", "")
    _assert_unavailable(client.get("/documents"), "/documents")
    con = duckdb.connect(db_path)
    try:
        con.execute("DELETE FROM documents WHERE document_id = 'bad'")
    finally:
        con.close()
    response = client.get("/documents")
    assert response.status_code == 200, response.text
    assert response.json()["documents"] == [{
        "document_id": "good", "title": "Good synthetic row", "source_uri": None,
        "document_type": "book", "source_tier": 2, "investigation_id": None,
        "content_class": "public_domain", "ip_holder_id": None,
    }]


def test_book_and_library_materialization_failure_then_valid_title_reads(
    monkeypatch, tmp_path,
):
    monkeypatch.setenv("ANTIEK_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("ANTIEK_PASSKEY_STORE", str(tmp_path / "passkeys.json"))

    def seed_catalog(path, *, title_type: str, title_value: int | str) -> None:
        con = duckdb.connect(str(path))
        try:
            con.execute(
                "CREATE TABLE documents (document_id TEXT, title " + title_type + ", "
                "author TEXT, content_class TEXT, ip_holder_id TEXT, owner_user_id TEXT)"
            )
            con.execute(
                "CREATE TABLE book_assets (document_id TEXT, page_count INTEGER, "
                "pagination_scheme TEXT, cover_uri TEXT, toc_json TEXT, "
                "provenance TEXT, license_basis TEXT, taken_down BOOLEAN, "
                "taken_down_at TIMESTAMP, takedown_reason TEXT, "
                "pre_takedown_content_class TEXT, created_at TIMESTAMP)"
            )
            con.execute(
                "INSERT INTO documents VALUES ('synthetic-book', ?, 'Synthetic', "
                "'public_domain', NULL, '__operator__')",
                [title_value],
            )
            con.execute(
                "INSERT INTO book_assets (document_id, page_count, pagination_scheme, "
                "taken_down, created_at) VALUES "
                "('synthetic-book', 1, 'pdf_page', FALSE, CURRENT_TIMESTAMP)"
            )
        finally:
            con.close()

    malformed = tmp_path / "malformed-title.duckdb"
    valid = tmp_path / "valid-title.duckdb"
    seed_catalog(malformed, title_type="INTEGER", title_value=7)
    seed_catalog(valid, title_type="TEXT", title_value="Valid synthetic title")
    client = _client(monkeypatch, str(malformed))
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", "")
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", "")
    for path in ("/books", "/library"):
        _assert_unavailable(client.get(path), path)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(valid))
    for path, field in (("/books", "books"), ("/library", "works")):
        response = client.get(path)
        assert response.status_code == 200, response.text
        assert response.json()[field][0]["title"] == "Valid synthetic title"


def test_unauthenticated_request_exposes_no_catalog(catalog):
    client, _, _ = catalog
    for path in ("/documents", "/books", "/library"):
        response = client.get(path)
        assert response.status_code == 401


def test_local_request_without_verified_principal_sees_only_shared_catalog(
    catalog, monkeypatch,
):
    client, _, _ = catalog
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", "")
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", "")
    for path, field in (("/documents", "documents"), ("/books?status=all", "books"),
                        ("/library", "works")):
        ids = _ids(client.get(path), field)
        assert ids == {"public", "legacy", "user-owned", "contribution"}


def test_private_row_with_blank_owner_is_not_discoverable(catalog):
    client, db_path, _ = catalog
    con = connect_write(db_path, purpose="discovery-blank-owner")
    try:
        con.execute("UPDATE documents SET owner_user_id = '' WHERE document_id = 'private-a'")
    finally:
        con.close()
    for path, field in (("/documents", "documents"), ("/books?status=all", "books"),
                        ("/library", "works")):
        assert "private-a" not in _ids(client.get(path, cookies=_cookie(ALICE)), field)


def test_inventory_failure_is_unavailable(catalog, monkeypatch):
    client, _, _ = catalog
    from substrate.graph import schema

    def broken_inventory(_con):
        raise RuntimeError("synthetic inventory failure")

    monkeypatch.setattr(schema, "list_tables", broken_inventory)
    for path in ("/documents", "/books", "/library"):
        response = client.get(path, cookies=_cookie(ALICE))
        _assert_unavailable(response, path)


@pytest.mark.parametrize("fail_query", [False, True])
def test_library_close_failure_preserves_unavailable_contract(
    catalog, monkeypatch, fail_query: bool,
):
    client, _, _ = catalog
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", "")
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", "")
    from runtime import db_lock

    real_connect = db_lock.connect_read

    class FailingClose:
        def __init__(self, con):
            self.con = con

        def execute(self, sql, *args):
            if fail_query and "information_schema.tables" in sql:
                raise RuntimeError("synthetic inventory failure")
            return self.con.execute(sql, *args)

        def close(self):
            self.con.close()
            raise RuntimeError("synthetic close failure")

    def connect_with_failure(path):
        return FailingClose(real_connect(path))

    monkeypatch.setattr(db_lock, "connect_read", connect_with_failure)
    response = client.get("/library")
    _assert_unavailable(response, "/library")
