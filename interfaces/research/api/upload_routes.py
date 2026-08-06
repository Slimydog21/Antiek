"""POST /sources/upload — uploaded-document → sanitized reader-HTML (doc→HTML S4).

The upload lane: a user drops a document they already hold (PDF / HTML /
Markdown / text) and it becomes viewable in the reader as sanitized HTML — the
same trusted version-provenance sidecar the URL lane writes. It is the
Bartz-lawful-acquisition twin of URL ingest: instead of fetching, the caller
attests they lawfully hold the file (``acquisition_attestation``) and supplies
the bytes.

CRITICAL invariant (the whole point of this lane — spec §3, FLEET-ALERT
compose-xss-recurring): the served body MUST pass the trusted allowlist
sanitizer (``substrate.books.html_sanitizer.sanitize_book_html``) before it is
ever stored. Storage goes ONLY through
``substrate.reader_html.store.store_reader_html``, which sanitizes INSIDE the
write and stamps ``SANITIZER_VERSION`` in the same INSERT — so no client HTML is
ever persisted as trusted. The document's ``raw_text`` for an HTML upload is
itself the sanitized body (never the raw upload). If a future caller needs to
store client HTML any other way, that is a BLOCKED, not a shortcut.

EPUB is refused with a typed 409 pointing at the authorized book-acquisition
ceremony — this lane does NOT fork that marketplace/transport decision (spec §3,
Bartz row 16). A PK-zip magic header is treated as EPUB for this purpose (magic
bytes win over extension).
"""

from __future__ import annotations

import hashlib
from typing import Literal

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel

from acquisition.books.reader import ReadResult, read_pdf
from acquisition.snapshot.reader_html import markdown_to_safe_html
from runtime.db_lock import connect_write
from substrate.books.html_sanitizer import sanitize_book_html, strip_trust_markers
from substrate.reader_html.store import store_reader_html

# Reuse the books-lane upload ceiling as the bounded-read cap (mirrors
# book_acquisition_routes.DEFAULT_MAX_EPUB_BYTES). General documents are not
# larger than EPUBs in practice; the cap is a DoS guard, not a format limit.
DEFAULT_MAX_UPLOAD_BYTES = 64 * 1024 * 1024

# The Bartz lawful-acquisition receipt values. Stored verbatim in document
# metadata; drive the deny-by-default content_class.
_ATTESTATIONS: tuple[str, ...] = ("user_owned", "personal_reading")

_EPUB_409_DETAIL = "EPUB goes through the authorized book-acquisition ceremony"

# document_reader_html.source_kind per upload kind — the spec's vocabulary
# ('upload_html' | 'upload_md' | 'upload_txt' | 'upload_pdf').
_SOURCE_KIND: dict[str, str] = {
    "pdf": "upload_pdf",
    "html": "upload_html",
    "md": "upload_md",
    "txt": "upload_txt",
}


class UploadResponse(BaseModel):
    """What ``POST /sources/upload`` returns.

    ``reader_html_available`` is True iff the sanitized sidecar was written
    with the exact current ``SANITIZER_VERSION`` — the reader-html serve gate
    then releases it as ``content_format="html"`` to an entitled reader (owner
    for ``personal_reading``; anyone for ``user_owned``). ``chunk_count`` is 0:
    this lane stores the document + sanitized reader body only; chunk/embedding
    ingestion is a separate lane (a named honest gap, not a silent 0).
    """

    document_id: str
    detected_kind: Literal["pdf", "html", "md", "txt"]
    reader_html_available: bool
    chunk_count: int


def _ext_of(filename: str | None) -> str:
    if filename and "." in filename:
        return filename.rsplit(".", 1)[1].lower()
    return ""


