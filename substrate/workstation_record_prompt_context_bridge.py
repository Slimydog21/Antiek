"""Workstation record pack → prompt context bridge (pure).

Bridges recursive records into a proposed prompt envelope.
prompts_injected and record_persisted always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from substrate.model_decision.prompt_compose import (
    ModelDecisionPromptComposeError,
    ModelDecisionPromptComposeResult,
    compose_model_decision_with_projection,
)
from substrate.workstation_recursive_record_pack import (
    WorkstationRecursiveRecordPack,
    WorkstationRecursiveRecordPackError,
    compose_workstation_recursive_record_pack,
)

ContextPlacement = Literal["prefix", "suffix"]


class WorkstationRecordPromptContextBridgeError(ValueError):
    """Fail-closed validation for record→prompt context bridge."""


@dataclass(frozen=True)
class PromptContextEnvelope:
    session_id: str
    user_prompt: str
    context_block: str
    proposed_prompt: str
    context_line_count: int
    placement: str
    pack: WorkstationRecursiveRecordPack
    model_decision: ModelDecisionPromptComposeResult | None
    bridge_ready: bool
    prompts_injected: bool
    record_persisted: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "user_prompt": self.user_prompt,
            "context_block": self.context_block,
            "proposed_prompt": self.proposed_prompt,
            "context_line_count": self.context_line_count,
            "placement": self.placement,
            "pack": self.pack.to_dict(),
            "model_decision": (
                self.model_decision.to_dict()
                if self.model_decision is not None
                else None
            ),
            "bridge_ready": self.bridge_ready,
            "prompts_injected": False,
            "record_persisted": False,
            "notes": list(self.notes),
            "authority": "workstation_record_prompt_context_bridge_advisory",
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorkstationRecordPromptContextBridgeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def _build_context_block(lines: list[str] | tuple[str, ...]) -> str:
    if not lines:
        return ""
    body = "\n".join(f"- {l}" for l in lines)
    return (
        "### Workstation recursive context (advisory; caller-supplied only)\n"
        + body
    )


def bridge_workstation_record_prompt_context(
    *,
    session_id: object,
    user_prompt: object,
    items: object | None = None,
    prebuilt_pack: object | None = None,
    max_context_lines: object | None = None,
    placement: object | None = None,
    model_decision: object | None = None,
) -> PromptContextEnvelope:
    """Bridge records into proposed prompt envelope. Never injects live."""
    sid = _require_nonempty(session_id, field="session_id")
    prompt = _require_nonempty(user_prompt, field="user_prompt")

    place: str = "prefix"
    if placement is not None:
        if placement not in ("prefix", "suffix"):
            raise WorkstationRecordPromptContextBridgeError(
                "placement must be prefix|suffix"
            )
        place = placement  # type: ignore[assignment]

    notes: list[str] = [
        "prompts_injected=false — proposed envelope only; no live injection",
        "record_persisted=false — bridge does not write records",
        "context lines are caller-supplied only (no invent)",
    ]

    pack: WorkstationRecursiveRecordPack
    if prebuilt_pack is not None:
        if not isinstance(prebuilt_pack, WorkstationRecursiveRecordPack):
            # Allow dict-shaped pack for route layer convenience
            if not isinstance(prebuilt_pack, dict):
                raise WorkstationRecordPromptContextBridgeError(
                    "prebuilt_pack must be an object when set"
                )
            if prebuilt_pack.get("record_persisted") is not False:
                raise WorkstationRecordPromptContextBridgeError(
                    "prebuilt_pack.record_persisted must be false"
                )
            if prebuilt_pack.get("prompts_injected") is not False:
                raise WorkstationRecordPromptContextBridgeError(
                    "prebuilt_pack.prompts_injected must be false"
                )
            lines = prebuilt_pack.get("prompt_context_lines")
            if not isinstance(lines, list):
                raise WorkstationRecordPromptContextBridgeError(
                    "prebuilt_pack.prompt_context_lines must be an array"
                )
            pack_sid = _require_nonempty(
                prebuilt_pack.get("session_id"),
                field="prebuilt_pack.session_id",
            )
            # Reconstruct via compose from empty items not allowed — use
            # lightweight frozen rebuild for dict prebuilt only when lines ok
            pack = WorkstationRecursiveRecordPack(
                session_id=pack_sid,
                item_count=int(prebuilt_pack.get("item_count") or len(lines)),
                by_kind=dict(
                    prebuilt_pack.get("by_kind")
                    or {
                        "insight": 0,
                        "question": 0,
                        "highlight": 0,
                        "finding": 0,
                        "open_thread": 0,
                    }
                ),
                prompt_context_lines=tuple(str(x) for x in lines),
                pack_ready=bool(prebuilt_pack.get("pack_ready")),
                record_persisted=False,
                prompts_injected=False,
                notes=tuple(prebuilt_pack.get("notes") or ()),
                authority="workstation_recursive_record_pack_advisory",
            )
        else:
            if prebuilt_pack.record_persisted is not False:
                raise WorkstationRecordPromptContextBridgeError(
                    "prebuilt_pack.record_persisted must be false"
                )
            if prebuilt_pack.prompts_injected is not False:
                raise WorkstationRecordPromptContextBridgeError(
                    "prebuilt_pack.prompts_injected must be false"
                )
            pack = prebuilt_pack
        notes.append("using prebuilt_pack (caller-supplied)")
    else:
        if not isinstance(items, list):
            raise WorkstationRecordPromptContextBridgeError(
                "items must be an array when prebuilt_pack is not set"
            )
        try:
            pack = compose_workstation_recursive_record_pack(
                session_id=sid,
                items=items,
                max_context_lines=max_context_lines,
            )
        except WorkstationRecursiveRecordPackError as e:
            raise WorkstationRecordPromptContextBridgeError(str(e)) from e
        notes.extend(pack.notes)

    context_block = _build_context_block(pack.prompt_context_lines)
    if not context_block:
        proposed = prompt
        notes.append(
            "context_block empty — proposed_prompt is user_prompt only (no invent context)"
        )
    elif place == "prefix":
        proposed = (
            f"{context_block}\n\n### User prompt\n{prompt}"
        )
        notes.append(
            f"context_lines={len(pack.prompt_context_lines)} placement=prefix"
        )
    else:
        proposed = (
            f"### User prompt\n{prompt}\n\n{context_block}"
        )
        notes.append(
            f"context_lines={len(pack.prompt_context_lines)} placement=suffix"
        )

    md: ModelDecisionPromptComposeResult | None = None
    if model_decision is not None:
        if not isinstance(model_decision, dict):
            raise WorkstationRecordPromptContextBridgeError(
                "model_decision must be an object when set"
            )
        try:
            md = compose_model_decision_with_projection(
                selected_model_id=model_decision.get("selected_model_id"),
                models=model_decision.get("models"),
                daily_cap_usd=model_decision.get("daily_cap_usd"),
                spent_usd=model_decision.get("spent_usd"),
                projected_cost_usd_high=model_decision.get(
                    "projected_cost_usd_high"
                ),
                projected_cost_usd_low=model_decision.get(
                    "projected_cost_usd_low"
                ),
            )
        except ModelDecisionPromptComposeError as e:
            raise WorkstationRecordPromptContextBridgeError(str(e)) from e
        notes.extend(md.notes)
        notes.append(
            f"model_decision attached for selected={md.selected_model_id}"
        )

    bridge_ready = True
    notes.append(
        "bridge_ready=true — proposed envelope prepared (not injected)"
    )
    notes.append("prompts_injected=false")
    notes.append("record_persisted=false")

    return PromptContextEnvelope(
        session_id=sid,
        user_prompt=prompt,
        context_block=context_block,
        proposed_prompt=proposed,
        context_line_count=len(pack.prompt_context_lines),
        placement=place,
        pack=pack,
        model_decision=md,
        bridge_ready=bridge_ready,
        prompts_injected=False,
        record_persisted=False,
        notes=tuple(notes),
        authority="workstation_record_prompt_context_bridge_advisory",
    )


__all__ = [
    "PromptContextEnvelope",
    "WorkstationRecordPromptContextBridgeError",
    "bridge_workstation_record_prompt_context",
]
