"""Research progress telemetry for multi-minute deep-research jobs.

Competitive residual (ar): OpenAI/Perplexity/Gemini surface multi-step progress.
Antiek records plan → gather → synthesize → cite events on a spawn (offline,
append-only) so the workstation and Midnight Oil can show honest status without
inventing completion.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

from .store import EngagementStore

ProgressStage = Literal["plan", "gather", "synthesize", "cite", "complete", "failed"]

_VALID_STAGES = frozenset(
    {"plan", "gather", "synthesize", "cite", "complete", "failed"}
)

# Residual (aqc): closed competitive multi-stage pipeline (parity frontend
# COMPETITIVE_DR_PIPELINE_STAGES · ape · complete/failed → terminal).
COMPETITIVE_DR_PIPELINE_STAGES: tuple[str, ...] = (
    "plan",
    "gather",
    "synthesize",
    "cite",
    "terminal",
)


@dataclass(frozen=True)
class ProgressEvent:
    spawn_id: str
    stage: ProgressStage
    message: str
    ts: float
    sequence: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "spawn_id": self.spawn_id,
            "stage": self.stage,
            "message": self.message,
            "ts": self.ts,
            "sequence": self.sequence,
        }


def _run_key(spawn_id: str) -> str:
    return f"_progress:{spawn_id}"


def record_progress(
    spawn_id: str,
    stage: ProgressStage | str,
    message: str = "",
    *,
    store: EngagementStore,
    ts: float | None = None,
) -> ProgressEvent:
    """Append one progress event for a spawn. Raises if stage invalid or spawn missing."""
    if not spawn_id.strip():
        raise ValueError("spawn_id is required")
    stage_s = str(stage).strip().lower()
    if stage_s not in _VALID_STAGES:
        raise ValueError(
            f"invalid stage {stage!r}; expected one of {sorted(_VALID_STAGES)}"
        )
    if store.get_spawn(spawn_id) is None:
        raise KeyError(f"unknown spawn_id: {spawn_id}")

    key = _run_key(spawn_id)
    # Progress log lives in the document store under a reserved key.
    doc = store.get_document(key) or {"document_id": key, "events": []}
    events = list(doc.get("events") or [])
    seq = len(events) + 1
    ev = ProgressEvent(
        spawn_id=spawn_id,
        stage=stage_s,  # type: ignore[arg-type]
        message=str(message or "").strip()[:500],
        ts=float(ts if ts is not None else time.time()),
        sequence=seq,
    )
    events.append(ev.to_dict())
    store.put_document(
        key,
        {
            "document_id": key,
            "spawn_id": spawn_id,
            "events": events,
            "latest_stage": stage_s,
            "view_format": "html",
            "mode": "research_progress",
        },
    )
    return ev


def list_progress(spawn_id: str, *, store: EngagementStore) -> list[ProgressEvent]:
    doc = store.get_document(_run_key(spawn_id))
    if not doc:
        return []
    out: list[ProgressEvent] = []
    for e in doc.get("events") or []:
        out.append(
            ProgressEvent(
                spawn_id=str(e.get("spawn_id") or spawn_id),
                stage=str(e.get("stage") or "plan"),  # type: ignore[arg-type]
                message=str(e.get("message") or ""),
                ts=float(e.get("ts") or 0),
                sequence=int(e.get("sequence") or 0),
            )
        )
    return out


def competitive_stage_pipeline_progress(
    *,
    events: Sequence[dict[str, Any] | ProgressEvent] | None = None,
    latest_stage: str | None = None,
    is_terminal: bool | None = None,
) -> dict[str, Any]:
    """Residual (aqc): multi-stage pipeline completeness (never invent stages).

    Parity frontend ``competitiveDrStageProgress`` / COMPETITIVE_DR_PIPELINE_STAGES.
    Maps complete/failed → terminal.
    """
    seen: set[str] = set()

    def _norm(stage: str | None) -> str | None:
        s = str(stage or "").strip().lower()
        if not s:
            return None
        if s in ("complete", "failed", "terminal", "done"):
            return "terminal"
        if s in COMPETITIVE_DR_PIPELINE_STAGES:
            return s
        if "plan" in s:
            return "plan"
        if "gather" in s or "search" in s:
            return "gather"
        if "synth" in s or "draft" in s:
            return "synthesize"
        if "cite" in s or "citation" in s:
            return "cite"
        return None

    for e in events or ():
        if isinstance(e, ProgressEvent):
            n = _norm(e.stage)
        elif isinstance(e, dict):
            n = _norm(str(e.get("stage") or ""))
        else:
            n = None
        if n:
            seen.add(n)
    latest_n = _norm(latest_stage)
    if latest_n:
        seen.add(latest_n)
    if is_terminal:
        seen.add("terminal")
    completed = [s for s in COMPETITIVE_DR_PIPELINE_STAGES if s in seen]
    total = len(COMPETITIVE_DR_PIPELINE_STAGES)
    completed_count = len(completed)
    if is_terminal or "terminal" in seen:
        current: str | None = "terminal"
    elif latest_n and latest_n != "terminal":
        current = latest_n
    elif completed:
        current = completed[-1]
    else:
        current = None
    return {
        "stages": list(COMPETITIVE_DR_PIPELINE_STAGES),
        "completed": completed,
        "current": current,
        "completed_count": completed_count,
        "total": total,
        "coverage_ratio": (completed_count / total) if total else 0.0,
        "is_terminal": bool(is_terminal) or "terminal" in seen,
    }


def progress_payload(
    spawn_id: str,
    *,
    store: EngagementStore,
    include_html: bool = False,
) -> dict[str, Any]:
    """Product-facing progress snapshot for API/UI.

    Residual (jz): include spawn ``research_tier`` when reserved (default deep)
    so multi-minute progress UI can stay aligned without a second fetch.
    Residual (aqc): include ``stage_pipeline`` completeness summary (ape parity).
    """
    from substrate.dispatch.research_tier import normalize_research_tier

    events = list_progress(spawn_id, store=store)
    stages = [e.stage for e in events]
    latest = stages[-1] if stages else None
    is_terminal = latest in ("complete", "failed") if latest else False
    spawn_row = store.get_spawn(spawn_id) or {}
    tier = normalize_research_tier(spawn_row.get("research_tier"))
    event_dicts = [e.to_dict() for e in events]
    stage_pipeline = competitive_stage_pipeline_progress(
        events=event_dicts,
        latest_stage=latest,
        is_terminal=is_terminal,
    )
    # Residual (aqf): world-class readiness from multi-stage only (hops unknown
    # on progress surface · never invent hop coverage).
    from .evidence import competitive_dr_world_class_readiness

    world_class = competitive_dr_world_class_readiness(
        stage_coverage_ratio=float(stage_pipeline.get("coverage_ratio") or 0),
        hop_coverage_ratio=None,
        stage_is_terminal=bool(stage_pipeline.get("is_terminal")),
    )
    payload: dict[str, Any] = {
        "spawn_id": spawn_id,
        "event_count": len(events),
        "events": event_dicts,
        "latest_stage": latest,
        "is_terminal": is_terminal,
        "stage_pipeline": stage_pipeline,
        "world_class_readiness": world_class,
        "research_tier": tier,
        "view_format": "html",
        "product_panel": "research_progress",
        "source": "engagement_spine.progress",
        "notes": [],
    }
    if not events:
        payload["notes"] = [
            "No progress events yet — deep research has not recorded plan/gather/synthesize/cite."
        ]
    if include_html:
        payload["html"] = project_progress_html(payload)
    return payload


def project_progress_html(payload: dict[str, Any]) -> str:
    from .project import project_to_html

    spawn_id = str(payload.get("spawn_id") or "")
    latest = payload.get("latest_stage") or "(none)"
    blocks: list[dict[str, Any]] = [
        {
            "type": "heading",
            "attrs": {"level": 1},
            "content": [{"type": "text", "text": "Deep research progress"}],
        },
        {
            "type": "paragraph",
            "content": [
                {
                    "type": "text",
                    "text": (
                        f"Spawn {spawn_id} · latest={latest}"
                        + (
                            f" · tier={payload.get('research_tier')}"
                            if payload.get("research_tier")
                            else ""
                        )
                        + " · view: HTML"
                    ),
                }
            ],
        },
    ]
    # Residual (aqc): competitive multi-stage pipeline completeness line.
    stage_pipe = payload.get("stage_pipeline")
    if not isinstance(stage_pipe, dict):
        stage_pipe = competitive_stage_pipeline_progress(
            events=payload.get("events") or [],
            latest_stage=str(latest) if latest != "(none)" else None,
            is_terminal=bool(payload.get("is_terminal")),
        )
    completed_n = int(stage_pipe.get("completed_count") or 0)
    total_n = int(stage_pipe.get("total") or len(COMPETITIVE_DR_PIPELINE_STAGES))
    current = stage_pipe.get("current") or ""
    terminal_s = " · terminal" if stage_pipe.get("is_terminal") else ""
    current_s = f" · current={current}" if current else ""
    blocks.append(
        {
            "type": "paragraph",
            "content": [
                {
                    "type": "text",
                    "text": (
                        f"Competitive pipeline · {completed_n}/{total_n} stages"
                        f"{current_s}{terminal_s}"
                    ),
                }
            ],
        }
    )
    events = payload.get("events") or []
    if not events:
        blocks.append(
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": "(no progress events yet)"}],
            }
        )
    else:
        for e in events:
            if not isinstance(e, dict):
                continue
            blocks.append(
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                f"#{e.get('sequence')} [{e.get('stage')}] "
                                f"{e.get('message') or ''}"
                            ),
                        }
                    ],
                }
            )
    return project_to_html(
        {"type": "doc", "content": blocks},
        document_id=f"progress-{spawn_id}",
        creator="engagement_spine.progress",
    )


def seed_default_pipeline(
    spawn_id: str,
    *,
    store: EngagementStore,
    messages: Sequence[str] | None = None,
) -> list[ProgressEvent]:
    """Record a default plan→gather→synthesize→cite skeleton (not terminal)."""
    defaults = messages or (
        "Plan research questions",
        "Gather sources (arxiv/substack/web)",
        "Synthesize findings",
        "Cite evidence",
    )
    stages: list[ProgressStage] = ["plan", "gather", "synthesize", "cite"]
    out: list[ProgressEvent] = []
    for stage, msg in zip(stages, defaults, strict=False):
        out.append(record_progress(spawn_id, stage, msg, store=store))
    return out
