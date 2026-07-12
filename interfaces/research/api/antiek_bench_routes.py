"""Antiek-bench API routes — the operator-facing surface for the recursive benchmark.

Three pure read/propose routes following the house ``settings_router`` convention:

- ``GET /antiek-bench/tasks`` — list the task registry (what the benchmark measures).
- ``GET /antiek-bench/week/{week_id}`` — read a week's composed evidence from the
  verified ledger (view records + usage events + incomplete flag). Absent/corrupt
  ledger → ``incomplete=True``, never silent recovery.
- ``POST /antiek-bench/runs/propose`` — propose a run WITHOUT executing: project a
  cost ceiling via the LIVE ``estimate_prompt_cost`` gate and surface
  ``would_exceed_budget`` for operator approval. This is the Midnight Oil
  recommend→approve→run pattern — the operator sees the ceiling before any paid
  dispatch. Returns ``live_dispatch_authorized=False`` always (the authorized
  runner, a separate path, sets that only after the gate clears + operator consent).

The execute path (paid dispatch) is deliberately NOT here — it lives in a future
authorized runner behind the budget gate + operator spend-consent. No engine
grades its own homework; no pure route dispatches a model or mutates spend.

Ledger path resolves from ``ANTIEK_BENCH_DIR`` (house env convention) — the same
root ``scorecards.antiek_bench_dir()`` uses. Absent dir → empty evidence, not an
error.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.settings_budget import (
    BudgetResponse,
    PromptCostEstimateRequest,
    PromptCostEstimateResponse,
    estimate_prompt_cost,
    read_operator_budget,
)
from substrate.antiek_bench.recorder import (
    read_ledger,
    week_incomplete,
    week_usage_events,
    week_view_records,
)
from substrate.antiek_bench.task_registry import BenchTask, TaskRegistry, load_default_registry

antiek_bench_router = APIRouter(prefix="/antiek-bench", tags=["antiek-bench"])


# ── response models ─────────────────────────────────────────────────────────


class TaskRow(BaseModel):
    """One task in the registry, flattened for the API."""

    model_config = {"frozen": True}

    task_id: str
    family: str
    scoring: str
    version: int
    model_cost_class: str
    prompt_preview: str = Field(description="First 200 chars of the task prompt")


class TasksResponse(BaseModel):
    model_config = {"frozen": True}

    tasks: list[TaskRow]
    families: list[str]
    count: int


class WeekEvidenceResponse(BaseModel):
    """A week's evidence, read from the verified ledger."""

    model_config = {"frozen": True}

    week_id: str
    view_records: list[dict[str, object]]
    usage_events: list[dict[str, object]]
    incomplete: bool
    n_records: int


class RunProposalRequest(BaseModel):
    """Propose a run: task + candidate model → projected cost ceiling + budget gate."""

    model_config = {"frozen": True}

    task_id: str
    provider: str | None = None
    model: str | None = None
    tier: str | None = "pro"
    expected_output_tokens: int = Field(default=500, ge=0)


class RunProposalResponse(BaseModel):
    """The recommend half of recommend→approve→run. Never executes."""

    model_config = {"frozen": True}

    task_id: str
    cost_estimate: PromptCostEstimateResponse
    would_exceed_budget: bool | None
    live_dispatch_authorized: bool = False
    notes: list[str] = Field(default_factory=list)


# ── helpers ─────────────────────────────────────────────────────────────────


def _bench_dir() -> Path:
    raw = os.environ.get("ANTIEK_BENCH_DIR")
    if raw:
        return Path(raw)
    home = Path(os.environ.get("ANTIEK_HOME", Path.home() / ".antiek"))
    return home / "antiek_bench"


def _ledger_path() -> Path:
    return _bench_dir() / "bench_ledger.jsonl"


def _to_task_row(task: BenchTask) -> TaskRow:
    return TaskRow(
        task_id=task.task_id,
        family=task.family,
        scoring=task.scoring,
        version=task.version,
        model_cost_class=task.model_cost_class,
        prompt_preview=task.prompt[:200],
    )


# ── routes ──────────────────────────────────────────────────────────────────


@antiek_bench_router.get("/tasks", response_model=TasksResponse)
def get_bench_tasks() -> TasksResponse:
    registry: TaskRegistry = load_default_registry()
    rows = [_to_task_row(t) for t in registry]
    families: list[str] = [str(f) for f in registry.families()]
    return TasksResponse(tasks=rows, families=families, count=len(rows))


@antiek_bench_router.get("/week/{week_id}", response_model=WeekEvidenceResponse)
def get_bench_week(week_id: str) -> WeekEvidenceResponse:
    ledger = _ledger_path()
    try:
        read_ledger(ledger)  # verifies the whole chain; raises on corruption
    except Exception:
        # Absent/corrupt ledger → incomplete, never silent recovery.
        return WeekEvidenceResponse(
            week_id=week_id,
            view_records=[],
            usage_events=[],
            incomplete=True,
            n_records=0,
        )
    return WeekEvidenceResponse(
        week_id=week_id,
        view_records=[r.model_dump(mode="json") for r in week_view_records(ledger, week_id=week_id)],
        usage_events=[e.model_dump(mode="json") for e in week_usage_events(ledger, week_id=week_id)],
        incomplete=week_incomplete(ledger, week_id=week_id),
        n_records=len(week_view_records(ledger, week_id=week_id)),
    )


@antiek_bench_router.post("/runs/propose", response_model=RunProposalResponse)
def post_bench_run_propose(req: RunProposalRequest) -> RunProposalResponse:
    """Project a run's cost ceiling + budget gate WITHOUT executing.

    The operator approves the ceiling; the authorized runner (separate path)
    executes only after consent + a LIVE gate re-check.
    """
    registry = load_default_registry()
    try:
        task = registry.get(req.task_id)  # fail-closed: unknown task → 404
    except Exception:
        raise HTTPException(status_code=404, detail=f"unknown task_id {req.task_id!r}") from None
    est_req = PromptCostEstimateRequest(
        provider=req.provider,
        model=req.model,
        tier=req.tier,
        input_chars=len(task.prompt),
        expected_output_tokens=req.expected_output_tokens,
    )
    budget: BudgetResponse = read_operator_budget()
    estimate = estimate_prompt_cost(est_req, budget=budget)
    notes: list[str] = []
    if estimate.would_exceed_budget:
        notes.append("projected run would exceed the operator budget — approval will not clear the gate")
    if not estimate.pricing_known:
        notes.append("pricing unknown for this provider/model — ceiling cannot be projected honestly")
    return RunProposalResponse(
        task_id=req.task_id,
        cost_estimate=estimate,
        would_exceed_budget=estimate.would_exceed_budget,
        live_dispatch_authorized=False,
        notes=notes,
    )


def register_antiek_bench_routes(app: FastAPI) -> None:
    app.include_router(antiek_bench_router)


__all__ = [
    "RunProposalRequest",
    "RunProposalResponse",
    "TaskRow",
    "TasksResponse",
    "WeekEvidenceResponse",
    "antiek_bench_router",
    "register_antiek_bench_routes",
]
