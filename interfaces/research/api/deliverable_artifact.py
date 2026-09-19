"""Deliverable artifact export route (HPRJ SPR-06) — the Write surface.

``GET /api/deliverables/{deliverable_id}/artifact.html`` — browser-inline,
script-free HTML projection (daily-use View HTML).

``GET /api/deliverables/{deliverable_id}/artifact?format=html|antiek|antiek_html``
— download / signed export (``format=html`` stays ``attachment``).

Rights filter lives in ``adapt_deliverable`` (cite-only on non-servable blocks);
zero-script gate runs in the route path.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, Response

from services.html_projection.adapters.deliverable import (
    DeliverableBlock,
    DeliverableExport,
    DeliverableSection,
    adapt_deliverable,
)
from substrate.contracts.anti_ek_honesty import html_projection_response_headers
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
    deliverable_id: str, *, db_path: str | None = None
) -> DeliverableExportSource | None:
    """Read a deliverable into a DeliverableExportSource, or None if absent.

    The operator-authored section prose (``deliverable_sections.prose_text``,
    user-owned -> servable) exports as a ``synthesized`` block. Each section's
    ``section_blocks`` refs (insight/open_question/operator_note/claim) are
    resolved against the substrate via ``resolve_refs`` -> the unit's text + the
    source document's content_class/ip_holder -> a ``DeliverableBlock``;
    ``adapt_deliverable`` cite-only's any non-servable block. A ref the graph
    cannot resolve is omitted (honest, not faked).
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
            "SELECT section_id, title, prose_text FROM deliverable_sections "
            "WHERE deliverable_id = ? ORDER BY section_index",
            [deliverable_id],
        ).fetchall()
        block_refs = {}
        for sid, _stitle, _prose in section_rows:
            block_refs[sid] = con.execute(
                "SELECT block_kind, block_id FROM section_blocks "
                "WHERE section_id = ? ORDER BY block_index",
                [sid],
            ).fetchall()
    finally:
        con.close()

    # Resolve every referenced block_id against the substrate in one pass.
    from services.html_projection.resolvers.substrate_refs import resolve_refs

    all_block_ids = [bid for refs in block_refs.values() for (_kind, bid) in refs]
    resolved = resolve_refs(all_block_ids, db_path=db) if all_block_ids else {}

    sections = []
    for sid, stitle, prose in section_rows:
        blocks = []
        if prose:
            # Operator-authored synthesized prose — user-owned, servable.
            blocks.append(
                DeliverableBlock(block_kind="synthesized", text=prose, content_class=None)
            )
        for block_kind, block_id in block_refs.get(sid, []):
            rr = resolved.get(block_id)
            if rr is None:
                continue  # unresolvable ref omitted (honest)
            text = (
                rr.payload.get("statement")
                or rr.payload.get("text")
                or rr.payload.get("body")
                or ""
            )
            blocks.append(
                DeliverableBlock(
                    block_kind=block_kind,
                    text=text,
                    content_class=rr.content_class,
                    ip_holder_id=rr.ip_holder_id,
                    source_title=rr.title,
                    source_document_id=rr.source_document_id,
                )
            )
        sections.append(DeliverableSection(heading=stitle or "", blocks=blocks))

    return DeliverableExportSource(
        export=DeliverableExport(title=row[1], sections=sections),
        owner_user_id=row[2] or "__operator__",
        document_id=deliverable_id,
    )



def _script_free_html(html: str) -> str:
    """Refuse poisoned renders — never serve script-bearing HTML."""
    try:
        assert_script_free(html)
    except ScriptViolation as err:
        raise HTTPException(
            status_code=500,
            detail="artifact failed the zero-script gate; refused",
        ) from err
    return html


def _html_headers(*, filename: str, inline: bool) -> dict[str, str]:
    """Honest Content-Disposition + projection metadata (no fake trust bits)."""
    return html_projection_response_headers(
        filename=filename,
        disposition="inline" if inline else "attachment",
    )


def register_deliverable_artifact_routes(app: FastAPI) -> None:
    """Mount deliverable artifact view + export. One call from create_app."""

    def _render_html(source: DeliverableExportSource) -> str:
        return _script_free_html(render(adapt_deliverable(source.export), RenderContext()))

    @app.get(
        "/api/deliverables/{deliverable_id}/artifact.html",
        tags=["deliverables"],
    )
    async def deliverable_artifact_html(deliverable_id: str) -> Response:
        """Daily-use HTML-native view — inline, script-free (not a download)."""
        source = resolve_deliverable_export(deliverable_id)
        if source is None:
            raise HTTPException(
                status_code=404, detail=f"deliverable {deliverable_id!r} not found"
            )
        html = _render_html(source)
        return HTMLResponse(
            content=html,
            headers=_html_headers(
                filename=f"deliverable-{deliverable_id}.html", inline=True
            ),
        )

    @app.get("/api/deliverables/{deliverable_id}/artifact", tags=["deliverables"])
    async def deliverable_artifact(deliverable_id: str, format: str = "html") -> Response:
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
            html = _script_free_html(render(doc_model, RenderContext()))
            return HTMLResponse(
                content=html,
                headers=_html_headers(
                    filename=f"deliverable-{deliverable_id}.html", inline=False
                ),
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
