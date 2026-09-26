"""Companion + evidence-base routes (companions SPR-02) — the surfaces.

GET /documents/{id}/companion        — the rendered narrative (HTML with the
                                       honesty headers) or its STRUCTURED
                                       payload (?format=json) — the rail and
                                       agents render the payload, NEVER raw
                                       generated HTML (the sanctioned-
                                       rendering discipline: no innerHTML of
                                       generated content anywhere);
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
owner isn't the requester is a 404, never a leak. Rebuild-on-read follows
the anchors' reanchor-on-read precedent (book_anchor_routes.py): the write
scope is the projector's bounded rebuild, then the read serves.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel

from interfaces.research.api.books import _reader_owner_id, _resolve_db_path
from substrate.companions.evidence_index import (
    KINDS,
    EvidenceRow,
    read_scope,
    resolve,
)
from substrate.companions.projector import (
    document_companion_payload,
    export_document_companion,
    rebuild_document_full,
    trajectory_status_line,
)
from substrate.event_log import default_events_dir

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
    """The tombstone honesty line (set when the row is tombstoned)."""
    note: str | None


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


def register_companion_routes(app: FastAPI) -> None:
    """Mount the companion + evidence routes. One call from create_app."""

    @app.get(
        "/documents/{document_id}/companion",
        tags=["companions"],
    )
    def get_document_companion(
        document_id: str, request: Request, format: Literal["html", "json"] = "html"
    ) -> Response:
        from fastapi.responses import HTMLResponse, JSONResponse

        from runtime.db_lock import connect_read

        owner = _reader_owner_id(request)
        db = _resolve_db_path()
        con = connect_read(db)
        try:
            _document_for_owner(con, document_id, owner)
        finally:
            con.close()
        if format == "json":
            # The structured payload (the sanctioned rendering input) — the
            # stamp rides the payload AND the header. Rebuild-on-read (the
            # anchors' reanchor-on-read precedent): the projector's bounded
            # write scope, then the serve.
            _html, view = rebuild_document_full(
                db, owner_user_id=owner, document_id=document_id
            )
            return JSONResponse(
                document_companion_payload(view),
                headers={
                    "x-antiek-companion-generated": "true",
                    "x-antiek-document-id": document_id,
                    "x-antiek-rebuilt-at": view.rebuilt_at,
                },
            )
        # The HTML export lands beside the research artifacts with its
        # honesty header (paths.py conventions). LAST-GOOD SERVING
        # (SPR-03): a failed rebuild NEVER serves a half-written companion
        # — the previous export is lawful to show, with the failure named
        # in the header.
        try:
            html, _out_path, stamp = export_document_companion(
                db, owner_user_id=owner, document_id=document_id
            )
            return HTMLResponse(
                html,
                headers={
                    "x-antiek-companion-generated": "true",
                    "x-antiek-document-id": document_id,
                    "x-antiek-rebuilt-at": stamp,
                },
            )
        except Exception as e:
            from substrate.research_artifact.paths import (
                companion_path_for,
                read_bounded_nofollow,
            )

            last_good = companion_path_for(document_id)
            if not last_good.exists():
                raise HTTPException(
                    status_code=500,
                    detail=f"companion_rebuild_failed: {type(e).__name__}",
                ) from e
            # The previous generation, served honestly as stale.
            body = read_bounded_nofollow(last_good, limit=8 * 1024 * 1024).decode(
                "utf-8"
            )
            return HTMLResponse(
                body,
                headers={
                    "x-antiek-companion-generated": "true",
                    "x-antiek-document-id": document_id,
                    "x-antiek-rebuild-failed": type(e).__name__,
                    "x-antiek-serving": "last-good",
                },
            )

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
            if row.kind == "claim":
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