def sniff_kind(data: bytes, filename: str | None) -> str | None:
    """Detect the upload kind by MAGIC BYTES first, extension second.

    Returns one of ``'pdf' | 'html' | 'md' | 'txt' | 'epub'`` — ``'epub'`` is the
    PK-zip/EPUB signal the caller turns into the 409 ceremony redirect — or
    ``None`` when the type is unsupported. Exposed for unit tests so the
    magic-over-extension order is pinned independently of the HTTP path.
    """
    # Magic bytes first. %PDF- → pdf; the PK-zip local-file header → EPUB
    # ceremony (409); a leading '<' (after leading whitespace) → HTML.
    if data[:5].startswith(b"%PDF-"):
        return "pdf"
    if data[:4] == b"PK\x03\x04":
        return "epub"
    if data.lstrip()[:1] == b"<":
        return "html"
    # Extension second.
    ext = _ext_of(filename)
    if ext == "pdf":
        return "pdf"
    if ext in ("html", "htm"):
        return "html"
    if ext in ("md", "markdown"):
        return "md"
    if ext in ("txt", "text"):
        return "txt"
    if ext == "epub":
        return "epub"
    return None


def upload_doc_id(file_bytes: bytes) -> str:
    """Stable Antiek doc id for an upload: ``doc-upload-<sha256(bytes)[:16]>``.

    Re-uploading the same bytes dedups on the id (mirrors
    ``acquisition.books.adapter.book_doc_id``); ``insert_document`` is called
    with ``on_conflict="ignore"`` and ``store_reader_html`` upserts the sidecar,
    so a re-upload is idempotent.
    """
    if not file_bytes:
        raise ValueError("empty upload body")
    digest = hashlib.sha256(file_bytes).hexdigest()[:16]
    return f"doc-upload-{digest}"


def _content_class_for(attestation: str) -> str:
    """Map the Bartz attestation to the substrate ``content_class``.

    ``user_owned`` is publicly servable (in ``SERVABLE_CONTENT_CLASSES``);
    ``personal_reading`` is the owner-only lane (never publicly served — the
    default for uploads per spec §3 Bartz row 16).
    """
    if attestation == "user_owned":
        return "user_owned"
    return "personal_reading"


async def _read_bounded(file: UploadFile, *, max_bytes: int) -> bytes:
    """Read the upload body with a hard byte ceiling (DoS guard).

    Mirrors the bounded-read discipline of
    ``book_acquisition_routes._read_epub``: read one byte past the cap and
    refuse if the file is larger, so a huge upload cannot be buffered fully
    before rejection.
    """
    data = await file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"upload exceeds {max_bytes} byte limit",
        )
    if not data:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="file body must not be empty",
        )
    return data


def _convert_pdf(file_bytes: bytes) -> tuple[str, str, str | None, str | None]:
    """PDF → (raw_text, html_body, title, author) via the repo's PDF reader.

    ``raw_text`` is the chunker-ready markdown (``## Page N`` anchors, title /
    author metadata) that ``acquisition.books.reader.read_pdf`` produces;
    ``html_body`` is the escape-first markdown→HTML the sidecar stores. Both are
    safe inputs to ``store_reader_html`` (which sanitizes again — idempotent).
    """
    result: ReadResult = read_pdf(file_bytes)
    markdown = result.markdown or ""
    return markdown, markdown_to_safe_html(markdown), result.title, result.author


def _convert_markdown(text: str) -> tuple[str, str]:
    """Markdown/text → (raw_text, html_body).

    ``raw_text`` is the decoded text; ``html_body`` is the escape-first
    markdown→HTML (``markdown_to_safe_html`` html-escapes every line, so the
    output is a safe input to the sidecar sanitizer).
    """
    return text, markdown_to_safe_html(text)


def _convert_html(raw_html: str) -> tuple[str, str]:
    """HTML → (raw_text, html_body). BOTH are the allowlist-sanitized body.

    The brief's CRITICAL guardrail: uploaded HTML is NEVER stored raw/trusted.
    Sanitize once here for ``raw_text`` (so even the text fallback path never
    holds unsanitized client HTML); ``store_reader_html`` sanitizes again for
    the sidecar (an idempotent fixed point).
    """
    sanitized = sanitize_book_html(raw_html)
    return sanitized, sanitized


