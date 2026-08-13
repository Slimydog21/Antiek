"""Reader-HTML sidecar store — trusted-producer + serve gate (doc→HTML S1).

The per-URL reader snapshot has been built during URL ingest for a long time
(``acquisition/snapshot/reader_html.py``), but its regex-denylist sanitizer is
explicitly NOT a sanitizer (see ``html_sanitizer.py``'s module docstring), so
the snapshot could never be served as HTML. This module is the trusted
replacement: **sanitize on write** through the book allowlist sanitizer
(:func:`substrate.books.html_sanitizer.sanitize_book_html`) and stamp the
exact ``SANITIZER_VERSION`` in the same INSERT — the sidecar table is the ONLY
trust carrier for reader bodies. ``documents.metadata`` is deliberately NOT
stamped (the §5.2 hazard: ``substrate/books/serve.py`` would then label the
*markdown* ``raw_text`` as ``content_format="html"`` and the reader would
innerHTML markdown).

Serve gate, two rings, fail-closed (mirrors ``is_trusted_sanitized``):

1. **RIGHTS** — delegate to ``substrate.books.serve_guard.serve_full_text_guarded``
   (the one sanctioned full-body serve caller, per
   ``tools/lint/serve_guard_check.py``): if that verdict would not release
   the text body, the HTML body is not released either (denial reasons pass
   through; a taken-down document serves nothing at all).
2. **VERSION** — the sidecar row must exist AND its ``sanitizer_version``
   must equal ``SANITIZER_VERSION`` exactly. A missing or version-stale row
   degrades to the document's existing text/markdown representation with an
   honest reason — never an HTML render.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from runtime.db_lock import LockedConnection
from substrate.books.html_sanitizer import SANITIZER_VERSION, sanitize_book_html

# Bounded sidecar ceiling — mirrors the markdown_to_safe_html ceiling in
# acquisition/snapshot/reader_html.py. Sanitization runs after the bound so
# the stored body is both bounded AND fully allowlist-sanitized.
MAX_READER_HTML_CHARS = 500_000


def _require_locked(con: Any) -> None:
    if not isinstance(con, LockedConnection):
        raise TypeError(
            f"reader-html store requires a LockedConnection (got {type(con).__name__}). "
            "Use runtime.db_lock.connect_write(db_path)."
        )


def store_reader_html(
    con: LockedConnection,
    *,
    document_id: str,
    main_html: str,
    source_kind: str,
    source_url: str | None = None,
) -> int:
    """The ONLY write path for the reader-HTML sidecar.

    Sanitizes INSIDE the call (write-side sanitize, same discipline as
    ``book_import/publish.py``) and stamps ``SANITIZER_VERSION`` in the same
    INSERT — the version bit is written at the same write that ran the
    sanitizer, so it cannot be stamped separately or forged by client
    metadata (no client-supplied metadata enters this table at all).

    Idempotent: re-storing for the same ``document_id`` upserts the row
    (``revision`` increments, ``captured_at`` refreshes) — the safe behaviour
    for the URL re-ingest / replace paths. Returns the stored byte length of
    the sanitized body.
    """
    _require_locked(con)
    sanitized = sanitize_book_html(main_html[:MAX_READER_HTML_CHARS])
    captured_at = datetime.now(UTC).replace(tzinfo=None)
    con.execute(
        """
        INSERT INTO document_reader_html (
            document_id, html_body, sanitizer_version, source_kind,
            source_url, captured_at, edited_at, revision
        ) VALUES (?, ?, ?, ?, ?, ?, NULL, 1)
        ON CONFLICT (document_id) DO UPDATE SET
            html_body = EXCLUDED.html_body,
            sanitizer_version = EXCLUDED.sanitizer_version,
            source_kind = EXCLUDED.source_kind,
            source_url = EXCLUDED.source_url,
            captured_at = EXCLUDED.captured_at,
            edited_at = NULL,
            revision = document_reader_html.revision + 1
        """,
        [document_id, sanitized, SANITIZER_VERSION, source_kind, source_url, captured_at],
    )
    return len(sanitized.encode("utf-8"))


@dataclass(frozen=True)
class ReaderHtmlResult:
    """The outcome of a reader-HTML serve request.

    ``content_format="html"`` (with the sanitized body in ``body``) is set
    ONLY when the rights ring released the body AND the sidecar row carries
    the exact current sanitizer version. Every other outcome is
    ``content_format="text"``: ``body`` then carries the document's existing
    text/markdown representation (the same bytes the books serve path would
    release), or ``None`` when nothing at all may be released (taken down).
    ``reason`` explains the outcome: ``'ok'`` | ``'no_reader_html'`` |
    ``'sanitizer_version_stale'`` | ``'rights_denied'`` | ``'taken_down'`` |
    ``'document_not_found'``.
    """

    document_id: str
    available: bool
    content_format: Literal["text", "html"]  # "text" == not serveable as HTML
    body: str | None
    source_kind: str | None
    source_url: str | None
    captured_at: str | None
    edited_at: str | None
    revision: int | None
    reason: str


def serve_reader_html(
    con: Any,
    document_id: str,
    *,
    owner: bool = False,
) -> ReaderHtmlResult:
    """Resolve what may be served for ``document_id``'s reader snapshot.

    Read-only. Two rings, fail-closed:

    1. **RIGHTS** — delegates to
       :func:`substrate.books.serve_guard.serve_full_text_guarded(con, id,
       owner=owner)` — the ONE sanctioned full-body serve caller (the raw
       ``serve_full_text`` gate is allowlist-linted to it; see
       ``tools/lint/serve_guard_check.py``). The guard adds the independent
       license-tier cross-check on top of the content_class gate. A verdict
       that would not release the text body (taken down, gated) also
       withholds the HTML body; the denial reason passes through. A gated
       document degrades to the same bounded snippet the books serve path
       would release — never the HTML body.
    2. **VERSION** — the sidecar row must exist and carry
       ``sanitizer_version == SANITIZER_VERSION`` exactly. Missing row ⇒
       ``no_reader_html``; version mismatch ⇒ ``sanitizer_version_stale``.
       Both degrade to the released text body with ``content_format="text"``
       (the reader falls back to its existing markdown representation —
       never an HTML render).
    """
    # The sanctioned full-body serve path: serve_full_text_guarded composes
    # the content_class gate with the independent license-tier cross-check and
    # returns the same ServeResult shape (serve-decision fields preserved
    # exactly). Calling the raw serve_full_text here would trip the
    # serve_guard_check allowlist lint — and bypass the rights drift check.
    from substrate.books.serve_guard import serve_full_text_guarded

    rights = serve_full_text_guarded(con, document_id, owner=owner)

    if not rights.found:
        return ReaderHtmlResult(
            document_id=document_id,
            available=False,
            content_format="text",
            body=None,
            source_kind=None,
            source_url=None,
            captured_at=None,
            edited_at=None,
            revision=None,
            reason="document_not_found",
        )

    if rights.full_text is None:
        # The text body would not be released → the HTML body is not released
        # either. Taken-down is absolute (no body, no snippet); anything else
        # (gated, gate disagreement) degrades to the existing snippet view.
        if rights.reason == "taken_down":
            return ReaderHtmlResult(
                document_id=document_id,
                available=False,
                content_format="text",
                body=None,
                source_kind=None,
                source_url=None,
                captured_at=None,
                edited_at=None,
                revision=None,
                reason="taken_down",
            )
        return ReaderHtmlResult(
            document_id=document_id,
            available=False,
            content_format="text",
            body=rights.snippet,
            source_kind=None,
            source_url=None,
            captured_at=None,
            edited_at=None,
            revision=None,
            reason="rights_denied",
        )

    # Ring 2 — VERSION: the sidecar row must exist AND carry the exact
    # current sanitizer version. deny by default, same posture as
    # is_trusted_sanitized.
    row = con.execute(
        """
        SELECT html_body, sanitizer_version, source_kind, source_url,
               captured_at, edited_at, revision
        FROM document_reader_html
        WHERE document_id = ?
        """,
        [document_id],
    ).fetchone()

    if row is None:
        return ReaderHtmlResult(
            document_id=document_id,
            available=False,
            content_format="text",
            body=rights.full_text,
            source_kind=None,
            source_url=None,
            captured_at=None,
            edited_at=None,
            revision=None,
            reason="no_reader_html",
        )

    html_body, version, source_kind, source_url, captured_at, edited_at, revision = row
    if version != SANITIZER_VERSION:
        return ReaderHtmlResult(
            document_id=document_id,
            available=False,
            content_format="text",
            body=rights.full_text,
            source_kind=source_kind,
            source_url=source_url,
            captured_at=str(captured_at),
            edited_at=str(edited_at) if edited_at else None,
            revision=revision,
            reason="sanitizer_version_stale",
        )

    return ReaderHtmlResult(
        document_id=document_id,
        available=True,
        content_format="html",
        body=html_body,
        source_kind=source_kind,
        source_url=source_url,
        captured_at=str(captured_at),
        edited_at=str(edited_at) if edited_at else None,
        revision=revision,
        reason="ok",
    )


__all__ = [
    "MAX_READER_HTML_CHARS",
    "ReaderHtmlResult",
    "serve_reader_html",
    "store_reader_html",
]
