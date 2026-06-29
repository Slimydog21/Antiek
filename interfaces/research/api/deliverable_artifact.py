"""Deliverable artifact export route (HPRJ SPR-06) — the Write surface.

``GET /api/deliverables/{deliverable_id}/artifact?format=html|antiek|antiek_html``
— exports a Write deliverable as a portable, signed, rights-safe artifact,
mirroring the synthesis + notebook routes. The rights filter lives in
``adapt_deliverable`` (cite-only on any non-servable block, reusing
SERVABLE_CONTENT_CLASSES); the routing map emits the format.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, Response

from services.html_projection.adapters.deliverable import (
    DeliverableBlock,
    DeliverableExport,
    DeliverableSection,
    adapt_deliverable,
)
from services.html_projection.context import RenderContext
from services.html_projection.gate import ScriptViolation, assert_script_free
from services.html_projection.renderer import render
from services.html_projection.routing_map import EXPORT_FORMATS, ExportItem, emit

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class DeliverableExportSource:
    export: DeliverableExport
    owner_user_id: str
    document_id: str


def _resolve_db_path() -> str:
    from substrate.graph import default_db_path, ensure_initialized

    path = default_db_path()
    ensure_initialized(path)
    return path


def resolve_deliverable_export(
    deliverable_id: str, *, db_path: Optional[str] = None
) -> Optional[DeliverableExportSource]:
    """Read a deliverable into a DeliverableExportSource, or None if absent.

    The operator-authored section prose (``deliverable_sections.prose_text``,
    user-owned -> servable) exports faithfully as a ``synthesized`` block.

    NOTE (rigor #1): the ``section_blocks`` references (insight/open_question/
    operator_note/claim -> the substrate row's text + the source's
    content_class/ip_holder) are NOT resolved here — 0 local deliverable rows to
    validate against, and asserting a resolver works on unseen data is the
    dishonesty the rigor forbids. They are omitted (not faked); the prose
    carries the content. When the substrate resolution lands, append resolved
    DeliverableBlocks with their real content_class — ``adapt_deliverable``
    already cite-only's any non-servable block.
    """
    from runtime.db_lock import connect_read

    db = db_path or _resolve_db_path()
    con = connect_read(db)
    try:
        row = con.execute(
            "SELECT deliverable_id, title, owner_user_id FROM deliverables "
            "WHERE deliverable_id = ?",
            [deliverable_id],
        ).fetchone()
        if row is None:
            return None
        section_rows = con.execute(
            "SELECT title, prose_text FROM deliverable_sections "
            "WHERE deliverable_id = ? ORDER BY section_index",
            [deliverable_id],
        ).fetchall()
    finally:
        con.close()

    sections = []
    for stitle, prose in section_rows:
        blocks = []
        if prose:
            # Operator-authored synthesized prose — user-owned, servable.
            blocks.append(
                DeliverableBlock(block_kind="synthesized", text=prose, content_class=None)
            )
        sections.append(DeliverableSection(heading=stitle or "", blocks=blocks))

    return DeliverableExportSource(
        export=DeliverableExport(title=row[1], sections=sections),
        owner_user_id=row[2] or "__operator__",
        document_id=deliverable_id,
    )


def register_deliverable_artifact_routes(app: FastAPI) -> None:
    """Mount ``GET /api/deliverables/{id}/artifact``. One call from create_app."""

    @app.get("/api/deliverables/{deliverable_id}/artifact", tags=["deliverables"])
    async def deliverable_artifact(deliverable_id: str, format: str = "html"):
        source = resolve_deliverable_export(deliverable_id)
        if source is None:
            raise HTTPException(
                status_code=404, detail=f"deliverable {deliverable_id!r} not found"
            )
        if format not in EXPORT_FORMATS:
            raise HTTPException(
                status_code=400,
                detail=f"unknown format {format!r}; valid: {list(EXPORT_FORMATS)}",
            )
        doc_model = adapt_deliverable(source.export)

        if format == "html":
            html = render(doc_model, RenderContext())
            try:
                assert_script_free(html)
            except ScriptViolation:
                raise HTTPException(
                    status_code=500,
                    detail="artifact failed the zero-script gate; refused",
                )
            return HTMLResponse(
                content=html,
                headers={
                    "Content-Disposition": (
                        f'attachment; filename="deliverable-{deliverable_id}.html"'
                    )
                },
            )

        from services.antiek_format.signature import ensure_keypair

        keypair = ensure_keypair(source.owner_user_id, db_path=_resolve_db_path())
        item = ExportItem(
            content_tiptap={"type": "doc", "content": doc_model.get("content", [])},
            title=source.export.title,
            document_id=source.document_id,
            user_id=source.owner_user_id,
            notebook_id=deliverable_id,
            content_class="deliverable",
        )
        artifact = emit(item, format, keypair=keypair)
        if format == "antiek":
            return Response(
                content=artifact,
                media_type="application/zip",
                headers={
                    "Content-Disposition": (
                        f'attachment; filename="deliverable-{deliverable_id}.antiek"'
                    )
                },
            )
        return HTMLResponse(
            content=artifact,
            headers={
                "Content-Disposition": (
                    f'attachment; filename="deliverable-{deliverable_id}.antiek.html"'
                )
            },
        )


__all__ = [
    "DeliverableExportSource",
    "register_deliverable_artifact_routes",
    "resolve_deliverable_export",
]
