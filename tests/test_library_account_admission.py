"""Real account middleware and stored-owner Library catalogue controls.

Only mail delivery is substituted by the existing isolated account fixture.
Account issuance, signed sessions, graph rows and book handlers are real.
"""

from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from test_operational_account_isolation import ALICE, BOB, OPERATOR, sign_in
from test_operational_account_isolation import account_api as account_api

from interfaces.research.api import library
from runtime import db_lock
from substrate.auth import mint_session_cookie
from substrate.books.ingest import register_book
from substrate.books.model import BookAsset
from substrate.books.takedown import take_down
from substrate.graph.ops import insert_document


@pytest.fixture
def library_accounts(account_api: Any) -> tuple[Any, Path, dict[str, TestClient], dict[str, str]]:
    app, sender, root = account_api
    clients = {email: sign_in(app, sender, email)[0] for email in (ALICE, BOB, OPERATOR)}
    subjects = {
        email: client.get("/auth/me").json()["user_id"] for email, client in clients.items()
    }
    assert len(set(subjects.values())) == 3
    return app, root, clients, subjects


def seed_book(
    con: db_lock.LockedConnection,
    document_id: str,
    owner: str,
    content_class: str | None,
    *,
    order: int = 0,
) -> BookAsset:
    insert_document(
        con,
        document_id=document_id,
        source_tier=2,
        document_type="book",
        title=f"Title {document_id}",
        author=f"Author {document_id}",
        raw_text=f"PRIVATE_BODY_{document_id}",
        owner_user_id=owner,
        content_class=content_class,
    )
    asset = register_book(
        con,
        document_id=document_id,
        content_class=content_class,
        rights_holder_name=f"Holder {document_id}",
        page_count=17 + order,
        cover_uri=f"https://example.test/cover/{document_id}",
    )
    # Explicit fixture ordering makes raw batch boundaries independent of clock precision.
    con.execute(
        "UPDATE book_assets SET created_at = TIMESTAMP '2026-01-01' + ? * INTERVAL '1 second' "
        "WHERE document_id = ?",
        [order, document_id],
    )
    if content_class is None:
        con.execute(
            "UPDATE documents SET content_class = NULL WHERE document_id = ?", [document_id]
        )
    return asset


def page(client: TestClient, **params: Any) -> dict[str, Any]:
    response = client.get("/library", params=params)
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"works", "total", "page", "page_size"}
    assert "PRIVATE_BODY_" not in response.text
    for work in body["works"]:
        assert set(work) == {
            "document_id",
            "title",
            "author",
            "servability",
            "servable_full_text",
            "page_count",
            "cover_uri",
            "ip_holder_id",
            "taken_down",
        }
    return body


@pytest.mark.parametrize(
    "content_class",
    ["public_domain", "opt_in_licensed", "source_declared_open", "user_public_contribution"],
)
def test_real_ordinary_account_can_list_public_metadata(
    library_accounts: Any,
    content_class: str,
) -> None:
    _app, root, clients, subjects = library_accounts
    with db_lock.connect_write(str(root / "graph.duckdb"), purpose="test/library-public") as con:
        asset = seed_book(con, "public", subjects[BOB], content_class)
    body = page(clients[ALICE])
    assert body["total"] == 1
    assert body["page"] == 1 and body["page_size"] == 20
    work = body["works"][0]
    assert work["document_id"] == "public"
    assert work["title"] == "Title public" and work["author"] == "Author public"
    assert work["cover_uri"] == "https://example.test/cover/public"
    assert work["page_count"] == 17 and work["ip_holder_id"] == asset.ip_holder_id
    assert work["taken_down"] is False
    if content_class == "public_domain":
        response = clients[ALICE].get("/books/public/full-text")
        assert response.status_code == 200
        assert "PRIVATE_BODY_public" in response.text


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE", "HEAD"])
def test_library_admission_is_exact_get(library_accounts: Any, method: str) -> None:
    _app, _root, clients, _subjects = library_accounts
    response = clients[ALICE].request(method, "/library")
    assert response.status_code == 403
    if method != "HEAD":
        assert response.json() == {"detail": "operator_access_required"}


def test_library_options_exposes_no_catalogue(library_accounts: Any) -> None:
    _app, _root, clients, _subjects = library_accounts
    response = clients[ALICE].options("/library")
    assert response.status_code == 405
    assert "works" not in response.json()


