"""Record→prompt model decision + HTML-native recursive twin MO pack (pure).

record_persisted / prompts_injected always False.
pdf_view_authorized / pdf_primary always False.
twin_written / charge_executed always False.
production_router_verdict always REJECT; live_router_authorized always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.html_native_recursive_twin_mo_write_pack_compose import (
    HtmlNativeRecursiveTwinMoWritePackCompose,
    HtmlNativeRecursiveTwinMoWritePackComposeError,
    compose_html_native_recursive_twin_mo_write_pack,
)
from substrate.workstation_record_prompt_model_decision_compose import (
    WorkstationRecordPromptModelDecisionCompose,
    WorkstationRecordPromptModelDecisionComposeError,
    compose_workstation_record_prompt_model_decision,
)


class RecordPromptHtmlNativeRecursiveTwinMoComposeError(ValueError):
    """Fail-closed validation for record→prompt + HTML recursive twin MO pack."""


@dataclass(frozen=True)
class RecordPromptHtmlNativeRecursiveTwinMoCompose:
    session_id: str
    parent_asset_id: str
    week_id: str
    record_prompt: WorkstationRecordPromptModelDecisionCompose
    html_pack: HtmlNativeRecursiveTwinMoWritePackCompose
    pack_ready: bool
    record_persisted: bool
    prompts_injected: bool
    live_router_authorized: bool
    secrets_stored: bool
    live_meter_read: bool
    pdf_view_authorized: bool
    pdf_primary: bool
    twin_written: bool
    charge_executed: bool
    live_execution_authorized: bool
    draft_written: bool
    analysis_written: bool
    merge_executed: bool
    inventory_mutated: bool
    live_dispatched: bool
    pack_dispatched: bool
    backlog_mutated: bool
    store_mutated: bool
    production_router_verdict: str
    purchase_executed: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "parent_asset_id": self.parent_asset_id,
            "week_id": self.week_id,
            "record_prompt": self.record_prompt.to_dict(),
            "html_pack": self.html_pack.to_dict(),
            "pack_ready": self.pack_ready,
            "record_persisted": False,
            "prompts_injected": False,
            "live_router_authorized": False,
            "secrets_stored": False,
            "live_meter_read": False,
            "pdf_view_authorized": False,
            "pdf_primary": False,
            "twin_written": False,
            "charge_executed": False,
            "live_execution_authorized": False,
            "draft_written": False,
            "analysis_written": False,
            "merge_executed": False,
            "inventory_mutated": False,
            "live_dispatched": False,
            "pack_dispatched": False,
            "backlog_mutated": False,
            "store_mutated": False,
            "production_router_verdict": "REJECT",
            "purchase_executed": False,
            "notes": list(self.notes),
            "authority": (
                "record_prompt_html_native_recursive_twin_mo_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RecordPromptHtmlNativeRecursiveTwinMoComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_record_prompt_html_native_recursive_twin_mo(
    *,
    record_prompt: object,
    html_pack: object,
    operator_ack: object,
    require_both: object | None = None,
) -> RecordPromptHtmlNativeRecursiveTwinMoCompose:
    """Record→prompt + HTML recursive twin MO. Never injects or persists."""
    if not isinstance(operator_ack, bool):
        raise RecordPromptHtmlNativeRecursiveTwinMoComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(record_prompt, dict):
        raise RecordPromptHtmlNativeRecursiveTwinMoComposeError(
            "record_prompt must be an object"
        )
    if not isinstance(html_pack, dict):
        raise RecordPromptHtmlNativeRecursiveTwinMoComposeError(
            "html_pack must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise RecordPromptHtmlNativeRecursiveTwinMoComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "record_persisted=false · prompts_injected=false · live_router_authorized=false",
        "pdf_view_authorized=false · pdf_primary=false",
        "twin_written=false · charge_executed=false",
        "production_router_verdict=REJECT",
    ]

    try:
        rp = compose_workstation_record_prompt_model_decision(
            session_id=record_prompt.get("session_id"),
            parent_asset_id=record_prompt.get("parent_asset_id"),
            records=record_prompt.get("records"),
            user_prompt=record_prompt.get("user_prompt"),
            selected_model_id=record_prompt.get("selected_model_id"),
            models=record_prompt.get("models"),
            daily_cap_usd=record_prompt.get("daily_cap_usd"),
            spent_usd=record_prompt.get("spent_usd"),
            operator_ack=operator_ack,
            placement=record_prompt.get("placement"),
            max_context_lines=record_prompt.get("max_context_lines"),
            projected_cost_usd_high=record_prompt.get("projected_cost_usd_high"),
            projected_cost_usd_low=record_prompt.get("projected_cost_usd_low"),
            bench_bests=record_prompt.get("bench_bests"),
            focus_task=record_prompt.get("focus_task"),
            nd_shadow=record_prompt.get("nd_shadow"),
        )
    except WorkstationRecordPromptModelDecisionComposeError as e:
        raise RecordPromptHtmlNativeRecursiveTwinMoComposeError(str(e)) from e
    notes.extend(f"[record_prompt] {n}" for n in rp.notes)

    try:
        hp = compose_html_native_recursive_twin_mo_write_pack(
            html_view=html_pack.get("html_view"),
            twin_mo=html_pack.get("twin_mo"),
            operator_ack=operator_ack,
            require_both=html_pack.get("require_both"),
        )
    except HtmlNativeRecursiveTwinMoWritePackComposeError as e:
        raise RecordPromptHtmlNativeRecursiveTwinMoComposeError(str(e)) from e
    notes.extend(f"[html_pack] {n}" for n in hp.notes)

    session = _require_nonempty(rp.session_id, field="session_id")
    parent = _require_nonempty(rp.parent_asset_id, field="parent_asset_id")
    week = _require_nonempty(hp.week_id, field="week_id")

    aligned = hp.session_id == session and hp.parent_asset_id == parent
    if not aligned:
        notes.append(
            "session/parent mismatch between record_prompt and html_pack — pack_ready blocked"
        )

    if require:
        pack_ready = (
            aligned
            and rp.pack_ready is True
            and hp.pack_ready is True
            and hp.production_router_verdict == "REJECT"
            and rp.prompts_injected is False
            and hp.pdf_primary is False
            and operator_ack is True
        )
    else:
        pack_ready = (
            aligned
            and operator_ack is True
            and hp.production_router_verdict == "REJECT"
            and rp.prompts_injected is False
            and (rp.pack_ready is True or hp.pack_ready is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — record→prompt + HTML-native recursive twin MO ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — record_prompt, html_pack, alignment, or operator_ack gate open"
        )

    if (
        rp.record_persisted is not False
        or rp.prompts_injected is not False
        or rp.live_router_authorized is not False
        or rp.secrets_stored is not False
        or rp.live_meter_read is not False
        or hp.pdf_view_authorized is not False
        or hp.pdf_primary is not False
        or hp.twin_written is not False
        or hp.charge_executed is not False
        or hp.production_router_verdict != "REJECT"
        or hp.live_router_authorized is not False
    ):
        raise RecordPromptHtmlNativeRecursiveTwinMoComposeError(
            "invariant: honesty flags must remain false"
        )

    notes.extend(
        (
            "record_persisted=false",
            "prompts_injected=false",
            "live_router_authorized=false",
            "secrets_stored=false",
            "live_meter_read=false",
            "pdf_view_authorized=false",
            "pdf_primary=false",
            "twin_written=false",
            "charge_executed=false",
            "live_execution_authorized=false",
            "draft_written=false",
            "analysis_written=false",
            "merge_executed=false",
            "inventory_mutated=false",
            "live_dispatched=false",
            "pack_dispatched=false",
            "backlog_mutated=false",
            "store_mutated=false",
            "production_router_verdict=REJECT",
            "purchase_executed=false",
        )
    )

    return RecordPromptHtmlNativeRecursiveTwinMoCompose(
        session_id=session,
        parent_asset_id=parent,
        week_id=week,
        record_prompt=rp,
        html_pack=hp,
        pack_ready=pack_ready,
        record_persisted=False,
        prompts_injected=False,
        live_router_authorized=False,
        secrets_stored=False,
        live_meter_read=False,
        pdf_view_authorized=False,
        pdf_primary=False,
        twin_written=False,
        charge_executed=False,
        live_execution_authorized=False,
        draft_written=False,
        analysis_written=False,
        merge_executed=False,
        inventory_mutated=False,
        live_dispatched=False,
        pack_dispatched=False,
        backlog_mutated=False,
        store_mutated=False,
        production_router_verdict="REJECT",
        purchase_executed=False,
        notes=tuple(notes),
        authority="record_prompt_html_native_recursive_twin_mo_compose_advisory",
    )


def format_record_prompt_html_native_recursive_twin_mo_summary(
    c: RecordPromptHtmlNativeRecursiveTwinMoCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"record_prompt_ready={c.record_prompt.pack_ready} · "
        f"html_pack_ready={c.html_pack.pack_ready} · "
        f"would_exceed={c.record_prompt.would_exceed} · "
        f"verdict={c.production_router_verdict} · "
        f"prompts_injected=false · pdf_primary=false · record_persisted=false"
    )


__all__ = [
    "RecordPromptHtmlNativeRecursiveTwinMoCompose",
    "RecordPromptHtmlNativeRecursiveTwinMoComposeError",
    "compose_record_prompt_html_native_recursive_twin_mo",
    "format_record_prompt_html_native_recursive_twin_mo_summary",
]
