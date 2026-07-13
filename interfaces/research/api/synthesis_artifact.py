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
    PathRef,
    RightsRefusal,
    SourceRef,
    SynthesisExport,
    adapt_synthesis,
)
from services.html_projection.context import Provenance, RenderContext
from services.html_projection.gate import ScriptViolation, assert_script_free
from services.html_projection.renderer import render

_log = logging.getLogger(__name__)
_INVALID_THESIS_WARNING = "Archived synthesis payload could not be validated."


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


def _thesis_claim_chunks(
    value: str | None,
    *,
    manifest_edges: dict[str, tuple[str, str]],
) -> tuple[list[tuple[str, list[str], list[PathRef]]], list[str]]:
    """Return canonical synthesis claims with their cited chunk ids.

    Archived theses are typed at write time, but old or manually imported rows
    can still contain malformed JSON. Invalid payloads contribute no grounding;
    they must never broaden a claim to the synthesis-level manifest.
    """
    from pydantic import ValidationError

    from substrate.schemas import SynthesizeDeliveredPayload

    try:
        payload = json.loads(value) if value else None
    except (TypeError, ValueError):
        return [], [_INVALID_THESIS_WARNING]
    if payload is None:
        return [], []
    try:
        delivered = SynthesizeDeliveredPayload.model_validate(payload)
    except (TypeError, ValidationError):
        return [], [_INVALID_THESIS_WARNING]

    claims: list[tuple[str, list[str], list[PathRef]]] = []
    warnings: list[str] = []
    for component_index, component in enumerate(delivered.thesis_components):
        statement = component.claim.strip()
        if not statement:
            warnings.append(f"Thesis component {component_index + 1} has empty claim text.")
            continue
        path_refs: list[PathRef] = []
        for path_index in dict.fromkeys(component.supporting_path_indices):
            if 0 <= path_index < len(delivered.reasoning_paths_used):
                path = delivered.reasoning_paths_used[path_index]
                node_ids = list(path.path_node_ids)
                edge_ids = list(path.path_edge_ids)
                path_pairs = list(zip(node_ids, node_ids[1:], strict=False))
                path_refs.append(
                    PathRef(
                        index=path_index,
                        node_ids=node_ids,
                        edge_ids=edge_ids,
                        support_summary=path.support_summary,
                        manifest_verified=(
                            bool(edge_ids)
                            and len(node_ids) == len(edge_ids) + 1
                            and all(
                                manifest_edges.get(edge_id) == path_pairs[i]
                                for i, edge_id in enumerate(edge_ids)
                            )
                        ),
                    )
                )
            else:
                path_refs.append(PathRef(index=path_index))
        claims.append(
            (
                statement,
                list(dict.fromkeys(component.supporting_chunk_ids)),
                path_refs,
            )
        )
    return claims, warnings


def resolve_synthesis_export(
    synthesis_id: str, *, db_path: str | None = None
) -> SynthesisExport | None:
    """Build a ``SynthesisExport`` from the graph, or None if it does not exist.

    Reads the typed archived synthesis and resolves each claim only through the
    exact chunks it cites and the synthesis manifest pins. Rights metadata comes
    from ``documents``; the downstream adapter remains the single embed-vs-cite-only
    authority. Invalid thesis data or dangling citations stay visibly unsourced;
    they never inherit unrelated manifest documents as support.
    """
    from runtime.db_lock import connect_read

    db = db_path or _resolve_db_path()
    con = connect_read(db)
    try:
        row = con.execute(
            "SELECT synthesis_id, target_question, thesis_text, "
            "implicit_recommendation, model_versions, parameters, thesis "
            "FROM syntheses WHERE synthesis_id = ?",
            [synthesis_id],
        ).fetchone()
        if row is None:
            return None
        chunk_rows = con.execute(
            "SELECT m.entity_id, c.document_id, d.title, d.content_class, "
            "d.ip_holder_id, c.text, COALESCE(b.taken_down, FALSE) "
            "FROM synthesis_substrate_manifest m "
            "JOIN chunks c ON c.chunk_id = m.entity_id "
            "JOIN documents d ON d.document_id = c.document_id "
            "LEFT JOIN book_assets b ON b.document_id = d.document_id "
            "WHERE m.synthesis_id = ? AND m.entity_kind = 'chunk' "
            "ORDER BY m.entity_id",
            [synthesis_id],
        ).fetchall()
        edge_rows = con.execute(
            "SELECT m.entity_id, e.source_node_id, e.target_node_id "
            "FROM synthesis_substrate_manifest m "
            "JOIN edges e ON e.edge_id = m.entity_id "
            "WHERE m.synthesis_id = ? AND m.entity_kind = 'edge' "
            "ORDER BY m.entity_id",
            [synthesis_id],
        ).fetchall()
    finally:
        con.close()

    source_by_chunk = {
        r[0]: SourceRef(
            document_id=r[1],
            document_title=r[2],
            content_class=r[3],
            ip_holder_id=r[4],
            locator=f"/read/{r[1]}?chunk={r[0]}",
            chunk_text=r[5],
            taken_down=bool(r[6]),
        )
        for r in chunk_rows
    }

    def _source_for_chunk(chunk_id: str) -> SourceRef:
        source = source_by_chunk.get(chunk_id)
        if source is not None:
            return source
        return SourceRef(
            document_id=None,
            document_title=f"Unresolved chunk {chunk_id}",
            content_class=None,
            ip_holder_id=None,
        )

    claim_provenance, provenance_warnings = _thesis_claim_chunks(
        row[6], manifest_edges={r[0]: (r[1], r[2]) for r in edge_rows}
    )
    claims = [
        Claim(
            statement=statement,
            sources=[_source_for_chunk(chunk_id) for chunk_id in chunk_ids],
            path_refs=path_refs,
        )
        for statement, chunk_ids, path_refs in claim_provenance
    ]

    document_ip_holders = {
        source.document_id: source.ip_holder_id
        for claim in claims
        for source in claim.sources
        if source.document_id
    }

    return SynthesisExport(
        synthesis_id=row[0],
        target_question=row[1] or "(untitled synthesis)",
        thesis_text=row[2],
        recommendation=row[3],
        model_versions=_loadjson(row[4]),
        parameters=_loadjson(row[5]),
        attribution_manifest={"document_ip_holders": document_ip_holders},
        claims=claims,
        provenance_warnings=provenance_warnings,
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
