"""POST /ingest/asset — document asset → canonical HTML sidecar (doc→HTML S-D2H).

Owner-scoped endpoint that accepts a document (multipart file OR source_url)
and ingests it as sanitized canonical HTML through the same trusted
version-provenance sidecar the URL and upload lanes write.

Fair-use gate: acquisition from known non-fair-use sources is REFUSED.
Memory hook: writes one MemoryItem after successful ingest (best-effort).
"""

from __future__ import annotations

import contextlib
import os
import tempfile
from typing import Any, Final, Literal

import httpx
from fastapi import APIRouter, FastAPI, File, Form, HTTPException, Request, UploadFile, status
from pydantic import BaseModel, Field, field_validator
from starlette.concurrency import run_in_threadpool

from acquisition.doc_to_html.ssrf import _MAX_REDIRECTS, SsrfError, validate_public_http_url
from services.demand_gate.roundtrip_detector import ExportRegistry

from .account_memory_identity import distinct_signed_owner


async def _download_public(url: str) -> bytes:
    """Download a public http(s) URL with per-hop SSRF validation.

    Redirects are followed manually (max {_MAX_REDIRECTS}) and each hop is
    re-validated — a redirect to loopback/internal is refused, not followed.
    """
    current = url
    for _ in range(_MAX_REDIRECTS + 1):
        validate_public_http_url(current)
        async with httpx.AsyncClient(
            timeout=_DOWNLOAD_TIMEOUT_SECONDS,
            follow_redirects=False,
        ) as client:
            # Per-call timeout is load-bearing for the SPR-03 lint (client-
            # level timeout does not satisfy no_unbounded_external_call) and
            # semantically per-hop: each redirect hop gets its own 30s bound.
            resp = await client.get(current, timeout=_DOWNLOAD_TIMEOUT_SECONDS)
        if resp.status_code in (301, 302, 303, 307, 308):
            location = resp.headers.get("location")
            if not location:
                raise httpx.HTTPError("redirect without location")
            current = str(httpx.URL(current).join(location))
            continue
        resp.raise_for_status()
        return resp.content
    raise httpx.HTTPError("too many redirects")


doc_ingest_router = APIRouter(prefix="/ingest", tags=["ingest"])

# Maximum file size for uploads (64 MB)
_MAX_UPLOAD_BYTES = 64 * 1024 * 1024

# Maximum URL download size (64 MB)
_MAX_DOWNLOAD_BYTES = 64 * 1024 * 1024

# Download timeout
_DOWNLOAD_TIMEOUT_SECONDS = 30.0


def _owner(request: Request) -> str:
    """Resolve the authenticated owner. Mirrors account_memory_routes._owner."""
    owner = distinct_signed_owner(request)
    if owner is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="signed owner identity required",
        )
    return owner


class AssetIngestRequest(BaseModel):
    """POST body when ingesting by source_url (JSON mode)."""

    source_url: str = Field(..., min_length=8, max_length=2048)
    kind: str | None = Field(default=None, max_length=32)
    fair_use_class: Literal["public", "licensed", "personal"] = "personal"
    license_note: str | None = Field(default=None, max_length=1024)

    @field_validator("source_url")
    @classmethod
    def _strip_url(cls, v: str) -> str:
        return v.strip()


class ProvenanceResponse(BaseModel):
    """Provenance metadata returned in the ingest response."""

    original_format: str
    source_url: str
    fetched_at: str
    fair_use_class: str
    license_note: str | None = None


class AssetIngestResponse(BaseModel):
    """What POST /ingest/asset returns."""

    document_id: str
    reader_html_url: str
    provenance: ProvenanceResponse


def _detect_kind(filename: str | None, content_type: str | None) -> str:
    """Detect the document kind from filename or content type."""
    if filename and "." in filename:
        return filename.rsplit(".", 1)[1].lower()
    if content_type:
        ct = content_type.partition(";")[0].strip().lower()
        mapping = {
            "application/pdf": "pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
            "application/epub+zip": "epub",
            "text/html": "html",
            "text/markdown": "md",
            "text/plain": "txt",
        }
        if ct in mapping:
            return mapping[ct]
    return "txt"


def _ext_from_url(url: str) -> str | None:
    """Extract file extension from URL path."""
    try:
        from urllib.parse import urlsplit
        parts = urlsplit(url)
        path = parts.path
        if "." in path:
            return path.rsplit(".", 1)[1].lower()
    except Exception:
        pass
    return None


