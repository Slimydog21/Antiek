"""Red-proofs: pure library catalog page builder (no DB)."""

from __future__ import annotations

import pytest

from interfaces.research.api.books import BookSummary
from interfaces.research.api.library_catalog import (
    apply_servability_filter,
    build_library_page,
    matches_search,
    summary_payload_has_no_body,
)
from substrate.books.servability import ServabilityStatus


def _sum(
    doc_id: str,
    *,
    title: str,
    author: str = "A",
    servable: bool = True,
) -> BookSummary:
    return BookSummary(
        document_id=doc_id,
        title=title,
        author=author,
        servability=(
            ServabilityStatus.PUBLIC_DOMAIN
            if servable
            else ServabilityStatus.GATED_METADATA_ONLY
        ),
        servable_full_text=servable,
        page_count=10,
        cover_uri=None,
        ip_holder_id=None,
        taken_down=False,
    )


def test_matches_search_title_author_only() -> None:
    s = _sum("d1", title="Scaling Laws", author="Kaplan")
    assert matches_search(s, "scaling")
    assert matches_search(s, "kaplan")
    assert not matches_search(s, "nonexistent")
    assert matches_search(s, "")


def test_servability_filter() -> None:
    rows = [
        _sum("s1", title="Open", servable=True),
        _sum("g1", title="Gated", servable=False),
    ]
    assert [x.document_id for x in apply_servability_filter(rows, "servable")] == ["s1"]
    assert [x.document_id for x in apply_servability_filter(rows, "gated")] == ["g1"]
    assert len(apply_servability_filter(rows, "all")) == 2


def test_build_page_pagination_and_total_after_filter() -> None:
    rows = [
        _sum(f"s{i}", title=f"Book {i}", servable=True) for i in range(5)
    ] + [
        _sum("g0", title="Secret", servable=False),
    ]
    page = build_library_page(rows, filt="servable", search="", page=1, page_size=2)
    assert page.total == 5
    assert len(page.works) == 2
    assert page.page == 1
    page2 = build_library_page(rows, filt="servable", page=2, page_size=2)
    assert len(page2.works) == 2
    page3 = build_library_page(rows, filt="servable", page=3, page_size=2)
    assert len(page3.works) == 1


def test_search_applied_before_total() -> None:
    rows = [
        _sum("a", title="Transformers", servable=True),
        _sum("b", title="Gardening", servable=True),
        _sum("c", title="Transformer Circuits", servable=False),
    ]
    page = build_library_page(rows, filt="all", search="transform", page=1, page_size=10)
    assert page.total == 2
    ids = {w.document_id for w in page.works}
    assert ids == {"a", "c"}


def test_summary_has_no_body_fields() -> None:
    s = _sum("d", title="T")
    assert summary_payload_has_no_body(s)
    data = s.model_dump()
    assert "raw_text" not in data
    assert "full_text" not in data
    assert "body" not in data


def test_invalid_page_params() -> None:
    with pytest.raises(ValueError, match="page"):
        build_library_page([], page=0)
    with pytest.raises(ValueError, match="page_size"):
        build_library_page([], page_size=0)
    with pytest.raises(ValueError, match="page_size"):
        build_library_page([], page_size=201)


def test_builder_handles_more_than_default_asset_limit() -> None:
    """Catalog honesty: totals must reflect full filtered set, not a 200 cap."""
    rows = [
        _sum(f"s{i}", title=f"Book {i}", servable=True) for i in range(250)
    ] + [
        _sum(f"g{i}", title=f"Gated {i}", servable=False) for i in range(30)
    ]
    page = build_library_page(rows, filt="gated", page=1, page_size=10)
    assert page.total == 30
    assert len(page.works) == 10
    all_page = build_library_page(rows, filt="all", page=1, page_size=50)
    assert all_page.total == 280

def _app_with_primary_cause_observer():
    """Observe opaque HTTP errors without replacing normal response handling."""
    from fastapi import FastAPI, HTTPException
    from fastapi.exception_handlers import http_exception_handler

    app = FastAPI()
    primary_causes: list[BaseException | None] = []

    @app.exception_handler(HTTPException)
    async def observe_http_exception(request, exc):
        primary_causes.append(exc.__cause__)
        return await http_exception_handler(request, exc)

    return app, primary_causes


_CATALOG_TABLE_QUERY = (
    "SELECT table_name FROM information_schema.tables "
    "WHERE table_schema='main' ORDER BY table_name"
)


