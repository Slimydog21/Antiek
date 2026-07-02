"""Notebook artifact export route (HPRJ SPR-06).

``GET /api/notebooks/{notebook_id}/artifact?format=html|antiek|antiek_html`` —
exports a notebook (the Read surface) as a portable, signed, rights-safe
artifact, mirroring the synthesis export route. The rights filter lives in the
EXPORT adapter (`adapt_notebook_for_export`, which pre-resolves refs and
cite-only's non-servable sources); the routing map emits the format.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, Response

from services.html_projection.adapters.notebook import ResolvedRefData
from services.html_projection.adapters.notebook_export import adapt_notebook_for_export
from services.html_projection.context import RenderContext
from services.html_projection.gate import ScriptViolation, assert_script_free
from services.html_projection.renderer import render
from services.html_projection.routing_map import EXPORT_FORMATS, ExportItem, emit

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class NotebookExportSource:
    content_tiptap: dict
    title: str | None
    document_id: str
    owner_user_id: str
    content_class: str = "notebook"
    resolved_refs: dict = field(default_factory=dict)  # ref_id -> ResolvedRefData


def _resolve_db_path() -> str:
    from substrate.graph import default_db_path, ensure_initialized

    path = default_db_path()
    ensure_initialized(path)
    return path


def resolve_notebook_export(
    notebook_id: str, *, db_path: str | None = None
) -> NotebookExportSource | None:
    """Read a notebook into a NotebookExportSource, or None if it does not exist.

    The notebook's ref-bearing nodes (claim/insight/question) are resolved
    against the substrate via ``resolve_refs`` — each ref's text + the SOURCE
    document's content_class/ip_holder — and handed to the export adapter, which
    rights-filters (cite-only on non-servable). A ref the graph cannot resolve
    is omitted and exports as a visible '[... unavailable]' marker (honest, not
    faked). The notebook's own structure (prose, headings) always exports.
    """
    from runtime.db_lock import connect_read

    db = db_path or _resolve_db_path()
    con = connect_read(db)
    try:
        row = con.execute(
            "SELECT notebook_id, title, content_class, owner_user_id, document_id "
            "FROM notebooks WHERE notebook_id = ?",
            [notebook_id],
        ).fetchone()
        if row is None:
            return None
        block_rows = con.execute(
            "SELECT content_json FROM notebook_blocks "
            "WHERE notebook_id = ? ORDER BY block_index",
            [notebook_id],
        ).fetchall()
    finally:
        con.close()

    from substrate.notebooks.tiptap_codec import compose

    blocks = []
    for r in block_rows:
        cj = r[0]
        if isinstance(cj, str):
            cj = json.loads(cj)
        blocks.append({"content_json": cj})
    content_tiptap = compose(blocks)

    from services.html_projection.adapters.notebook_export import collect_ref_ids
    from services.html_projection.resolvers.substrate_refs import resolve_refs

    ref_ids = collect_ref_ids(content_tiptap)
    resolved_refs = resolve_refs(ref_ids, db_path=db) if ref_ids else {}

    return NotebookExportSource(
        content_tiptap=content_tiptap,
        title=row[1],
        document_id=row[4] or notebook_id,
        owner_user_id=row[3] or "__operator__",
        content_class="notebook",
        resolved_refs=resolved_refs,
    )


def register_notebook_artifact_routes(app: FastAPI) -> None:
    """Mount ``GET /api/notebooks/{id}/artifact``. One call from create_app."""

    @app.get("/api/notebooks/{notebook_id}/artifact", tags=["notebooks"])
    async def notebook_artifact(notebook_id: str, format: str = "html"):
        source = resolve_notebook_export(notebook_id)
        if source is None:
            raise HTTPException(
                status_code=404, detail=f"notebook {notebook_id!r} not found"
            )
        if format not in EXPORT_FORMATS:
            raise HTTPException(
                status_code=400,
                detail=f"unknown format {format!r}; valid: {list(EXPORT_FORMATS)}",
            )
        # The rights-filtering pre-resolve happens here (the only path).
        resolved_refs: dict[str, ResolvedRefData] = source.resolved_refs
        doc_model = adapt_notebook_for_export(
            source.content_tiptap, title=source.title, resolved_refs=resolved_refs
        )

        if format == "html":
            html = render(doc_model, RenderContext())
            try:
                assert_script_free(html)
            except ScriptViolation as err:
                raise HTTPException(
                    status_code=500,
                    detail="artifact failed the zero-script gate; refused",
                ) from err
            return HTMLResponse(
                content=html,
                headers={
                    "Content-Disposition": (
                        f'attachment; filename="notebook-{notebook_id}.html"'
                    )
                },
            )

        from services.antiek_format.signature import ensure_keypair

        keypair = ensure_keypair(source.owner_user_id, db_path=_resolve_db_path())
        item = ExportItem(
            content_tiptap={"type": "doc", "content": doc_model.get("content", [])},
            title=source.title,
            document_id=source.document_id,
            user_id=source.owner_user_id,
            notebook_id=notebook_id,
            content_class="notebook",
        )
        artifact = emit(item, format, keypair=keypair)
        if format == "antiek":
            return Response(
                content=artifact,
                media_type="application/zip",
                headers={
                    "Content-Disposition": (
                        f'attachment; filename="notebook-{notebook_id}.antiek"'
                    )
                },
            )
        return HTMLResponse(
            content=artifact,
            headers={
                "Content-Disposition": (
                    f'attachment; filename="notebook-{notebook_id}.antiek.html"'
                )
            },
        )


__all__ = ["NotebookExportSource", "register_notebook_artifact_routes", "resolve_notebook_export"]
