"""Workstation session insight/question/data record compose (pure).

record_persisted, prompts_injected, store_mutated always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

RecordKind = Literal["insight", "question", "data", "claim"]
VALID_KINDS = frozenset(("insight", "question", "data", "claim"))


class WorkstationSessionInsightRecordComposeError(ValueError):
    """Fail-closed validation for session insight records."""


@dataclass(frozen=True)
class WorkstationSessionInsightRecordCompose:
    session_id: str
    parent_asset_id: str
    record_ids: tuple[str, ...]
    record_count: int
    insight_count: int
    question_count: int
    data_count: int
    claim_count: int
    mark_for_prompt_context: bool
    record_ready: bool
    record_persisted: bool
    prompts_injected: bool
    store_mutated: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "parent_asset_id": self.parent_asset_id,
            "record_ids": list(self.record_ids),
            "record_count": self.record_count,
            "insight_count": self.insight_count,
            "question_count": self.question_count,
            "data_count": self.data_count,
            "claim_count": self.claim_count,
            "mark_for_prompt_context": self.mark_for_prompt_context,
            "record_ready": self.record_ready,
            "record_persisted": False,
            "prompts_injected": False,
            "store_mutated": False,
            "notes": list(self.notes),
            "authority": "workstation_session_insight_record_compose_advisory",
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorkstationSessionInsightRecordComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_workstation_session_insight_record(
    *,
    session_id: object,
    parent_asset_id: object,
    records: object,
    operator_ack: object,
    mark_for_prompt_context: object | None = None,
) -> WorkstationSessionInsightRecordCompose:
    """Compose session memory pack. Never persists or injects prompts."""
    if not isinstance(operator_ack, bool):
        raise WorkstationSessionInsightRecordComposeError(
            "operator_ack must be an explicit boolean"
        )
    sid = _require_nonempty(session_id, field="session_id")
    parent = _require_nonempty(parent_asset_id, field="parent_asset_id")
    if not isinstance(records, list) or len(records) == 0:
        raise WorkstationSessionInsightRecordComposeError(
            "records must be a non-empty array"
        )
    mark = False if mark_for_prompt_context is None else mark_for_prompt_context
    if not isinstance(mark, bool):
        raise WorkstationSessionInsightRecordComposeError(
            "mark_for_prompt_context must be boolean when set"
        )

    notes: list[str] = [
        "record_persisted=false — session records not written to store",
        "prompts_injected=false — prompt-context mark is advisory only",
        "store_mutated=false",
        "record bodies are caller-supplied only (no invent)",
    ]

    record_ids: list[str] = []
    seen: set[str] = set()
    insight_count = 0
    question_count = 0
    data_count = 0
    claim_count = 0

    for i, r in enumerate(records):
        if not isinstance(r, dict):
            raise WorkstationSessionInsightRecordComposeError(
                f"records[{i}] must be an object"
            )
        rid = _require_nonempty(r.get("record_id"), field=f"records[{i}].record_id")
        if rid in seen:
            raise WorkstationSessionInsightRecordComposeError(
                f"duplicate record_id: {rid}"
            )
        seen.add(rid)
        kind = r.get("kind")
        if kind not in VALID_KINDS:
            raise WorkstationSessionInsightRecordComposeError(
                f"records[{i}].kind must be insight|question|data|claim"
            )
        _require_nonempty(r.get("body"), field=f"records[{i}].body")
        if r.get("source_ref") is not None:
            _require_nonempty(r.get("source_ref"), field=f"records[{i}].source_ref")
        record_ids.append(rid)
        if kind == "insight":
            insight_count += 1
        elif kind == "question":
            question_count += 1
        elif kind == "data":
            data_count += 1
        else:
            claim_count += 1

    record_count = len(record_ids)
    notes.append(
        f"records={record_count} · insights={insight_count} · "
        f"questions={question_count} · data={data_count} · claims={claim_count}"
    )
    if mark:
        notes.append(
            "mark_for_prompt_context=true — candidates for record→prompt bridge "
            "(still prompts_injected=false)"
        )

    record_ready = operator_ack and record_count >= 1
    if not operator_ack:
        notes.append("record_ready=false — operator_ack required")
    else:
        notes.append(
            "record_ready=true — provisional session memory pack "
            "(still record_persisted=false)"
        )
    notes.extend(
        (
            "record_persisted=false",
            "prompts_injected=false",
            "store_mutated=false",
        )
    )

    return WorkstationSessionInsightRecordCompose(
        session_id=sid,
        parent_asset_id=parent,
        record_ids=tuple(record_ids),
        record_count=record_count,
        insight_count=insight_count,
        question_count=question_count,
        data_count=data_count,
        claim_count=claim_count,
        mark_for_prompt_context=mark,
        record_ready=record_ready,
        record_persisted=False,
        prompts_injected=False,
        store_mutated=False,
        notes=tuple(notes),
        authority="workstation_session_insight_record_compose_advisory",
    )


__all__ = [
    "WorkstationSessionInsightRecordCompose",
    "WorkstationSessionInsightRecordComposeError",
    "compose_workstation_session_insight_record",
]
