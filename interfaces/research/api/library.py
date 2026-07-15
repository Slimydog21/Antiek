"""Library catalog endpoint (Read SPR-09 M1).

Thin FastAPI composition over ``list_book_assets`` + pure
``build_library_page`` (filter/search/paginate). §9.0: catalog payloads are
metadata-only; bodies only via ``/books/{id}/full-text``.
"""

from __future__ import annotations

from typing import Literal

from fastapi import FastAPI, Query

from substrate.books.model import list_book_assets

from .books import BookSummary, _resolve_db_path
from .library_catalog import LibraryPage, build_library_page

# Load the metadata-only catalog in bounded deterministic batches. The route
# exhausts the iterator before computing ``total``; this is a memory trade-off
# while title/author filtering remains pure, but never an arbitrary corpus cap.
_CATALOG_BATCH_SIZE = 1_000

__all__ = ["LibraryPage", "build_library_page", "register_library_routes"]


def register_library_routes(app: FastAPI) -> None:
    """Mount the library catalog route."""

    @app.get("/library", response_model=LibraryPage, tags=["library"])
    async def list_library(
        filter: Literal["servable", "gated", "all"] = "all",
        search: str = "",
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=20, ge=1, le=200),
    ) -> LibraryPage:
        from runtime.db_lock import connect_read

        db = _resolve_db_path()
        con = connect_read(db)
        committed = False
        try:
            # DuckDB snapshots are transaction-scoped. Keep every offset batch
            # on one snapshot so concurrent inserts/takedowns cannot shift the
            # remaining pages and corrupt the catalog total.
            con.execute("BEGIN TRANSACTION")
            assets = []
            offset = 0
            while True:
                batch = list_book_assets(
                    con,
                    servable_only=filter == "servable",
                    limit=_CATALOG_BATCH_SIZE,
                    offset=offset,
                )
                assets.extend(batch)
                if len(batch) < _CATALOG_BATCH_SIZE:
                    break
                offset += len(batch)
            con.execute("COMMIT")
            committed = True
        finally:
            if not committed:
                con.execute("ROLLBACK")
            con.close()

        summaries = [BookSummary.from_asset(a) for a in assets]
        return build_library_page(
            summaries,
            filt=filter,
            search=search,
            page=page,
            page_size=page_size,
        )
