"""Registerable HTTP surface for HTML host port evaluation."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.books.html_host_port import (
    HtmlHostPortError,
    evaluate_html_host_port_from_maps,
)

html_host_router = APIRouter(
    prefix="/books/html-host",
    tags=["book-html-host-port"],
)


class HtmlHostRequest(BaseModel):
    model_config = {"extra": "forbid"}

    title: str = Field(min_length=1, max_length=512)
    parent_asset_id: str | None = None
    operator_id: str | None = None
    free_copy_preflight: dict[str, Any] | None = None
    purchase_gate: dict[str, Any] | None = None
    html_projection: dict[str, Any] | None = None


@html_host_router.post("/evaluate")
def post_html_host(req: HtmlHostRequest) -> dict[str, Any]:
    try:
        receipt = evaluate_html_host_port_from_maps(
            title=req.title,
            free_copy_preflight=req.free_copy_preflight,
            purchase_gate=req.purchase_gate,
            html_projection=req.html_projection,
            parent_asset_id=req.parent_asset_id,
            operator_id=req.operator_id,
        )
    except HtmlHostPortError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return receipt.to_dict()


def register_html_host_routes(app: FastAPI) -> None:
    app.include_router(html_host_router)


__all__ = ["html_host_router", "register_html_host_routes"]
