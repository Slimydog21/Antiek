"""Library catalog endpoint (Read SPR-09 M1).

Thin FastAPI composition over ``list_book_assets`` + pure
``build_library_page`` (filter/search/paginate). §9.0: catalog payloads are
metadata-only; bodies only via ``/books/{id}/full-text``.
"""

from __future__ import annotations

import contextlib
import functools
import sys
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from starlette.concurrency import run_in_threadpool

from substrate.books.model import list_book_assets

from .books import BookSummary, _resolve_db_path
from .library_catalog import LibraryPage, build_library_page

# Load the metadata-only catalog in bounded deterministic batches. The route
# exhausts the iterator before computing ``total``; this is a memory trade-off
# while title/author filtering remains pure, but never an arbitrary corpus cap.
_CATALOG_BATCH_SIZE = 1_000

# An arXiv bulk pass holds antiek.duckdb ~97% of the time - one ~15s batch, then
# a 0.5s yield - so a read that gives up the instant another process holds the
# file answers 500 for the whole ingest. Wait a bounded 8s instead: about half
# the batch period, which both turns a good share of those failures into a
# success and, when it still loses, leaves a retryable 503 rather than a 500.
# A reader cannot currently shorten that lottery, because only writers publish a
# handoff token (runtime/db_lock.py:376); see PR #3589's review thread.
_LOCK_WAIT_S = 8.0

# Clients already retry this route; 503 + Retry-After is the contract they can
# act on, and unlike a raw 500 it leaves through the app's error handler, so the
# CORS middleware decorates it and the browser can read the status.
_RETRY_AFTER_S = 1

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
        from runtime.db_lock import ReadLockTimeout, connect_read

        db = _resolve_db_path()
        try:
            # The wait is synchronous, so it must not run on the event loop: a
            # contended read would otherwise block every other request and the
            # health probe with it.
            con = await run_in_threadpool(
                functools.partial(connect_read, db, external_lock_timeout_s=_LOCK_WAIT_S)
            )
        except ReadLockTimeout as exc:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Library catalog is busy: another process holds the database. Retry shortly."
                ),
                headers={"Retry-After": str(_RETRY_AFTER_S)},
            ) from exc
        transaction_started = False
        try:
            # DuckDB snapshots are transaction-scoped. Keep every offset batch
            # on one snapshot so concurrent inserts/takedowns cannot shift the
            # remaining pages and corrupt the catalog total.
            con.execute("BEGIN TRANSACTION")
            transaction_started = True
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
            transaction_started = False
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
                    con.close()

        summaries = [BookSummary.from_asset(a) for a in assets]
        return build_library_page(
            summaries,
            filt=filter,
            search=search,
            page=page,
            page_size=page_size,
        )
