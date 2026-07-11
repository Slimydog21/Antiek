"""Registerable HTTP surface for competition gap residual execute compose."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.competition_gap_residual_execute_compose import (
    CompetitionGapResidualExecuteComposeError,
    compose_competition_gap_residual_execute,
)

competition_gap_residual_execute_compose_router = APIRouter(
    prefix="/research/competition-residual-execute",
    tags=["competition-gap-residual-execute-compose"],
)


class ResidualBody(BaseModel):
    model_config = {"extra": "forbid"}

    residual_id: str = Field(min_length=1, max_length=256)
    area: str = Field(min_length=1, max_length=128)
    competitor: str = Field(min_length=1, max_length=128)
    residual_text: str = Field(min_length=1, max_length=8000)
    antiek_status: Literal["behind", "unknown", "parity", "ahead"]
    priority: Literal["P0", "P1", "P2", "P3"]
    execution_hint: str = Field(min_length=1, max_length=4000)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    residual: ResidualBody
    operator_ack: bool = Field(strict=True)
    extra_gates: list[str] | None = None
    proposed_owned_files: list[str] | None = None


@competition_gap_residual_execute_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_competition_gap_residual_execute(
            residual=req.residual.model_dump(),
            operator_ack=req.operator_ack,
            extra_gates=req.extra_gates,
            proposed_owned_files=req.proposed_owned_files,
        )
    except CompetitionGapResidualExecuteComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_competition_gap_residual_execute_compose_routes(app: FastAPI) -> None:
    app.include_router(competition_gap_residual_execute_compose_router)


__all__ = [
    "competition_gap_residual_execute_compose_router",
    "register_competition_gap_residual_execute_compose_routes",
]
