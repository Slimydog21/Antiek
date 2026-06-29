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
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse

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

_log = logging.getLogger(__name__)


def _resolve_db_path() -> str:
    from substrate.graph import default_db_path, ensure_initialized

    path = default_db_path()
    ensure_initialized(path)
    return path


def _loadjson(value) -> dict:
    try:
        return json.loads(value) if value else {}
    except (TypeError, ValueError):
        return {}


def resolve_synthesis_export(
    synthesis_id: str, *, db_path: Optional[str] = None
) -> Optional[SynthesisExport]:
    """Build a ``SynthesisExport`` from the graph, or None if it does not exist.

    Reads the synthesis metadata + the substrate-manifest documents as
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
        doc_rows = con.execute(
            "SELECT m.entity_id, d.title, d.content_class, d.ip_holder_id "
            "FROM synthesis_substrate_manifest m "
            "JOIN documents d ON d.document_id = m.entity_id "
            "WHERE m.synthesis_id = ? AND m.entity_kind = 'document'",
            [synthesis_id],
        ).fetchall()
    finally:
        con.close()

    sources = [
        SourceRef(
            document_id=r[0],
            document_title=r[1],
            content_class=r[2],
            ip_holder_id=r[3],
            locator=f"/read/{r[0]}",
            chunk_text=None,  # document-level source; chunk text resolved per-claim later
        )
        for r in doc_rows
    ]
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
    async def synthesis_artifact(synthesis_id: str):
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
        except ScriptViolation:
            _log.error(
                "synthesis artifact %s failed the zero-script gate; refusing",
                synthesis_id,
            )
            raise HTTPException(
                status_code=500,
                detail="artifact failed the zero-script gate; refused",
            )
        return HTMLResponse(
            content=html,
            headers={
                "Content-Disposition": (
                    f'attachment; filename="synthesis-{synthesis_id}.html"'
                )
            },
        )


__all__ = ["register_synthesis_artifact_routes", "resolve_synthesis_export"]
