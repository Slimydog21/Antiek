"""Owner-bound API for canonical HTML-native hosted documents."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from services.hosted_documents import HostAuthorization, ingest_hosted_document
from services.hosted_documents.events import emit_document_loaded as _emit_document_loaded
from substrate.marketplace_host import project_hosted_book_html
from substrate.marketplace_host.library import HostStore

from .marketplace_host_routes import get_marketplace_host_store

hosted_document_router = APIRouter(prefix="/hosted-documents", tags=["hosted-documents"])
HOSTED_HTML_PROJECTION_VERSION = "hosted-html-projection-v1"


class HostedDocumentIngestBody(BaseModel):
    content_b64: str = Field(min_length=1)
    source_format: str = Field(min_length=1, max_length=16)
    investigation_id: str = Field(min_length=1, max_length=200)
    title: str | None = Field(default=None, max_length=500)
    source_uri: str | None = Field(default=None, max_length=2_000)
    intent: Literal["user_owned"] = "user_owned"


class CitationPositionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    citation_evidence: dict[str, Any]
    index: int = Field(ge=0, le=63)
    anchor_count: int = Field(ge=1, le=64)
    mutation_key: str = Field(min_length=1, max_length=512)


def _no_store_error(status_code: int, detail: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail=detail, headers={"Cache-Control": "no-store"})


def _citation_document_authority(document_id: str, owner_id: str):
    import duckdb

    from substrate.graph import default_db_path
    from substrate.investigation_streams import InvestigationStreamUnbound
    from substrate.investigation_tenancy import (
        InvestigationAuthority,
        InvestigationOwnershipConflict,
    )
    from substrate.legal_gate.read import (
        LegalPolicyDenied,
        document_investigation_hint,
        read_document,
    )

    try:
        con = duckdb.connect(default_db_path(), read_only=True)
    except duckdb.IOException as exc:
        raise _no_store_error(503, "citation position durability unavailable") from exc
    try:
        investigation_id = document_investigation_hint(con, document_id)
        if not investigation_id:
            raise _no_store_error(404, "cited evidence is unavailable")
        authority = InvestigationAuthority(owner_id, investigation_id)
        read_document(con, authority, document_id)
        return authority
    except (InvestigationStreamUnbound, InvestigationOwnershipConflict, LegalPolicyDenied):
        raise _no_store_error(404, "cited evidence is unavailable") from None
    except duckdb.Error as exc:
        raise _no_store_error(503, "citation position durability unavailable") from exc
    finally:
        con.close()


def _request_owner(request: Request) -> str:
    owner_id = str(getattr(request.state, "user_id", "") or "").strip()
    if not owner_id:
        raise HTTPException(
            status_code=503,
            detail="authenticated request identity is unavailable",
        )
    return owner_id


def _request_account(request: Request) -> str:
    """Use the authenticated claims object as the sole durable account source."""
    from substrate.multi_user.auth import UserClaims

    claims = getattr(request.state, "user_claims", None)
    if not isinstance(claims, UserClaims):
        raise _no_store_error(404, "cited evidence is unavailable")
    return claims.user_id


def _projection_hash(html: str) -> str:
    return "sha256:" + hashlib.sha256(html.encode()).hexdigest()


def _acknowledge_projection(document_id: str, html: str, *, store: HostStore) -> dict[str, Any]:
    doc = store.get_document(document_id)
    if doc is None:
        raise RuntimeError("hosted document disappeared before projection acknowledgement")
    projection_hash = _projection_hash(html)
    if (
        doc.get("projection_state") == "ready"
        and doc.get("projection_hash") == projection_hash
        and doc.get("projection_version") == HOSTED_HTML_PROJECTION_VERSION
    ):
        return doc
    doc["projection_state"] = "ready"
    doc["projection_hash"] = projection_hash
    doc["projection_version"] = HOSTED_HTML_PROJECTION_VERSION
    try:
        store.put_document(document_id, doc)
    except OSError as exc:
        raise RuntimeError("hosted HTML projection checkpoint failed") from exc
    return doc


def _receipt_fields(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_event_id": doc.get("document_loaded_event_id"),
        "author": doc.get("author"),
        "page_count": doc.get("page_count"),
        "word_count": doc.get("word_count"),
        "projection_state": doc.get("projection_state")
        or ("non_viewable" if doc.get("state") == "non_viewable" else "pending"),
        "projection_hash": doc.get("projection_hash"),
        "projection_version": doc.get("projection_version"),
        "extraction_receipt": {
            "extractor_version": doc.get("extractor_version"),
            "source_byte_hash": doc.get("source_byte_hash"),
            "extracted_content_hash": doc.get("extracted_content_hash"),
            "canonical_content_hash": doc.get("canonical_content_hash"),
            "source_format": doc.get("source_format"),
            "word_count": doc.get("word_count"),
            "minimum_viewable_words": doc.get("minimum_viewable_words"),
            "truncated": bool(doc.get("truncated")),
            "viewable": doc.get("state") == "ready",
            "non_viewable_reason": doc.get("non_viewable_reason"),
        },
    }


def _chunk_anchor_id(chunk_id: str) -> str:
    return "antiek-chunk-" + hashlib.sha256(chunk_id.encode()).hexdigest()


def resolve_citation_evidence_groups(
    chunk_ids: list[str],
    *,
    owner_id: str,
    source_asset_id: str,
    claim_id: str,
) -> tuple[Any, ...]:
    """Resolve exact ordered chunks into existing one-document receipts.

    The returned digest is identity, not authority. Hosted HTML re-runs the
    legal read for every group. Groups larger than CitationEvidence's closed
    64-chunk bound are deterministically partitioned without reordering.
    """
    if (
        not chunk_ids
        or len(chunk_ids) > 1000
        or len(set(chunk_ids)) != len(chunk_ids)
        or any(
            not value
            or value != value.strip()
            or len(value.encode()) > 512
            or any(ord(character) < 0x20 or ord(character) == 0x7F for character in value)
            for value in chunk_ids
        )
    ):
        raise _no_store_error(404, "cited evidence is unavailable")
    import duckdb

    from substrate.engagement_spine.citation_evidence import parse_citation_evidence
    from substrate.graph import default_db_path
    from substrate.investigation_streams import InvestigationStreamUnbound
    from substrate.investigation_tenancy import (
        InvestigationAuthority,
        InvestigationOwnershipConflict,
    )
    from substrate.legal_gate.read import LegalPolicyDenied, read_chunks

    try:
        con = duckdb.connect(default_db_path(), read_only=True)
    except duckdb.IOException as exc:
        raise _no_store_error(503, "citation authority unavailable") from exc
    try:
        placeholders = ",".join("?" for _ in chunk_ids)
        rows = con.execute(
            "SELECT c.chunk_id, c.document_id, d.investigation_id FROM chunks c "
            "JOIN documents d ON d.document_id = c.document_id "
            f"WHERE c.chunk_id IN ({placeholders})",
            chunk_ids,
        ).fetchall()
        hints = {str(row[0]): (str(row[1]), str(row[2] or "")) for row in rows}
        if len(hints) != len(chunk_ids) or any(chunk_id not in hints for chunk_id in chunk_ids):
            raise _no_store_error(404, "cited evidence is unavailable")
        grouped: dict[str, list[str]] = {}
        investigation_by_document: dict[str, str] = {}
        for chunk_id in chunk_ids:
            document_id, investigation_id = hints[chunk_id]
            if not document_id or not investigation_id:
                raise _no_store_error(404, "cited evidence is unavailable")
            prior = investigation_by_document.setdefault(document_id, investigation_id)
            if prior != investigation_id:
                raise _no_store_error(404, "cited evidence is unavailable")
            grouped.setdefault(document_id, []).append(chunk_id)
        out: list[Any] = []
        for document_id, selected_ids in grouped.items():
            authority = InvestigationAuthority(owner_id, investigation_by_document[document_id])
            readable = {str(item["chunk_id"]) for item in read_chunks(con, authority, document_id)}
            if any(chunk_id not in readable for chunk_id in selected_ids):
                raise _no_store_error(404, "cited evidence is unavailable")
            for offset in range(0, len(selected_ids), 64):
                evidence = parse_citation_evidence({
                    "source_kind": "synthesis_claim",
                    "source_asset_id": source_asset_id,
                    "claim_id": claim_id,
                    "chunk_ids": selected_ids[offset:offset + 64],
                    "document_id": document_id,
                })
                assert evidence is not None
                out.append(evidence)
        return tuple(out)
    except (InvestigationStreamUnbound, InvestigationOwnershipConflict, LegalPolicyDenied, ValueError):
        raise _no_store_error(404, "cited evidence is unavailable") from None
    except duckdb.Error as exc:
        raise _no_store_error(503, "citation authority unavailable") from exc
    finally:
        con.close()


def _legal_citation_payload(
    document_id: str, chunk_ids: list[str], *, owner_id: str
) -> dict[str, Any]:
    if (
        not chunk_ids
        or len(chunk_ids) > 64
        or len(set(chunk_ids)) != len(chunk_ids)
        or any(
            not value
            or value != value.strip()
            or len(value.encode()) > 512
            or any(ord(character) < 0x20 or ord(character) == 0x7F for character in value)
            for value in chunk_ids
        )
    ):
        raise HTTPException(status_code=404, detail="cited evidence is unavailable")
    import duckdb

    from substrate.engagement_spine.project import project_to_html
    from substrate.graph import default_db_path
    from substrate.investigation_streams import InvestigationStreamUnbound
    from substrate.investigation_tenancy import (
        InvestigationAuthority,
        InvestigationOwnershipConflict,
    )
    from substrate.legal_gate.read import (
        LegalPolicyDenied,
        document_investigation_hint,
        read_chunks,
        read_document,
    )

    try:
        con = duckdb.connect(default_db_path(), read_only=True)
    except duckdb.IOException as exc:
        raise HTTPException(status_code=503, detail="citation authority unavailable") from exc
    try:
        investigation_id = document_investigation_hint(con, document_id)
        if not investigation_id:
            raise HTTPException(status_code=404, detail="cited evidence is unavailable")
        authority = InvestigationAuthority(owner_id, investigation_id)
        try:
            document = read_document(con, authority, document_id)
            chunks = read_chunks(con, authority, document_id)
        except (
            InvestigationStreamUnbound,
            InvestigationOwnershipConflict,
            LegalPolicyDenied,
        ) as exc:
            raise HTTPException(status_code=404, detail="cited evidence is unavailable") from exc
    except duckdb.Error as exc:
        raise HTTPException(status_code=503, detail="citation authority unavailable") from exc
    finally:
        con.close()
    by_id = {str(item["chunk_id"]): item for item in chunks}
    if any(chunk_id not in by_id for chunk_id in chunk_ids):
        raise HTTPException(status_code=404, detail="cited evidence is unavailable")
    content = [
        {
            "type": "paragraph",
            "attrs": {"anchor_id": _chunk_anchor_id(str(item["chunk_id"]))},
            "content": [{"type": "text", "text": str(item["text"])}],
        }
        for item in chunks
    ]
    html = project_to_html(
        {"type": "doc", "content": content},
        document_id=document_id,
        creator="legal_citation_projection",
    )
    raw_text = str(document["raw_text"])
    return {
        "document_id": document_id,
        "owner_id": owner_id,
        "state": "ready",
        "source_byte_hash": "sha256:" + hashlib.sha256(raw_text.encode()).hexdigest(),
        "canonical_content_hash": hashlib.sha256(raw_text.encode()).hexdigest(),
        "source_format": str(document.get("document_type") or "text"),
        "view_format": "html",
        "html": html,
        "title": document.get("title") or document_id,
        "document_loaded_event_id": None,
        "already_hosted": True,
        "non_viewable_reason": None,
        "source_event_id": None,
        "author": document.get("author"),
        "page_count": None,
        "word_count": len(raw_text.split()),
        "projection_state": "ready",
        "projection_hash": _projection_hash(html),
        "projection_version": "legal-citation-html-v1",
        "extraction_receipt": {
            "extractor_version": "legal-sealed-chunk-manifest-v1",
            "source_byte_hash": "sha256:" + hashlib.sha256(raw_text.encode()).hexdigest(),
            "extracted_content_hash": hashlib.sha256(raw_text.encode()).hexdigest(),
            "canonical_content_hash": hashlib.sha256(raw_text.encode()).hexdigest(),
            "source_format": str(document.get("document_type") or "text"),
            "word_count": len(raw_text.split()),
            "minimum_viewable_words": 1,
            "truncated": False,
            "viewable": True,
            "non_viewable_reason": None,
        },
        "chunk_anchors": [
            {"chunk_id": chunk_id, "anchor_id": _chunk_anchor_id(chunk_id)}
            for chunk_id in chunk_ids
        ],
    }


def resolve_legal_citation_insertion_source(
    document_id: str, chunk_ids: list[str], *, owner_id: str, con: Any | None = None,
) -> tuple[str, str, str]:
    """Return current title, full source hash, and exact ordered sealed excerpt."""
    if (not chunk_ids or len(chunk_ids) > 64 or len(set(chunk_ids)) != len(chunk_ids)
            or any(not item or item != item.strip() or len(item.encode()) > 512
                   for item in chunk_ids)):
        raise _no_store_error(404, "cited evidence is unavailable")
    import duckdb

    from substrate.graph import default_db_path
    from substrate.investigation_streams import InvestigationStreamUnbound
    from substrate.investigation_tenancy import (
        InvestigationAuthority,
        InvestigationOwnershipConflict,
    )
    from substrate.legal_gate.read import (
        LegalPolicyDenied,
        document_investigation_hint,
        read_chunks,
        read_document,
    )

    owned_connection = con is None
    if owned_connection:
        try:
            con = duckdb.connect(default_db_path(), read_only=True)
        except duckdb.IOException as exc:
            raise _no_store_error(503, "citation authority unavailable") from exc
    assert con is not None
    try:
        investigation_id = document_investigation_hint(con, document_id)
        if not investigation_id:
            raise _no_store_error(404, "cited evidence is unavailable")
        authority = InvestigationAuthority(owner_id, investigation_id)
        document = read_document(con, authority, document_id)
        chunks = read_chunks(con, authority, document_id)
    except (InvestigationStreamUnbound, InvestigationOwnershipConflict, LegalPolicyDenied):
        raise _no_store_error(404, "cited evidence is unavailable") from None
    except duckdb.Error as exc:
        raise _no_store_error(503, "citation authority unavailable") from exc
    finally:
        if owned_connection:
            con.close()
    by_id = {str(item["chunk_id"]): item for item in chunks}
    if any(item not in by_id for item in chunk_ids):
        raise _no_store_error(404, "cited evidence is unavailable")
    raw_text = str(document["raw_text"])
    title = str(document.get("title") or document_id).strip()
    excerpt = "\n\n".join(str(by_id[item]["text"]) for item in chunk_ids)
    if not title or not excerpt.strip():
        raise _no_store_error(404, "cited evidence is unavailable")
    return title, hashlib.sha256(raw_text.encode()).hexdigest(), excerpt


def _payload(result: Any, *, store: HostStore) -> dict[str, Any]:
    out = {
        "document_id": result.document_id,
        "owner_id": result.owner_id,
        "state": result.state,
        "source_byte_hash": result.source_byte_hash,
        "canonical_content_hash": result.canonical_content_hash,
        "source_format": result.source_format,
        "title": result.title,
        "document_loaded_event_id": result.document_loaded_event_id,
        "already_hosted": result.already_hosted,
        "non_viewable_reason": result.non_viewable_reason,
        "view_format": "html",
        "intent": "user_owned",
        "html": None,
    }
    if result.state == "ready":
        html = project_hosted_book_html(
            result.document_id,
            store=store,
        )
        out["html"] = html
        doc = _acknowledge_projection(result.document_id, html, store=store)
    else:
        doc = store.get_document(result.document_id) or {}
    out.update(_receipt_fields(doc))
    return out


@hosted_document_router.post("/ingest")
def post_hosted_document(body: HostedDocumentIngestBody, request: Request) -> dict[str, Any]:
    owner_id = _request_owner(request)
    store = get_marketplace_host_store(request)
    try:
        raw = base64.b64decode(body.content_b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=400, detail="content_b64 is not valid base64") from exc
    try:
        result = ingest_hosted_document(
            owner_id=owner_id,
            raw=raw,
            source_format=body.source_format,
            store=store,
            authorization=HostAuthorization("private_upload"),
            emit_document_loaded=_emit_document_loaded,
            investigation_id=body.investigation_id,
            title=body.title,
            source_uri=body.source_uri,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (KeyError, RuntimeError, TypeError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    try:
        return _payload(result, store=store)
    except (KeyError, RuntimeError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@hosted_document_router.get("/{document_id}/html")
def get_hosted_document_html(
    document_id: str,
    request: Request,
    response: Response,
    citation_chunk_id: list[str] = Query(default=[]),
) -> dict[str, Any]:
    response.headers["Cache-Control"] = "private, no-store"
    owner_id = _request_owner(request)
    if citation_chunk_id:
        try:
            return _legal_citation_payload(document_id, citation_chunk_id, owner_id=owner_id)
        except HTTPException as exc:
            headers = dict(exc.headers or {})
            headers["Cache-Control"] = "private, no-store"
            exc.headers = headers
            raise exc from None
    store = get_marketplace_host_store(request)
    doc = store.get_document(document_id)
    if doc is None:
        raise _no_store_error(404, "hosted document was not found")
    if str(doc.get("owner_id") or "") != owner_id:
        raise _no_store_error(403, "document belongs to another account")
    if doc.get("state") != "ready":
        raise _no_store_error(
            409, str(doc.get("non_viewable_reason") or "document is not viewable")
        )
    try:
        html = project_hosted_book_html(document_id, store=store)
        doc = _acknowledge_projection(document_id, html, store=store)
    except (KeyError, RuntimeError, TypeError, ValueError) as exc:
        raise _no_store_error(503, str(exc)) from exc
    return {
        "document_id": document_id,
        "owner_id": owner_id,
        "state": "ready",
        "source_byte_hash": doc.get("source_byte_hash"),
        "canonical_content_hash": doc.get("canonical_content_hash"),
        "source_format": doc.get("source_format"),
        "view_format": "html",
        "html": html,
        "title": doc.get("title") or document_id,
        "document_loaded_event_id": doc.get("document_loaded_event_id"),
        "already_hosted": True,
        "non_viewable_reason": None,
        **_receipt_fields(doc),
    }


@hosted_document_router.put("/{document_id}/citation-position")
def put_citation_position(
    document_id: str, body: CitationPositionBody, request: Request, response: Response
) -> dict[str, Any]:
    from substrate.engagement_spine.citation_evidence import parse_citation_evidence
    from substrate.event_log import IdempotencyConflict, append_idempotent_typed_event_authorized
    from substrate.schemas import DocumentCitationPositionSetPayload

    response.headers["Cache-Control"] = "no-store"
    owner_id = _request_account(request)
    supplied = body.citation_evidence
    if set(supplied) != {
        "source_kind", "source_asset_id", "claim_id", "chunk_ids", "document_id", "receipt_sha256"
    }:
        raise _no_store_error(404, "cited evidence is unavailable")
    supplied_receipt = supplied.get("receipt_sha256")
    try:
        evidence = parse_citation_evidence({key: value for key, value in supplied.items() if key != "receipt_sha256"})
    except ValueError:
        raise _no_store_error(404, "cited evidence is unavailable") from None
    if (
        evidence is None
        or supplied_receipt != evidence.receipt_sha256
        or evidence.document_id != document_id
        or len(evidence.chunk_ids) != body.anchor_count
        or body.index >= body.anchor_count
    ):
        raise _no_store_error(404, "cited evidence is unavailable")
    # Re-run the current legal projection for every sealed chunk; this is the
    # legal-read authority check, not a receipt-only shortcut.
    try:
        projected = _legal_citation_payload(
            document_id, list(evidence.chunk_ids), owner_id=owner_id
        )
    except HTTPException as exc:
        headers = dict(exc.headers or {})
        headers["Cache-Control"] = "no-store"
        exc.headers = headers
        raise
    if len(projected.get("chunk_anchors") or []) != body.anchor_count:
        raise _no_store_error(404, "cited evidence is unavailable")
    authority = _citation_document_authority(document_id, owner_id)
    mutation_digest = hashlib.sha256(body.mutation_key.encode()).hexdigest()
    canonical_request = json.dumps(
        {
            "citation_evidence": evidence.to_dict(),
            "index": body.index,
            "anchor_count": body.anchor_count,
        },
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    request_digest = hashlib.sha256(canonical_request.encode()).hexdigest()
    payload = DocumentCitationPositionSetPayload(
        receipt_sha256=evidence.receipt_sha256,
        index=body.index,
        anchor_count=body.anchor_count,
        mutation_key_sha256=mutation_digest,
        request_sha256=request_digest,
    )
    try:
        event = append_idempotent_typed_event_authorized(
            authority,
            payload,
            document_id=document_id,
            mutation_key_sha256=mutation_digest,
            request_sha256=request_digest,
            role="reader",
            policy_id="interfaces/research/api/hosted_documents",
        )
    except IdempotencyConflict as exc:
        raise _no_store_error(409, str(exc)) from exc
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise _no_store_error(503, "citation position durability unavailable") from exc
    return {"status": "synced", "event_id": event.event_id, "index": payload.index}


@hosted_document_router.get("/{document_id}/citation-position")
def get_citation_position(
    document_id: str,
    request: Request,
    response: Response,
    receipt_sha256: str = Query(pattern=r"^[a-f0-9]{64}$"),
    anchor_count: int = Query(ge=1, le=64),
) -> dict[str, Any]:
    from substrate.event_log import trajectory_authorized_append_order

    response.headers["Cache-Control"] = "no-store"
    owner_id = _request_account(request)
    authority = _citation_document_authority(document_id, owner_id)
    try:
        rows = trajectory_authorized_append_order(authority)
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise _no_store_error(503, "citation position durability unavailable") from exc
    matches = [
        row for row in rows
        if row.get("action_type") == "document.citation_position_set"
        and row.get("document_id") == document_id
        and isinstance(row.get("payload"), dict)
        and row["payload"].get("receipt_sha256") == receipt_sha256
        and row["payload"].get("anchor_count") == anchor_count
    ]
    if not matches:
        return {"status": "not_found"}
    latest = matches[-1]
    return {"status": "found", "index": latest["payload"]["index"]}


def register_hosted_document_routes(app: FastAPI) -> None:
    app.include_router(hosted_document_router)


__all__ = [
    "HOSTED_HTML_PROJECTION_VERSION",
    "hosted_document_router",
    "register_hosted_document_routes",
]
