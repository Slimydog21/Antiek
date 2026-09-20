"""Reader-HTML serve routes (doc→HTML S1).

``GET /sources/{document_id}/reader-html`` — the gated endpoint that makes an
ingested URL's sanitized reader snapshot viewable in the reader. It returns
``content_format="html"`` ONLY when the sidecar body is trusted-sanitized
(exact ``SANITIZER_VERSION`` equality, enforced in
``substrate.reader_html.store.serve_reader_html``); otherwise it degrades to
the document's existing text/markdown representation with an honest reason —
never an HTML render (stored-XSS was a live defect in this exact chain; the
version gate is the whole point).

Owner resolution mirrors the owner-full-text endpoint
(``interfaces/research/api/books.py``): the privileged ``operator_only``
policy tag is granted only on a real authenticated credential under the
single-operator invariant, and only that path releases ``personal_reading``
URL bodies in full. The public path serves the same bounded view the books
serve gate would release — URL ingests are ``personal_reading`` by default.
"""

from __future__ import annotations

from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

from substrate.reader_html.store import serve_reader_html


class ReaderHtmlResponse(BaseModel):
    """What ``GET /sources/{document_id}/reader-html`` returns.

    ``content_format="html"`` (with the sanitized body in ``body``) is set
    ONLY when the sidecar row exists AND carries the exact current
    ``SANITIZER_VERSION``. Every other outcome is ``content_format="text"``
    with the document's existing text/markdown representation in ``body``
    (or ``None`` when nothing at all may be released — taken down).
    ``reason``: ``'ok'`` | ``'no_reader_html'`` | ``'sanitizer_version_stale'``
    | ``'rights_denied'`` | ``'taken_down'``.
    """

    document_id: str
    available: bool
    content_format: Literal["text", "html"]
    body: str | None
    source_kind: str | None
    source_url: str | None
    captured_at: str | None
    edited_at: str | None
    revision: int | None
    reason: str


def _resolve_db_path() -> str:
    from substrate.graph import default_db_path, ensure_initialized

    path = default_db_path()
    ensure_initialized(path)
    return path


def register_reader_html_routes(app: FastAPI) -> None:
    """Mount the reader-HTML serve routes. Mirrors
    ``register_book_routes`` — one call from ``create_app``."""

    @app.get(
        "/sources/{document_id}/reader-html",
        response_model=ReaderHtmlResponse,
        tags=["sources"],
    )
    async def get_source_reader_html(
        document_id: str, request: Request
    ) -> ReaderHtmlResponse:
        from runtime.db_lock import connect_read

        # Owner resolution identical to the owner-full-text endpoint: the
        # privileged tag binds to a real authenticated credential under the
        # single-operator invariant (never to "auth disabled"). Only the
        # owner path releases personal_reading URL bodies in full.
        from .books import _OWNER_READ_POLICY_TAG, _owner_read_policy_tag

        db = _resolve_db_path()
        con = connect_read(db)
        try:
            result = serve_reader_html(
                con,
                document_id,
                owner=(
                    _owner_read_policy_tag(request) == _OWNER_READ_POLICY_TAG
                ),
            )
        finally:
            con.close()
        if result.reason == "document_not_found":
            raise HTTPException(status_code=404, detail="document_not_found")
        return ReaderHtmlResponse(
            document_id=result.document_id,
            available=result.available,
            content_format=result.content_format,
            body=result.body,
            source_kind=result.source_kind,
            source_url=result.source_url,
            captured_at=result.captured_at,
            edited_at=result.edited_at,
            revision=result.revision,
            reason=result.reason,
        )