def _initialized_catalog_query(command, transaction_commands, schema_queries):
    """Model only the real catalog gate's initialized-schema diagnostic."""
    if command != _CATALOG_TABLE_QUERY:
        return None
    assert transaction_commands == ["BEGIN TRANSACTION"]
    schema_queries.append(command)

    class _Rows:
        def fetchall(self):
            return [("book_assets",), ("documents",)]

    return _Rows()


def test_register_library_exhausts_bounded_batches(
    monkeypatch: pytest.MonkeyPatch, tmp_path,
) -> None:
    """Route totals the complete catalog rather than applying a hidden cap."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import interfaces.research.api.library as lib

    calls: list[dict] = []
    transaction_commands: list[str] = []
    schema_queries: list[str] = []

    class _Asset:
        document_id = "d1"
        title = "T"
        author = "A"
        servability = ServabilityStatus.PUBLIC_DOMAIN
        servable_full_text = True
        page_count = 1
        cover_uri = None
        ip_holder_id = None
        taken_down = False

    def fake_list(
        con,
        *,
        owner_user_id,
        status="all",
        limit=200,
        offset=0,
    ):
        assert con is connection
        assert transaction_commands == ["BEGIN TRANSACTION"]
        assert owner_user_id is None
        assert status == "all"
        calls.append(
            {
                "owner_user_id": owner_user_id,
                "status": status,
                "limit": limit,
                "offset": offset,
            }
        )
        return [_Asset()] * limit if offset == 0 else [_Asset()]

    class _Con:
        def execute(self, command: str):
            assert self is connection
            rows = _initialized_catalog_query(
                command, transaction_commands, schema_queries,
            )
            if rows is not None:
                return rows
            transaction_commands.append(command)

        def close(self) -> None:
            return None

    monkeypatch.setattr(lib, "list_discoverable_book_assets", fake_list)
    synthetic_path = str(tmp_path / "synthetic-catalog.duckdb")
    monkeypatch.setattr("substrate.graph.default_db_path", lambda: synthetic_path)
    connection = _Con()

    def fake_connect(db):
        assert db == synthetic_path
        return connection

    monkeypatch.setattr("runtime.db_lock.connect_read", fake_connect)

    app = FastAPI()
    lib.register_library_routes(app)
    client = TestClient(app)
    r = client.get("/library", params={"filter": "all"})
    assert r.status_code == 200, r.text
    assert calls, "list_discoverable_book_assets not called"
    assert calls == [
        {
            "owner_user_id": None,
            "status": "all",
            "limit": lib._CATALOG_BATCH_SIZE,
            "offset": 0,
        },
        {
            "owner_user_id": None,
            "status": "all",
            "limit": lib._CATALOG_BATCH_SIZE,
            "offset": lib._CATALOG_BATCH_SIZE,
        },
    ]
    assert r.json()["total"] == lib._CATALOG_BATCH_SIZE + 1
    assert transaction_commands == ["BEGIN TRANSACTION", "COMMIT"]
    assert schema_queries == [_CATALOG_TABLE_QUERY]


def test_register_library_rolls_back_failed_snapshot(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """Opaque batch failure preserves its cause through rollback/close failures."""
    from fastapi.testclient import TestClient

    import interfaces.research.api.library as lib

    transaction_commands: list[str] = []
    schema_queries: list[str] = []
    closed = False

    class _Con:
        def execute(self, command: str):
            assert self is connection
            rows = _initialized_catalog_query(
                command, transaction_commands, schema_queries,
            )
            if rows is not None:
                return rows
            transaction_commands.append(command)
            if command == "ROLLBACK":
                raise RuntimeError("rollback failed")

        def close(self) -> None:
            nonlocal closed
            closed = True
            raise RuntimeError("close failed")

    list_calls = []

    def fail_list(con, *, owner_user_id, status="all", limit=200, offset=0):
        assert con is connection
        assert transaction_commands == ["BEGIN TRANSACTION"]
        assert owner_user_id is None
        assert status == "all"
        assert limit == lib._CATALOG_BATCH_SIZE and offset == 0
        list_calls.append((owner_user_id, status, limit, offset))
        raise RuntimeError("catalog changed")

    monkeypatch.setattr(lib, "list_discoverable_book_assets", fail_list)
    synthetic_path = str(tmp_path / "synthetic-catalog.duckdb")
    monkeypatch.setattr("substrate.graph.default_db_path", lambda: synthetic_path)
    connection = _Con()

    def fake_connect(db):
        assert db == synthetic_path
        return connection

    monkeypatch.setattr("runtime.db_lock.connect_read", fake_connect)

    app, primary_causes = _app_with_primary_cause_observer()
    lib.register_library_routes(app)
    response = TestClient(app).get("/library")
    assert response.status_code == 503
    assert response.json() == {"detail": "read_unavailable"}
    assert len(primary_causes) == 1
    assert isinstance(primary_causes[0], RuntimeError)
    assert str(primary_causes[0]) == "catalog changed"
    assert len(list_calls) == 1

    assert transaction_commands == ["BEGIN TRANSACTION", "ROLLBACK"]
    assert schema_queries == [_CATALOG_TABLE_QUERY]
    assert closed


def test_register_library_closes_when_begin_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """Opaque BEGIN failure preserves its cause, skips rollback, and closes."""
    from fastapi.testclient import TestClient

    import interfaces.research.api.library as lib

    transaction_commands: list[str] = []
    schema_queries: list[str] = []
    closed = False

    class _Con:
        def execute(self, command: str):
            assert self is connection
            rows = _initialized_catalog_query(
                command, transaction_commands, schema_queries,
            )
            if rows is not None:
                return rows
            transaction_commands.append(command)
            raise RuntimeError("begin failed")

        def close(self) -> None:
            nonlocal closed
            closed = True

    synthetic_path = str(tmp_path / "synthetic-catalog.duckdb")
    monkeypatch.setattr("substrate.graph.default_db_path", lambda: synthetic_path)
    connection = _Con()

    def fake_connect(db):
        assert db == synthetic_path
        return connection

    monkeypatch.setattr("runtime.db_lock.connect_read", fake_connect)

    app, primary_causes = _app_with_primary_cause_observer()
    lib.register_library_routes(app)
    response = TestClient(app).get("/library")
    assert response.status_code == 503
    assert response.json() == {"detail": "read_unavailable"}
    assert len(primary_causes) == 1
    assert isinstance(primary_causes[0], RuntimeError)
    assert str(primary_causes[0]) == "begin failed"

    assert transaction_commands == ["BEGIN TRANSACTION"]
    assert schema_queries == []
    assert closed


def test_register_library_rolls_back_commit_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """Opaque COMMIT failure preserves its cause through rollback and close."""
    from fastapi.testclient import TestClient

    import interfaces.research.api.library as lib

    transaction_commands: list[str] = []
    schema_queries: list[str] = []
    closed = False

    class _Con:
        def execute(self, command: str):
            assert self is connection
            rows = _initialized_catalog_query(
                command, transaction_commands, schema_queries,
            )
            if rows is not None:
                return rows
            transaction_commands.append(command)
            if command == "COMMIT":
                raise RuntimeError("commit failed")

        def close(self) -> None:
            nonlocal closed
            closed = True

    list_calls = []

    def empty_list(con, *, owner_user_id, status="all", limit=200, offset=0):
        assert con is connection
        assert transaction_commands == ["BEGIN TRANSACTION"]
        assert owner_user_id is None
        assert status == "all"
        assert limit == lib._CATALOG_BATCH_SIZE and offset == 0
        list_calls.append((owner_user_id, status, limit, offset))
        return []

    monkeypatch.setattr(lib, "list_discoverable_book_assets", empty_list)
    synthetic_path = str(tmp_path / "synthetic-catalog.duckdb")
    monkeypatch.setattr("substrate.graph.default_db_path", lambda: synthetic_path)
    connection = _Con()

    def fake_connect(db):
        assert db == synthetic_path
        return connection

    monkeypatch.setattr("runtime.db_lock.connect_read", fake_connect)

    app, primary_causes = _app_with_primary_cause_observer()
    lib.register_library_routes(app)
    response = TestClient(app).get("/library")
    assert response.status_code == 503
    assert response.json() == {"detail": "read_unavailable"}
    assert len(primary_causes) == 1
    assert isinstance(primary_causes[0], RuntimeError)
    assert str(primary_causes[0]) == "commit failed"
    assert len(list_calls) == 1

    assert transaction_commands == ["BEGIN TRANSACTION", "COMMIT", "ROLLBACK"]
    assert schema_queries == [_CATALOG_TABLE_QUERY]
    assert closed