@pytest.mark.parametrize("path", ["/library/", "/library/foreign", "/libraries"])
def test_library_admission_does_not_open_a_prefix(library_accounts: Any, path: str) -> None:
    _app, _root, clients, _subjects = library_accounts
    response = clients[ALICE].get(path, follow_redirects=False)
    assert response.status_code == 403
    assert response.json() == {"detail": "operator_access_required"}


def test_public_and_all_three_private_owners_coexist_without_unknown_owner_disclosure(
    library_accounts: Any,
) -> None:
    _app, root, clients, subjects = library_accounts
    with db_lock.connect_write(str(root / "graph.duckdb"), purpose="test/library-mixed") as con:
        seed_book(con, "public", subjects[BOB], "public_domain")
        seed_book(con, "alice", subjects[ALICE], "personal_reading")
        seed_book(con, "bob", subjects[BOB], "user_owned")
        seed_book(con, "legacy", "__operator__", "personal_reading")
        seed_book(con, "unowned-null", "unresolved-library-owner", None)
        seed_book(con, "unowned-private", "unresolved-library-owner", "user_owned")
    public_rows = []
    for email, own in ((ALICE, "alice"), (BOB, "bob"), (OPERATOR, "legacy")):
        result = page(clients[email])
        assert result["total"] == 2
        by_id = {row["document_id"]: row for row in result["works"]}
        assert set(by_id) == {"public", own}
        public_rows.append(by_id["public"])
        assert "unowned" not in json.dumps(result)
    assert public_rows[0] == public_rows[1] == public_rows[2]


@pytest.mark.parametrize(
    "content_class", ["personal_reading", "user_owned", "restricted_pending_opt_in", None]
)
def test_stored_owner_filters_every_private_metadata_field_and_forged_input(
    library_accounts: Any,
    content_class: str | None,
) -> None:
    _app, root, clients, subjects = library_accounts
    with db_lock.connect_write(str(root / "graph.duckdb"), purpose="test/library-owner") as con:
        assets = {
            "alice-private": seed_book(
                con, "alice-private", subjects[ALICE], content_class, order=1
            ),
            "bob-private": seed_book(con, "bob-private", subjects[BOB], content_class, order=2),
            "legacy-private": seed_book(
                con, "legacy-private", "__operator__", "personal_reading", order=3
            ),
        }
    for email, own in ((ALICE, "alice-private"), (BOB, "bob-private")):
        body = page(clients[email])
        assert body["total"] == 1
        assert {work["document_id"] for work in body["works"]} == {own}
        work = body["works"][0]
        assert work["title"] == f"Title {own}" and work["author"] == f"Author {own}"
        assert work["cover_uri"] == f"https://example.test/cover/{own}"
        assert work["page_count"] == assets[own].page_count
        assert work["ip_holder_id"] == assets[own].ip_holder_id
        foreign = "bob-private" if email == ALICE else "alice-private"
        forged = clients[email].get(
            "/library",
            params={"owner_user_id": subjects[BOB if email == ALICE else ALICE]},
            headers={"X-User-Id": subjects[BOB if email == ALICE else ALICE]},
        )
        assert forged.status_code == 200
        assert forged.json() == body
        for private_id in (foreign, "legacy-private"):
            assert private_id not in forged.text
            holder = assets[private_id].ip_holder_id
            assert isinstance(holder, str)
            assert holder not in forged.text
            for suffix in ("", "/full-text", "/owner-full-text"):
                denied = clients[email].get(f"/books/{private_id}{suffix}")
                assert denied.status_code == 403
                assert private_id not in denied.text
    assert clients[ALICE].get("/books/alice-private").status_code == 200
    if content_class == "personal_reading":
        own_body = clients[ALICE].get("/books/alice-private/owner-full-text")
        assert own_body.status_code == 200
        assert "PRIVATE_BODY_alice-private" in own_body.text


