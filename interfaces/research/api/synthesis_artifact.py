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

import ipaddress
import json
import logging
import os
import re
from typing import Any, cast
from urllib.parse import quote, urlsplit

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
from substrate.contracts.anti_ek_honesty import html_projection_response_headers

_log = logging.getLogger(__name__)


def _resolve_db_path() -> str:
    from substrate.graph import default_db_path, ensure_initialized

    path = default_db_path()
    ensure_initialized(path)
    return path


def _loadjson(value: str | None) -> dict[str, Any]:
    try:
        parsed = json.loads(value) if value else {}
        return cast(dict[str, Any], parsed) if isinstance(parsed, dict) else {}
    except (TypeError, ValueError, RecursionError):
        return {}


# Export is a bounded reader of archived JSON. Oversized/malformed claim data
# falls back visibly; it must never be partially counted as complete.
_MAX_THESIS_CHARS = 2_000_000
_MAX_COMPONENTS = 10_000
_MAX_CITATIONS = 100_000
_MAX_CITATION_ID_LENGTH = 4096


def _archived_components(value: str | None) -> list[dict[str, Any]]:
    if not isinstance(value, str) or len(value) > _MAX_THESIS_CHARS:
        return []
    thesis = _loadjson(value)
    components = thesis.get("thesis_components")
    if not isinstance(components, list) or not 0 < len(components) <= _MAX_COMPONENTS:
        return []
    citation_count = 0
    for component in components:
        if (not isinstance(component, dict)
                or not isinstance(component.get("claim"), str)
                or not component["claim"].strip()):
            return []
        ids = component.get("supporting_chunk_ids", [])
        if isinstance(ids, list):
            citation_count += len(ids)
            if citation_count > _MAX_CITATIONS:
                return []
            if any(isinstance(cid, str) and len(cid) > _MAX_CITATION_ID_LENGTH for cid in ids):
                return []
    return cast(list[dict[str, Any]], components)


