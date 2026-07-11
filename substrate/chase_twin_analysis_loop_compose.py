"""Chase → twin feed → collective analysis loop compose (pure).

live_dispatched, twin_written, analysis_written, record_persisted,
pack_dispatched always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.chase_completion_collective_analysis_compose import (
    ChaseCompletionCollectiveAnalysisCompose,
    ChaseCompletionCollectiveAnalysisComposeError,
    compose_chase_completion_collective_analysis,
)
from substrate.research_interrogation_subagent_chase_compose import (
    ResearchInterrogationSubagentChaseCompose,
    ResearchInterrogationSubagentChaseComposeError,
    compose_research_interrogation_subagent_chase,
)
from substrate.twin_chase_analysis_feed_compose import (
    TwinChaseAnalysisFeedCompose,
    TwinChaseAnalysisFeedComposeError,
    compose_twin_chase_analysis_feed,
)


class ChaseTwinAnalysisLoopComposeError(ValueError):
    """Fail-closed validation for chase-twin-analysis loop."""


@dataclass(frozen=True)
class ChaseTwinAnalysisLoopCompose:
    session_id: str
    parent_asset_id: str
    chase: ResearchInterrogationSubagentChaseCompose
    twin_feed: TwinChaseAnalysisFeedCompose | None
    analysis: ChaseCompletionCollectiveAnalysisCompose | None
    loop_ready: bool
    live_dispatched: bool
    twin_written: bool
    analysis_written: bool
    record_persisted: bool
    pack_dispatched: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "parent_asset_id": self.parent_asset_id,
            "chase": self.chase.to_dict(),
            "twin_feed": self.twin_feed.to_dict() if self.twin_feed else None,
            "analysis": self.analysis.to_dict() if self.analysis else None,
            "loop_ready": self.loop_ready,
            "live_dispatched": False,
            "twin_written": False,
            "analysis_written": False,
            "record_persisted": False,
            "pack_dispatched": False,
            "notes": list(self.notes),
            "authority": "chase_twin_analysis_loop_compose_advisory",
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ChaseTwinAnalysisLoopComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_chase_twin_analysis_loop(
    *,
    session_id: object,
    parent_asset_id: object,
    questions: object,
    chase_mode: object,
    would_exceed: object,
    operator_ack: object,
    completed_slots: object,
    analysis_kind: object,
    operator_override: object | None = None,
    selected_model_id: object | None = None,
    source_families: object | None = None,
    twin_findings: object | None = None,
    analysis_excerpt: object | None = None,
    existing_twin_asset_id: object | None = None,
    mark_for_prompt_context: object | None = None,
) -> ChaseTwinAnalysisLoopCompose:
    """Compose chase → twin feed → collective analysis pure loop."""
    if not isinstance(operator_ack, bool):
        raise ChaseTwinAnalysisLoopComposeError(
            "operator_ack must be an explicit boolean"
        )
    session = _require_nonempty(session_id, field="session_id")
    parent = _require_nonempty(parent_asset_id, field="parent_asset_id")

    notes: list[str] = [
        "live_dispatched=false — loop is pure intent only",
        "twin_written=false — twin scaffold only",
        "analysis_written=false — analysis intent only",
        "record_persisted=false",
        "pack_dispatched=false",
    ]

    try:
        chase = compose_research_interrogation_subagent_chase(
            session_id=session,
            parent_asset_id=parent,
            questions=questions,
            chase_mode=chase_mode,
            would_exceed=would_exceed,
            operator_override=operator_override,
            selected_model_id=selected_model_id,
            source_families=source_families,
            operator_ack=operator_ack,
            mark_for_twin_record=True,
        )
    except ResearchInterrogationSubagentChaseComposeError as e:
        raise ChaseTwinAnalysisLoopComposeError(str(e)) from e
    notes.extend(chase.notes)

    findings: list[dict[str, Any]] = []
    if twin_findings is not None:
        if not isinstance(twin_findings, list):
            raise ChaseTwinAnalysisLoopComposeError(
                "twin_findings must be an array when set"
            )
        for f in twin_findings:
            if not isinstance(f, dict):
                raise ChaseTwinAnalysisLoopComposeError(
                    "twin_findings entries must be objects"
                )
            findings.append(dict(f))
    elif isinstance(completed_slots, list):
        for slot in completed_slots:
            if not isinstance(slot, dict):
                continue
            slot_id = slot.get("slot_id")
            raw_findings = slot.get("findings")
            if isinstance(raw_findings, list):
                for i, body in enumerate(raw_findings):
                    if isinstance(body, str) and body.strip():
                        findings.append(
                            {
                                "source_id": f"{slot_id}_f{i}",
                                "body": body.strip(),
                                "kind": "insight",
                            }
                        )
            else:
                body = slot.get("body")
                if isinstance(body, str) and body.strip() and slot_id:
                    findings.append(
                        {
                            "source_id": str(slot_id),
                            "body": body.strip(),
                            "kind": "question",
                        }
                    )

    twin_feed: TwinChaseAnalysisFeedCompose | None = None
    if findings:
        try:
            twin_feed = compose_twin_chase_analysis_feed(
                session_id=session,
                parent_asset_id=parent,
                findings=findings,
                analysis_excerpt=analysis_excerpt,
                existing_twin_asset_id=existing_twin_asset_id,
                operator_ack=operator_ack,
                mark_for_prompt_context=mark_for_prompt_context,
            )
        except TwinChaseAnalysisFeedComposeError as e:
            raise ChaseTwinAnalysisLoopComposeError(str(e)) from e
        notes.extend(twin_feed.notes)
    else:
        notes.append("twin_feed skipped — no twin_findings or slot findings")

    analysis: ChaseCompletionCollectiveAnalysisCompose | None = None
    if isinstance(completed_slots, list) and len(completed_slots) >= 2:
        try:
            analysis = compose_chase_completion_collective_analysis(
                session_id=session,
                parent_asset_id=parent,
                slots=completed_slots,
                kind=analysis_kind,
                operator_ack=operator_ack,
            )
        except ChaseCompletionCollectiveAnalysisComposeError as e:
            raise ChaseTwinAnalysisLoopComposeError(str(e)) from e
        notes.extend(analysis.notes)
    else:
        notes.append(
            "analysis skipped — need ≥2 completed_slots for collective analysis"
        )

    loop_ready = (
        chase.chase_ready
        and twin_feed is not None
        and twin_feed.feed_ready
        and analysis is not None
        and analysis.analysis_ready
    )
    if not chase.chase_ready:
        notes.append("loop_ready=false — chase not ready")
    elif twin_feed is None or not twin_feed.feed_ready:
        notes.append("loop_ready=false — twin feed not ready")
    elif analysis is None or not analysis.analysis_ready:
        notes.append("loop_ready=false — analysis not ready")
    else:
        notes.append(
            "loop_ready=true — chase→twin→analysis intent only; still pure"
        )

    if chase.live_dispatched is not False:
        raise ChaseTwinAnalysisLoopComposeError(
            "invariant: chase honesty flags must remain false"
        )
    if twin_feed is not None and (
        twin_feed.twin_written is not False
        or twin_feed.record_persisted is not False
    ):
        raise ChaseTwinAnalysisLoopComposeError(
            "invariant: twin_feed honesty flags must remain false"
        )
    if analysis is not None and (
        analysis.analysis_written is not False
        or analysis.live_dispatched is not False
        or analysis.pack_dispatched is not False
    ):
        raise ChaseTwinAnalysisLoopComposeError(
            "invariant: analysis honesty flags must remain false"
        )

    notes.extend(
        (
            "live_dispatched=false",
            "twin_written=false",
            "analysis_written=false",
            "record_persisted=false",
            "pack_dispatched=false",
        )
    )

    return ChaseTwinAnalysisLoopCompose(
        session_id=session,
        parent_asset_id=parent,
        chase=chase,
        twin_feed=twin_feed,
        analysis=analysis,
        loop_ready=loop_ready,
        live_dispatched=False,
        twin_written=False,
        analysis_written=False,
        record_persisted=False,
        pack_dispatched=False,
        notes=tuple(notes),
        authority="chase_twin_analysis_loop_compose_advisory",
    )


def format_chase_twin_analysis_loop_summary(
    c: ChaseTwinAnalysisLoopCompose,
) -> str:
    feed = c.twin_feed.feed_ready if c.twin_feed is not None else "n/a"
    analysis_ready = (
        c.analysis.analysis_ready if c.analysis is not None else "n/a"
    )
    return (
        f"loop_ready={c.loop_ready} · chase_ready={c.chase.chase_ready} · "
        f"feed_ready={feed} · analysis_ready={analysis_ready} · "
        f"live_dispatched=false · twin_written=false · analysis_written=false · "
        f"record_persisted=false · pack_dispatched=false"
    )


__all__ = [
    "ChaseTwinAnalysisLoopCompose",
    "ChaseTwinAnalysisLoopComposeError",
    "compose_chase_twin_analysis_loop",
    "format_chase_twin_analysis_loop_summary",
]
