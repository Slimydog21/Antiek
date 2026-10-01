"""Current-rights projection for retained book-anchor quotes."""

from __future__ import annotations

from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
from runtime.db_lock import connect_read, connect_write
from substrate.graph import ensure_initialized
from substrate.graph.ops import insert_document

_TEXT = "A public synthetic passage holds a retained anchor sentence."
_PRIVATE = "A private synthetic sentence remains owner scoped."
_SECRET = "anchor-current-rights-test-secret-" + "x" * 48


def _seed(db: str, document_id: str, *, content_class: str, text: str) -> None:
    ensure_initialized(db)
    from substrate.multi_user.auth import subject_owner_id

    with connect_write(db, purpose="test/anchor-current-rights-seed") as con:
        insert_document(
            con,
            document_id=document_id,
            source_tier=2,
            document_type="book",
            title="Synthetic anchor book",
            raw_text=text,
            content_class=content_class,
            owner_user_id=(
                subject_owner_id("magic_link", "owner-a@example.test")
                if content_class == "user_authored_private"
                else "__operator__"
            ),
        )
        con.execute(
            "INSERT INTO chunks "
            "(chunk_id,document_id,chunk_index,section_path,text,token_count) "
            "VALUES (?, ?, 0, 'Page 1', ?, ?)",
            [f"{document_id}-chunk", document_id, text, len(text.split())],
        )


def _payload() -> dict[str, str]:
    quote = "retained anchor sentence"
    start = _TEXT.index(quote)
    return {
        "quote": quote,
        "prefix": _TEXT[max(0, start - 8) : start],
        "suffix": _TEXT[start + len(quote) : start + len(quote) + 8],
        "source": "pin",
    }


