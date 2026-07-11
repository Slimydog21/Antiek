"""Research workstation interrogation loop compose (pure).

live_dispatched, pack_dispatched, record_persisted, prompts_injected,
live_router_authorized always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.research_interrogation_subagent_chase_compose import (
    ResearchInterrogationSubagentChaseCompose,
    ResearchInterrogationSubagentChaseComposeError,
    compose_research_interrogation_subagent_chase,
)
from substrate.workstation_record_prompt_model_decision_compose import (
    WorkstationRecordPromptModelDecisionCompose,
    WorkstationRecordPromptModelDecisionComposeError,
    compose_workstation_record_prompt_model_decision,
)


class ResearchWorkstationInterrogationLoopComposeError(ValueError):
    """Fail-closed validation for research workstation interrogation loop."""


@dataclass(frozen=True)
class ResearchWorkstationInterrogationLoopCompose:
    session_id: str
    parent_asset_id: str
    chase: ResearchInterrogationSubagentChaseCompose
    prompt_pack: WorkstationRecordPromptModelDecisionCompose
    loop_ready: bool
    live_dispatched: bool
    pack_dispatched: bool
    record_persisted: bool
    prompts_injected: bool
    live_router_authorized: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "parent_asset_id": self.parent_asset_id,
            "chase": self.chase.to_dict(),
            "prompt_pack": self.prompt_pack.to_dict(),
            "loop_ready": self.loop_ready,
            "live_dispatched": False,
            "pack_dispatched": False,
            "record_persisted": False,
            "prompts_injected": False,
            "live_router_authorized": False,
            "notes": list(self.notes),
            "authority": (
                "research_workstation_interrogation_loop_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ResearchWorkstationInterrogationLoopComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def _build_loop_records(
    questions: list[object],
    prior: object | None,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if prior is not None:
        if not isinstance(prior, list):
            raise ResearchWorkstationInterrogationLoopComposeError(
                "prior_records must be an array when set"
            )
        for r in prior:
            if isinstance(r, dict):
                records.append(dict(r))
    for q in questions:
        if not isinstance(q, dict):
            raise ResearchWorkstationInterrogationLoopComposeError(
                "questions entries must be objects"
            )
        qid = _require_nonempty(q.get("question_id"), field="question_id")
        body = _require_nonempty(q.get("body"), field="body")
        records.append(
            {
                "record_id": f"q-{qid}",
                "kind": "question",
                "body": body,
                "source_ref": qid,
            }
        )
    if len(records) == 0:
        raise ResearchWorkstationInterrogationLoopComposeError(
            "loop requires ≥1 question or prior record"
        )
    return records


def compose_research_workstation_interrogation_loop(
    *,
    session_id: object,
    parent_asset_id: object,
    questions: object,
    chase_mode: object,
    user_prompt: object,
    selected_model_id: object,
    models: object,
    daily_cap_usd: object,
    spent_usd: object,
    operator_ack: object,
    prior_records: object | None = None,
    projected_cost_usd_high: object | None = None,
    projected_cost_usd_low: object | None = None,
    would_exceed: object | None = None,
    operator_override: object | None = None,
    source_families: object | None = None,
    bench_bests: object | None = None,
    focus_task: object | None = None,
    nd_shadow: object | None = None,
    mark_for_twin_record: object | None = None,
) -> ResearchWorkstationInterrogationLoopCompose:
    """Interrogate → chase → records → prompt pack. Never dispatches/injects."""
    if not isinstance(operator_ack, bool):
        raise ResearchWorkstationInterrogationLoopComposeError(
            "operator_ack must be an explicit boolean"
        )
    session = _require_nonempty(session_id, field="session_id")
    parent = _require_nonempty(parent_asset_id, field="parent_asset_id")
    if not isinstance(questions, list) or len(questions) == 0:
        raise ResearchWorkstationInterrogationLoopComposeError(
            "questions must be a non-empty array"
        )

    notes: list[str] = [
        "live_dispatched=false — chase slots are pure intent",
        "pack_dispatched=false",
        "record_persisted=false — session substrate advisory only",
        "prompts_injected=false — proposed prompt envelope only",
        "live_router_authorized=false — operator selects model",
    ]

    mark_twin = True if mark_for_twin_record is None else mark_for_twin_record
    if not isinstance(mark_twin, bool):
        raise ResearchWorkstationInterrogationLoopComposeError(
            "mark_for_twin_record must be boolean when set"
        )

    try:
        chase = compose_research_interrogation_subagent_chase(
            session_id=session,
            parent_asset_id=parent,
            questions=questions,
            chase_mode=chase_mode,
            would_exceed=would_exceed,
            operator_ack=operator_ack,
            operator_override=operator_override,
            selected_model_id=selected_model_id,
            source_families=source_families,
            mark_for_twin_record=mark_twin,
        )
    except ResearchInterrogationSubagentChaseComposeError as e:
        raise ResearchWorkstationInterrogationLoopComposeError(str(e)) from e
    notes.extend(f"[chase] {n}" for n in chase.notes)

    records = _build_loop_records(questions, prior_records)
    notes.append(
        f"session_records={len(records)} from questions+prior (caller-supplied only)"
    )

    try:
        prompt_pack = compose_workstation_record_prompt_model_decision(
            session_id=session,
            parent_asset_id=parent,
            records=records,
            user_prompt=user_prompt,
            selected_model_id=selected_model_id,
            models=models,
            daily_cap_usd=daily_cap_usd,
            spent_usd=spent_usd,
            operator_ack=operator_ack,
            projected_cost_usd_high=projected_cost_usd_high,
            projected_cost_usd_low=projected_cost_usd_low,
            bench_bests=bench_bests,
            focus_task=(
                "deep_research" if focus_task is None else focus_task
            ),
            nd_shadow=nd_shadow,
        )
    except WorkstationRecordPromptModelDecisionComposeError as e:
        raise ResearchWorkstationInterrogationLoopComposeError(str(e)) from e
    notes.extend(f"[prompt] {n}" for n in prompt_pack.notes)

    loop_ready = (
        chase.chase_ready is True
        and prompt_pack.pack_ready is True
        and operator_ack is True
    )
    if loop_ready:
        notes.append(
            "loop_ready=true — interrogate→chase→record→prompt pack ready; still pure"
        )
    else:
        notes.append(
            "loop_ready=false — chase, prompt pack, or operator_ack gate open"
        )

    if (
        chase.live_dispatched is not False
        or chase.pack_dispatched is not False
        or chase.record_persisted is not False
        or chase.prompts_injected is not False
        or prompt_pack.record_persisted is not False
        or prompt_pack.prompts_injected is not False
        or prompt_pack.live_router_authorized is not False
    ):
        raise ResearchWorkstationInterrogationLoopComposeError(
            "invariant: honesty flags must remain false"
        )

    notes.extend(
        (
            "live_dispatched=false",
            "record_persisted=false",
            "prompts_injected=false",
            "live_router_authorized=false",
        )
    )

    return ResearchWorkstationInterrogationLoopCompose(
        session_id=session,
        parent_asset_id=parent,
        chase=chase,
        prompt_pack=prompt_pack,
        loop_ready=loop_ready,
        live_dispatched=False,
        pack_dispatched=False,
        record_persisted=False,
        prompts_injected=False,
        live_router_authorized=False,
        notes=tuple(notes),
        authority="research_workstation_interrogation_loop_compose_advisory",
    )


def format_research_workstation_interrogation_loop_summary(
    c: ResearchWorkstationInterrogationLoopCompose,
) -> str:
    return (
        f"loop_ready={c.loop_ready} · chase_slots={c.chase.slot_count} · "
        f"would_exceed={c.prompt_pack.would_exceed} · "
        f"live_dispatched=false · record_persisted=false · prompts_injected=false"
    )


__all__ = [
    "ResearchWorkstationInterrogationLoopCompose",
    "ResearchWorkstationInterrogationLoopComposeError",
    "compose_research_workstation_interrogation_loop",
    "format_research_workstation_interrogation_loop_summary",
]
