"""Midnight Oil — autonomous research sub-agent swarm (offline-from-UI).

Product surface: operator sets goals + work duration; system recommends a
price ceiling; after **explicit approve** a worker iterates without a
workstation session. Spend hard-halts at the approved ceiling and deposits
partial HTML + twin notes via ``substrate.engagement_spine``.

No network is required for the pure job/ceiling/approve/worker/deposit path —
tests inject clocks and spawn functions.
"""

from __future__ import annotations

from .ceiling import recommend_price_ceiling
from .deposit import DepositResult, deposit_job_results
from .job import (
    JobStatus,
    MidnightOilJob,
    approve_job,
    create_job,
    get_job,
)
from .product_path import (
    ANTIEK_MIDNIGHT_OIL_LIVE_STEP_ENV,
    MidnightOilProductResult,
    approve_price_ceiling,
    clear_midnight_oil_live_step,
    configure_midnight_oil_live_step,
    create_recommend_and_approve,
    create_with_recommended_ceiling,
    job_summary_html,
    live_step_enabled,
    offline_goal_step_fn,
    product_result_html,
    resolve_worker_step_fn,
    run_job_offline,
)
from .worker import WorkerStepResult, run_worker_iteration, run_worker_loop

__all__ = [
    "ANTIEK_MIDNIGHT_OIL_LIVE_STEP_ENV",
    "DepositResult",
    "JobStatus",
    "MidnightOilJob",
    "MidnightOilProductResult",
    "WorkerStepResult",
    "approve_job",
    "approve_price_ceiling",
    "clear_midnight_oil_live_step",
    "configure_midnight_oil_live_step",
    "create_job",
    "create_recommend_and_approve",
    "create_with_recommended_ceiling",
    "deposit_job_results",
    "get_job",
    "job_summary_html",
    "live_step_enabled",
    "product_result_html",
    "offline_goal_step_fn",
    "recommend_price_ceiling",
    "resolve_worker_step_fn",
    "run_job_offline",
    "run_worker_iteration",
    "run_worker_loop",
]
