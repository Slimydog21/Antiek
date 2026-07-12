"""Registerable HTTP surface for Antiek-bench weekly learn + twin presentation write collective."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.recursive_twin_presentation_write_twin_collective_fullscreen_mo_nd_twin_compose_routes import (
    PresentationBody,
    TwinBody,
    WritePackBody,
)
from substrate.antiek_bench_weekly_learn_recursive_twin_presentation_write_collective_compose import (
    AntiekBenchWeeklyLearnRecursiveTwinPresentationWriteCollectiveComposeError,
    compose_antiek_bench_weekly_learn_recursive_twin_presentation_write_collective,
)

antiek_bench_weekly_learn_recursive_twin_presentation_write_collective_compose_router = (
    APIRouter(
        prefix=(
            "/research/antiek-bench-weekly-learn-recursive-twin-presentation-write-collective"
        ),
        tags=[
            "antiek-bench-weekly-learn-recursive-twin-presentation-write-collective-compose"
        ],
    )
)


class EventBody(BaseModel):
    model_config = {"extra": "forbid"}

    event_id: str = Field(min_length=1, max_length=256)
    task: str = Field(min_length=1, max_length=256)
    model_id: str = Field(min_length=1, max_length=128)
    outcome: Literal["worked", "failed", "mixed", "unknown"]
    score: float | None = Field(default=None, ge=0, le=1)


class WeeklyLearnBody(BaseModel):
    model_config = {"extra": "forbid"}

    week_id: str = Field(min_length=1, max_length=64)
    events: list[EventBody]
    min_events_per_task: int | None = Field(default=None, ge=1)


class TwinPresentationPackBody(BaseModel):
    model_config = {"extra": "forbid"}

    twin: TwinBody
    presentation: PresentationBody
    write_pack: WritePackBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    weekly_learn: WeeklyLearnBody
    twin_presentation_pack: TwinPresentationPackBody
    operator_ack: bool = Field(strict=True)
    require_both: bool = Field(default=True, strict=True)


@antiek_bench_weekly_learn_recursive_twin_presentation_write_collective_compose_router.post(
    "/compose"
)
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_antiek_bench_weekly_learn_recursive_twin_presentation_write_collective(
            weekly_learn=req.weekly_learn.model_dump(),
            twin_presentation_pack=req.twin_presentation_pack.model_dump(),
            operator_ack=req.operator_ack,
            require_both=req.require_both,
        )
    except AntiekBenchWeeklyLearnRecursiveTwinPresentationWriteCollectiveComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_antiek_bench_weekly_learn_recursive_twin_presentation_write_collective_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        antiek_bench_weekly_learn_recursive_twin_presentation_write_collective_compose_router
    )


__all__ = [
    "antiek_bench_weekly_learn_recursive_twin_presentation_write_collective_compose_router",
    "register_antiek_bench_weekly_learn_recursive_twin_presentation_write_collective_compose_routes",
]
