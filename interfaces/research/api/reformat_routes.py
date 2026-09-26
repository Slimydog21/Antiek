"""Reformat routes (reformat-provenance SPR-02) — the generation call + the
provenance read.

POST /books/{id}/reformats — run the pipeline (substrate/reformat/
pipeline.py, the ONLY provenance writer) for the owner: prompt + mode → a
generation record + the derived document. Owner-scoped per the books.py:140
convention; the pipeline's own refusals (a gated source, an unclassable
generation) surface as honest 422s, never fabricated output.

GET /documents/{id}/provenance — the generation record + per-bite
provenance for a DERIVED document (404 for a plain document — no
generation record, honestly). The review surface renders THIS (structured
content, never generated HTML). Per-bite source page hints resolve
server-side (the anchor chain's chunk → page), so the trace jump is one
click to the core passage.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from interfaces.research.api.books import _reader_owner_id, _resolve_db_path
from substrate.books.page_anchor import page_index_from_section_path
from substrate.provenance.store import ProvenanceStore
from substrate.reformat.pipeline import ReformatError, reformat_document


class ReformatIn(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)
    mode: Literal["time_window", "themes"] = "time_window"
    model: str | None = None


class ReformatOut(BaseModel):
    generation_id: str
    derived_document_id: str
    """The generation thread — the engagement that STAYS in the pane (the
    pipeline's dispatch events carry it)."""
    thread_id: str
    bite_count: int
    contribution_classes: list[str]
    mostly_generated: bool
    reclassed_verbatim: int
    null_source_share: float


class ProvenanceBiteOut(BaseModel):
    bite_id: str
    ordinal: int
    contribution_class: str
    """The unit-1 anchor payloads into the CORE document (None = the honest
    no-direct-source connective tissue)."""
    source_refs: list[dict[str, Any]] | None
    """The core PASSAGE's page per source ref (server-resolved — the trace
    jump is one click)."""
    source_page_hints: list[int | None]
    investigation_id: str | None
    byte_verified: bool


class ProvenanceOut(BaseModel):
    document_id: str
    generation: dict[str, Any]
    bites: list[ProvenanceBiteOut]


class PassageOut(BaseModel):
    """The gate-served core snippet (SPR-03's pull-a-snippet): the passage
    text when the owner lane serves it, else METADATA ONLY — a withheld
    source's probe carries position, never body (the §9.0 rule)."""
    servable: bool
    text: str | None
    page_index_hint: int | None
    chunk_id: str
    start_scalar: int
    end_scalar: int


def register_reformat_routes(app: FastAPI) -> None:
    """Mount the reformat routes. One call from create_app."""

    @app.post(
        "/books/{document_id}/reformats",
        response_model=ReformatOut,
        status_code=201,
        tags=["books", "reformat"],
    )
    def post_reformat(
        document_id: str, body: ReformatIn, request: Request
    ) -> ReformatOut:
        owner = _reader_owner_id(request)
        db = _resolve_db_path()
        # The writer is owner-scoped, exactly like its sibling routes: a
        # caller may only reformat a document they own (never another
        # owner's personal_reading body through the pipeline's owner path).
        from runtime.db_lock import connect_read

        con = connect_read(db)
        try:
            doc = con.execute(
                "SELECT owner_user_id FROM documents WHERE document_id = ? LIMIT 1",
                [document_id],
            ).fetchone()
        finally:
            con.close()
        if doc is None or str(doc[0]) != owner:
            raise HTTPException(status_code=404, detail="book_not_found")
        # The test seam: the pipeline's generator is injectable (the SpawnFn
        # precedent) — a route-level override for tests, the dispatch path by
        # default.
        from interfaces.research.api import reformat_routes as _self

        try:
            result = reformat_document(
                db,
                owner_user_id=owner,
                source_document_id=document_id,
                prompt=body.prompt,
                mode=body.mode,
                model=body.model or "operator-default",
                generate_fn=_self._generate_fn_override,
            )
        except ReformatError as e:
            raise HTTPException(status_code=422, detail=str(e)) from e
        return ReformatOut(
            generation_id=result.generation_id,
            derived_document_id=result.derived_document_id,
            thread_id=f"reformat:{result.generation_id}",
            bite_count=len(result.bite_ids),
            contribution_classes=result.contribution_classes,
            mostly_generated=result.mostly_generated,
            reclassed_verbatim=result.reclassed_verbatim,
            null_source_share=result.null_source_share,
        )

    @app.get(
        "/documents/{document_id}/provenance",
        response_model=ProvenanceOut,
        tags=["companions", "provenance"],
    )
    def get_provenance(document_id: str, request: Request) -> ProvenanceOut:
        from runtime.db_lock import connect_read

        owner = _reader_owner_id(request)
        db = _resolve_db_path()
        con = connect_read(db)
        try:
            doc = con.execute(
                "SELECT owner_user_id FROM documents WHERE document_id = ? LIMIT 1",
                [document_id],
            ).fetchone()
            if doc is None or str(doc[0]) != owner:
                raise HTTPException(status_code=404, detail="book_not_found")
            record_row = con.execute(
                "SELECT generation_id FROM generation_records "
                "WHERE derived_document_id = ? LIMIT 1",
                [document_id],
            ).fetchone() if _table(con, "generation_records") else None
            if record_row is None:
                raise HTTPException(
                    status_code=404,
                    detail="provenance_not_found: not a derived document",
                )
            store = ProvenanceStore()
            record = store.get_generation(con, str(record_row[0]))
            if record is None:  # the FK guarantees it — refuse loudly if not
                raise HTTPException(
                    status_code=500, detail="provenance_record_missing"
                )
            source_title_row = con.execute(
                "SELECT title FROM documents WHERE document_id = ? LIMIT 1",
                [record.source_document_id],
            ).fetchone()
            source_title = (
                None if source_title_row is None or source_title_row[0] is None
                else str(source_title_row[0])
            )
            bites = store.bites_for_generation(con, record.generation_id)
            out_bites = []
            for bite in bites:
                refs = (
                    None
                    if bite.source_refs is None
                    else [json_loads(r) for r in bite.source_refs]
                )
                hints: list[int | None] = []
                if refs:
                    for ref in refs:
                        section = con.execute(
                            "SELECT section_path FROM chunks WHERE chunk_id = ? "
                            "AND document_id = ? LIMIT 1",
                            [ref.get("node_id"), record.source_document_id],
                        ).fetchone()
                        hints.append(
                            page_index_from_section_path(
                                None if section is None else str(section[0])
                            )
                        )
                out_bites.append(
                    ProvenanceBiteOut(
                        bite_id=bite.bite_id,
                        ordinal=bite.ordinal,
                        contribution_class=bite.contribution_class,
                        source_refs=refs,
                        source_page_hints=hints,
                        investigation_id=bite.investigation_id,
                        byte_verified=(
                            bite.contribution_class == "author_verbatim"
                            and bite.source_span_sha256 is not None
                            and bite.derived_text_sha256 == bite.source_span_sha256
                        ),
                    )
                )
        finally:
            con.close()
        return ProvenanceOut(
            document_id=document_id,
            generation={
                "generation_id": record.generation_id,
                "source_document_id": record.source_document_id,
                "source_title": source_title,
                "prompt": record.prompt,
                "model": record.model,
                "params": json_loads(record.params_json),
                "mostly_generated": record.mostly_generated,
                "created_at": record.created_at,
            },
            bites=out_bites,
        )


    @app.get(
        "/books/{document_id}/passage",
        response_model=PassageOut,
        tags=["books", "reformat"],
    )
    def get_passage(
        document_id: str,
        request: Request,
        chunk_id: str,
        start_scalar: int,
        end_scalar: int,
    ) -> PassageOut:
        """The pull-a-snippet probe (SPR-03): the core document's passage,
        GATE-SERVED (the owner lane — the probe surface is owner-scoped);
        a withheld source's probe carries position, NEVER body."""
        # A client-supplied span is chunk-relative and may never reach
        # outside the chunk it names: negative wrap-around, an inverted
        # span, or overshoot past the chunk body is a client error, never
        # silent beyond-chunk text (the citation substrate contract).
        if start_scalar < 0 or end_scalar <= start_scalar:
            raise HTTPException(status_code=422, detail="passage_span_invalid")
        from runtime.db_lock import connect_read
        from substrate.books.serve_guard import serve_full_text_guarded

        owner = _reader_owner_id(request)
        db = _resolve_db_path()
        con = connect_read(db)
        try:
            doc = con.execute(
                "SELECT owner_user_id FROM documents WHERE document_id = ? LIMIT 1",
                [document_id],
            ).fetchone()
            if doc is None or str(doc[0]) != owner:
                raise HTTPException(status_code=404, detail="book_not_found")
            chunk = con.execute(
                "SELECT section_path FROM chunks WHERE chunk_id = ? "
                "AND document_id = ? LIMIT 1",
                [chunk_id, document_id],
            ).fetchone()
            if chunk is None:
                raise HTTPException(status_code=404, detail="passage_not_found")
            served = serve_full_text_guarded(con, document_id, owner=True)
            hint = page_index_from_section_path(
                None if chunk[0] is None else str(chunk[0])
            )
            text: str | None = None
            if served.full_text is not None:
                from substrate.feedback.domain import normalize_node_text

                normalized = normalize_node_text(served.full_text)
                # The span resolves chunk-relative through the anchor-map —
                # the SAME normalized scalar space the anchors use.
                from substrate.books.highlights.anchor_map import build_anchor_map

                anchor_map = build_anchor_map(
                    con, document_id=document_id, served_text=normalized
                )
                chunk_map = next(
                    (c for c in anchor_map.chunks if c.chunk_id == chunk_id), None
                )
                if chunk_map is None:
                    # The chunk row exists but did not locate in the served
                    # body: the span cannot be resolved, so say so — never
                    # servable-with-null-text, which misreads as withheld.
                    raise HTTPException(status_code=404, detail="passage_not_found")
                body_length = chunk_map.body_end - chunk_map.body_start
                if end_scalar > body_length:
                    raise HTTPException(status_code=422, detail="passage_span_invalid")
                text = normalized[
                    chunk_map.body_start + start_scalar : chunk_map.body_start + end_scalar
                ]
        finally:
            con.close()
        return PassageOut(
            servable=served.full_text is not None,
            text=text,
            page_index_hint=hint,
            chunk_id=chunk_id,
            start_scalar=start_scalar,
            end_scalar=end_scalar,
        )


def _table(con: Any, name: str) -> bool:
    row = con.execute(
        "SELECT 1 FROM duckdb_tables() WHERE table_name = ? LIMIT 1", [name]
    ).fetchone()
    return row is not None


def json_loads(raw: str) -> Any:
    import json

    return json.loads(raw)


#: The test seam (the SpawnFn precedent): tests inject a deterministic
#: generator here; production leaves it None (the dispatch path).
_generate_fn_override: Any = None
