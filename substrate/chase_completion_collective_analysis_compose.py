"""Chase completion → collective analysis compose (pure).

After subagent chases complete, merge findings into draft/full analysis intent.
analysis_written, live_dispatched, pack_dispatched always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from substrate.collective_deep_research_merge import (
    CollectiveAnalysisIntent,
    CollectiveAnalysisMergeError,
    propose_collective_analysis_merge,
)

AnalysisMergeKind = Literal["draft_analysis", "full_analysis"]
VALID_STATUS = frozenset(("proposed", "open", "completed", "closed"))


class ChaseCompletionCollectiveAnalysisComposeError(ValueError):
    """Fail-closed validation for chase completion collective analysis."""


@dataclass(frozen=True)
class ChaseCompletionCollectiveAnalysisCompose:
    session_id: str
    parent_asset_id: str
    completed_slot_count: int
    selected_slot_ids: tuple[str, ...]
    analysis: CollectiveAnalysisIntent
    analysis_ready: bool
    analysis_written: bool
    live_dispatched: bool
    pack_dispatched: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "parent_asset_id": self.parent_asset_id,
            "completed_slot_count": self.completed_slot_count,
            "selected_slot_ids": list(self.selected_slot_ids),
            "analysis": self.analysis.to_dict(),
            "analysis_ready": self.analysis_ready,
            "analysis_written": False,
            "live_dispatched": False,
            "pack_dispatched": False,
            "notes": list(self.notes),
            "authority": "chase_completion_collective_analysis_compose_advisory",
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ChaseCompletionCollectiveAnalysisComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_chase_completion_collective_analysis(
    *,
    session_id: object,
    parent_asset_id: object,
    slots: object,
    kind: object,
    operator_ack: object,
    extra_findings: object | None = None,
) -> ChaseCompletionCollectiveAnalysisCompose:
    """Compose pure collective analysis intent from completed chase slots."""
    if not isinstance(operator_ack, bool):
        raise ChaseCompletionCollectiveAnalysisComposeError(
            "operator_ack must be an explicit boolean"
        )
    if kind not in ("draft_analysis", "full_analysis"):
        raise ChaseCompletionCollectiveAnalysisComposeError(
            "kind must be draft_analysis or full_analysis"
        )

    session = _require_nonempty(session_id, field="session_id")
    parent = _require_nonempty(parent_asset_id, field="parent_asset_id")
    if not isinstance(slots, list) or len(slots) < 2:
        raise ChaseCompletionCollectiveAnalysisComposeError(
            "slots must be an array with at least 2 chase slots"
        )

    notes: list[str] = [
        "analysis_written=false — pure collective analysis intent only",
        "live_dispatched=false — no chase re-dispatch",
        "pack_dispatched=false — no pack execution",
    ]

    instances: list[dict[str, Any]] = []
    selected_slot_ids: list[str] = []
    completed_slot_count = 0
    seen: set[str] = set()

    for i, s in enumerate(slots):
        if not isinstance(s, dict):
            raise ChaseCompletionCollectiveAnalysisComposeError(
                f"slots[{i}] must be an object"
            )
        slot_id = _require_nonempty(s.get("slot_id"), field=f"slots[{i}].slot_id")
        if slot_id in seen:
            raise ChaseCompletionCollectiveAnalysisComposeError(
                f"duplicate slot_id: {slot_id}"
            )
        seen.add(slot_id)
        _require_nonempty(s.get("question_id"), field=f"slots[{i}].question_id")
        p = _require_nonempty(
            s.get("parent_asset_id"), field=f"slots[{i}].parent_asset_id"
        )
        if p != parent:
            raise ChaseCompletionCollectiveAnalysisComposeError(
                "all slots must share parent_asset_id"
            )
        status = s.get("status")
        if status not in VALID_STATUS:
            raise ChaseCompletionCollectiveAnalysisComposeError(
                f"slots[{i}].status invalid"
            )
        if status == "closed":
            notes.append(f"skipped closed slot {slot_id}")
            continue
        if status == "completed":
            completed_slot_count += 1

        findings: list[str] = []
        raw = s.get("findings")
        if raw is not None:
            if not isinstance(raw, list):
                raise ChaseCompletionCollectiveAnalysisComposeError(
                    f"slots[{i}].findings must be string[] when set"
                )
            for j, f in enumerate(raw):
                if not isinstance(f, str) or not f.strip():
                    raise ChaseCompletionCollectiveAnalysisComposeError(
                        f"slots[{i}].findings[{j}] must be non-empty string"
                    )
                findings.append(f.strip())

        selected_slot_ids.append(slot_id)
        inst: dict[str, Any] = {
            "instance_id": slot_id,
            "parent_asset_id": p,
            "status": status,
        }
        if s.get("body") is not None:
            inst["highlight"] = s.get("body")
        if findings:
            inst["findings"] = findings
        instances.append(inst)

    if len(instances) < 2:
        raise ChaseCompletionCollectiveAnalysisComposeError(
            "need ≥2 non-closed chase slots for collective analysis"
        )

    notes.append(
        f"selected_slots={len(selected_slot_ids)} · completed={completed_slot_count}"
    )

    try:
        analysis = propose_collective_analysis_merge(
            instances,
            kind=kind,
            operator_ack=operator_ack,
            extra_findings=extra_findings,
        )
    except CollectiveAnalysisMergeError as e:
        raise ChaseCompletionCollectiveAnalysisComposeError(str(e)) from e
    notes.extend(analysis.notes)

    analysis_ready = False
    if kind == "full_analysis":
        analysis_ready = (
            operator_ack is True
            and completed_slot_count == len(instances)
            and analysis.analysis_written is False
        )
        if not operator_ack:
            notes.append(
                "analysis_ready=false — full_analysis requires operator_ack"
            )
        elif completed_slot_count != len(instances):
            notes.append(
                "analysis_ready=false — full_analysis requires all selected slots completed"
            )
        else:
            notes.append(
                "analysis_ready=true — full analysis intent ready; analysis_written=false"
            )
    else:
        analysis_ready = (
            len(instances) >= 2 and analysis.analysis_written is False
        )
        notes.append(
            "analysis_ready=true — draft analysis intent ready; analysis_written=false"
            if analysis_ready
            else "analysis_ready=false"
        )

    if analysis.analysis_written is not False:
        raise ChaseCompletionCollectiveAnalysisComposeError(
            "invariant: analysis_written must remain false"
        )

    notes.extend(
        (
            "analysis_written=false",
            "live_dispatched=false",
            "pack_dispatched=false",
        )
    )

    return ChaseCompletionCollectiveAnalysisCompose(
        session_id=session,
        parent_asset_id=parent,
        completed_slot_count=completed_slot_count,
        selected_slot_ids=tuple(selected_slot_ids),
        analysis=analysis,
        analysis_ready=analysis_ready,
        analysis_written=False,
        live_dispatched=False,
        pack_dispatched=False,
        notes=tuple(notes),
        authority="chase_completion_collective_analysis_compose_advisory",
    )


def format_chase_completion_collective_analysis_summary(
    c: ChaseCompletionCollectiveAnalysisCompose,
) -> str:
    return (
        f"analysis_ready={c.analysis_ready} · kind={c.analysis.kind} · "
        f"slots={len(c.selected_slot_ids)} · completed={c.completed_slot_count} · "
        f"analysis_written=false · live_dispatched=false · pack_dispatched=false"
    )


__all__ = [
    "ChaseCompletionCollectiveAnalysisCompose",
    "ChaseCompletionCollectiveAnalysisComposeError",
    "compose_chase_completion_collective_analysis",
    "format_chase_completion_collective_analysis_summary",
]
