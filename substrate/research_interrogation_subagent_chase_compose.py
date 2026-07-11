"""Research interrogation → subagent chase compose (pure).

Operator vision: live in the research workstation; send subagents to chase
questions while interrogating/assessing/wrestling. Pure chase plan only.

live_dispatched always False.
pack_dispatched always False.
record_persisted always False.
prompts_injected always False.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

ChaseMode = Literal[
    "single_question",
    "swarm_fanout",
    "collective_merge_after",
]
VALID_MODES = frozenset(
    ("single_question", "swarm_fanout", "collective_merge_after")
)
VALID_FAMILIES = frozenset(
    ("arxiv", "substack", "openalex", "web", "custom")
)
_SECRETISH = re.compile(r"sk-|api[_-]?key|secret", re.I)


class ResearchInterrogationSubagentChaseComposeError(ValueError):
    """Fail-closed validation for interrogation subagent chase."""


@dataclass(frozen=True)
class PlannedChaseSlot:
    slot_id: str
    question_id: str
    body: str
    priority: int
    selected_model_id: str | None
    source_families: tuple[str, ...]
    live_dispatched: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "slot_id": self.slot_id,
            "question_id": self.question_id,
            "body": self.body,
            "priority": self.priority,
            "selected_model_id": self.selected_model_id,
            "source_families": list(self.source_families),
            "live_dispatched": False,
        }


@dataclass(frozen=True)
class ResearchInterrogationSubagentChaseCompose:
    session_id: str
    parent_asset_id: str
    chase_mode: str
    planned_slots: tuple[PlannedChaseSlot, ...]
    slot_count: int
    budget_ready: bool
    would_exceed: bool | None
    mark_for_twin_record: bool
    chase_ready: bool
    live_dispatched: bool
    pack_dispatched: bool
    record_persisted: bool
    prompts_injected: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "parent_asset_id": self.parent_asset_id,
            "chase_mode": self.chase_mode,
            "planned_slots": [s.to_dict() for s in self.planned_slots],
            "slot_count": self.slot_count,
            "budget_ready": self.budget_ready,
            "would_exceed": self.would_exceed,
            "mark_for_twin_record": self.mark_for_twin_record,
            "chase_ready": self.chase_ready,
            "live_dispatched": False,
            "pack_dispatched": False,
            "record_persisted": False,
            "prompts_injected": False,
            "notes": list(self.notes),
            "authority": "research_interrogation_subagent_chase_compose_advisory",
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ResearchInterrogationSubagentChaseComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_research_interrogation_subagent_chase(
    *,
    session_id: object,
    parent_asset_id: object,
    questions: object,
    chase_mode: object,
    would_exceed: object,
    operator_ack: object,
    operator_override: object | None = None,
    selected_model_id: object | None = None,
    source_families: object | None = None,
    mark_for_twin_record: object | None = None,
) -> ResearchInterrogationSubagentChaseCompose:
    """Compose pure subagent chase plan. Never dispatches or persists."""
    if not isinstance(operator_ack, bool):
        raise ResearchInterrogationSubagentChaseComposeError(
            "operator_ack must be an explicit boolean"
        )
    if would_exceed is not None and not isinstance(would_exceed, bool):
        raise ResearchInterrogationSubagentChaseComposeError(
            "would_exceed must be boolean or null"
        )
    override = False if operator_override is None else operator_override
    if not isinstance(override, bool):
        raise ResearchInterrogationSubagentChaseComposeError(
            "operator_override must be boolean when set"
        )

    session = _require_nonempty(session_id, field="session_id")
    parent = _require_nonempty(parent_asset_id, field="parent_asset_id")
    if chase_mode not in VALID_MODES:
        raise ResearchInterrogationSubagentChaseComposeError(
            "chase_mode must be single_question|swarm_fanout|collective_merge_after"
        )
    if not isinstance(questions, list) or len(questions) == 0:
        raise ResearchInterrogationSubagentChaseComposeError(
            "questions must be a non-empty array"
        )

    mark = False if mark_for_twin_record is None else mark_for_twin_record
    if not isinstance(mark, bool):
        raise ResearchInterrogationSubagentChaseComposeError(
            "mark_for_twin_record must be boolean when set"
        )

    notes: list[str] = [
        "live_dispatched=false — chase plan is pure intent only",
        "pack_dispatched=false — collective merge after is intent only",
        "record_persisted=false — twin/session records not written",
        "prompts_injected=false — no live prompt mutation",
    ]

    model_id: str | None = None
    if selected_model_id is not None:
        model_id = _require_nonempty(
            selected_model_id, field="selected_model_id"
        )
        if len(model_id) > 128 or _SECRETISH.search(model_id):
            raise ResearchInterrogationSubagentChaseComposeError(
                "selected_model_id must be a model id, not secret material"
            )
        notes.append(f"selected_model_id={model_id} (operator authority)")
    else:
        notes.append(
            "selected_model_id=null — operator may choose before live chase"
        )

    families: list[str] = []
    if source_families is not None:
        if not isinstance(source_families, list):
            raise ResearchInterrogationSubagentChaseComposeError(
                "source_families must be an array when set"
            )
        seen_f: set[str] = set()
        for i, f in enumerate(source_families):
            if f not in VALID_FAMILIES:
                raise ResearchInterrogationSubagentChaseComposeError(
                    f"source_families[{i}] must be arxiv|substack|openalex|web|custom"
                )
            if f in seen_f:
                raise ResearchInterrogationSubagentChaseComposeError(
                    f"duplicate source_family: {f}"
                )
            seen_f.add(str(f))
            families.append(str(f))
    notes.append(f"source_family_count={len(families)}")

    normalized: list[dict[str, Any]] = []
    seen_q: set[str] = set()
    for i, q in enumerate(questions):
        if not isinstance(q, dict):
            raise ResearchInterrogationSubagentChaseComposeError(
                f"questions[{i}] must be an object"
            )
        qid = _require_nonempty(
            q.get("question_id"), field=f"questions[{i}].question_id"
        )
        body = _require_nonempty(q.get("body"), field=f"questions[{i}].body")
        if qid in seen_q:
            raise ResearchInterrogationSubagentChaseComposeError(
                f"duplicate question_id: {qid}"
            )
        seen_q.add(qid)
        priority = 0
        if "priority" in q and q["priority"] is not None:
            pr = q["priority"]
            if not isinstance(pr, int) or isinstance(pr, bool):
                raise ResearchInterrogationSubagentChaseComposeError(
                    f"questions[{i}].priority must be a finite integer"
                )
            priority = pr
        normalized.append(
            {"question_id": qid, "body": body, "priority": priority}
        )

    if chase_mode == "single_question" and len(normalized) != 1:
        raise ResearchInterrogationSubagentChaseComposeError(
            "single_question mode requires exactly 1 question"
        )
    if chase_mode in ("swarm_fanout", "collective_merge_after") and len(
        normalized
    ) < 2:
        raise ResearchInterrogationSubagentChaseComposeError(
            f"{chase_mode} requires ≥2 questions"
        )

    normalized.sort(
        key=lambda x: (-int(x["priority"]), str(x["question_id"]))
    )

    slots: list[PlannedChaseSlot] = []
    for idx, q in enumerate(normalized):
        slots.append(
            PlannedChaseSlot(
                slot_id=f"chase_{session}_{idx + 1}_{q['question_id']}",
                question_id=str(q["question_id"]),
                body=str(q["body"]),
                priority=int(q["priority"]),
                selected_model_id=model_id,
                source_families=tuple(families),
                live_dispatched=False,
            )
        )

    notes.append(
        f"planned_slots={len(slots)} · chase_mode={chase_mode}"
    )
    if chase_mode == "collective_merge_after":
        notes.append(
            "collective_merge_after — merge intent only; pack_dispatched=false"
        )
    if mark:
        notes.append(
            "mark_for_twin_record=true — candidates only; record_persisted=false"
        )

    budget_ready = False
    if would_exceed is None:
        if override:
            budget_ready = True
            notes.append(
                "budget_ready=true via operator_override (would_exceed unknown)"
            )
        else:
            notes.append(
                "budget_ready=false — would_exceed unknown and no operator_override"
            )
    elif would_exceed is True:
        if override:
            budget_ready = True
            notes.append(
                "budget_ready=true via operator_override despite would_exceed=true"
            )
        else:
            notes.append("budget_ready=false — would_exceed=true")
    else:
        budget_ready = True
        notes.append("budget_ready=true — would_exceed=false")

    chase_ready = operator_ack and budget_ready and len(slots) > 0
    if not operator_ack:
        notes.append("chase_ready=false — operator_ack required")
    elif not budget_ready:
        notes.append("chase_ready=false — budget gate closed")
    else:
        notes.append(
            "chase_ready=true — pure chase plan ready; still live_dispatched=false"
        )

    notes.extend(
        (
            "live_dispatched=false",
            "pack_dispatched=false",
            "record_persisted=false",
            "prompts_injected=false",
        )
    )

    return ResearchInterrogationSubagentChaseCompose(
        session_id=session,
        parent_asset_id=parent,
        chase_mode=str(chase_mode),
        planned_slots=tuple(slots),
        slot_count=len(slots),
        budget_ready=budget_ready,
        would_exceed=would_exceed if isinstance(would_exceed, bool) or would_exceed is None else None,
        mark_for_twin_record=mark,
        chase_ready=chase_ready,
        live_dispatched=False,
        pack_dispatched=False,
        record_persisted=False,
        prompts_injected=False,
        notes=tuple(notes),
        authority="research_interrogation_subagent_chase_compose_advisory",
    )


def format_research_interrogation_subagent_chase_summary(
    c: ResearchInterrogationSubagentChaseCompose,
) -> str:
    return (
        f"chase_ready={c.chase_ready} · mode={c.chase_mode} · "
        f"slots={c.slot_count} · budget_ready={c.budget_ready} · "
        f"live_dispatched=false · pack_dispatched=false · "
        f"record_persisted=false · prompts_injected=false"
    )


__all__ = [
    "PlannedChaseSlot",
    "ResearchInterrogationSubagentChaseCompose",
    "ResearchInterrogationSubagentChaseComposeError",
    "compose_research_interrogation_subagent_chase",
    "format_research_interrogation_subagent_chase_summary",
]
