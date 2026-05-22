"""User-state HTTP API (2026-05-22 follow-up).

Today's only route: ``GET /api/users/me/is-returning`` — the substrate-
authoritative answer to SPR-06's post-login routing question. Wraps
``substrate.behavior.sessions.is_returning_user`` so the TS layer can
distinguish a real returning operator from a first-time visitor without
relying on the per-device localStorage proxy.

Behavior posture (rigor #1 — calibrate confidence to evidence):
  - The substrate is the source of truth when reachable. If a behavior
    event older than ``threshold_days`` exists for the user, the
    operator is returning.
  - The localStorage proxy in ``apps/reading/src/routing/postLogin.ts``
    remains as the fallback for when the backend is unreachable
    (offline, transient failure). The TS layer races the substrate
    call against a timeout and falls back gracefully.
"""

from __future__ import annotations

import os
import sys
from typing import Optional

from fastapi import FastAPI, Query
from pydantic import BaseModel

_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

from substrate.behavior.sessions import (  # noqa: E402
    get_last_session_at,
    is_returning_user,
)


class IsReturningResponse(BaseModel):
    """Body of ``GET /api/users/me/is-returning``."""

    user_id: str
    is_returning: bool
    last_session_at: Optional[str] = None
    threshold_days: int


def register_user_routes(
    app: FastAPI,
    *,
    db_path: Optional[str] = None,
) -> None:
    """Mount user-state routes on ``app``."""

    @app.get(
        "/api/users/me/is-returning",
        response_model=IsReturningResponse,
        tags=["users"],
    )
    async def get_is_returning(
        user_id: str = Query(default="__operator__"),
        threshold_days: int = Query(default=1, ge=0, le=365),
    ) -> IsReturningResponse:
        last = get_last_session_at(user_id, db_path=db_path)
        returning = is_returning_user(
            user_id, threshold_days=threshold_days, db_path=db_path,
        )
        return IsReturningResponse(
            user_id=user_id,
            is_returning=returning,
            last_session_at=last.isoformat() if last else None,
            threshold_days=threshold_days,
        )
