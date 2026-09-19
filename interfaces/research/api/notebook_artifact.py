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
import os
from dataclasses import dataclass, field
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, Response

from services.html_projection.adapters.notebook import ResolvedRefData
from services.html_projection.adapters.notebook_export import adapt_notebook_for_export
from services.html_projection.context import RenderContext
from services.html_projection.gate import ScriptViolation, assert_script_free
from services.html_projection.renderer import render
from services.html_projection.routing_map import EXPORT_FORMATS, ExportItem, emit
from substrate.notebooks.authority import NotebookAuthority

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class NotebookExportSource:
    content_tiptap: dict[str, Any]
    title: str | None
    document_id: str
    owner_user_id: str
    content_class: str = "notebook"
    resolved_refs: dict[str, Any] = field(default_factory=dict)  # ref_id -> ResolvedRefData


def _resolve_db_path() -> str:
    from substrate.graph import default_db_path, ensure_initialized

    path = default_db_path()
    ensure_initialized(path)
    return path


def resolve_notebook_export(
    notebook_authority: NotebookAuthority,
    *,
    db_path: str | None = None,
    engagement_store: Any | None = None,
    investigation_authority: Any | None = None,
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
    from substrate.notebooks import get_notebook

    db = db_path or _resolve_db_path()
    con = connect_read(db)
    try:
        notebook = get_notebook(con, notebook_authority)
        if notebook is None:
            return None
        block_rows = [
            (block.block_type, block.ref_id, block.content_json)
            for block in notebook.blocks
        ]
        linked_document = None
        if notebook.document_id:
            from substrate.legal_gate.read import read_document_compatibility

            document = read_document_compatibility(
                con,
                str(notebook.document_id),
                authority=investigation_authority,
                enforce=os.environ.get("ANTIEK_LEGAL_READ_ENFORCEMENT") == "1",
            )
            if document is not None:
                linked_document = (
                    document.get("title"),
                    document.get("content_class"),
                    document.get("ip_holder_id"),
                )
    finally:
        con.close()

    from substrate.notebooks.tiptap_codec import compose

    blocks = []
    for r in block_rows:
        block_type, ref_id, cj = r
        if isinstance(cj, str):
            cj = json.loads(cj)
        if block_type == "note" and str(ref_id or "").startswith("twin_"):
            cj = {"type": "note_block", "attrs": {"note_id": str(ref_id)}}
        blocks.append({"content_json": cj})
    content_tiptap = compose(blocks)

    from services.html_projection.adapters.notebook_export import collect_ref_ids
    from services.html_projection.resolvers.substrate_refs import resolve_refs

    ref_ids = collect_ref_ids(content_tiptap)
    resolved_refs = (
        resolve_refs(ref_ids, db_path=db, authority=investigation_authority)
        if ref_ids
        else {}
    )
    if ref_ids and notebook.document_id and (
        os.environ.get("ANTIEK_LEGAL_READ_ENFORCEMENT") != "1"
        or linked_document is not None
    ):
        from interfaces.research.api.engagement_routes import get_engagement_store
        from substrate.engagement_spine.twin import list_twin_notes

        store = engagement_store or get_engagement_store()
        wanted = set(ref_ids)
        linked_title = (
            str(linked_document[0])
            if linked_document and linked_document[0]
            else str(notebook.title or notebook.document_id)
        )
        linked_content_class = (
            str(linked_document[1])
            if linked_document and linked_document[1]
            else None
        )
        linked_ip_holder = (
            str(linked_document[2])
            if linked_document and linked_document[2]
            else None
        )
        for note in list_twin_notes(str(notebook.document_id), store=store):
            if note.note_id not in wanted:
                continue
            payload_key = "question" if note.kind == "question" else "statement"
            resolved_refs[note.note_id] = ResolvedRefData(
                kind=note.kind,
                content_class=linked_content_class,
                ip_holder_id=linked_ip_holder,
                title=linked_title,
                payload={payload_key: note.text, "text": note.text},
                source_document_id=str(notebook.document_id),
            )

    return NotebookExportSource(
        content_tiptap=content_tiptap,
        title=notebook.title,
        document_id=notebook.document_id or notebook_authority.notebook_id,
        owner_user_id=notebook.owner_user_id,
        content_class="notebook",
        resolved_refs=resolved_refs,
    )


def register_notebook_artifact_routes(
    app: FastAPI, *, unauthenticated_local: bool = True
) -> None:
    """Mount ``GET /api/notebooks/{id}/artifact``. One call from create_app."""

    app.state.notebook_artifact_unauthenticated_local = bool(unauthenticated_local)

    @app.get("/api/notebooks/{notebook_id}/artifact", tags=["notebooks"])
    async def notebook_artifact(
        notebook_id: str, request: Request, format: str = "html"
    ) -> Response:
        from interfaces.research.api.notebook_access import (
            NotebookAuthenticationRequired,
            notebook_account_authority_from_request,
        )
        from substrate.notebooks import NotebookCorruptError, get_notebook

        try:
            account = notebook_account_authority_from_request(
                request,
                allow_missing_local_state=getattr(
                    request.app.state,
                    "notebook_artifact_unauthenticated_local",
                    False,
                ),
            )
        except NotebookAuthenticationRequired as exc:
            raise HTTPException(
                status_code=401,
                detail="authentication required",
                headers={"Cache-Control": "no-store"},
            ) from exc
        notebook_authority = account.notebook(notebook_id)
        investigation_authority = None
        if os.environ.get("ANTIEK_LEGAL_READ_ENFORCEMENT") == "1":
            from interfaces.research.api.investigation_access import (
                InvestigationAccessDenied,
                authority_from_request,
                require_investigation_owner,
            )
            from runtime.db_lock import connect_read

            try:
                with connect_read(_resolve_db_path()) as con:
                    selected = get_notebook(con, notebook_authority)
            except NotebookCorruptError as exc:
                raise HTTPException(
                    status_code=503,
                    detail={"code": "notebook_unavailable"},
                    headers={"Cache-Control": "no-store"},
                ) from exc
            if selected is None or not selected.investigation_id:
                raise HTTPException(
                    status_code=404,
                    detail="notebook not found",
                    headers={"Cache-Control": "no-store"},
                )
            try:
                access = authority_from_request(request, selected.investigation_id)
                require_investigation_owner(access)
                investigation_authority = access.authority
            except InvestigationAccessDenied as exc:
                raise HTTPException(
                    status_code=404,
                    detail="notebook not found",
                    headers={"Cache-Control": "no-store"},
                ) from exc
        from interfaces.research.api.engagement_routes import (
            get_account_engagement_store,
        )

        try:
            source = resolve_notebook_export(
                notebook_authority,
                engagement_store=get_account_engagement_store(account.account_id),
                investigation_authority=investigation_authority,
            )
        except NotebookCorruptError as exc:
            raise HTTPException(
                status_code=503,
                detail={"code": "notebook_unavailable"},
                headers={"Cache-Control": "no-store"},
            ) from exc
        if source is None:
            raise HTTPException(
                status_code=404,
                detail="notebook not found",
                headers={"Cache-Control": "no-store"},
            )
        if format not in EXPORT_FORMATS:
            raise HTTPException(
                status_code=400,
                detail=f"unknown format {format!r}; valid: {list(EXPORT_FORMATS)}",
                headers={"Cache-Control": "no-store"},
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
                    headers={"Cache-Control": "no-store"},
                ) from err
            return HTMLResponse(
                content=html,
                headers={
                    "Content-Disposition": (
                        f'attachment; filename="notebook-{notebook_id}.html"'
                    ),
                    "Cache-Control": "no-store",
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
                    ),
                    "Cache-Control": "no-store",
                },
            )
        return HTMLResponse(
            content=artifact,
            headers={
                "Content-Disposition": (
                    f'attachment; filename="notebook-{notebook_id}.antiek.html"'
                ),
                "Cache-Control": "no-store",
            },
        )


__all__ = ["NotebookExportSource", "register_notebook_artifact_routes", "resolve_notebook_export"]