@pytest.mark.parametrize(
    ("filt", "search", "expected"),
    [
        ("all", "", {"public", "alice-gated"}),
        ("servable", "", {"public"}),
        ("gated", "", {"alice-gated"}),
        ("all", "TITLE ALICE", {"alice-gated"}),
        ("all", "aUtHoR PUBLIC", {"public"}),
        ("all", "bob-secret", set()),
        ("gated", "bob-secret", set()),
        ("servable", "bob-secret", set()),
        ("all", "PRIVATE_BODY", set()),
    ],
)
def test_authorized_search_filter_totals_and_pages(
    library_accounts: Any,
    filt: str,
    search: str,
    expected: set[str],
) -> None:
    _app, root, clients, subjects = library_accounts
    with db_lock.connect_write(str(root / "graph.duckdb"), purpose="test/library-search") as con:
        seed_book(con, "public", subjects[BOB], "public_domain", order=3)
        seed_book(con, "alice-gated", subjects[ALICE], "personal_reading", order=2)
        seed_book(con, "bob-secret", subjects[BOB], "personal_reading", order=1)
    results = [
        page(clients[ALICE], filter=filt, search=search, page=index, page_size=1)
        for index in (1, 2, 3)
    ]
    assert all(result["total"] == len(expected) for result in results)
    assert [result["page"] for result in results] == [1, 2, 3]
    ids = [work["document_id"] for result in results for work in result["works"]]
    assert len(ids) == len(set(ids)) == len(expected)
    assert set(ids) == expected