@doc_ingest_router.post(
    "/asset",
    response_model=AssetIngestResponse,
    status_code=status.HTTP_201_CREATED,
)
async def ingest_asset_route(
    request: Request,
    file: UploadFile | None = File(default=None),
    source_url: str | None = Form(default=None),
    kind: str | None = Form(default=None),
    fair_use_class: str = Form(default="personal"),
    license_note: str | None = Form(default=None),
) -> AssetIngestResponse:
    """Ingest a document asset as canonical HTML.

    Accepts EITHER:
    - A multipart file upload (file parameter)
    - A source_url (multipart form field)

    The fair_use_class must be set explicitly (public|licensed|personal).
    """
    owner = _owner(request)

    # Validate fair_use_class
    if fair_use_class not in ("public", "licensed", "personal"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="fair_use_class must be one of: public, licensed, personal",
        )

    from acquisition.doc_to_html import (
        ConversionError,
        FairUseError,
        ingest_asset,
    )

    tmp_path: str | None = None
    try:
        if file is not None:
            # File upload mode
            file_bytes = await file.read(_MAX_UPLOAD_BYTES + 1)
            if len(file_bytes) > _MAX_UPLOAD_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail=f"upload exceeds {_MAX_UPLOAD_BYTES} byte limit",
                )
            if not file_bytes:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="file body must not be empty",
                )

            # Write to temp file for the conversion pipeline
            detected_kind = kind or _detect_kind(file.filename, file.content_type)
            fd, tmp_path = tempfile.mkstemp(suffix=f".{detected_kind}")
            try:
                os.write(fd, file_bytes)
            finally:
                os.close(fd)

            effective_source_url = source_url or file.filename or "uploaded-file"
            result = ingest_asset(
                source_uri=effective_source_url,
                bytes_path=tmp_path,
                kind=detected_kind,
                provenance={
                    "fair_use_class": fair_use_class,
                    "license_note": license_note,
                    "source_url": effective_source_url,
                },
                owner_user_id=owner,
            )

        elif source_url is not None:
            # URL download mode (form field)
            source_url = source_url.strip()
            if not source_url:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="source_url must not be empty",
                )

            # Check fair-use BEFORE downloading (save bandwidth + fast feedback)
            try:
                from acquisition.doc_to_html.converter import FairUseError, _check_fair_use
                _check_fair_use({
                    "fair_use_class": fair_use_class,
                    "source_url": source_url,
                })
            except FairUseError as exc:
                raise HTTPException(
                    status_code=status.HTTP_451_UNAVAILABLE_FOR_LEGAL_REASONS,
                    detail=str(exc),
                ) from exc

            # Download the file — every hop SSRF-validated (CWE-918)
            try:
                file_bytes = await _download_public(source_url)
            except SsrfError as exc:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail=str(exc),
                ) from exc
            except httpx.HTTPError as exc:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail=f"failed to download source: {exc}",
                ) from exc

            if len(file_bytes) > _MAX_DOWNLOAD_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail=f"download exceeds {_MAX_DOWNLOAD_BYTES} byte limit",
                )

            # Detect kind from URL or content type
            detected_kind = kind or _ext_from_url(source_url) or "txt"
            fd, tmp_path = tempfile.mkstemp(suffix=f".{detected_kind}")
            try:
                os.write(fd, file_bytes)
            finally:
                os.close(fd)

            result = ingest_asset(
                source_uri=source_url,
                bytes_path=tmp_path,
                kind=detected_kind,
                provenance={
                    "fair_use_class": fair_use_class,
                    "license_note": license_note,
                    "source_url": source_url,
                },
                owner_user_id=owner,
            )

        else:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="either file or source_url must be provided",
            )

    except FairUseError as exc:
        raise HTTPException(
            status_code=status.HTTP_451_UNAVAILABLE_FOR_LEGAL_REASONS,
            detail=str(exc),
        ) from exc
    except ConversionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"conversion failed: {exc}",
        ) from exc
    finally:
        # Clean up temp file
        if tmp_path and os.path.exists(tmp_path):
            with contextlib.suppress(OSError):
                os.unlink(tmp_path)

    return AssetIngestResponse(
        document_id=result["document_id"],
        reader_html_url=result["reader_html_url"],
        provenance=ProvenanceResponse(**result["provenance"]),
    )


