"""Registerable HTTP surface for Antiek-bench task-family expand compose."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.antiek_bench_task_family_expand_compose import (
    AntiekBenchTaskFamilyExpandComposeError,
    compose_antiek_bench_task_family_expand,
)

antiek_bench_task_family_expand_compose_router = APIRouter(
    prefix="/research/antiek-bench-task-family-expand",
    tags=["antiek-bench-task-family-expand-compose"],
)


class EventBody(BaseModel):
    model_config = {"extra": "forbid"}

    event_id: str = Field(min_length=1, max_length=256)
    task: str = Field(min_length=1, max_length=256)
    model_id: str = Field(min_length=1, max_length=128)
    outcome: Literal["worked", "failed", "mixed", "unknown"]
    score: float | None = Field(default=None, ge=0, le=1)


class ProposedTaskBody(BaseModel):
    model_config = {"extra": "forbid"}

    task: str = Field(min_length=1, max_length=256)
    description: str | None = Field(default=None, max_length=2000)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    week_id: str = Field(min_length=1, max_length=64)
    existing_tasks: list[str]
    proposed_new_tasks: list[ProposedTaskBody] | None = None
    events: list[EventBody]
    operator_ack: bool = Field(strict=True)
    min_events_per_task: int | None = Field(default=None, ge=1)


@antiek_bench_task_family_expand_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_antiek_bench_task_family_expand(
            week_id=req.week_id,
            existing_tasks=list(req.existing_tasks),
            proposed_new_tasks=(
                [p.model_dump() for p in req.proposed_new_tasks]
                if req.proposed_new_tasks is not None
                else None
            ),
            events=[e.model_dump() for e in req.events],
            operator_ack=req.operator_ack,
            min_events_per_task=req.min_events_per_task,
        )
    except AntiekBenchTaskFamilyExpandComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_antiek_bench_task_family_expand_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(antiek_bench_task_family_expand_compose_router)


__all__ = [
    "antiek_bench_task_family_expand_compose_router",
    "register_antiek_bench_task_family_expand_compose_routes",
]
