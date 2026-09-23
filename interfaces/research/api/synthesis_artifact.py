"""Synthesis-artifact export route (HPRJ SPR-05 M3).

``GET /api/syntheses/{synthesis_id}/artifact.html`` — adapt → render →
zero-script gate (IN the route path, not decorative) → download; or 403 with
a structured reason on a synthesis-level restriction; or 404 when the
synthesis does not exist.

The rights filter lives in the ADAPTER
(``services/html_projection/adapters/synthesis.py``), which reuses
``substrate.constants.SERVABLE_CONTENT_CLASSES``. This route only resolves the
synthesis from the graph and wires the gate. A 403 carries a reason — never a
200 with silently omitted content (a silent omission reads as "this is the
whole synthesis", which is a lie).
"""

from __future__ import annotations

import json
import logging
from typing import Any, cast

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, Response

from services.html_projection.adapters.synthesis import (
    Claim,
    RightsRefusal,
    SourceRef,
    SynthesisExport,
    adapt_synthesis,
)
from services.html_projection.context import Provenance, RenderContext
from services.html_projection.gate import ScriptViolation, assert_script_free
from services.html_projection.renderer import render
from services.html_projection.resolvers.substrate_refs import resolve_manifest_sources
from substrate.contracts.anti_ek_honesty import html_projection_response_headers

_log = logging.getLogger(__name__)


def _resolve_db_path() -> str:
    from substrate.graph import default_db_path, ensure_initialized

    path = default_db_path()
    ensure_initialized(path)
    return path


def _loadjson(value: str | None) -> dict[str, Any]:
    try:
        return cast(dict[str, Any], json.loads(value)) if value else {}
    except (TypeError, ValueError):
        return {}


def resolve_synthesis_export(
    synthesis_id: str, *, db_path: str | None = None
) -> SynthesisExport | None:
    """Build a ``SynthesisExport`` from the graph, or None if it does not exist.

    Reads the synthesis metadata and follows every substrate-manifest pin
    (document, chunk, node, edge) to the document it stands on, as
    document-level provenance sources. The document-level rights data
    (``content_class`` + ``ip_holder_id``) comes straight from ``documents``;
    the rights FILTER is applied downstream in the adapter (single source of
    truth), so this resolver never decides embed-vs-cite-only.

    NOTE (rigor #1): the per-claim chunk-level structure of
    ``syntheses.evidence`` is NOT yet validated against a real archived
    synthesis (the local graph had zero rows at build time). This resolver
    reads what is reliably present and renders the thesis as one claim grounded
    in the manifest documents; it **degrades** to that rather than fabricating a
    claim structure it cannot verify. When a real synthesis exists, extend this
    to parse the validated evidence shape into per-claim chunk sources — the
    adapter already handles arbitrarily many claims + sources.
    """
    from runtime.db_lock import connect_read

    db = db_path or _resolve_db_path()
    con = connect_read(db)
    try:
        row = con.execute(
            "SELECT synthesis_id, target_question, thesis_text, "
            "implicit_recommendation, model_versions, parameters "
            "FROM syntheses WHERE synthesis_id = ?",
            [synthesis_id],
        ).fetchone()
        if row is None:
            return None
        # Every pin kind, not only document pins: the archive writer pins
        # chunks and edges, so a document-only read left a real synthesis with
        # no sources at all, and a missing chunk pin was dropped before the M4
        # gate. A pin that cannot be followed to a live document reaches the
        # gate as a source with no document, which it counts as unresolved.
        pinned = resolve_manifest_sources(con, [synthesis_id])
    finally:
        con.close()

    sources: list[SourceRef] = []
    cited: set[str] = set()
    for pin in pinned:
        if pin.document_id is None:
            sources.append(
                SourceRef(
                    document_id=None,
                    document_title=f"missing {pin.entity_kind} {pin.entity_id}",
                    content_class=None,
                    ip_holder_id=None,
                )
            )
        elif pin.document_id not in cited:
            # Two chunks of one document cite that document once.
            cited.add(pin.document_id)
            sources.append(
                SourceRef(
                    document_id=pin.document_id,
                    document_title=pin.title,
                    content_class=pin.content_class,
                    ip_holder_id=pin.ip_holder_id,
                    locator=f"/read/{pin.document_id}",
                    chunk_text=None,  # document-level source
                )
            )
    claims = [Claim(statement=row[2], sources=sources)] if row[2] else []

    return SynthesisExport(
        synthesis_id=row[0],
        target_question=row[1] or "(untitled synthesis)",
        thesis_text=None,  # surfaced as the first claim above
        recommendation=row[3],
        model_versions=_loadjson(row[4]),
        parameters=_loadjson(row[5]),
        attribution_manifest={
            "document_ip_holders": {
                s.document_id: s.ip_holder_id for s in sources if s.document_id
            }
        },
        claims=claims,
    )


