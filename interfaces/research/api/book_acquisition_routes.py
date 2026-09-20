"""Authenticated HTTP adapter for authorized, bytes-only book acquisition."""

from __future__ import annotations

import asyncio
from dataclasses import asdict
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

from runtime.db_lock import connect_write
from substrate.book_acquisition import (
    AcquisitionConflictError,
    AcquisitionIntegrityError,
    AuthorizationDecision,
    DesiredFormat,
    authorize_purchase_intent,
    create_purchase_intent,
    ensure_schema,
)
from substrate.book_acquisition.port import (
    AuthorizedBookPort,
    PortReceiptIntegrityError,
    commit_authorized_port,
    convert_authorized_epub,
    ensure_port_schema,
)
from substrate.book_import import BookImportError

EPUB_MEDIA_TYPE = "application/epub+zip"
DEFAULT_MAX_EPUB_BYTES = 64 * 1024 * 1024
MAX_USD_CENTS = 9_223_372_036_854_775_807
_AUTHENTICATED_METHODS = frozenset(
    {
        "antiek_session_cookie",
        "cloudflare_access_email",
        "cloudflare_service_token",
        "bearer_token",
    }
)


class PurchaseIntentRequest(BaseModel):
    title: str = Field(min_length=1, max_length=512)
    author: str = Field(min_length=1, max_length=512)
    store: str = Field(min_length=1, max_length=512)
    max_price_usd_cents: int = Field(ge=0, le=MAX_USD_CENTS, strict=True)
    desired_format: Literal["epub"] = "epub"


class PurchaseIntentResponse(BaseModel):
    intent_receipt_id: str
    operator_id: str
    title: str
    author: str
    store: str
    max_price_usd_cents: int
    desired_format: str
    intent_hash: str
    status: str


class AuthorizationRequest(BaseModel):
    decision: AuthorizationDecision
    authorized_price_ceiling_usd_cents: int = Field(
        ge=0,
        le=MAX_USD_CENTS,
        strict=True,
    )


class AuthorizationResponse(BaseModel):
    authorization_receipt_id: str
    intent_receipt_id: str
    intent_hash: str
    operator_id: str
    decision: AuthorizationDecision
    authorized_price_ceiling_usd_cents: int
    authorization_hash: str
    purchase_occurred: Literal[False] = False


class AuthorizedBookPortResponse(BaseModel):
    port_receipt_id: str
    authorization_receipt_id: str
    epub_sha256: str
    document_id: str
    reader_route: str
    content_class: Literal["personal_reading"]
    servability: Literal["personal_readable"]
    was_new: bool
    port_hash: str


def _operator_id(request: Request) -> str:
    state = getattr(request, "state", None)
    auth_method = getattr(state, "auth_method", None)
    operator_id = getattr(state, "user_id", None)
    if auth_method not in _AUTHENTICATED_METHODS or not isinstance(operator_id, str):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="book acquisition requires an authenticated operator",
        )
    operator_id = operator_id.strip()
    if not operator_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="book acquisition requires an authenticated operator",
        )
    return operator_id


def _domain_error(exc: Exception) -> HTTPException:
    if isinstance(exc, AcquisitionIntegrityError):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    if isinstance(exc, (AcquisitionConflictError, PortReceiptIntegrityError)):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, (BookImportError, ValueError)):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        )
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="book acquisition failed",
    )


async def _read_epub(
    request: Request,
    *,
    content_type: str | None,
    content_length: str | None,
    max_bytes: int,
) -> bytes:
    normalized_type = (content_type or "").split(";", 1)[0].strip().lower()
    if normalized_type != EPUB_MEDIA_TYPE:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Content-Type must be {EPUB_MEDIA_TYPE}",
        )
    if content_length is not None:
        try:
            declared_length = int(content_length)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Content-Length must be an integer",
            ) from exc
        if declared_length < 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Content-Length cannot be negative",
            )
        if declared_length > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"EPUB exceeds {max_bytes} byte upload limit",
            )
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"EPUB exceeds {max_bytes} byte upload limit",
            )
        body.extend(chunk)
    if not body:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="EPUB body must not be empty",
        )
    return bytes(body)


def _intent_response(intent: Any) -> PurchaseIntentResponse:
    values = asdict(intent)
    values["desired_format"] = intent.desired_format.value
    return PurchaseIntentResponse.model_validate(values)


def _authorization_response(authorization: Any) -> AuthorizationResponse:
    values = asdict(authorization)
    values["purchase_occurred"] = authorization.purchase_occurred
    return AuthorizationResponse.model_validate(values)


def _port_response(result: AuthorizedBookPort) -> AuthorizedBookPortResponse:
    return AuthorizedBookPortResponse.model_validate(asdict(result))


