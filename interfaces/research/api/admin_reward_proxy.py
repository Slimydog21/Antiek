"""Reward-proxy worker invocation HTTP API (2026-05-22 follow-up).

The three reward-proxy backfill workers (immediate / medium / deep)
exist as substrate functions but nothing schedules them. Operators
have two options:

1. **Operator-scheduled cron** — call ``POST /api/admin/reward-proxy/run``
   on a schedule of their choosing (cron / systemd timer / GitHub
   Actions). The workers are idempotent + cheap; no harm in running
   every 5 minutes.

2. **Startup sweep** — register_admin_reward_proxy_routes wires a
   FastAPI startup hook that runs one sweep on boot. This catches
   any backfill needed after a deploy without operator action.

This is the simplest abstraction that fits: avoid hard-coding a
scheduler dep (APScheduler / Celery beat), expose the operation as a
route the operator can poll however they want, and run once at boot
so the first request after a deploy isn't waiting on backfill.

Auth posture: this route is operator-only. The middleware in app.py
should gate /api/admin/* behind a role check; today's single-operator
posture treats every request as operator, so the route is open. When
multi-user lands (Sprint 22+), an admin-role check belongs here.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Optional

from fastapi import FastAPI
from pydantic import BaseModel

_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

from substrate.behavior.workers.reward_immediate import (  # noqa: E402
    run_reward_immediate_backfill,
)
from substrate.behavior.workers.reward_medium import (  # noqa: E402
    run_reward_medium_backfill,
)
from substrate.behavior.workers.reward_deep import (  # noqa: E402
    run_reward_deep_backfill,
)

_log = logging.getLogger(__name__)


class RewardProxyRunResponse(BaseModel):
    immediate_status: str
    immediate_rows_updated: int
    immediate_reason: str
    medium_status: str
    medium_rows_updated: int
    medium_reason: str
    deep_status: str
    deep_rows_updated: int
    deep_reason: str


def _run_all_workers(db_path: Optional[str]) -> RewardProxyRunResponse:
    """Run the three backfill workers in order. Each is idempotent and
    cheap; running them sequentially is correct and avoids contention
    on the behavior_events UPDATE."""
    imm = run_reward_immediate_backfill(db_path=db_path)
    med = run_reward_medium_backfill(db_path=db_path)
    deep = run_reward_deep_backfill(db_path=db_path)
    return RewardProxyRunResponse(
        immediate_status=imm.status,
        immediate_rows_updated=getattr(imm, "rows_updated", 0),
        immediate_reason=imm.reason,
        medium_status=med.status,
        medium_rows_updated=getattr(med, "rows_updated", 0),
        medium_reason=med.reason,
        deep_status=deep.status,
        deep_rows_updated=getattr(deep, "rows_updated", 0),
        deep_reason=deep.reason,
    )


def register_admin_reward_proxy_routes(
    app: FastAPI,
    *,
    db_path: Optional[str] = None,
    run_on_startup: bool = True,
) -> None:
    """Mount the admin route + register the startup sweep.

    ``run_on_startup=False`` skips the sweep — used by tests that don't
    want substrate writes on app construction.
    """

    @app.post(
        "/api/admin/reward-proxy/run",
        response_model=RewardProxyRunResponse,
        tags=["admin"],
    )
    async def run_reward_proxy() -> RewardProxyRunResponse:
        return _run_all_workers(db_path)

    if run_on_startup:
        @app.on_event("startup")
        async def _startup_sweep() -> None:
            try:
                result = _run_all_workers(db_path)
                _log.info(
                    "reward-proxy startup sweep: immediate=%s (n=%d), "
                    "medium=%s (n=%d), deep=%s (n=%d)",
                    result.immediate_status, result.immediate_rows_updated,
                    result.medium_status, result.medium_rows_updated,
                    result.deep_status, result.deep_rows_updated,
                )
            except Exception as exc:  # noqa: BLE001 — never block boot
                _log.warning(
                    "reward-proxy startup sweep failed (boot continues): %s",
                    exc,
                )