# ── POST /ingest/antiek — the `.antiek` return leg (HPRJ SPR-4) ──
#
# The export half ships three signed formats. Until this route existed the
# import half was a library with no caller: an artifact could leave Antiek and
# never come home, which is most of the argument for having a signed container
# at all.
#
# WHAT A VALID SIGNATURE DOES AND DOES NOT PROVE. Both verifiers check the
# artifact against the public key the artifact itself carries, so a signature
# that verifies proves the bytes are internally consistent — nobody edited a
# signed file — and proves nothing whatsoever about who signed it. Authorship is
# established by the round-trip classification instead: a document_id and
# content hash that match what Antiek exported. That distinction decides the
# rights class below, and conflating the two would be the §9.0 leak.


class AntiekIngestResponse(BaseModel):
    """What POST /ingest/antiek returns for an artifact that came home."""

    document_id: str
    reader_html_url: str
    render_url: str
    title: str | None = None
    content_class: str
    # "returned_unmodified" | "traveled_and_changed" | None when this instance
    # has no record of exporting the document.
    roundtrip: str | None = None


class _SubstrateExportRegistry(ExportRegistry):
    """An ExportRegistry that answers from the substrate rather than memory.

    ``ExportRegistry`` is an in-memory ledger of "what did Antiek export", and
    nothing in the tree ever populated one outside a test, so a route that
    handed ``ingest_antiek`` a bare registry would classify every returning
    artifact as untracked and the round-trip signal would be dead on arrival —
    the same has-no-caller defect this lane exists to fix, one layer down.

    Exports are reproducible, so the ledger does not have to be stored: the
    export route builds its ``ExportItem`` from the notebook rows, and
    ``notebook_export_item`` is now the one place that shape lives, so asking
    "what would we export for this document today?" is a read away. Lookups are
    lazy because ``ingest_antiek`` learns the document_id only after it has
    parsed and verified the artifact.

    The honest limit: this compares against what Antiek would export NOW. A
    notebook edited in place after its artifact left will classify that
    artifact's unmodified return as ``traveled_and_changed``. The classification
    stays truthful about the content ("these bytes are not our current
    content") and loses the ability to say which side moved. Recording export
    hashes at emit time is what would close that, and it needs a durable ledger
    this lane does not own.
    """

    def __init__(self, db_path: str) -> None:
        super().__init__()
        self._db_path = db_path
        self._loaded: set[str] = set()

    def _load(self, document_id: str) -> None:
        if document_id in self._loaded:
            return
        self._loaded.add(document_id)
        notebook_id = _notebook_id_for_document(document_id, self._db_path)
        if notebook_id is None:
            return
        from .notebook_artifact import notebook_export_item, resolve_notebook_export

        source = resolve_notebook_export(notebook_id, db_path=self._db_path)
        if source is None:
            return
        item = notebook_export_item(source, notebook_id)
        self.record_export(item.document_id, item.content_tiptap)

    def knows_document(self, document_id: str) -> bool:
        self._load(document_id)
        return super().knows_document(document_id)

    def knows_exact(self, document_id: str, hash_: str) -> bool:
        self._load(document_id)
        return super().knows_exact(document_id, hash_)


def _notebook_id_for_document(document_id: str, db_path: str) -> str | None:
    """The notebook an exported document_id came from, or None.

    ``resolve_notebook_export`` falls back to the notebook_id when a notebook
    has no bound document, so an exported artifact's document_id is either the
    ``notebooks.document_id`` binding or the notebook_id itself. Both are
    checked, bound column first.
    """
    from runtime.db_lock import connect_read

    con = connect_read(db_path)
    try:
        row = con.execute(
            "SELECT notebook_id FROM notebooks WHERE document_id = ? LIMIT 1",
            [document_id],
        ).fetchone()
        if row is not None:
            return str(row[0])
        row = con.execute(
            "SELECT notebook_id FROM notebooks WHERE notebook_id = ? LIMIT 1",
            [document_id],
        ).fetchone()
        return str(row[0]) if row is not None else None
    except Exception:  # pragma: no cover — a missing notebooks table is not
        # an ingest failure; it only means nothing can be classified.
        return None
    finally:
        con.close()


ANTIEK_SOURCE_KIND: Final[str] = "antiek"
ANTIEK_DOCUMENT_TYPE: Final[str] = "antiek_artifact"


