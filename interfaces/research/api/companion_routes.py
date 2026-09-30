"""Companion + evidence-base routes (companions SPR-02) — the surfaces.

GET /documents/{id}/companion        — the LAST BUILD of the requester's
                                       companion of the document: the
                                       rendered narrative (HTML with the
                                       honesty headers) or its STRUCTURED
                                       payload (?format=json) — the rail and
                                       agents render the payload, NEVER raw
                                       generated HTML (the sanctioned-
                                       rendering discipline: no innerHTML of
                                       generated content anywhere). It never
                                       writes (THREAD-CONTRACT §1.12);
POST /documents/{id}/companion/refresh — the rebuild, under the writer
                                       lock; answers what the next GET
                                       serves;
GET /documents/{id}/evidence?kind=&q= — the document's index rows,
                                       STRUCTURED filters only (kind facet +
                                       substring over refs — no vector
                                       search, no text to search);
GET /evidence/{evidence_id}          — claim + evidence + process by stable
                                       id; a TOMBSTONED id resolves honestly
                                       (never dangling, never re-pointed);
GET /projects/{id}/companion|evidence — honestly UNAVAILABLE (501) until the
                                       unit-3 container lands — never a fake
                                       project aggregate.

A NEW router module (not more mass in books.py) following the unit
conventions: register_*_routes from create_app, _reader_owner_id /
_resolve_db_path (books.py:140+) for the owner boundary — a document whose
owner isn't the requester is a 404, never a leak.

The companion GET serves the persisted build and never rebuilds: the
Reading rail calls it on every reader open, and a rebuild there took the
single writer lock each time. Only the POST refresh rebuilds. The build is
keyed by (owner, document), and serving re-checks the document with the
reader's own predicate, so a taken-down or no-longer-servable document's
build is withheld.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel

from interfaces.research.api.books import _reader_owner_id, _resolve_db_path
from substrate.books.servability import (
    ServabilityStatus,
    is_servable_full_text,
    servability_of,
)
from substrate.companions.evidence_index import (
    KINDS,
    EvidenceRow,
    read_scope,
    resolve,
)
from substrate.companions.projector import (
    CompanionOwnerChanged,
    export_document_companion,
    load_document_companion_build,
    trajectory_status_line,
)
from substrate.event_log import default_events_dir

logger = logging.getLogger(__name__)

_PROJECT_UNAVAILABLE = (
    "project_scope_unavailable: no project aggregate exists until the "
    "workstation container lands (unit 3) — document scope ships first"
)


class EvidenceRowOut(BaseModel):
    evidence_id: str
    kind: str
    scope: str
    scope_id: str
    refs: list[str]
    tombstone: bool
    rebuilt_at: str


class EvidenceListOut(BaseModel):
    document_id: str
    rows: list[EvidenceRowOut]
    count: int


class ClaimDetail(BaseModel):
    node_ref: str
    kind: str
    """The claim text ONLY when the source document is servable — a withheld
    source's claim carries text=None (metadata only), the §9.0 rule at the
    evidence API too."""
    text: str | None


class EvidenceDetailOut(BaseModel):
    evidence_id: str
    kind: str
    scope: str
    scope_id: str
    refs: list[str]
    tombstone: bool
    rebuilt_at: str
    claim: ClaimDetail | None
    evidence: dict[str, Any] | None
    process: dict[str, Any] | None
    """A unit-8 derived bite's provenance detail (SPR-03) — class,
    byte-verification, core span refs, the investigation."""
    bite: dict[str, Any] | None
    """The tombstone honesty line (set when the row is tombstoned)."""
    note: str | None


def _resolve_bite(con: Any, row: EvidenceRow) -> dict[str, Any]:
    """Resolve a unit-8 bite row's provenance from the provenance store —
    the class, the byte-verification, the core span refs, the investigation.
    The bite's TEXT rides ONLY when the derived document serves its owner
    (the gate exercised on the derived id, never assumed)."""
    from substrate.books.serve_guard import serve_full_text_guarded

    bite_id = next(r for r in row.refs if r.startswith("bite:"))[5:]
    gen_ref = next((r for r in row.refs if r.startswith("generation:")), None)
    record_row = (
        con.execute(
            "SELECT source_document_id, prompt, model, mostly_generated "
            "FROM generation_records WHERE generation_id = ? LIMIT 1",
            [gen_ref[11:]],
        ).fetchone()
        if gen_ref
        else None
    )
    bite_row = con.execute(
        "SELECT ordinal, contribution_class, source_refs_json, "
        "investigation_id, derived_text_sha256, source_span_sha256 "
        "FROM bite_provenance WHERE bite_id = ? LIMIT 1",
        [bite_id],
    ).fetchone()
    if bite_row is None:
        return {"bite_ref": f"bite:{bite_id}", "gone": True}
    import json as _json

    source_refs = (
        None if bite_row[2] is None else [str(r) for r in _json.loads(str(bite_row[2]))]
    )
    # The bite's text: the derived document's bite-aligned chunk — only when
    # the owner lane lawfully serves it.
    text: str | None = None
    if serve_full_text_guarded(con, row.scope_id, owner=True).full_text is not None:
        chunk = con.execute(
            "SELECT text FROM chunks WHERE chunk_id = ? AND document_id = ? LIMIT 1",
            [f"{row.scope_id}-b{int(bite_row[0])}", row.scope_id],
        ).fetchone()
        text = None if chunk is None else str(chunk[0])
    return {
        "bite_ref": f"bite:{bite_id}",
        "ordinal": int(bite_row[0]),
        "contribution_class": str(bite_row[1]),
        "source_refs": source_refs,
        "investigation_id": None if bite_row[3] is None else str(bite_row[3]),
        "byte_verified": (
            str(bite_row[1]) == "author_verbatim"
            and bite_row[5] is not None
            and str(bite_row[4]) == str(bite_row[5])
        ),
        "text": text,
        "generation": (
            None
            if record_row is None
            else {
                "generation_id": gen_ref[11:] if gen_ref else None,
                "source_document_id": str(record_row[0]),
                "prompt": str(record_row[1]),
                "model": str(record_row[2]),
                "mostly_generated": bool(record_row[3]),
            }
        ),
    }


def _row_out(row: EvidenceRow) -> EvidenceRowOut:
    return EvidenceRowOut(
        evidence_id=row.evidence_id,
        kind=row.kind,
        scope=row.scope,
        scope_id=row.scope_id,
        refs=list(row.refs),
        tombstone=row.tombstone,
        rebuilt_at=row.rebuilt_at,
    )


def _document_for_owner(con: Any, document_id: str, owner: str) -> None:
    """The owner boundary at the document: a document that isn't the
    requester's is a 404, never a leak."""
    row = con.execute(
        "SELECT owner_user_id FROM documents WHERE document_id = ? LIMIT 1",
        [document_id],
    ).fetchone()
    if row is None or str(row[0]) != owner:
        raise HTTPException(status_code=404, detail="book_not_found")


