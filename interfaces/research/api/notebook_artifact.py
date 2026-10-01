"""Notebook artifact export route (HPRJ SPR-06).

``GET /api/notebooks/{notebook_id}/artifact.html`` — browser-inline,
script-free HTML projection (daily-use View HTML).

``GET /api/notebooks/{notebook_id}/artifact?format=html|antiek|antiek_html`` —
download / signed export (``format=html`` stays ``attachment``).

Rights filter lives in ``adapt_notebook_for_export``; zero-script gate in-route.
"""

from __future__ import annotations

import contextlib
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, Response

from services.html_projection.adapters.notebook import ResolvedRefData
from services.html_projection.adapters.notebook_export import adapt_notebook_for_export
from services.html_projection.context import RenderContext
from services.html_projection.gate import ScriptViolation, assert_script_free
from services.html_projection.renderer import render
from services.html_projection.routing_map import EXPORT_FORMATS, ExportItem, emit
from substrate.contracts.anti_ek_honesty import html_projection_response_headers

from .notebook_authority import NotebookAuthority, admit_parent, authority_from_request

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class NotebookExportSource:
    content_tiptap: dict[str, Any]
    title: str | None
    document_id: str
    owner_user_id: str | None
    content_class: str = "notebook"
    resolved_refs: dict[str, Any] = field(default_factory=dict)  # ref_id -> ResolvedRefData


def _resolve_db_path() -> str:
    from substrate.graph import default_db_path, ensure_initialized

    path = default_db_path()
    ensure_initialized(path)
    return path


def resolve_notebook_export(
    notebook_id: str, *, authority: NotebookAuthority,
    mode: Literal["read", "sign"], db_path: str | None = None,
) -> NotebookExportSource | None:
    """Authorize and snapshot one notebook before resolving refs or signing.

    The notebook's ref-bearing nodes (claim/insight/question) are resolved
    against the substrate via ``resolve_refs`` — each ref's text + the SOURCE
    document's content_class/ip_holder — and handed to the export adapter, which
    rights-filters (cite-only on non-servable). A ref the graph cannot resolve
    is omitted and exports as a visible '[... unavailable]' marker (honest, not
    faked). The notebook's own structure (prose, headings) always exports.
    """
    from runtime.db_lock import connect_read

    if mode not in {"read", "sign"}:
        raise ValueError("unsupported notebook artifact mode")
    db = db_path or _resolve_db_path()
    con = connect_read(db)
    try:
        con.execute("BEGIN TRANSACTION")
        parent = admit_parent(
            con, notebook_id, authority,
            mode="read" if mode == "read" else "write",
        )
        if parent is None or (mode == "sign" and not parent.owner_user_id):
            con.execute("ROLLBACK")
            return None
        block_rows = con.execute(
            "SELECT content_json FROM notebook_blocks "
            "WHERE notebook_id = ? ORDER BY block_index",
            [notebook_id],
        ).fetchall()
        con.execute("COMMIT")
    except BaseException:
        with contextlib.suppress(Exception):
            con.execute("ROLLBACK")
        raise
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
        title=parent.title,
        document_id=parent.document_id or notebook_id,
        owner_user_id=parent.owner_user_id,
        content_class="notebook",
        resolved_refs=resolved_refs,
    )



def _script_free_html(html: str) -> str:
    try:
        assert_script_free(html)
    except ScriptViolation as err:
        raise HTTPException(
            status_code=500,
            detail="artifact failed the zero-script gate; refused",
        ) from err
    return html


def _html_headers(*, filename: str, inline: bool) -> dict[str, str]:
    return html_projection_response_headers(
        filename=filename,
        disposition="inline" if inline else "attachment",
    )


def register_notebook_artifact_routes(app: FastAPI) -> None:
    """Mount notebook artifact view + export. One call from create_app."""

    def _doc_model(source: NotebookExportSource) -> dict[str, Any]:
        resolved_refs: dict[str, ResolvedRefData] = source.resolved_refs
        return adapt_notebook_for_export(
            source.content_tiptap, title=source.title, resolved_refs=resolved_refs
        )

    @app.get("/api/notebooks/{notebook_id}/artifact.html", tags=["notebooks"])
    async def notebook_artifact_html(notebook_id: str, request: Request) -> Response:
        """Daily-use HTML-native view — inline, script-free (not a download)."""
        source = resolve_notebook_export(
            notebook_id, authority=authority_from_request(request), mode="read",
        )
        if source is None:
            raise HTTPException(status_code=404, detail="notebook not found")
        html = _script_free_html(render(_doc_model(source), RenderContext()))
        return HTMLResponse(
            content=html,
            headers=_html_headers(
                filename=f"notebook-{notebook_id}.html", inline=True
            ),
        )

    @app.get("/api/notebooks/{notebook_id}/artifact", tags=["notebooks"])
    async def notebook_artifact(
        notebook_id: str, request: Request, format: str = "html",
    ) -> Response:
        if format not in EXPORT_FORMATS:
            raise HTTPException(
                status_code=400,
                detail=f"unknown format {format!r}; valid: {list(EXPORT_FORMATS)}",
            )
        mode: Literal["read", "sign"] = "read" if format == "html" else "sign"
        source = resolve_notebook_export(
            notebook_id, authority=authority_from_request(request), mode=mode,
        )
        if source is None:
            raise HTTPException(status_code=404, detail="notebook not found")
        # The rights-filtering pre-resolve happens here (the only path).
        doc_model = _doc_model(source)

        if format == "html":
            html = _script_free_html(render(doc_model, RenderContext()))
            return HTMLResponse(
                content=html,
                headers=_html_headers(
                    filename=f"notebook-{notebook_id}.html", inline=False
                ),
            )

        from services.antiek_format.signature import ensure_keypair

        if source.owner_user_id is None:
            raise HTTPException(status_code=404, detail="notebook not found")
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