def _claimed_id_is_free_or_ours(document_id: str, db_path: str) -> bool:
    """Whether the return leg may write under the id an artifact claims.

    The return leg must never take over a document some other lane wrote. A
    notebook can be BOUND to a document (``notebooks.document_id``), and the
    export path stamps that binding into the manifest, so a wrestle notebook
    attached to a book exports an artifact whose claimed document_id is the
    BOOK's. Honouring the claim would replace the book's reader body with the
    notebook's prose — served under the book's title, its provenance footer and
    its rights class, silently and with no way back.

    BOTH tables have to be asked, because a document and its reader body are
    written separately and a document routinely exists before its reader HTML
    does. Asking only the sidecar reads a book that has not been projected yet
    as "nothing is there", which is the loudest version of exactly the clobber
    this guard exists to refuse. So the claim is honoured only when the id is
    unoccupied in both tables, or when this route is what occupies it — which
    keeps a second import of the same artifact idempotent instead of minting a
    duplicate.
    """
    from runtime.db_lock import connect_read

    con = connect_read(db_path)
    try:
        row = con.execute(
            "SELECT document_type FROM documents WHERE document_id = ?",
            [document_id],
        ).fetchone()
        if row is not None and str(row[0]) != ANTIEK_DOCUMENT_TYPE:
            return False
        row = con.execute(
            "SELECT source_kind FROM document_reader_html WHERE document_id = ?",
            [document_id],
        ).fetchone()
        return row is None or row[0] is None or str(row[0]) == ANTIEK_SOURCE_KIND
    except Exception:  # pragma: no cover — schema drift, not an ingest failure.
        # Fail closed. A guard that cannot read the tables cannot say the id is
        # free, and refusing costs only a minted id on the personal_reading
        # lane, where every unproven artifact lands anyway.
        return False
    finally:
        con.close()


def _antiek_db_path() -> str:
    from substrate.graph import default_db_path, ensure_initialized

    path = str(default_db_path())
    ensure_initialized(path)
    return path


def _doc_model_content(doc_model: dict[str, Any]) -> list[Any]:
    """The top-level node array, whichever doc-model shape arrived.

    A container hands back the TipTap document (``{"type": "doc", "content":
    [...]}``); a single-file island hands back the projection doc-model
    (``{"content": [...], "title": ...}``). Both keep the nodes under
    ``content``, which is the only field the renderer needs.
    """
    content = doc_model.get("content")
    return content if isinstance(content, list) else []


def _plain_text(nodes: list[Any]) -> str:
    """Flatten the doc-model's text nodes for the document's ``raw_text``.

    The substrate stores a text representation next to every document; a
    returning artifact that stored none would be invisible to search while
    appearing ingested. Structure is deliberately dropped here — the structured
    payload survives as the doc-model the projection renders, and this is the
    plain reading of it, not a second source of truth.
    """
    out: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, str):
            out.append(node)
            return
        if not isinstance(node, dict):
            return
        text = node.get("text")
        if isinstance(text, str):
            out.append(text)
        children = node.get("content")
        if isinstance(children, list):
            for child in children:
                walk(child)

    for node in nodes:
        walk(node)
        out.append("\n")
    return "".join(out).strip()


def _minted_document_id(doc_model: dict[str, Any]) -> str:
    """A content-derived id for an artifact that cannot prove where it is from.

    Derived from the canonical content hash — the same canonicalisation the
    `.antiek` signature covers — so re-uploading the same artifact lands on the
    same row instead of accumulating duplicates, and so an id can never be
    steered by whatever the uploaded manifest claims.
    """
    from services.demand_gate.roundtrip_detector import content_hash

    return f"doc-antiek-{content_hash(doc_model)[:16]}"


