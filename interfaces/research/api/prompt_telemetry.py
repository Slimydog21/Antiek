"""Prompt / question telemetry for the research→notebook path.

SoT is the investigation event-log trajectory (``dispatch.call`` + start
question). This module projects a UI-friendly view — it does not invent a
parallel store. Full prompt bodies are intentionally not persisted on
``dispatch.call`` (only ``prompt_hash``); the opening research question comes
from ``investigation.start_requested``.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from substrate.event_log import trajectory
from substrate.schemas import ActionType

prompt_telemetry_router = APIRouter(tags=["prompt-telemetry"])


class PromptCallOut(BaseModel):
    event_id: str | None = None
    emitted_at: str | None = None
    role: str
    provider: str
    model: str
    tier: str | None = None
    finish_reason: str | None = None
    latency_ms: int = 0
    cost_usd: float = 0.0
    prompt_hash: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0


class PromptTelemetryOut(BaseModel):
    investigation_id: str
    question: str | None = None
    call_count: int = 0
    total_cost_usd: float = 0.0
    total_latency_ms: int = 0
    calls: list[PromptCallOut] = Field(default_factory=list)
    # Honest: trajectory is SoT; bodies are not on dispatch.call rows.
    prompt_bodies_stored: bool = False


def build_prompt_telemetry(
    investigation_id: str, rows: list[dict[str, Any]]
) -> PromptTelemetryOut:
    """Project trajectory rows into prompt/question telemetry.

    Pure / deterministic given ``rows``. Empty trajectory → empty calls,
    question None (caller may 404 separately).
    """
    start = ActionType.INVESTIGATION_START_REQUESTED.value
    dispatch = ActionType.DISPATCH_CALL.value
    question: str | None = None
    calls: list[PromptCallOut] = []
    total_cost = 0.0
    total_lat = 0

    for row in rows:
        at = row.get("action_type")
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        if at == start and question is None:
            q = payload.get("question") or payload.get("sub_question")
            if isinstance(q, str) and q.strip():
                question = q.strip()
            continue
        if at != dispatch:
            continue
        role = str(payload.get("target_role") or row.get("role") or "unknown")
        provider = str(payload.get("provider") or "unknown")
        model = str(payload.get("model") or "unknown")
        finish = payload.get("finish_reason")
        finish_s = str(finish) if finish is not None else None
        try:
            latency = int(payload.get("latency_ms") or 0)
        except (TypeError, ValueError):
            latency = 0
        try:
            cost = float(payload.get("cost_usd") or 0.0)
        except (TypeError, ValueError):
            cost = 0.0
        try:
            tin = int(payload.get("input_tokens") or 0)
            tout = int(payload.get("output_tokens") or 0)
        except (TypeError, ValueError):
            tin, tout = 0, 0
        ph = payload.get("prompt_hash")
        calls.append(
            PromptCallOut(
                event_id=row.get("event_id"),
                emitted_at=row.get("emitted_at") or row.get("created_at"),
                role=role,
                provider=provider,
                model=model,
                tier=str(payload["tier"]) if payload.get("tier") is not None else None,
                finish_reason=finish_s,
                latency_ms=latency,
                cost_usd=round(cost, 6),
                prompt_hash=str(ph) if ph is not None else None,
                input_tokens=tin,
                output_tokens=tout,
            )
        )
        total_cost += cost
        total_lat += latency

    return PromptTelemetryOut(
        investigation_id=investigation_id,
        question=question,
        call_count=len(calls),
        total_cost_usd=round(total_cost, 6),
        total_latency_ms=total_lat,
        calls=calls,
        prompt_bodies_stored=False,
    )


@prompt_telemetry_router.get(
    "/investigations/{investigation_id}/prompt-telemetry",
    response_model=PromptTelemetryOut,
)
async def get_prompt_telemetry(investigation_id: str) -> PromptTelemetryOut:
    """Read prompt/question telemetry from the investigation trajectory."""
    rows = trajectory(investigation_id)
    if not rows:
        raise HTTPException(status_code=404, detail="investigation_not_found")
    return build_prompt_telemetry(investigation_id, rows)


def register_prompt_telemetry_routes(app) -> None:
    app.include_router(prompt_telemetry_router)
