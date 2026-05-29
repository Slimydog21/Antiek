"""Library catalog endpoint (Read SPR-09 M1).

The Library surface (Unit B's ``apps/reading/``) needs a paginated, filterable,
searchable catalog of the owned corpus. This router is a THIN composition over
the SAME servable-corpus read path ``books.py`` already exposes — it adds
pagination + a title/author substring search + a servable|gated|all filter on
top of ``substrate.books.model.list_book_assets`` and reuses the EXISTING
``BookSummary`` shape verbatim (no parallel response model).

§9.0 (deny-by-default) is inherited, not re-implemented: ``BookSummary`` carries
only metadata + the derived ``servability`` / ``servable_full_text`` flags. A
gated work appears here FLAGGED as metadata, and its body text is NEVER inline
in any list payload — the only path that can surface full text is
``/books/{id}/full-text``, which routes through ``substrate.books.serve``. This
endpoint never touches ``raw_text`` and never widens to taken-down books.

All reads; uses ``connect_read`` and runs concurrently with the single writer.
"""

from __future__ import annotations

from typing import Literal

from fastapi import FastAPI, Query
from pydantic import BaseModel

from substrate.books.model import list_book_assets

from .books import BookSummary, _resolve_db_path


class LibraryPage(BaseModel):
    """One page of the catalog. ``works`` reuses the ``BookSummary`` shape the
    ``/books`` read path already returns (servability + servable_full_text +
    metadata only — never a body). ``total`` is the count BEFORE pagination so
    the surface can render a pager; ``page`` / ``page_size`` echo the request."""

    works: list[BookSummary]
    total: int
    page: int
    page_size: int


def _matches_search(asset_summary: BookSummary, needle: str) -> bool:
    """Case-insensitive substring match over title + author (metadata only —
    NEVER the body). An empty needle matches everything."""
    if not needle:
        return True
    hay = " ".join(
        part.lower() for part in (asset_summary.title, asset_summary.author) if part
    )
    return needle.lower() in hay


def register_library_routes(app: FastAPI) -> None:
    """Mount the library catalog route. Mirrors ``register_book_routes`` — one
    call from ``create_app``."""

    @app.get("/library", response_model=LibraryPage, tags=["library"])
    async def list_library(
        filter: Literal["servable", "gated", "all"] = "all",
        search: str = "",
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=20, ge=1, le=200),
    ) -> LibraryPage:
        """Paginated, filterable, searchable library catalog.

        ``filter`` selects servable-only / gated-only / both (each work is
        flagged with its ``servability`` either way). ``search`` is a
        case-insensitive substring over title + author (metadata only — the
        gate keeps bodies out of the payload entirely). Pagination is applied
        AFTER the filter + search so ``total`` reflects the matched set."""
        from runtime.db_lock import connect_read

        db = _resolve_db_path()
        con = connect_read(db)
        try:
            if filter == "servable":
                assets = list_book_assets(con, servable_only=True)
            else:
                # "gated" and "all" list non-taken-down books; the servability
                # flag on each lets the caller distinguish. We never widen to
                # taken-down books on a public catalog.
                assets = list_book_assets(con, servable_only=False)
                if filter == "gated":
                    assets = [a for a in assets if not a.servable_full_text]
        finally:
            con.close()

        summaries = [BookSummary.from_asset(a) for a in assets]
        matched = [s for s in summaries if _matches_search(s, search)]
        total = len(matched)

        start = (page - 1) * page_size
        works = matched[start : start + page_size]
        return LibraryPage(
            works=works, total=total, page=page, page_size=page_size
        )
