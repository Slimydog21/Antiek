"""Midnight-oil autonomous research preflight API.

This route is intentionally a preflight only. It validates the operator's
approved time/price/route/source envelope and returns the role allocation that
a future runner must obey; it does not launch agents or reserve budget.
"""

from __future__ import annotations

from fastapi import APIRouter, FastAPI

from substrate.midnight_oil import (
    MidnightOilPreflight,
    MidnightOilRequest,
    preflight_midnight_oil,
)

midnight_oil_router = APIRouter(prefix="/research/midnight-oil", tags=["deep-research"])


@midnight_oil_router.post("/preflight", response_model=MidnightOilPreflight)
def post_midnight_oil_preflight(req: MidnightOilRequest) -> MidnightOilPreflight:
    return preflight_midnight_oil(req)


def register_midnight_oil_routes(app: FastAPI) -> None:
    app.include_router(midnight_oil_router)


__all__ = [
    "midnight_oil_router",
    "post_midnight_oil_preflight",
    "register_midnight_oil_routes",
]
