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
        try:
            if filter == "servable":
                assets = list_book_assets(con, servable_only=True)
            else:
                assets = list_book_assets(con, servable_only=False)
        finally:
            con.close()

        summaries = [BookSummary.from_asset(a) for a in assets]
        return build_library_page(
            summaries,
            filt=filter,
            search=search,
            page=page,
            page_size=page_size,
        )
