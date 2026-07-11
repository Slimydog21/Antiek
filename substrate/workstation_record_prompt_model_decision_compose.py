"""Workstation record → prompt context → model decision pack (pure).

record_persisted, prompts_injected, live_router_authorized, secrets_stored,
live_meter_read always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.settings_decision_tree_usage_bar_compose import (
    SettingsDecisionTreeUsageBarCompose,
    SettingsDecisionTreeUsageBarComposeError,
    compose_settings_decision_tree_usage_bar,
)
from substrate.workstation_record_prompt_context_bridge import (
    PromptContextEnvelope,
    WorkstationRecordPromptContextBridgeError,
    bridge_workstation_record_prompt_context,
)
from substrate.workstation_session_insight_record_compose import (
    WorkstationSessionInsightRecordCompose,
    WorkstationSessionInsightRecordComposeError,
    compose_workstation_session_insight_record,
)

KIND_MAP = {
    "insight": "insight",
    "question": "question",
    "data": "finding",
    "claim": "finding",
}


class WorkstationRecordPromptModelDecisionComposeError(ValueError):
    """Fail-closed validation for record→prompt→model pack."""


@dataclass(frozen=True)
class WorkstationRecordPromptModelDecisionCompose:
    session_id: str
    parent_asset_id: str
    records: WorkstationSessionInsightRecordCompose
    bridge: PromptContextEnvelope
    decision: SettingsDecisionTreeUsageBarCompose
    pack_ready: bool
    proposed_prompt: str
    would_exceed: bool | None
    usage_percent: float | None
    record_persisted: bool
    prompts_injected: bool
    live_router_authorized: bool
    secrets_stored: bool
    live_meter_read: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "parent_asset_id": self.parent_asset_id,
            "records": self.records.to_dict(),
            "bridge": self.bridge.to_dict(),
            "decision": self.decision.to_dict(),
            "pack_ready": self.pack_ready,
            "proposed_prompt": self.proposed_prompt,
            "would_exceed": self.would_exceed,
            "usage_percent": self.usage_percent,
            "record_persisted": False,
            "prompts_injected": False,
            "live_router_authorized": False,
            "secrets_stored": False,
            "live_meter_read": False,
            "notes": list(self.notes),
            "authority": "workstation_record_prompt_model_decision_compose_advisory",
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorkstationRecordPromptModelDecisionComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def _map_session_to_pack_items(records: list[object]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for i, r in enumerate(records):
        if not isinstance(r, dict):
            raise WorkstationRecordPromptModelDecisionComposeError(
                f"records[{i}] must be an object"
            )
        kind = r.get("kind")
        if kind not in KIND_MAP:
            raise WorkstationRecordPromptModelDecisionComposeError(
                f"unsupported session record kind: {kind!r}"
            )
        item: dict[str, Any] = {
            "record_id": r.get("record_id"),
            "kind": KIND_MAP[str(kind)],
            "text": r.get("body"),
        }
        if r.get("source_ref"):
            item["asset_id"] = r.get("source_ref")
        items.append(item)
    return items


def compose_workstation_record_prompt_model_decision(
    *,
    session_id: object,
    parent_asset_id: object,
    records: object,
    user_prompt: object,
    selected_model_id: object,
    models: object,
    daily_cap_usd: object,
    spent_usd: object,
    operator_ack: object,
    placement: object | None = None,
    max_context_lines: object | None = None,
    projected_cost_usd_high: object | None = None,
    projected_cost_usd_low: object | None = None,
    bench_bests: object | None = None,
    focus_task: object | None = None,
    nd_shadow: object | None = None,
) -> WorkstationRecordPromptModelDecisionCompose:
    """Compose records → prompt envelope → model decision. Never injects/routes."""
    if not isinstance(operator_ack, bool):
        raise WorkstationRecordPromptModelDecisionComposeError(
            "operator_ack must be an explicit boolean"
        )
    session = _require_nonempty(session_id, field="session_id")
    parent = _require_nonempty(parent_asset_id, field="parent_asset_id")
    if not isinstance(records, list):
        raise WorkstationRecordPromptModelDecisionComposeError(
            "records must be an array"
        )

    notes: list[str] = [
        "record_persisted=false — records are pure pack only",
        "prompts_injected=false — proposed envelope only",
        "live_router_authorized=false — operator selects model",
        "secrets_stored=false",
        "live_meter_read=false",
    ]

    try:
        record_pack = compose_workstation_session_insight_record(
            session_id=session,
            parent_asset_id=parent,
            records=records,
            operator_ack=operator_ack,
            mark_for_prompt_context=True,
        )
    except WorkstationSessionInsightRecordComposeError as e:
        raise WorkstationRecordPromptModelDecisionComposeError(str(e)) from e
    notes.extend(record_pack.notes)

    pack_items = _map_session_to_pack_items(records)
    try:
        bridge = bridge_workstation_record_prompt_context(
            session_id=session,
            user_prompt=user_prompt,
            items=pack_items,
            max_context_lines=max_context_lines,
            placement=placement,
            model_decision={
                "selected_model_id": selected_model_id,
                "models": models,
                "daily_cap_usd": daily_cap_usd,
                "spent_usd": spent_usd,
                "projected_cost_usd_high": projected_cost_usd_high,
                "projected_cost_usd_low": projected_cost_usd_low,
            },
        )
    except WorkstationRecordPromptContextBridgeError as e:
        raise WorkstationRecordPromptModelDecisionComposeError(str(e)) from e
    notes.extend(bridge.notes)

    try:
        decision = compose_settings_decision_tree_usage_bar(
            selected_model_id=selected_model_id,
            models=models,
            daily_cap_usd=daily_cap_usd,
            spent_usd=spent_usd,
            projected_cost_usd_high=projected_cost_usd_high,
            projected_cost_usd_low=projected_cost_usd_low,
            bench_bests=bench_bests,
            focus_task=focus_task,
            nd_shadow=nd_shadow,
            operator_ack=operator_ack,
        )
    except SettingsDecisionTreeUsageBarComposeError as e:
        raise WorkstationRecordPromptModelDecisionComposeError(str(e)) from e
    notes.extend(decision.notes)

    would_exceed = decision.would_exceed
    if would_exceed is None and bridge.model_decision is not None:
        would_exceed = bridge.model_decision.would_exceed

    pack_ready = (
        record_pack.record_ready
        and bridge.bridge_ready
        and decision.decision_ready
        and record_pack.record_persisted is False
        and bridge.prompts_injected is False
        and decision.live_router_authorized is False
    )
    if not record_pack.record_ready:
        notes.append("pack_ready=false — session records not ready")
    elif not bridge.bridge_ready:
        notes.append("pack_ready=false — prompt context bridge not ready")
    elif not decision.decision_ready:
        notes.append("pack_ready=false — model decision tree not ready")
    else:
        notes.append(
            "pack_ready=true — records→prompt→model intent only; still pure"
        )

    if (
        record_pack.record_persisted is not False
        or record_pack.prompts_injected is not False
        or bridge.prompts_injected is not False
        or bridge.record_persisted is not False
        or decision.live_router_authorized is not False
        or decision.secrets_stored is not False
        or decision.live_meter_read is not False
    ):
        raise WorkstationRecordPromptModelDecisionComposeError(
            "invariant: nested honesty flags must remain false"
        )

    notes.extend(
        (
            "record_persisted=false",
            "prompts_injected=false",
            "live_router_authorized=false",
            "secrets_stored=false",
            "live_meter_read=false",
        )
    )

    return WorkstationRecordPromptModelDecisionCompose(
        session_id=session,
        parent_asset_id=parent,
        records=record_pack,
        bridge=bridge,
        decision=decision,
        pack_ready=pack_ready,
        proposed_prompt=bridge.proposed_prompt,
        would_exceed=would_exceed,
        usage_percent=decision.usage_percent,
        record_persisted=False,
        prompts_injected=False,
        live_router_authorized=False,
        secrets_stored=False,
        live_meter_read=False,
        notes=tuple(notes),
        authority="workstation_record_prompt_model_decision_compose_advisory",
    )


def format_workstation_record_prompt_model_decision_summary(
    c: WorkstationRecordPromptModelDecisionCompose,
) -> str:
    w = (
        "would_exceed=null"
        if c.would_exceed is None
        else f"would_exceed={c.would_exceed}"
    )
    pct = (
        "usage%=null"
        if c.usage_percent is None
        else f"usage%={c.usage_percent:.1f}"
    )
    return (
        f"pack_ready={c.pack_ready} · records={c.records.record_count} · "
        f"model={c.decision.driver.decision.selected_model_id} · "
        f"{pct} · {w} · "
        f"record_persisted=false · prompts_injected=false · "
        f"live_router_authorized=false · secrets_stored=false · live_meter_read=false"
    )


__all__ = [
    "WorkstationRecordPromptModelDecisionCompose",
    "WorkstationRecordPromptModelDecisionComposeError",
    "compose_workstation_record_prompt_model_decision",
    "format_workstation_record_prompt_model_decision_summary",
]