def _app(monkeypatch, tmp_path) -> tuple[TestClient, str]:
    db = str(tmp_path / "anchor-rights.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("ANTIEK_RESEARCH_ARTIFACTS_DIR", str(tmp_path / "artifacts"))
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", _SECRET)
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", "owner-a@example.test,owner-b@example.test")
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    return (
        TestClient(create_app(register_wrestling=False, register_providers=False, cors_origins=[])),
        db,
    )


def _owner_cookie(email: str) -> dict[str, str]:
    from substrate.multi_user.auth import mint_session_cookie

    return {"ANTIEK_SESSION": mint_session_cookie("magic_link", email, email)}


def _set_takedown(db: str, document_id: str, *, taken_down: bool) -> None:
    with connect_write(db, purpose="test/anchor-current-rights-toggle") as con:
        con.execute(
            "INSERT INTO book_assets (document_id, taken_down) VALUES (?, ?) "
            "ON CONFLICT (document_id) DO UPDATE SET taken_down=excluded.taken_down",
            [document_id, taken_down],
        )


def _assert_text(anchor: dict, expected: bool) -> None:
    fields = anchor["anchor"]
    if expected:
        assert fields["quote"] == "retained anchor sentence"
        assert fields["prefix"] is not None and fields["suffix"] is not None
    else:
        assert fields["quote"] is None
        assert fields["prefix"] is None
        assert fields["suffix"] is None


def test_create_duplicate_list_and_link_apply_current_rights_without_rewriting_history(
    monkeypatch, tmp_path
) -> None:
    api, db = _app(monkeypatch, tmp_path)
    _seed(db, "public-book", content_class="public_domain", text=_TEXT)
    owner = _owner_cookie("owner-a@example.test")

    created = api.post("/books/public-book/anchors", json=_payload(), cookies=owner)
    assert created.status_code == 201, created.text
    anchor_id = created.json()["anchor_id"]
    assert created.json()["servable_at_pin"] is True
    _assert_text(created.json(), True)

    # Reclassification into another otherwise allowlisted class does not
    # override the independent takedown bit.
    with connect_write(db, purpose="test/reclass-and-takedown") as con:
        con.execute(
            "UPDATE documents SET content_class='public_domain' WHERE document_id=?",
            ["public-book"],
        )
        con.execute(
            "INSERT INTO book_assets (document_id, taken_down) VALUES (?, TRUE)",
            ["public-book"],
        )

    listing = api.get("/books/public-book/anchors", cookies=owner)
    assert listing.status_code == 200, listing.text
    assert listing.json()["count"] == 1
    _assert_text(listing.json()["anchors"][0], False)
    assert listing.json()["anchors"][0]["servable_at_pin"] is True

    duplicate = api.post("/books/public-book/anchors", json=_payload(), cookies=owner)
    assert duplicate.status_code == 200, duplicate.text
    assert duplicate.json()["anchor_id"] == anchor_id
    _assert_text(duplicate.json(), False)
    assert duplicate.json()["servable_at_pin"] is True

    linked = api.patch(
        f"/books/public-book/anchors/{anchor_id}",
        json={"investigation_id": "synthetic-investigation"},
        cookies=owner,
    )
    assert linked.status_code == 200, linked.text
    _assert_text(linked.json(), False)
    assert linked.json()["servable_at_pin"] is True
    assert linked.json()["investigation_id"] == "synthetic-investigation"

    with connect_read(db) as con:
        stored = con.execute(
            "SELECT servable_at_pin, anchor_quote, anchor_prefix, anchor_suffix "
            "FROM anchored_highlights WHERE anchor_id=?",
            [anchor_id],
        ).fetchone()
    assert stored == (
        True,
        created.json()["anchor"]["quote"],
        created.json()["anchor"]["prefix"],
        created.json()["anchor"]["suffix"],
    )

    _set_takedown(db, "public-book", taken_down=False)
    reinstated = api.get("/books/public-book/anchors", cookies=owner)
    assert reinstated.status_code == 200, reinstated.text
    _assert_text(reinstated.json()["anchors"][0], True)
    duplicate_after_reinstate = api.post(
        "/books/public-book/anchors", json=_payload(), cookies=owner
    )
    assert duplicate_after_reinstate.status_code == 200
    _assert_text(duplicate_after_reinstate.json(), True)
    relinked_after_reinstate = api.patch(
        f"/books/public-book/anchors/{anchor_id}",
        json={"investigation_id": "synthetic-investigation"},
        cookies=owner,
    )
    assert relinked_after_reinstate.status_code == 200
    _assert_text(relinked_after_reinstate.json(), True)


def test_list_reanchor_refreshes_rights_after_the_write_pass(monkeypatch, tmp_path) -> None:
    import interfaces.research.api.book_anchor_routes as routes

    api, db = _app(monkeypatch, tmp_path)
    _seed(db, "reanchor-book", content_class="public_domain", text=_TEXT)
    owner = _owner_cookie("owner-a@example.test")
    created = api.post("/books/reanchor-book/anchors", json=_payload(), cookies=owner)
    assert created.status_code == 201, created.text

    # Stale the chunk hash so GET runs its authorized reanchor write pass.
    with connect_write(db, purpose="test/stale-anchor-before-reanchor") as con:
        con.execute(
            "UPDATE chunks SET text=? WHERE document_id=?",
            ["A newly revised synthetic passage retaining anchor sentence.", "reanchor-book"],
        )
    original = routes.reanchor_document

    def reanchor_then_takedown(con, *, document_id: str):
        report = original(con, document_id=document_id)
        con.execute(
            "INSERT INTO book_assets (document_id, taken_down) VALUES (?, TRUE) "
            "ON CONFLICT (document_id) DO UPDATE SET taken_down=TRUE",
            [document_id],
        )
        return report

    monkeypatch.setattr(routes, "reanchor_document", reanchor_then_takedown)
    listing = api.get("/books/reanchor-book/anchors", cookies=owner)
    assert listing.status_code == 200, listing.text
    assert listing.json()["count"] == 1
    _assert_text(listing.json()["anchors"][0], False)
    assert listing.json()["anchors"][0]["servable_at_pin"] is True


def test_list_rows_and_rights_share_a_read_snapshot(monkeypatch, tmp_path) -> None:
    import duckdb

    import interfaces.research.api.book_anchor_routes as routes

    api, db = _app(monkeypatch, tmp_path)
    _seed(db, "snapshot-book", content_class="public_domain", text=_TEXT)
    _set_takedown(db, "snapshot-book", taken_down=False)
    owner = _owner_cookie("owner-a@example.test")
    created = api.post("/books/snapshot-book/anchors", json=_payload(), cookies=owner)
    assert created.status_code == 201, created.text
    anchor_id = created.json()["anchor_id"]

    # Keep DuckDB's writer configuration open so connect_read uses the
    # guarded RW fallback; a separate locked writer can commit during the
    # route's explicit read transaction.
    keeper = duckdb.connect(db)
    original = routes.HighlightsStore.list_for_document
    interleaved: list[str] = []

    def takedown_and_delete(self, con, document_id):
        if not interleaved:
            with connect_write(db, purpose="test/list-snapshot-interleaved-writer") as writer:
                writer.execute(
                    "UPDATE book_assets SET taken_down=TRUE WHERE document_id=?",
                    [document_id],
                )
                writer.execute("DELETE FROM anchored_highlights WHERE anchor_id=?", [anchor_id])
            interleaved.append("committed")
        return original(self, con, document_id)

    monkeypatch.setattr(routes.HighlightsStore, "list_for_document", takedown_and_delete)
    try:
        listing = api.get("/books/snapshot-book/anchors", cookies=owner)
    finally:
        keeper.close()
    assert listing.status_code == 200, listing.text
    assert interleaved == ["committed"]
    assert listing.json()["count"] == 1
    assert listing.json()["anchors"][0]["anchor_id"] == anchor_id
    _assert_text(listing.json()["anchors"][0], True)
    with connect_read(db) as con:
        assert con.execute(
            "SELECT taken_down FROM book_assets WHERE document_id=?",
            ["snapshot-book"],
        ).fetchone() == (True,)
        assert con.execute(
            "SELECT COUNT(*) FROM anchored_highlights WHERE anchor_id=?",
            [anchor_id],
        ).fetchone() == (0,)

    # The snapshot response linearized before the concurrent write; the next
    # request observes its committed takedown and deletion.
    current = api.get("/books/snapshot-book/anchors", cookies=owner)
    assert current.status_code == 200, current.text
    assert current.json()["count"] == 0


def test_link_requires_its_path_document_and_projects_that_documents_rights(
    monkeypatch, tmp_path
) -> None:
    api, db = _app(monkeypatch, tmp_path)
    _seed(db, "link-book-a", content_class="public_domain", text=_TEXT)
    _seed(db, "link-book-b", content_class="public_domain", text=_TEXT)
    owner = _owner_cookie("owner-a@example.test")
    created = api.post("/books/link-book-a/anchors", json=_payload(), cookies=owner)
    assert created.status_code == 201, created.text
    anchor_id = created.json()["anchor_id"]

    wrong_document = api.patch(
        f"/books/link-book-b/anchors/{anchor_id}",
        json={"investigation_id": "synthetic-investigation"},
        cookies=owner,
    )
    assert wrong_document.status_code == 404
    assert wrong_document.json()["detail"] == "anchor_not_found"
    with connect_read(db) as con:
        unchanged = con.execute(
            "SELECT investigation_id, servable_at_pin, anchor_quote "
            "FROM anchored_highlights WHERE anchor_id=?",
            [anchor_id],
        ).fetchone()
    assert unchanged == (
        None,
        True,
        created.json()["anchor"]["quote"],
    )

    correct_document = api.patch(
        f"/books/link-book-a/anchors/{anchor_id}",
        json={"investigation_id": "synthetic-investigation"},
        cookies=owner,
    )
    assert correct_document.status_code == 200, correct_document.text
    assert correct_document.json()["investigation_id"] == "synthetic-investigation"
    _assert_text(correct_document.json(), True)

    _set_takedown(db, "link-book-a", taken_down=True)
    current_denial = api.patch(
        f"/books/link-book-a/anchors/{anchor_id}",
        json={"investigation_id": "synthetic-investigation"},
        cookies=owner,
    )
    assert current_denial.status_code == 200, current_denial.text
    assert current_denial.json()["investigation_id"] == "synthetic-investigation"
    assert current_denial.json()["servable_at_pin"] is True
    _assert_text(current_denial.json(), False)


def test_historical_metadata_only_and_private_owner_policy_are_preserved(
    monkeypatch, tmp_path
) -> None:
    api, db = _app(monkeypatch, tmp_path)
    _seed(
        db,
        "private-book",
        content_class="user_authored_private",
        text=_PRIVATE,
    )
    owner = _owner_cookie("owner-a@example.test")
    quote = "owner scoped"
    start = _PRIVATE.index(quote)
    private_payload = {
        "quote": quote,
        "prefix": _PRIVATE[max(0, start - 8) : start],
        "suffix": _PRIVATE[start + len(quote) : start + len(quote) + 8],
        "source": "pin",
    }
    foreign = _owner_cookie("owner-b@example.test")
    denied = api.post("/books/private-book/anchors", json=private_payload, cookies=foreign)
    assert denied.status_code == 404
    created = api.post("/books/private-book/anchors", json=private_payload, cookies=owner)
    assert created.status_code == 201, created.text
    _assert_text(created.json(), False)
    assert created.json()["servable_at_pin"] is False

    # A later public class decision cannot make an historically metadata-only
    # row expose text; a present takedown remains an independent mask as well.
    with connect_write(db, purpose="test/restore-private-class-fixture") as con:
        con.execute(
            "UPDATE documents SET content_class='public_domain' WHERE document_id=?",
            ["private-book"],
        )
    public_class = api.get("/books/private-book/anchors", cookies=owner)
    assert public_class.status_code == 200, public_class.text
    _assert_text(public_class.json()["anchors"][0], False)
    _set_takedown(db, "private-book", taken_down=True)
    masked = api.get("/books/private-book/anchors", cookies=owner)
    assert masked.status_code == 200, masked.text
    _assert_text(masked.json()["anchors"][0], False)
