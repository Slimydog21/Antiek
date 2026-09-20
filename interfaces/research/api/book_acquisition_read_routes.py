"""Authenticated recovery API for signed book-acquisition lifecycles."""

from __future__ import annotations

from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel

from runtime.db_lock import connect_read
from substrate.book_acquisition import AcquisitionIntegrityError
from substrate.book_acquisition.port import PortReceiptIntegrityError
from substrate.book_acquisition.read_model import (
    BookAcquisitionRecord,
    list_book_acquisitions,
)

from .book_acquisition_routes import (
    AuthorizationResponse,
    AuthorizedBookPortResponse,
    PurchaseIntentResponse,
)

_AUTHENTICATED_METHODS = frozenset(
    {
        "antiek_session_cookie",
        "cloudflare_access_email",
        "cloudflare_service_token",
        "bearer_token",
    }
)


class BookAcquisitionRecordResponse(BaseModel):
    intent: PurchaseIntentResponse
    authorization: AuthorizationResponse | None
    port: AuthorizedBookPortResponse | None


class BookAcquisitionPageResponse(BaseModel):
    records: tuple[BookAcquisitionRecordResponse, ...]
    next_cursor: str | None


def create_book_acquisition_read_router(
    *,
    db_path: str,
    signing_key: bytes,
) -> APIRouter:
    if not isinstance(db_path, str) or not db_path.strip():
        raise ValueError("db_path is required")
    if not isinstance(signing_key, bytes) or len(signing_key) < 32:
        raise ValueError("signing_key must contain at least 32 bytes")
    router = APIRouter(prefix="/book-acquisition", tags=["book-acquisition"])

    @router.get("/records", response_model=BookAcquisitionPageResponse)
    def list_records(
        request: Request,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        after: Annotated[str | None, Query(min_length=1)] = None,
    ) -> BookAcquisitionPageResponse:
        operator_id = _operator_id(request)
        try:
            with connect_read(db_path) as con:
                page = list_book_acquisitions(
                    con,
                    operator_id=operator_id,
                    signing_key=signing_key,
                    limit=limit,
                    after=after,
                )
        except (AcquisitionIntegrityError, PortReceiptIntegrityError) as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="book acquisition recovery failed integrity checks",
            ) from exc
        records = tuple(_record_response(record) for record in page.records)
        return BookAcquisitionPageResponse(records=records, next_cursor=page.next_cursor)

    return router


def _operator_id(request: Request) -> str:
    method = getattr(request.state, "auth_method", None)
    operator_id = getattr(request.state, "user_id", None)
    if method not in _AUTHENTICATED_METHODS or not isinstance(operator_id, str):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required"
        )
    operator_id = operator_id.strip()
    if not operator_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required"
        )
    return operator_id


def _record_response(record: BookAcquisitionRecord) -> BookAcquisitionRecordResponse:
    intent = asdict(record.intent)
    intent["desired_format"] = record.intent.desired_format.value
    authorization = None
    if record.authorization is not None:
        authorization = asdict(record.authorization)
        authorization["decision"] = record.authorization.decision.value
        authorization["purchase_occurred"] = False
    port = asdict(record.port) if record.port is not None else None
    return BookAcquisitionRecordResponse(
        intent=PurchaseIntentResponse.model_validate(intent),
        authorization=(
            AuthorizationResponse.model_validate(authorization)
            if authorization is not None
            else None
        ),
        port=AuthorizedBookPortResponse.model_validate(port) if port is not None else None,
    )


__all__ = [
    "BookAcquisitionPageResponse",
    "BookAcquisitionRecordResponse",
    "create_book_acquisition_read_router",
]
