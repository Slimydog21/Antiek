"""Research progress telemetry for multi-minute deep-research jobs.

Competitive residual (ar): OpenAI/Perplexity/Gemini surface multi-step progress.
Antiek records plan → gather → synthesize → cite events on a spawn (offline,
append-only) so the workstation and Midnight Oil can show honest status without
inventing completion.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Literal, Sequence

from .store import EngagementStore

ProgressStage = Literal["plan", "gather", "synthesize", "cite", "complete", "failed"]

_VALID_STAGES = frozenset(
    {"plan", "gather", "synthesize", "cite", "complete", "failed"}
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


def progress_payload(
    spawn_id: str,
    *,
    store: EngagementStore,
    include_html: bool = False,
) -> dict[str, Any]:
    """Product-facing progress snapshot for API/UI.

    Residual (jz): include spawn ``research_tier`` when reserved (default deep)
    so multi-minute progress UI can stay aligned without a second fetch.
    """
    from substrate.dispatch.research_tier import normalize_research_tier

    events = list_progress(spawn_id, store=store)
    stages = [e.stage for e in events]
    latest = stages[-1] if stages else None
    spawn_row = store.get_spawn(spawn_id) or {}
    tier = normalize_research_tier(spawn_row.get("research_tier"))
    payload: dict[str, Any] = {
        "spawn_id": spawn_id,
        "event_count": len(events),
        "events": [e.to_dict() for e in events],
        "latest_stage": latest,
        "is_terminal": latest in ("complete", "failed") if latest else False,
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
                    "text": f"Spawn {spawn_id} · latest={latest} · view: HTML",
                }
            ],
        },
    ]
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
