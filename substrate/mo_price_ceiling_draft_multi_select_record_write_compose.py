"""MO price-ceiling over draft-before-merge multi-select record write pack (pure).

live_execution_authorized / charge_executed always False.
draft_written / merge_executed / live_dispatched always False.
production_router_verdict always REJECT.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.draft_before_merge_multi_select_record_write_compose import (
    DraftBeforeMergeMultiSelectRecordWriteCompose,
    DraftBeforeMergeMultiSelectRecordWriteComposeError,
    compose_draft_before_merge_multi_select_record_write,
)
from substrate.midnight_oil_price_ceiling_approval_compose import (
    MidnightOilPriceCeilingApprovalCompose,
    MidnightOilPriceCeilingApprovalComposeError,
    compose_midnight_oil_price_ceiling_approval,
)


class MoPriceCeilingDraftMultiSelectRecordWriteComposeError(ValueError):
    """Fail-closed validation for MO price-ceiling + draft multi pack."""


@dataclass(frozen=True)
class MoPriceCeilingDraftMultiSelectRecordWriteCompose:
    session_id: str
    parent_asset_id: str
    operator_id: str
    mo: MidnightOilPriceCeilingApprovalCompose
    draft_multi: DraftBeforeMergeMultiSelectRecordWriteCompose
    pack_ready: bool
    live_execution_authorized: bool
    charge_executed: bool
    draft_written: bool
    merge_executed: bool
    live_dispatched: bool
    pack_dispatched: bool
    prompts_injected: bool
    record_persisted: bool
    remote_index_queried: bool
    twin_written: bool
    analysis_written: bool
    production_router_verdict: str
    live_router_authorized: bool
    purchase_executed: bool
    hosted: bool
    store_mutated: bool
    backlog_mutated: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "parent_asset_id": self.parent_asset_id,
            "operator_id": self.operator_id,
            "mo": self.mo.to_dict(),
            "draft_multi": self.draft_multi.to_dict(),
            "pack_ready": self.pack_ready,
            "live_execution_authorized": False,
            "charge_executed": False,
            "draft_written": False,
            "merge_executed": False,
            "live_dispatched": False,
            "pack_dispatched": False,
            "prompts_injected": False,
            "record_persisted": False,
            "remote_index_queried": False,
            "twin_written": False,
            "analysis_written": False,
            "production_router_verdict": "REJECT",
            "live_router_authorized": False,
            "purchase_executed": False,
            "hosted": False,
            "store_mutated": False,
            "backlog_mutated": False,
            "notes": list(self.notes),
            "authority": "mo_price_ceiling_draft_multi_select_record_write_compose_advisory",
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MoPriceCeilingDraftMultiSelectRecordWriteComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_mo_price_ceiling_draft_multi_select_record_write(
    *,
    mo: object,
    draft_multi: object,
    operator_ack: object,
    require_both: object | None = None,
) -> MoPriceCeilingDraftMultiSelectRecordWriteCompose:
    """MO price-ceiling + draft multi-select pack. Never charges or launches."""
    if not isinstance(operator_ack, bool):
        raise MoPriceCeilingDraftMultiSelectRecordWriteComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(mo, dict):
        raise MoPriceCeilingDraftMultiSelectRecordWriteComposeError(
            "mo must be an object"
        )
    if not isinstance(draft_multi, dict):
        raise MoPriceCeilingDraftMultiSelectRecordWriteComposeError(
            "draft_multi must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise MoPriceCeilingDraftMultiSelectRecordWriteComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "live_execution_authorized=false · charge_executed=false",
        "draft_written=false · merge_executed=false · live_dispatched=false",
        "production_router_verdict=REJECT",
    ]

    try:
        mo_pack = compose_midnight_oil_price_ceiling_approval(
            operator_id=mo.get("operator_id"),
            work_minutes=mo.get("work_minutes"),
            goals=mo.get("goals"),
            price_ceiling_ack=mo.get("price_ceiling_ack"),
            operator_ack=operator_ack,
            stage=mo.get("stage"),
            usd_per_hour=mo.get("usd_per_hour"),
            goal_intensity=mo.get("goal_intensity"),
            approved_ceiling_usd=mo.get("approved_ceiling_usd"),
            below_recommend_override=mo.get("below_recommend_override"),
            unattended_ack=mo.get("unattended_ack"),
            spend_consent=mo.get("spend_consent"),
        )
    except MidnightOilPriceCeilingApprovalComposeError as e:
        raise MoPriceCeilingDraftMultiSelectRecordWriteComposeError(str(e)) from e
    notes.extend(f"[mo] {n}" for n in mo_pack.notes)

    try:
        dm = compose_draft_before_merge_multi_select_record_write(
            draft_gate=draft_multi.get("draft_gate"),
            multi_pack=draft_multi.get("multi_pack"),
            operator_ack=operator_ack,
            require_both=draft_multi.get("require_both"),
        )
    except DraftBeforeMergeMultiSelectRecordWriteComposeError as e:
        raise MoPriceCeilingDraftMultiSelectRecordWriteComposeError(str(e)) from e
    notes.extend(f"[draft_multi] {n}" for n in dm.notes)

    session = _require_nonempty(dm.session_id, field="session_id")
    parent = _require_nonempty(dm.parent_asset_id, field="parent_asset_id")
    operator = _require_nonempty(mo_pack.operator_id, field="operator_id")

    if require:
        pack_ready = (
            mo_pack.pack_ready is True
            and dm.pack_ready is True
            and dm.production_router_verdict == "REJECT"
            and mo_pack.live_execution_authorized is False
            and mo_pack.charge_executed is False
            and dm.draft_written is False
            and dm.merge_executed is False
            and dm.live_dispatched is False
            and operator_ack is True
        )
    else:
        pack_ready = (
            operator_ack is True
            and dm.production_router_verdict == "REJECT"
            and mo_pack.charge_executed is False
            and (mo_pack.pack_ready is True or dm.pack_ready is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — MO price-ceiling + draft multi-select record write ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — mo, draft_multi, or operator_ack gate open"
        )

    if (
        mo_pack.live_execution_authorized is not False
        or mo_pack.charge_executed is not False
        or dm.draft_written is not False
        or dm.merge_executed is not False
        or dm.live_dispatched is not False
        or dm.production_router_verdict != "REJECT"
    ):
        raise MoPriceCeilingDraftMultiSelectRecordWriteComposeError(
            "invariant: honesty flags must remain false"
        )

    notes.extend(
        (
            "live_execution_authorized=false",
            "charge_executed=false",
            "draft_written=false",
            "merge_executed=false",
            "live_dispatched=false",
            "pack_dispatched=false",
            "prompts_injected=false",
            "record_persisted=false",
            "remote_index_queried=false",
            "twin_written=false",
            "analysis_written=false",
            "production_router_verdict=REJECT",
            "live_router_authorized=false",
            "purchase_executed=false",
            "hosted=false",
            "store_mutated=false",
            "backlog_mutated=false",
        )
    )

    return MoPriceCeilingDraftMultiSelectRecordWriteCompose(
        session_id=session,
        parent_asset_id=parent,
        operator_id=operator,
        mo=mo_pack,
        draft_multi=dm,
        pack_ready=pack_ready,
        live_execution_authorized=False,
        charge_executed=False,
        draft_written=False,
        merge_executed=False,
        live_dispatched=False,
        pack_dispatched=False,
        prompts_injected=False,
        record_persisted=False,
        remote_index_queried=False,
        twin_written=False,
        analysis_written=False,
        production_router_verdict="REJECT",
        live_router_authorized=False,
        purchase_executed=False,
        hosted=False,
        store_mutated=False,
        backlog_mutated=False,
        notes=tuple(notes),
        authority="mo_price_ceiling_draft_multi_select_record_write_compose_advisory",
    )


def format_mo_price_ceiling_draft_multi_select_record_write_summary(
    c: MoPriceCeilingDraftMultiSelectRecordWriteCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"mo_ready={c.mo.pack_ready} · "
        f"ceiling_approved={c.mo.ceiling_approved} · "
        f"draft_multi_ready={c.draft_multi.pack_ready} · "
        f"verdict={c.production_router_verdict} · "
        f"live_execution_authorized=false · charge_executed=false · draft_written=false"
    )


__all__ = [
    "MoPriceCeilingDraftMultiSelectRecordWriteCompose",
    "MoPriceCeilingDraftMultiSelectRecordWriteComposeError",
    "compose_mo_price_ceiling_draft_multi_select_record_write",
    "format_mo_price_ceiling_draft_multi_select_record_write_summary",
]