def _valid_reader_host(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        pass
    try:
        ascii_host = host.encode("idna").decode("ascii").rstrip(".")
    except UnicodeError:
        return False
    if not ascii_host or len(ascii_host) > 253:
        return False
    # WHATWG parses numeric final labels as IPv4, including hex and octal.
    # Canonical IP literals already passed ipaddress above.
    if re.fullmatch(r"(?:[0-9]+|0[xX][0-9a-fA-F]*)", ascii_host.rsplit(".", 1)[-1]):
        return False
    return all(re.fullmatch(r"[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?", label)
               for label in ascii_host.split("."))


def _reader_origin() -> str | None:
    """Use deployment configuration, never request-controlled host headers.

    Precedence matches the login frontend redirect. A downloaded artifact has
    no same-origin fallback, so an unavailable origin leaves plain references.
    """
    value = (os.environ.get("ANTIEK_FRONTEND_BASE_URL", "").strip()
             or os.environ.get("ANTIEK_PUBLIC_BASE_URL", "").strip())
    if not value or any(ord(c) <= 32 or ord(c) == 127 for c in value):
        return None
    if "\\" in value or "?" in value or "#" in value:
        return None
    try:
        parsed = urlsplit(value)
        if (parsed.scheme not in {"http", "https"} or not parsed.hostname
                or parsed.username is not None or parsed.password is not None
                or parsed.path not in {"", "/"} or "%" in parsed.netloc
                or not _valid_reader_host(parsed.hostname)):
            return None
        # urlsplit validates brackets; accessing port also validates its range.
        _ = parsed.port
    except ValueError:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


def _reader_locator(origin: str | None, document_id: str) -> str | None:
    if origin is None or not document_id or document_id in {".", ".."}:
        return None
    return f"{origin}/read/{quote(document_id, safe='')}"


def resolve_synthesis_export(
    synthesis_id: str, *, db_path: str | None = None
) -> SynthesisExport | None:
    """Resolve archived synthesis claims through their exact graph citations.

    Claim parsing and graph lookup follow PR856's archived-thesis approach.
    Unknown citations remain unresolved, including federated IDs whose registry
    is not part of this local-graph resolver. Legacy document references remain
    useful citations but never establish a complete chunk provenance chain.
    """
    from runtime.db_lock import connect_read

    origin = _reader_origin()
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
        doc_rows = con.execute(
            "SELECT m.entity_id, d.title, d.content_class, d.ip_holder_id "
            "FROM synthesis_substrate_manifest m "
            "JOIN documents d ON d.document_id = m.entity_id "
            "WHERE m.synthesis_id = ? AND m.entity_kind = 'document'",
            [synthesis_id],
        ).fetchall()
        components = _archived_components(row[6])
        cited: set[str] = set()
        for component in components:
            component_ids = component.get("supporting_chunk_ids")
            if isinstance(component_ids, list):
                cited.update(cid for cid in component_ids if isinstance(cid, str) and cid)
        cited_ids = sorted(cited)
        graph_sources: dict[str, SourceRef] = {}
        # Bound SQL parameter lists without truncating the archived citations.
        for offset in range(0, len(cited_ids), 500):
            batch = cited_ids[offset:offset + 500]
            placeholders = ",".join("?" for _ in batch)
            chunk_rows = con.execute(
                "SELECT c.chunk_id, d.document_id, d.title, d.content_class, "
                "d.ip_holder_id, c.text FROM chunks c JOIN documents d "
                "ON d.document_id = c.document_id "
                f"WHERE c.chunk_id IN ({placeholders})", batch,
            ).fetchall()
            for chunk in chunk_rows:
                graph_sources[chunk[0]] = SourceRef(
                    document_id=chunk[1], document_title=chunk[2],
                    content_class=chunk[3], ip_holder_id=chunk[4],
                    locator=_reader_locator(origin, chunk[1]),
                    chunk_text=chunk[5], chunk_id=chunk[0],
                )
    finally:
        con.close()

    document_sources = [
        SourceRef(document_id=r[0], document_title=r[1], content_class=r[2],
                  ip_holder_id=r[3], locator=_reader_locator(origin, r[0]))
        for r in doc_rows
    ]
    claims: list[Claim] = []
    for component in components:
        ids = component.get("supporting_chunk_ids", [])
        sources: list[SourceRef] = []
        if not isinstance(ids, list):
            ids = [None]
        seen: set[str] = set()
        for chunk_id in ids:
            if isinstance(chunk_id, str) and chunk_id:
                if chunk_id in seen:
                    continue
                seen.add(chunk_id)
                source = graph_sources.get(chunk_id)
                if source is not None:
                    sources.append(source)
                    continue
            sources.append(SourceRef(
                document_id=None, document_title=None, content_class=None,
                ip_holder_id=None,
                chunk_id=chunk_id if isinstance(chunk_id, str) else None,
            ))
        claims.append(Claim(statement=component["claim"], sources=sources))
    if not claims and row[2]:
        claims = [Claim(statement=row[2], sources=document_sources)]

    provenance_note = None
    if not components:
        provenance_note = (
            "Archived claim provenance unavailable; any available summary and document references follow."
        )
    elif any(not c.get("supporting_chunk_ids") and c.get("supporting_path_indices")
             for c in components):
        provenance_note = "Analogy paths are not resolved as chunk citations in this export."

    return SynthesisExport(
        synthesis_id=row[0], target_question=row[1] or "(untitled synthesis)",
        thesis_text=row[2] if components else None,
        provenance_note=provenance_note,
        recommendation=row[3], model_versions=_loadjson(row[4]),
        parameters=_loadjson(row[5]),
        attribution_manifest={
            "document_ip_holders": {
                source.document_id: source.ip_holder_id
                for claim in claims for source in claim.sources if source.document_id
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