def _withheld_reason(con: Any, document_id: str) -> str | None:
    """Whether the document's companion may be served NOW, by the reader's
    predicate (``servability_of`` over the class and the book's
    ``taken_down`` flag, as ``serve_full_text`` decides): "taken_down",
    "not_servable", or None when it may be served."""
    row = con.execute(
        "SELECT d.content_class, COALESCE(b.taken_down, FALSE) FROM documents d "
        "LEFT JOIN book_assets b ON b.document_id = d.document_id "
        "WHERE d.document_id = ? LIMIT 1",
        [document_id],
    ).fetchone()
    if row is None:
        return "not_servable"
    status = servability_of(
        None if row[0] is None else str(row[0]), taken_down=bool(row[1])
    )
    if status is ServabilityStatus.TAKEN_DOWN:
        return "taken_down"
    if not is_servable_full_text(status):
        return "not_servable"
    return None


def _serve_last_build(
    db: str, *, owner: str, document_id: str, format: Literal["html", "json"]
) -> Response:
    """Serve the requester's last persisted build, read-only.

    JSON: 200 with the payload plus ``state: "built"``; 200
    ``{document_id, state: "not_built"}`` when (owner, document) has no
    build; 200 ``{document_id, state: "withheld", reason}`` when the
    document is taken down or not servable now. HTML: the stored export, or
    404 ``companion_not_built`` / ``companion_withheld``. A foreign or
    missing document is the owner-boundary 404 first."""
    from fastapi.responses import HTMLResponse, JSONResponse

    from runtime.db_lock import connect_read

    con = connect_read(db)
    try:
        _document_for_owner(con, document_id, owner)
        withheld = _withheld_reason(con, document_id)
    finally:
        con.close()
    build = load_document_companion_build(owner_user_id=owner, document_id=document_id)
    if build is None:
        if format == "json":
            return JSONResponse({"document_id": document_id, "state": "not_built"})
        raise HTTPException(status_code=404, detail="companion_not_built")
    if withheld is not None:
        if format == "json":
            return JSONResponse(
                {"document_id": document_id, "state": "withheld", "reason": withheld}
            )
        raise HTTPException(status_code=404, detail="companion_withheld")
    headers = {
        "x-antiek-companion-generated": "true",
        "x-antiek-document-id": document_id,
        "x-antiek-rebuilt-at": build.rebuilt_at,
        "x-antiek-serving": "last-build",
    }
    if format == "json":
        return JSONResponse({**build.payload, "state": "built"}, headers=headers)
    return HTMLResponse(build.html, headers=headers)