def register_synthesis_artifact_routes(app: FastAPI) -> None:
    """Mount ``GET /api/syntheses/{id}/artifact.html``. One call from
    ``create_app``."""

    @app.get("/api/syntheses/{synthesis_id}/artifact.html", tags=["syntheses"])
    async def synthesis_artifact(synthesis_id: str) -> Response:
        export = resolve_synthesis_export(synthesis_id)
        if export is None:
            raise HTTPException(
                status_code=404, detail=f"synthesis {synthesis_id!r} not found"
            )
        try:
            doc_model = adapt_synthesis(export)
        except RightsRefusal as refusal:
            return JSONResponse(
                status_code=403,
                content={
                    "error": "export_refused",
                    "reason": refusal.reason,
                    "synthesis_id": synthesis_id,
                },
            )
        ctx = RenderContext(
            provenance=Provenance(
                document_id=export.synthesis_id,
                title=export.target_question,
                content_class="synthesis",
                schema_version="1",
            )
        )
        html = render(doc_model, ctx)
        # The zero-script gate runs IN the route path — a poisoned render is
        # refused, never served.
        try:
            assert_script_free(html)
        except ScriptViolation as err:
            _log.error(
                "synthesis artifact %s failed the zero-script gate; refusing",
                synthesis_id,
            )
            raise HTTPException(
                status_code=500,
                detail="artifact failed the zero-script gate; refused",
            ) from err
        return HTMLResponse(
            content=html,
            headers=html_projection_response_headers(
                filename=f"synthesis-{synthesis_id}.html",
                disposition="inline",
            ),
        )

    @app.get("/api/syntheses/{synthesis_id}/artifact", tags=["syntheses"])
    async def synthesis_artifact_format(synthesis_id: str, format: str = "html") -> Response:
        """Export a synthesis as html / antiek / antiek_html through the SPR-06
        M4 routing map. The rights filter is applied in adapt_synthesis (the
        doc-model is already cite-only-filtered before emission); the signed
        formats are gate-clean by SPR-04 construction. 403 on a synthesis-level
        restriction; 404 missing; 400 unknown format."""
        from services.html_projection.routing_map import EXPORT_FORMATS, ExportItem, emit

        export = resolve_synthesis_export(synthesis_id)
        if export is None:
            raise HTTPException(
                status_code=404, detail=f"synthesis {synthesis_id!r} not found"
            )
        if format not in EXPORT_FORMATS:
            raise HTTPException(
                status_code=400,
                detail=f"unknown format {format!r}; valid: {list(EXPORT_FORMATS)}",
            )
        try:
            doc_model = adapt_synthesis(export)
        except RightsRefusal as refusal:
            return JSONResponse(
                status_code=403,
                content={
                    "error": "export_refused",
                    "reason": refusal.reason,
                    "synthesis_id": synthesis_id,
                },
            )

        if format == "html":
            ctx = RenderContext(
                provenance=Provenance(
                    document_id=export.synthesis_id,
                    title=export.target_question,
                    content_class="synthesis",
                    schema_version="1",
                )
            )
            html = render(doc_model, ctx)
            try:
                assert_script_free(html)
            except ScriptViolation as err:
                raise HTTPException(
                    status_code=500,
                    detail="artifact failed the zero-script gate; refused",
                ) from err
            return HTMLResponse(
                content=html,
                headers=html_projection_response_headers(
                    filename=f"synthesis-{synthesis_id}.html",
                    disposition="attachment",
                ),
            )

        # Signed formats — emit the rights-filtered doc-model through the routing
        # map. (Operator keypair: created-on-first-call; in prod pre-create it so
        # this read route does not take the keypair write lock at serve time.)
        from services.antiek_format.signature import ensure_keypair

        keypair = ensure_keypair("operator", db_path=_resolve_db_path())
        item = ExportItem(
            content_tiptap={"type": "doc", "content": doc_model.get("content", [])},
            title=export.target_question,
            document_id=synthesis_id,
            user_id="operator",
            notebook_id=synthesis_id,
            content_class="deliverable",
        )
        artifact = emit(item, format, keypair=keypair)
        if format == "antiek":
            return Response(
                content=artifact,
                media_type="application/zip",
                headers={
                    "Content-Disposition": (
                        f'attachment; filename="synthesis-{synthesis_id}.antiek"'
                    )
                },
            )
        # antiek_html — a signed single-file HTML
        return HTMLResponse(
            content=artifact,
            headers={
                "Content-Disposition": (
                    f'attachment; filename="synthesis-{synthesis_id}.antiek.html"'
                )
            },
        )


__all__ = ["register_synthesis_artifact_routes", "resolve_synthesis_export"]