def _commit_port(
    *,
    db_path: str,
    authorization_receipt_id: str,
    operator_id: str,
    signing_key: bytes,
    prepared: Any,
) -> AuthorizedBookPortResponse:
    """Run all blocking lock and DuckDB work on a worker thread."""
    with connect_write(db_path, purpose="book-acquisition/port") as con:
        ensure_schema(con)
        ensure_port_schema(con)
        return _port_response(
            commit_authorized_port(
                con,
                authorization_receipt_id=authorization_receipt_id,
                operator_id=operator_id,
                signing_key=signing_key,
                prepared=prepared,
            )
        )


def create_book_acquisition_router(
    *,
    db_path: str,
    signing_key: bytes,
    max_epub_bytes: int = DEFAULT_MAX_EPUB_BYTES,
) -> APIRouter:
    if not db_path.strip():
        raise ValueError("db_path is required")
    if not isinstance(signing_key, bytes) or len(signing_key) < 32:
        raise ValueError("signing_key must contain at least 32 bytes")
    if (
        isinstance(max_epub_bytes, bool)
        or not isinstance(max_epub_bytes, int)
        or max_epub_bytes <= 0
    ):
        raise ValueError("max_epub_bytes must be a positive integer")

    router = APIRouter(prefix="/book-acquisition", tags=["book-acquisition"])

    @router.post(
        "/intents",
        response_model=PurchaseIntentResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def create_intent(request: Request, body: PurchaseIntentRequest) -> PurchaseIntentResponse:
        operator_id = _operator_id(request)
        try:
            with connect_write(db_path, purpose="book-acquisition/create-intent") as con:
                ensure_schema(con)
                return _intent_response(
                    create_purchase_intent(
                        con,
                        operator_id=operator_id,
                        title=body.title,
                        author=body.author,
                        store=body.store,
                        max_price_usd_cents=body.max_price_usd_cents,
                        desired_format=DesiredFormat(body.desired_format),
                        signing_key=signing_key,
                    )
                )
        except Exception as exc:
            raise _domain_error(exc) from exc

    @router.post(
        "/intents/{intent_receipt_id}/authorization",
        response_model=AuthorizationResponse,
    )
    def authorize_intent(
        intent_receipt_id: str,
        request: Request,
        body: AuthorizationRequest,
    ) -> AuthorizationResponse:
        operator_id = _operator_id(request)
        try:
            with connect_write(db_path, purpose="book-acquisition/authorize") as con:
                ensure_schema(con)
                return _authorization_response(
                    authorize_purchase_intent(
                        con,
                        intent_receipt_id=intent_receipt_id,
                        operator_id=operator_id,
                        decision=body.decision,
                        authorized_price_ceiling_usd_cents=(
                            body.authorized_price_ceiling_usd_cents
                        ),
                        signing_key=signing_key,
                    )
                )
        except Exception as exc:
            raise _domain_error(exc) from exc

    @router.post(
        "/authorizations/{authorization_receipt_id}/port",
        response_model=AuthorizedBookPortResponse,
    )
    async def port_epub(
        authorization_receipt_id: str,
        request: Request,
        content_type: Annotated[str | None, Header()] = None,
        content_length: Annotated[str | None, Header()] = None,
    ) -> AuthorizedBookPortResponse:
        operator_id = _operator_id(request)
        epub_bytes = await _read_epub(
            request,
            content_type=content_type,
            content_length=content_length,
            max_bytes=max_epub_bytes,
        )
        # Phase 1: bounded conversion OFF the event loop, OUTSIDE the
        # writer lock.  convert_authorized_epub is pure CPU with no DB
        # access — asyncio.to_thread keeps the event loop unblocked
        # while the global DuckDB writer lock is free for other writers.
        try:
            prepared = await asyncio.to_thread(convert_authorized_epub, epub_bytes)
        except Exception as exc:
            raise _domain_error(exc) from exc
        # Phase 2: one DB transaction — verify authorization, publish,
        # mint signed port receipt.  Authorization verification happens
        # INSIDE this writer transaction to prevent TOCTOU bypass.
        try:
            return await asyncio.to_thread(
                _commit_port,
                db_path=db_path,
                authorization_receipt_id=authorization_receipt_id,
                operator_id=operator_id,
                signing_key=signing_key,
                prepared=prepared,
            )
        except Exception as exc:
            raise _domain_error(exc) from exc

    return router


__all__ = [
    "AuthorizedBookPortResponse",
    "AuthorizationRequest",
    "AuthorizationResponse",
    "DEFAULT_MAX_EPUB_BYTES",
    "EPUB_MEDIA_TYPE",
    "MAX_USD_CENTS",
    "PurchaseIntentRequest",
    "PurchaseIntentResponse",
    "create_book_acquisition_router",
]
