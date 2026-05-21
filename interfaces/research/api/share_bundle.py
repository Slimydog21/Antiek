"""Share-with-annotations bundle HTTP API (SPR-10 / M5).

FastAPI route handler for:

  POST /api/library/share-bundle — given a document_id, return a streamed
                                   zip containing <title>.pdf +
                                   <title>.antiek (sidecar). The
                                   recipient drops the zip into the
                                   library; SPR-10's sidecar_detector
                                   picks up the pair on ingest and
                                   restores user data.

Depends on the ``documents.raw_bytes_path`` column added by
substrate/graph/migrations/0001 (2026-05-22 follow-up). If a document
row has no raw_bytes_path or the file is missing, the endpoint returns
404 with the actionable error rather than producing a corrupt bundle.

Audio bytes: ``build_sidecar_input_for_document`` already handles the
absence-of-audio-storage gap; voice-note rows without
``content_json.audio_blob_path`` (none today) produce a sidecar with
transcript-only voice blocks. That's the honest state until the audio
substrate lands.
"""

from __future__ import annotations

import hashlib
import io
import os
import sys
import zipfile
from typing import Optional

import duckdb
from fastapi import FastAPI, HTTPException, Response, status
from pydantic import BaseModel, Field

_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

from services.antiek_format.sidecar_writer import (  # noqa: E402
    build_sidecar_input_for_document,
    write_sidecar,
)
from services.antiek_format.signature import ensure_keypair  # noqa: E402
from substrate.graph import default_db_path  # noqa: E402


class ShareBundleRequest(BaseModel):
    """Body for ``POST /api/library/share-bundle``."""

    document_id: str = Field(min_length=1)
    user_id: str = Field(min_length=1, default="__operator__")
    title_hint: Optional[str] = None


def _resolve_pdf_bytes(
    *, document_id: str, db_path: Optional[str],
) -> tuple[bytes, str]:
    """Return (pdf_bytes, filename_hint) for the document.

    Reads ``documents.raw_bytes_path`` (added by the 2026-05-22
    substrate migration) and slurps the file. Raises HTTPException
    on missing column / row / file.
    """
    path = db_path or default_db_path()
    with duckdb.connect(path) as con:
        row = con.execute(
            "SELECT raw_bytes_path, title, source_uri "
            "FROM documents WHERE document_id = ?",
            [document_id],
        ).fetchone()
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "document_not_found", "message": document_id}},
        )
    raw_path, title, source_uri = row[0], row[1], row[2]
    if not raw_path:
        raise HTTPException(
            status_code=409,
            detail={
                "error": {
                    "code": "raw_bytes_path_missing",
                    "message": (
                        f"Document {document_id} has no raw_bytes_path. "
                        "The share-bundle endpoint requires the original "
                        "bytes; populate documents.raw_bytes_path on "
                        "ingest (the column landed 2026-05-22). "
                        "If the document was ingested before the "
                        "migration, the operator needs to backfill."
                    ),
                },
            },
        )
    if not os.path.exists(raw_path):
        raise HTTPException(
            status_code=410,
            detail={
                "error": {
                    "code": "raw_bytes_file_missing",
                    "message": (
                        f"Document {document_id} references "
                        f"{raw_path!r} but the file is gone."
                    ),
                },
            },
        )
    with open(raw_path, "rb") as f:
        pdf_bytes = f.read()
    filename_hint = (
        title
        or (os.path.basename(source_uri) if source_uri else None)
        or document_id
    )
    if not filename_hint.endswith(".pdf"):
        filename_hint = filename_hint + ".pdf"
    return pdf_bytes, filename_hint


def register_share_bundle_routes(
    app: FastAPI,
    *,
    db_path: Optional[str] = None,
) -> None:
    """Mount the share-bundle route on ``app``."""

    @app.post(
        "/api/library/share-bundle",
        tags=["library"],
    )
    async def post_share_bundle(body: ShareBundleRequest) -> Response:
        pdf_bytes, filename_hint = _resolve_pdf_bytes(
            document_id=body.document_id, db_path=db_path,
        )

        # Build the sidecar input from substrate rows. The factory is
        # honest about absent audio-blob storage (transcript-only) and
        # absent user-asserted-edges table (empty edges).
        sidecar_input = build_sidecar_input_for_document(
            document_id=body.document_id,
            user_id=body.user_id,
            parent_pdf_bytes=pdf_bytes,
            parent_pdf_filename_hint=filename_hint,
            title=body.title_hint,
            db_path=db_path,
        )

        keypair = ensure_keypair(user_id=body.user_id, db_path=db_path)
        sidecar_bytes = write_sidecar(sidecar_input, keypair=keypair)

        # Bundle PDF + sidecar in a zip. The recipient drops the zip
        # in the library; SPR-10's parse_zip_upload detects the pair
        # and applies the sidecar after ingest.
        bundle = io.BytesIO()
        with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_STORED) as zf:
            base = os.path.splitext(filename_hint)[0]
            zf.writestr(filename_hint, pdf_bytes)
            zf.writestr(f"{base}.antiek", sidecar_bytes)

        # The recipient's hash check uses the bundled PDF — compute it
        # here for completeness in the response header.
        pdf_sha256 = hashlib.sha256(pdf_bytes).hexdigest()
        return Response(
            content=bundle.getvalue(),
            media_type="application/zip",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="{base}-with-annotations.zip"'
                ),
                "X-Parent-PDF-SHA256": pdf_sha256,
            },
        )
