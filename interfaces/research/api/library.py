"""Library catalog endpoint (Read SPR-09 M1).

Thin FastAPI composition over ``list_book_assets`` + pure
``build_library_page`` (filter/search/paginate). §9.0: catalog payloads are
metadata-only; bodies only via ``/books/{id}/full-text``.
"""

from __future__ import annotations

import contextlib
import sys
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request

from substrate.books.model import catalog_is_uninitialized, list_discoverable_book_assets

from .books import BookSummary, _private_owner_id
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
        request: Request,
        filter: Literal["servable", "gated", "all"] = "all",
        search: str = "",
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=20, ge=1, le=200),
    ) -> LibraryPage:
        from runtime.db_lock import connect_read
        from substrate.graph import default_db_path

        try:
            con = connect_read(default_db_path())
        except Exception as exc:
            raise HTTPException(status_code=503, detail="read_unavailable") from exc
        transaction_started = False
        try:
            # DuckDB snapshots are transaction-scoped. Keep every offset batch
            # on one snapshot so concurrent inserts/takedowns cannot shift the
            # remaining pages and corrupt the catalog total.
            con.execute("BEGIN TRANSACTION")
            transaction_started = True
            assets = []
            offset = 0
            if not catalog_is_uninitialized(con):
                while True:
                    batch = list_discoverable_book_assets(
                        con, owner_user_id=_private_owner_id(request), status=filter,
                        limit=_CATALOG_BATCH_SIZE, offset=offset,
                    )
                    assets.extend(batch)
                    if len(batch) < _CATALOG_BATCH_SIZE:
                        break
                    offset += len(batch)
            con.execute("COMMIT")
            transaction_started = False
        except Exception as exc:
            raise HTTPException(status_code=503, detail="read_unavailable") from exc
        finally:
            primary_failure = sys.exc_info()[0] is not None
            try:
                if transaction_started:
                    # Cleanup must preserve the batch/commit failure that
                    # caused this path; closing releases the read snapshot.
                    with contextlib.suppress(Exception):
                        con.execute("ROLLBACK")
            finally:
                if primary_failure:
                    with contextlib.suppress(Exception):
                        con.close()
                else:
                    try:
                        con.close()
                    except Exception as exc:
                        raise HTTPException(
                            status_code=503, detail="read_unavailable",
                        ) from exc

        try:
            summaries = [BookSummary.from_asset(a) for a in assets]
            return build_library_page(
                summaries,
                filt=filter,
                search=search,
                page=page,
                page_size=page_size,
            )
        except Exception as exc:
            raise HTTPException(status_code=503, detail="read_unavailable") from exc
