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
from typing import Literal

import httpx
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile, status
from pydantic import BaseModel, Field, field_validator

from acquisition.doc_to_html.ssrf import _MAX_REDIRECTS, SsrfError, validate_public_http_url

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
            resp = await client.get(current)
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


__all__ = ["doc_ingest_router", "register_doc_ingest_routes"]


def register_doc_ingest_routes(app) -> None:
    """Mount the doc ingest routes. Mirrors register_reader_html_routes."""
    app.include_router(doc_ingest_router)