@doc_ingest_router.post(
    "/antiek",
    response_model=AntiekIngestResponse,
    status_code=status.HTTP_201_CREATED,
)
async def ingest_antiek_route(
    request: Request,
    file: UploadFile = File(...),
) -> AntiekIngestResponse:
    """Bring a born-Antiek artifact home.

    Accepts a `.antiek` container or a signed single-file `.antiek.html`, reads
    ONLY the signed structured doc-model (the rendered markup is never parsed
    for content), and stores it as a document the reader and the style wheel can
    open. A quarantined artifact is refused with its typed reason and is never
    rendered.
    """
    owner = _owner(request)

    data = await file.read(_MAX_UPLOAD_BYTES + 1)
    if len(data) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"upload exceeds {_MAX_UPLOAD_BYTES} byte limit",
        )
    if not data:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="file body must not be empty",
        )

    def _ingest_and_store() -> AntiekIngestResponse:
        # Everything below takes the DuckDB write lock or blocks on a read, so
        # it runs in a worker thread: connect_write polls with time.sleep, and
        # the single uvicorn worker would stop serving for the whole wait.
        from runtime.db_lock import WriteLockTimeout, connect_write
        from services.html_projection.context import RenderContext
        from services.html_projection.renderer import render_block
        from services.ingestion.ingest_antiek import (
            DISPOSITION_MALFORMED,
            ingest_antiek,
            quarantine_disposition,
        )
        from substrate.books.html_sanitizer import strip_trust_markers
        from substrate.constants import PERSONAL_READING_CONTENT_CLASS
        from substrate.graph.ops import insert_document
        from substrate.reader_html.store import store_reader_html

        db_path = _antiek_db_path()
        result = ingest_antiek(data, export_registry=_SubstrateExportRegistry(db_path))

        if result.quarantined or not result.ok or result.doc_model is None:
            # A dict detail, where this module's other refusals use a string.
            # The classification IS the product here: a caller has to act
            # differently on a tampered artifact than on a malformed one, and a
            # sentence it has to parse would make that a guess.
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={
                    "error": "quarantined",
                    "disposition": (
                        quarantine_disposition(result.reason_code)
                        if result.quarantined
                        else DISPOSITION_MALFORMED
                    ),
                    "reason_code": result.reason_code,
                    "reason": result.reason,
                },
            )

        content = _doc_model_content(result.doc_model)

        # WHICH DOCUMENT THIS BECOMES, AND UNDER WHICH RIGHTS CLASS.
        #
        # A signature verifies against the key the artifact carries, so it says
        # "nobody edited these bytes", not "Antiek made this". Only
        # `returned_unmodified` says the second thing: the document_id AND the
        # canonical content hash match what this instance exports for that
        # document, so the body is the one Antiek would emit today. That earns
        # `user_owned` — and it still does not, on its own, earn the claimed
        # id. A bound notebook exports under the BOUND DOCUMENT's id, so
        # "matches what we export for this id" and "is what this id already
        # holds" are different sentences; `_claimed_id_is_free_or_ours` is what
        # checks the second one.
        #
        # Everything else, `traveled_and_changed` included, carries content this
        # instance did not produce, whatever id the manifest claims. It lands on
        # a content-derived id so an upload can never overwrite an existing
        # document's reader body, and as `personal_reading`: owner-readable,
        # never publicly servable, never earning. That is the §9.0 discipline —
        # an uploaded body reaching the monetized read path because it asserted
        # an id is exactly the leak the rights states exist to prevent.
        returned_home = (
            result.roundtrip == "returned_unmodified"
            and result.document_id is not None
            and _claimed_id_is_free_or_ours(result.document_id, db_path)
        )
        if returned_home and result.document_id is not None:
            document_id = result.document_id
            content_class = "user_owned"
        else:
            document_id = _minted_document_id(result.doc_model)
            content_class = PERSONAL_READING_CONTENT_CLASS

        ctx = RenderContext()
        body_html = "".join(render_block(node, ctx) for node in content)
        raw_text = _plain_text(content)

        metadata = strip_trust_markers(
            {
                "source": "ingest_antiek",
                "artifact_format": (
                    "antiek_container" if data[:2] == b"PK" else "antiek_single_file"
                ),
                "roundtrip": result.roundtrip,
                # What the artifact SAID it was, kept separately from the id it
                # was given, so a claim is never mistaken for a fact.
                "claimed_document_id": result.document_id,
                "signature_verified": True,
            }
        )

        def _sync() -> None:
            with connect_write(db_path, purpose="ingest/antiek") as con:
                insert_document(
                    con,
                    document_id=document_id,
                    source_tier=2,
                    document_type=ANTIEK_DOCUMENT_TYPE,
                    source_uri=f"antiek://{document_id}",
                    title=result.title,
                    raw_text=raw_text,
                    metadata=metadata,
                    content_class=content_class,
                    owner_user_id=owner,
                    # An artifact that comes home twice must not rewrite the
                    # rights class the document already carries.
                    on_conflict="ignore",
                )
                store_reader_html(
                    con,
                    document_id=document_id,
                    main_html=body_html,
                    source_kind=ANTIEK_SOURCE_KIND,
                    source_url=None,
                )

        try:
            _sync()
        except WriteLockTimeout as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="write lock unavailable; retry",
            ) from exc

        return AntiekIngestResponse(
            document_id=document_id,
            reader_html_url=f"/sources/{document_id}/reader-html",
            render_url=f"/documents/{document_id}/render",
            title=result.title,
            content_class=content_class,
            roundtrip=result.roundtrip,
        )

    # flock wait + the substrate reads off the uvicorn loop.
    return await run_in_threadpool(_ingest_and_store)


__all__ = [
    "AntiekIngestResponse",
    "doc_ingest_router",
    "register_doc_ingest_routes",
]


def register_doc_ingest_routes(app: FastAPI) -> None:
    """Mount the doc ingest routes. Mirrors register_reader_html_routes."""
    app.include_router(doc_ingest_router)
