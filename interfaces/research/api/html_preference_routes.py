"""HTTP surface for HTML-native view preference.

Consumes ``prefer_html_view`` (#801). Does not convert PDFs.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, field_validator

from substrate.books.html_preference import prefer_html_view

html_preference_router = APIRouter(
    prefix="/assets/view-preference",
    tags=["html-view-preference"],
)


def _require_bool(v: object, *, name: str) -> bool:
    if isinstance(v, bool):
        return v
    raise ValueError(f"{name} must be a boolean")


class ViewPreferenceRequest(BaseModel):
    html_ready: bool
    pdf_available: bool = False
    require_html: bool = True
    asset_id: str = ""

    @field_validator("html_ready", "pdf_available", "require_html", mode="before")
    @classmethod
    def _bools(cls, v: object) -> object:
        if isinstance(v, bool):
            return v
        # Reject truthy strings like "false" that would invent readiness
        raise ValueError("must be a boolean (not a string or number)")


@html_preference_router.post("/decide")
def decide_view_preference(req: ViewPreferenceRequest) -> dict[str, Any]:
    """Decide preferred view mode. No conversion, no network."""
    try:
        decision = prefer_html_view(
            html_ready=_require_bool(req.html_ready, name="html_ready"),
            pdf_available=_require_bool(req.pdf_available, name="pdf_available"),
            require_html=_require_bool(req.require_html, name="require_html"),
            asset_id=req.asset_id,
        )
    except TypeError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return decision.to_dict()


def register_html_preference_routes(app: FastAPI) -> None:
    app.include_router(html_preference_router)


__all__ = [
    "ViewPreferenceRequest",
    "decide_view_preference",
    "html_preference_router",
    "register_html_preference_routes",
]