def test_hidden_raw_batches_do_not_end_or_shift_authorized_pages(
    library_accounts: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _app, root, clients, subjects = library_accounts
    raw_order = [
        "hidden-0",
        "hidden-1",
        "own-0",
        "hidden-2",
        "hidden-3",
        "own-1",
        "hidden-4",
        "hidden-5",
    ]
    with db_lock.connect_write(str(root / "graph.duckdb"), purpose="test/library-batches") as con:
        for index, document_id in enumerate(raw_order):
            owner = subjects[ALICE] if document_id.startswith("own") else subjects[BOB]
            seed_book(con, document_id, owner, "personal_reading", order=len(raw_order) - index)
    monkeypatch.setattr(library, "_CATALOG_BATCH_SIZE", 2)
    real_batch = library.list_book_assets
    offsets: list[int] = []

    def batch(con: Any, *, servable_only: bool, limit: int, offset: int) -> list[BookAsset]:
        offsets.append(offset)
        return real_batch(con, servable_only=servable_only, limit=limit, offset=offset)

    monkeypatch.setattr(library, "list_book_assets", batch)
    for index, expected in ((1, ["own-0"]), (2, ["own-1"]), (3, [])):
        offsets.clear()
        result = page(clients[ALICE], page=index, page_size=1)
        assert result["total"] == 2
        assert [work["document_id"] for work in result["works"]] == expected
        assert offsets == [0, 2, 4, 6, 8]


def test_real_persisted_original_legacy_alias_does_not_grant_other_accounts(
    library_accounts: Any,
) -> None:
    _app, root, clients, subjects = library_accounts
    persisted = json.loads((root / "accounts.json").read_text())
    original = next(row for row in persisted["accounts"] if row["email"] == OPERATOR)
    assert original["user_id"] == subjects[OPERATOR]
    assert original["legacy_owner"] == "__operator__"
    with db_lock.connect_write(str(root / "graph.duckdb"), purpose="test/library-alias") as con:
        seed_book(con, "legacy", "__operator__", "personal_reading")
        seed_book(con, "original-canonical", subjects[OPERATOR], "user_owned")
        seed_book(con, "alice", subjects[ALICE], "personal_reading")
    result = page(clients[OPERATOR])
    assert result["total"] == 2
    assert {row["document_id"] for row in result["works"]} == {"legacy", "original-canonical"}
    assert {row["document_id"] for row in page(clients[ALICE])["works"]} == {"alice"}
    assert page(clients[BOB])["total"] == 0


def test_interim_operator_policy_alone_cannot_grant_legacy_library_rows(
    account_api: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, sender, root = account_api
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", f"{OPERATOR},{ALICE}")
    alice = sign_in(app, sender, ALICE)[0]
    subject = alice.get("/auth/me").json()["user_id"]
    with db_lock.connect_write(str(root / "graph.duckdb"), purpose="test/library-no-alias") as con:
        seed_book(con, "legacy-secret", "__operator__", "personal_reading")
        seed_book(con, "interim-own", subject, "personal_reading")
    result = page(alice)
    assert result["total"] == 1
    assert {row["document_id"] for row in result["works"]} == {"interim-own"}
    assert "legacy-secret" not in json.dumps(result)


def test_closed_operator_mode_retains_existing_catalogue_semantics(
    account_api: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, _sender, root = account_api
    monkeypatch.delenv("ANTIEK_OPEN_SIGNUP")
    monkeypatch.delenv("ANTIEK_LEGACY_OPERATOR_EMAIL")
    client = TestClient(app)
    client.cookies.set(
        "ANTIEK_SESSION", mint_session_cookie(user_id="__operator__", email=OPERATOR)
    )
    with db_lock.connect_write(str(root / "graph.duckdb"), purpose="test/library-closed") as con:
        seed_book(con, "legacy", "__operator__", "personal_reading")
        seed_book(con, "old-private", "old-cli-owner", "user_owned")
    assert {row["document_id"] for row in page(client)["works"]} == {"legacy", "old-private"}


@pytest.mark.parametrize("owner", [ALICE, BOB])
def test_takedown_excluded_from_catalogue_without_changing_registered_metadata(
    library_accounts: Any,
    owner: str,
) -> None:
    _app, root, clients, subjects = library_accounts
    with db_lock.connect_write(str(root / "graph.duckdb"), purpose="test/library-takedown") as con:
        seed_book(con, "taken-down", subjects[owner], "public_domain")
        assert take_down(con, "taken-down", reason="isolated Library control")
    for filt in ("all", "gated", "servable"):
        assert page(clients[owner], filter=filt) == {
            "works": [],
            "total": 0,
            "page": 1,
            "page_size": 20,
        }
    metadata = clients[owner].get("/books/taken-down")
    assert metadata.status_code == 200
    assert metadata.json()["taken_down"] is True
    assert metadata.json()["servable_full_text"] is False
    for suffix in ("/full-text", "/owner-full-text"):
        response = clients[owner].get(f"/books/taken-down{suffix}")
        assert response.status_code == 403
        assert "PRIVATE_BODY_" not in response.text


@pytest.mark.parametrize(
    "credential", ["missing", "invalid", "expired", "unknown-account", "wrong-email"]
)
def test_library_requires_current_verified_account_session(
    library_accounts: Any,
    credential: str,
) -> None:
    app, _root, _clients, subjects = library_accounts
    client = TestClient(app)
    if credential == "invalid":
        value = "invalid-signature"
    elif credential == "expired":
        value = mint_session_cookie(user_id=subjects[ALICE], email=ALICE, max_age_seconds=-1)
    elif credential == "unknown-account":
        value = mint_session_cookie(user_id="acct_" + "0" * 32, email=ALICE)
    elif credential == "wrong-email":
        value = mint_session_cookie(user_id=subjects[ALICE], email=BOB)
    else:
        value = ""
    if value:
        client.cookies.set("ANTIEK_SESSION", value)
    response = client.get("/library", headers={"X-User-Id": subjects[ALICE]})
    assert response.status_code == 401
    assert "works" not in response.json()


def test_owner_filter_batches_and_takedown_use_one_read_snapshot(
    library_accounts: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _app, root, clients, subjects = library_accounts
    db = str(root / "graph.duckdb")
    with db_lock.connect_write(db, purpose="test/library-snapshot-seed") as con:
        seed_book(con, "public-before", subjects[BOB], "public_domain", order=3)
        seed_book(con, "alice-before", subjects[ALICE], "personal_reading", order=2)
        seed_book(con, "bob-before", subjects[BOB], "personal_reading", order=1)
    entered, release = threading.Event(), threading.Event()
    real_batch = library.list_book_assets
    first_request = True

    def batch(con: Any, *, servable_only: bool, limit: int, offset: int) -> list[BookAsset]:
        assets = real_batch(con, servable_only=servable_only, limit=limit, offset=offset)
        if first_request and offset == 0:
            entered.set()
            if not release.wait(timeout=5):
                raise TimeoutError("private Library snapshot barrier was not released")
        return assets

    monkeypatch.setattr(library, "_CATALOG_BATCH_SIZE", 1)
    monkeypatch.setattr(library, "list_book_assets", batch)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(clients[ALICE].get, "/library")
        try:
            assert entered.wait(timeout=5)
            with db_lock.connect_write(db, purpose="test/library-concurrent-write") as con:
                assert take_down(con, "public-before", reason="concurrent private control")
                con.execute(
                    "UPDATE documents SET owner_user_id = ? WHERE document_id = ?",
                    [subjects[BOB], "alice-before"],
                )
                seed_book(con, "public-after", subjects[BOB], "public_domain", order=4)
        finally:
            release.set()
        response = pending.result(timeout=5)
    assert response.status_code == 200
    assert response.json()["total"] == 2
    assert {row["document_id"] for row in response.json()["works"]} == {
        "public-before",
        "alice-before",
    }
    first_request = False
    result = page(clients[ALICE])
    assert result["total"] == 1
    assert {row["document_id"] for row in result["works"]} == {"public-after"}