def register_companion_routes(app: FastAPI) -> None:
    """Mount the companion + evidence routes. One call from create_app."""

    @app.get(
        "/documents/{document_id}/companion",
        tags=["companions"],
    )
    def get_document_companion(
        document_id: str, request: Request, format: Literal["html", "json"] = "html"
    ) -> Response:
        """The last build, never a rebuild (THREAD-CONTRACT §1.12: GET
        routes never write; a refresh is a POST). Before any build the JSON
        answer is 200 ``{"document_id", "state": "not_built"}`` (the rail
        shows an empty state rather than an error) and the HTML answer is
        404 ``companion_not_built``.

        The path comes from ``default_db_path``, not ``_resolve_db_path``:
        the latter's ``ensure_initialized`` takes the writer lock on a cold
        schema probe, and this GET never reaches the writer."""
        from substrate.graph import default_db_path

        owner = _reader_owner_id(request)
        return _serve_last_build(
            default_db_path(), owner=owner, document_id=document_id, format=format
        )

    @app.post(
        "/documents/{document_id}/companion/refresh",
        tags=["companions"],
    )
    def refresh_document_companion(document_id: str, request: Request) -> Response:
        """Rebuild the requester's companion of the document under the
        writer lock and answer what the next GET serves (JSON). A failed
        rebuild keeps the previous build and answers 503
        ``companion_rebuild_failed`` with the error's type only."""
        from fastapi.responses import JSONResponse

        from runtime.db_lock import connect_read

        owner = _reader_owner_id(request)
        db = _resolve_db_path()
        con = connect_read(db)
        try:
            _document_for_owner(con, document_id, owner)
        finally:
            con.close()
        try:
            export_document_companion(
                db,
                owner_user_id=owner,
                document_id=document_id,
                evict_other_owners=True,
            )
        except CompanionOwnerChanged:
            raise HTTPException(status_code=404, detail="book_not_found") from None
        except Exception as e:
            logger.warning(
                "companion refresh failed for %s", document_id, exc_info=True
            )
            has_last_build = (
                load_document_companion_build(
                    owner_user_id=owner, document_id=document_id
                )
                is not None
            )
            return JSONResponse(
                {
                    "detail": "companion_rebuild_failed",
                    "error_type": type(e).__name__,
                    "has_last_build": has_last_build,
                },
                status_code=503,
            )
        return _serve_last_build(db, owner=owner, document_id=document_id, format="json")

    @app.get(
        "/documents/{document_id}/evidence",
        response_model=EvidenceListOut,
        tags=["companions"],
    )
    def list_document_evidence(
        document_id: str,
        request: Request,
        kind: str | None = None,
        q: str | None = None,
    ) -> EvidenceListOut:
        from runtime.db_lock import connect_read

        owner = _reader_owner_id(request)
        db = _resolve_db_path()
        con = connect_read(db)
        try:
            _document_for_owner(con, document_id, owner)
            rows = read_scope(
                con, owner_user_id=owner, scope="document", scope_id=document_id
            )
        finally:
            con.close()
        if kind is not None:
            if kind not in KINDS:
                raise HTTPException(
                    status_code=422,
                    detail=f"evidence_kind_invalid: one of {', '.join(KINDS)}",
                )
            rows = [r for r in rows if r.kind == kind]
        if q is not None and q.strip():
            needle = q.strip().lower()
            # Structured filtering only — over REFS (the index is refs-only;
            # there is no text to search).
            rows = [r for r in rows if any(needle in ref.lower() for ref in r.refs)]
        return EvidenceListOut(
            document_id=document_id,
            rows=[_row_out(r) for r in rows],
            count=len(rows),
        )

    @app.get(
        "/evidence/{evidence_id}",
        response_model=EvidenceDetailOut,
        tags=["companions"],
    )
    def get_evidence(evidence_id: str, request: Request) -> EvidenceDetailOut:
        from runtime.db_lock import connect_read

        owner = _reader_owner_id(request)
        db = _resolve_db_path()
        con = connect_read(db)
        try:
            row = resolve(con, evidence_id)
            if row is None or row.owner_user_id != owner:
                raise HTTPException(status_code=404, detail="evidence_not_found")
            claim = None
            evidence = None
            process = None
            bite = None
            bite_ref = next((r for r in row.refs if r.startswith("bite:")), None)
            if bite_ref is not None:
                # A unit-8 derived bite: resolve its provenance from the
                # store (consumed, never re-derived). The bite's TEXT rides
                # ONLY when the derived document serves its owner (the gate
                # exercised, never assumed).
                bite = _resolve_bite(con, row)
            elif row.kind == "claim":
                node_ref = next((r for r in row.refs if r.startswith("node:")), None)
                node_id = node_ref[5:] if node_ref else None
                node = (
                    con.execute(
                        "SELECT node_type, canonical_label FROM nodes WHERE node_id = ? LIMIT 1",
                        [node_id],
                    ).fetchone()
                    if node_id
                    else None
                )
                from substrate.books.highlights.resolve import document_servable

                servable = document_servable(con, row.scope_id)
                claim = ClaimDetail(
                    node_ref=node_ref or "",
                    kind=str(node[0]) if node else "unknown",
                    text=(str(node[1]) if node and servable else None),
                )
            elif row.kind == "evidence":
                anchor_ref = next((r for r in row.refs if r.startswith("anchor:")), None)
                anchor = (
                    con.execute(
                        "SELECT status FROM anchored_highlights WHERE anchor_id = ? LIMIT 1",
                        [anchor_ref[7:]],
                    ).fetchone()
                    if anchor_ref
                    else None
                )
                evidence = {
                    "anchor_ref": anchor_ref or "",
                    "status": str(anchor[0]) if anchor else "gone",
                }
            elif row.kind == "process":
                inv_ref = next(
                    (r for r in row.refs if r.startswith("investigation:")), None
                )
                process = {
                    "ref": inv_ref or (row.refs[0] if row.refs else ""),
                    "status_line": (
                        trajectory_status_line(default_events_dir(), inv_ref[14:])
                        if inv_ref
                        else "on record"
                    ),
                }
        finally:
            con.close()
        return EvidenceDetailOut(
            evidence_id=row.evidence_id,
            kind=row.kind,
            scope=row.scope,
            scope_id=row.scope_id,
            refs=list(row.refs),
            tombstone=row.tombstone,
            rebuilt_at=row.rebuilt_at,
            claim=claim,
            evidence=evidence,
            process=process,
            bite=bite,
            note=(
                "The source this evidence traced is gone — this row is an "
                "honest tombstone: the id still resolves, the content stays "
                "with its (vanished) source."
                if row.tombstone
                else None
            ),
        )

    @app.get("/projects/{project_id}/companion", tags=["companions"])
    def get_project_companion(project_id: str, request: Request) -> None:
        _reader_owner_id(request)
        raise HTTPException(status_code=501, detail=_PROJECT_UNAVAILABLE)

    @app.get("/projects/{project_id}/evidence", tags=["companions"])
    def get_project_evidence(project_id: str, request: Request) -> None:
        _reader_owner_id(request)
        raise HTTPException(status_code=501, detail=_PROJECT_UNAVAILABLE)
