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

    Reads the synthesis metadata + the substrate-manifest documents as
    document-level provenance sources. The document-level rights data
    (``content_class`` + ``ip_holder_id``) comes straight from ``documents``;
    the rights FILTER is applied downstream in the adapter (single source of
    truth), so this resolver never decides embed-vs-cite-only.

    Claim-level citations come from the archived, typed synthesizer payload.
    Graph chunk ids resolve through graph documents; federated ``span_*`` ids
    resolve through the validated archived Phase-2 registry. Malformed or
    missing provenance stays visibly unsourced.
    """
    from runtime.db_lock import connect_read

    db = db_path or _resolve_db_path()
    con = connect_read(db)
    try:
        row = con.execute(
            "SELECT synthesis_id, target_question, thesis_text, "
            "implicit_recommendation, model_versions, parameters, thesis, substrate "
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

        thesis = _loadjson(row[6])
        components = thesis.get("thesis_components")
        cited_ids: set[str] = set()
        if type(components) is list:
            for component in components:
                if type(component) is not dict:
                    continue
                component_ids = component.get("supporting_chunk_ids")
                if type(component_ids) is list:
                    cited_ids.update(
                        chunk_id
                        for chunk_id in component_ids
                        if type(chunk_id) is str
                    )
        graph_chunk_rows: list[tuple[Any, ...]] = []
        if cited_ids:
            placeholders = ",".join("?" for _ in cited_ids)
            graph_chunk_rows = con.execute(
                "SELECT c.chunk_id, d.document_id, d.title, d.content_class, "
                "d.ip_holder_id FROM chunks c JOIN documents d "
                "ON d.document_id = c.document_id "
                f"WHERE c.chunk_id IN ({placeholders})",
                sorted(cited_ids),
            ).fetchall()
    finally:
        con.close()

    from orchestration.loop_one.federated_span_registry import registry_from_archive

    try:
        span_registry = registry_from_archive(_loadjson(row[7]))
    except ValueError:
        span_registry = {}
    graph_by_chunk = {
        r[0]: SourceRef(
            document_id=r[1],
            document_title=r[2],
            content_class=r[3],
            ip_holder_id=r[4],
            locator=f"/read/{r[1]}",
            chunk_text=None,
        )
        for r in graph_chunk_rows
    }

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
    claims: list[Claim] = []
    if type(components) is list:
        for component in components:
            if type(component) is not dict or type(component.get("claim")) is not str:
                continue
            component_sources: list[SourceRef] = []
            chunk_ids = component.get("supporting_chunk_ids")
            if type(chunk_ids) is list:
                for chunk_id in chunk_ids:
                    if type(chunk_id) is not str:
                        continue
                    graph_source = graph_by_chunk.get(chunk_id)
                    if graph_source is not None:
                        component_sources.append(graph_source)
                        continue
                    span = span_registry.get(chunk_id)
                    if span is not None:
                        component_sources.append(
                            SourceRef(
                                document_id=None,
                                document_title=span.origin_ref,
                                content_class=None,
                                ip_holder_id=None,
                                external_source_id=span.corpus_id,
                                source_kind=span.source_kind,
                                rights_class=span.license_class,
                                retrieved_at=span.retrieved_at,
                                source_tier=span.source_tier,
                                locator=None,
                                chunk_text=span.text,
                            )
                        )
            claims.append(Claim(statement=component["claim"], sources=component_sources))
    if not claims and row[2]:
        claims = [Claim(statement=row[2], sources=sources)]

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
            headers={
                "Content-Disposition": (
                    f'attachment; filename="synthesis-{synthesis_id}.html"'
                )
            },
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
                headers={
                    "Content-Disposition": (
                        f'attachment; filename="synthesis-{synthesis_id}.html"'
                    )
                },
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