def register_upload_routes(app: FastAPI) -> None:
    """Mount ``POST /sources/upload``. Mirrors ``register_reader_html_routes`` —
    one call from ``create_app``."""

    @app.post(
        "/sources/upload",
        response_model=UploadResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["sources"],
    )
    async def upload_source(
        file: UploadFile = File(...),
        acquisition_attestation: str = Form(...),
        title: str | None = Form(None),
        source_url: str | None = Form(None),
    ) -> UploadResponse:
        if acquisition_attestation not in _ATTESTATIONS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=(
                    "acquisition_attestation must be one of: "
                    + ", ".join(_ATTESTATIONS)
                ),
            )

        file_bytes = await _read_bounded(file, max_bytes=DEFAULT_MAX_UPLOAD_BYTES)

        kind = sniff_kind(file_bytes, file.filename)
        if kind == "epub":
            # EPUB / PK-zip → the authorized book-acquisition ceremony owns this.
            # Do NOT fork that lane (spec §3, Bartz row 16).
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail=_EPUB_409_DETAIL
            )
        if kind is None:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="unsupported file type; upload PDF, HTML, Markdown, or text",
            )
        if kind not in ("pdf", "html", "md", "txt"):
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="unsupported file type; upload PDF, HTML, Markdown, or text",
            )
        # Here kind is narrowed to Literal["pdf", "html", "md", "txt"].

        raw_text: str
        html_body: str
        detected_kind: Literal["pdf", "html", "md", "txt"]
        author: str | None = None
        try:
            if kind == "pdf":
                detected_kind = "pdf"
                raw_text, html_body, pdf_title, author = _convert_pdf(file_bytes)
                title = title or pdf_title
            elif kind == "md":
                detected_kind = "md"
                decoded = file_bytes.decode("utf-8", errors="replace")
                raw_text, html_body = _convert_markdown(decoded)
            elif kind == "txt":
                detected_kind = "txt"
                decoded = file_bytes.decode("utf-8", errors="replace")
                raw_text, html_body = _convert_markdown(decoded)
            else:  # html
                detected_kind = "html"
                decoded = file_bytes.decode("utf-8", errors="replace")
                raw_text, html_body = _convert_html(decoded)
        except Exception as exc:  # corrupt PDF / decode failure → honest 422
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"could not convert upload: {type(exc).__name__}",
            ) from exc

        document_id = upload_doc_id(file_bytes)
        content_class = _content_class_for(acquisition_attestation)

        # I5: insert_document stamps twin_source_envelope (ops.py:224). metadata
        # is built from SERVER-controlled values only and still passes
        # strip_trust_markers (W2 mandatory) — a client can never relay a forged
        # content_sanitized bit through it. The §5.2 hazard is held: we do NOT
        # stamp sanitized_html_provenance() into documents.metadata (the sidecar
        # is the sole trust carrier for reader bodies); the books full-text
        # endpoint therefore keeps serving this doc as content_format="text".
        metadata = strip_trust_markers(
            {
                "source": "upload",
                "upload_kind": detected_kind,
                "acquisition_attestation": acquisition_attestation,
            }
        )

        from substrate.graph import default_db_path, ensure_initialized
        from substrate.graph.ops import insert_document

        db_path = default_db_path()
        ensure_initialized(db_path)

        with connect_write(db_path, purpose="sources/upload") as con:
            insert_document(
                con,
                document_id=document_id,
                source_tier=2,
                document_type="upload",
                source_uri=source_url,
                title=title,
                author=author,
                published_at=None,
                investigation_id=None,
                raw_text=raw_text,
                metadata=metadata,
                content_class=content_class,
                on_conflict="ignore",
            )
            # The ONLY writer for the reader-HTML sidecar. Sanitizes INSIDE the
            # call and stamps SANITIZER_VERSION in the same INSERT — the stored
            # body is version-provenance-trusted by construction.
            store_reader_html(
                con,
                document_id=document_id,
                main_html=html_body,
                source_kind=_SOURCE_KIND[detected_kind],
                source_url=source_url,
            )

        return UploadResponse(
            document_id=document_id,
            detected_kind=detected_kind,
            reader_html_available=True,
            chunk_count=0,
        )


__all__ = [
    "DEFAULT_MAX_UPLOAD_BYTES",
    "UploadResponse",
    "register_upload_routes",
    "sniff_kind",
    "upload_doc_id",
]
