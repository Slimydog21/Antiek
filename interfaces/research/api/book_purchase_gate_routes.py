"""Registerable HTTP surface for marketplace purchase gate."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.books.marketplace_purchase_gate import (
    PurchaseGateError,
    evaluate_purchase_gate,
)

book_purchase_gate_router = APIRouter(
    prefix="/books/purchase-gate",
    tags=["book-purchase-gate"],
)


class PurchaseGateRequest(BaseModel):
    model_config = {"extra": "forbid"}

    title: str = Field(min_length=1, max_length=512)
    author: str | None = None
    free_copy_preflight: dict[str, Any] | None = None
    skip_free_copy: bool = Field(strict=True)
    operator_skip_acknowledged: bool | None = Field(default=None, strict=True)
    store: str | None = None


@book_purchase_gate_router.post("/evaluate")
def post_purchase_gate(req: PurchaseGateRequest) -> dict[str, Any]:
    try:
        decision = evaluate_purchase_gate(
            title=req.title,
            author=req.author,
            free_copy_preflight=req.free_copy_preflight,
            skip_free_copy=req.skip_free_copy,
            operator_skip_acknowledged=req.operator_skip_acknowledged,
            store=req.store,
        )
    except PurchaseGateError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return decision.to_dict()


def register_book_purchase_gate_routes(app: FastAPI) -> None:
    app.include_router(book_purchase_gate_router)


__all__ = [
    "book_purchase_gate_router",
    "register_book_purchase_gate_routes",
]
