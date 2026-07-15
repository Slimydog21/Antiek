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
        servability="servable" if servable else "gated",
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

def test_register_library_exhausts_bounded_batches(monkeypatch: pytest.MonkeyPatch) -> None:
    """Route totals the complete catalog rather than applying a hidden cap."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import interfaces.research.api.library as lib

    calls: list[dict] = []
    transaction_commands: list[str] = []

    class _Asset:
        document_id = "d1"
        title = "T"
        author = "A"
        servability = type("S", (), {"value": "servable"})()
        servable_full_text = True
        page_count = 1
        cover_uri = None
        ip_holder_id = None
        taken_down = False

    def fake_list(
        con,
        *,
        servable_only=False,
        include_taken_down=False,
        limit=200,
        offset=0,
    ):
        assert transaction_commands == ["BEGIN TRANSACTION"]
        calls.append(
            {"servable_only": servable_only, "limit": limit, "offset": offset}
        )
        return [_Asset()] * limit if offset == 0 else [_Asset()]

    class _Con:
        def execute(self, command: str) -> None:
            transaction_commands.append(command)

        def close(self) -> None:
            return None

    monkeypatch.setattr(lib, "list_book_assets", fake_list)
    monkeypatch.setattr(lib, "_resolve_db_path", lambda: ":memory:")
    monkeypatch.setattr(
        "runtime.db_lock.connect_read",
        lambda db: _Con(),
    )

    app = FastAPI()
    lib.register_library_routes(app)
    client = TestClient(app)
    r = client.get("/library", params={"filter": "all"})
    assert r.status_code == 200, r.text
    assert calls, "list_book_assets not called"
    assert calls == [
        {
            "servable_only": False,
            "limit": lib._CATALOG_BATCH_SIZE,
            "offset": 0,
        },
        {
            "servable_only": False,
            "limit": lib._CATALOG_BATCH_SIZE,
            "offset": lib._CATALOG_BATCH_SIZE,
        },
    ]
    assert r.json()["total"] == lib._CATALOG_BATCH_SIZE + 1
    assert transaction_commands == ["BEGIN TRANSACTION", "COMMIT"]


def test_register_library_rolls_back_failed_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed batch cannot leave the read connection in a transaction."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import interfaces.research.api.library as lib

    transaction_commands: list[str] = []
    closed = False

    class _Con:
        def execute(self, command: str) -> None:
            transaction_commands.append(command)

        def close(self) -> None:
            nonlocal closed
            closed = True

    def fail_list(*args, **kwargs):
        assert transaction_commands == ["BEGIN TRANSACTION"]
        raise RuntimeError("catalog changed")

    monkeypatch.setattr(lib, "list_book_assets", fail_list)
    monkeypatch.setattr(lib, "_resolve_db_path", lambda: ":memory:")
    monkeypatch.setattr("runtime.db_lock.connect_read", lambda db: _Con())

    app = FastAPI()
    lib.register_library_routes(app)
    with pytest.raises(RuntimeError, match="catalog changed"):
        TestClient(app).get("/library")

    assert transaction_commands == ["BEGIN TRANSACTION", "ROLLBACK"]
    assert closed
