"""MO price-ceiling over recursive twin note-taker + twin search model decision pack (pure).

live_execution_authorized / charge_executed always False.
twin_written / remote_index_queried always False.
production_router_verdict always REJECT.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.midnight_oil_price_ceiling_approval_compose import (
    MidnightOilPriceCeilingApprovalCompose,
    MidnightOilPriceCeilingApprovalComposeError,
    compose_midnight_oil_price_ceiling_approval,
)
from substrate.recursive_twin_note_taker_twin_search_model_decision_compose import (
    RecursiveTwinNoteTakerTwinSearchModelDecisionCompose,
    RecursiveTwinNoteTakerTwinSearchModelDecisionComposeError,
    compose_recursive_twin_note_taker_twin_search_model_decision,
)


class MoPriceCeilingRecursiveTwinNoteTakerTwinSearchComposeError(ValueError):
    """Fail-closed validation for MO price-ceiling + recursive twin pack."""


@dataclass(frozen=True)
class MoPriceCeilingRecursiveTwinNoteTakerTwinSearchCompose:
    session_id: str
    parent_asset_id: str
    week_id: str
    asset_id: str
    title: str
    account_id: str
    mo: MidnightOilPriceCeilingApprovalCompose
    twin_pack: RecursiveTwinNoteTakerTwinSearchModelDecisionCompose
    pack_ready: bool
    live_execution_authorized: bool
    charge_executed: bool
    live_dispatched: bool
    pack_dispatched: bool
    merge_executed: bool
    draft_written: bool
    analysis_written: bool
    live_router_authorized: bool
    secrets_stored: bool
    live_meter_read: bool
    remote_index_queried: bool
    backlog_mutated: bool
    store_mutated: bool
    suite_rewritten: bool
    pdf_view_authorized: bool
    pdf_primary: bool
    twin_written: bool
    prompts_injected: bool
    live_dispatch_authorized: bool
    inventory_mutated: bool
    record_persisted: bool
    purchase_executed: bool
    hosted: bool
    remote_fetched: bool
    production_router_verdict: str
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "parent_asset_id": self.parent_asset_id,
            "week_id": self.week_id,
            "asset_id": self.asset_id,
            "title": self.title,
            "account_id": self.account_id,
            "mo": self.mo.to_dict(),
            "twin_pack": self.twin_pack.to_dict(),
            "pack_ready": self.pack_ready,
            "live_execution_authorized": False,
            "charge_executed": False,
            "live_dispatched": False,
            "pack_dispatched": False,
            "merge_executed": False,
            "draft_written": False,
            "analysis_written": False,
            "live_router_authorized": False,
            "secrets_stored": False,
            "live_meter_read": False,
            "remote_index_queried": False,
            "backlog_mutated": False,
            "store_mutated": False,
            "suite_rewritten": False,
            "pdf_view_authorized": False,
            "pdf_primary": False,
            "twin_written": False,
            "prompts_injected": False,
            "live_dispatch_authorized": False,
            "inventory_mutated": False,
            "record_persisted": False,
            "purchase_executed": False,
            "hosted": False,
            "remote_fetched": False,
            "production_router_verdict": "REJECT",
            "notes": list(self.notes),
            "authority": (
                "mo_price_ceiling_recursive_twin_note_taker_twin_search_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MoPriceCeilingRecursiveTwinNoteTakerTwinSearchComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_mo_price_ceiling_recursive_twin_note_taker_twin_search(
    *,
    mo: object,
    twin_pack: object,
    operator_ack: object,
    require_both: object | None = None,
) -> MoPriceCeilingRecursiveTwinNoteTakerTwinSearchCompose:
    """MO price-ceiling on recursive twin note-taker twin search. Never launches."""
    if not isinstance(operator_ack, bool):
        raise MoPriceCeilingRecursiveTwinNoteTakerTwinSearchComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(mo, dict):
        raise MoPriceCeilingRecursiveTwinNoteTakerTwinSearchComposeError(
            "mo must be an object"
        )
    if not isinstance(twin_pack, dict):
        raise MoPriceCeilingRecursiveTwinNoteTakerTwinSearchComposeError(
            "twin_pack must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise MoPriceCeilingRecursiveTwinNoteTakerTwinSearchComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "live_execution_authorized=false — MO never launches from pure pack",
        "charge_executed=false — recommended ceiling is advisory only",
        "twin_written=false · remote_index_queried=false · production_router_verdict=REJECT",
    ]

    try:
        mo_c = compose_midnight_oil_price_ceiling_approval(
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
        raise MoPriceCeilingRecursiveTwinNoteTakerTwinSearchComposeError(
            str(e)
        ) from e
    notes.extend(f"[mo] {n}" for n in mo_c.notes)

    try:
        tp = compose_recursive_twin_note_taker_twin_search_model_decision(
            twin=twin_pack.get("twin"),
            twin_search_pack=twin_pack.get("twin_search_pack"),
            operator_ack=operator_ack,
            require_both=twin_pack.get("require_both"),
        )
    except RecursiveTwinNoteTakerTwinSearchModelDecisionComposeError as e:
        raise MoPriceCeilingRecursiveTwinNoteTakerTwinSearchComposeError(
            str(e)
        ) from e
    notes.extend(f"[twin_pack] {n}" for n in tp.notes)

    session = _require_nonempty(tp.session_id, field="session_id")
    parent = _require_nonempty(tp.parent_asset_id, field="parent_asset_id")
    week = _require_nonempty(tp.week_id, field="week_id")
    asset = _require_nonempty(tp.asset_id, field="asset_id")
    title = _require_nonempty(tp.title, field="title")
    account = _require_nonempty(tp.account_id, field="account_id")

    if require:
        pack_ready = (
            mo_c.pack_ready is True
            and tp.pack_ready is True
            and mo_c.live_execution_authorized is False
            and mo_c.charge_executed is False
            and tp.twin_written is False
            and tp.prompts_injected is False
            and tp.live_dispatch_authorized is False
            and tp.remote_index_queried is False
            and tp.pdf_primary is False
            and tp.pdf_view_authorized is False
            and tp.purchase_executed is False
            and tp.hosted is False
            and tp.secrets_stored is False
            and tp.live_router_authorized is False
            and tp.live_meter_read is False
            and tp.inventory_mutated is False
            and tp.suite_rewritten is False
            and tp.charge_executed is False
            and tp.production_router_verdict == "REJECT"
            and operator_ack is True
        )
    else:
        pack_ready = (
            operator_ack is True
            and mo_c.live_execution_authorized is False
            and mo_c.charge_executed is False
            and tp.twin_written is False
            and tp.remote_index_queried is False
            and tp.pdf_primary is False
            and tp.production_router_verdict == "REJECT"
            and (mo_c.pack_ready is True or tp.pack_ready is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — MO price-ceiling + recursive twin note-taker twin "
            "search ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — mo, twin_pack, or operator_ack gate open"
        )

    if (
        mo_c.live_execution_authorized is not False
        or mo_c.charge_executed is not False
        or tp.twin_written is not False
        or tp.prompts_injected is not False
        or tp.live_dispatch_authorized is not False
        or tp.remote_index_queried is not False
        or tp.pdf_primary is not False
        or tp.pdf_view_authorized is not False
        or tp.purchase_executed is not False
        or tp.hosted is not False
        or tp.secrets_stored is not False
        or tp.live_router_authorized is not False
        or tp.live_meter_read is not False
        or tp.inventory_mutated is not False
        or tp.suite_rewritten is not False
        or tp.charge_executed is not False
        or tp.production_router_verdict != "REJECT"
    ):
        raise MoPriceCeilingRecursiveTwinNoteTakerTwinSearchComposeError(
            "invariant: honesty flags must remain false / REJECT"
        )

    notes.extend(
        (
            "live_execution_authorized=false",
            "charge_executed=false",
            "live_dispatched=false",
            "pack_dispatched=false",
            "merge_executed=false",
            "draft_written=false",
            "analysis_written=false",
            "live_router_authorized=false",
            "secrets_stored=false",
            "live_meter_read=false",
            "remote_index_queried=false",
            "backlog_mutated=false",
            "store_mutated=false",
            "suite_rewritten=false",
            "pdf_view_authorized=false",
            "pdf_primary=false",
            "twin_written=false",
            "prompts_injected=false",
            "live_dispatch_authorized=false",
            "inventory_mutated=false",
            "record_persisted=false",
            "purchase_executed=false",
            "hosted=false",
            "remote_fetched=false",
            "production_router_verdict=REJECT",
        )
    )

    return MoPriceCeilingRecursiveTwinNoteTakerTwinSearchCompose(
        session_id=session,
        parent_asset_id=parent,
        week_id=week,
        asset_id=asset,
        title=title,
        account_id=account,
        mo=mo_c,
        twin_pack=tp,
        pack_ready=pack_ready,
        live_execution_authorized=False,
        charge_executed=False,
        live_dispatched=False,
        pack_dispatched=False,
        merge_executed=False,
        draft_written=False,
        analysis_written=False,
        live_router_authorized=False,
        secrets_stored=False,
        live_meter_read=False,
        remote_index_queried=False,
        backlog_mutated=False,
        store_mutated=False,
        suite_rewritten=False,
        pdf_view_authorized=False,
        pdf_primary=False,
        twin_written=False,
        prompts_injected=False,
        live_dispatch_authorized=False,
        inventory_mutated=False,
        record_persisted=False,
        purchase_executed=False,
        hosted=False,
        remote_fetched=False,
        production_router_verdict="REJECT",
        notes=tuple(notes),
        authority=(
            "mo_price_ceiling_recursive_twin_note_taker_twin_search_compose_advisory"
        ),
    )


def format_mo_price_ceiling_recursive_twin_note_taker_twin_search_summary(
    c: MoPriceCeilingRecursiveTwinNoteTakerTwinSearchCompose,
) -> str:
    rec = c.mo.recommend.recommended_ceiling_usd
    rec_str = "rec=null" if rec is None else f"rec=${rec}"
    return (
        f"pack_ready={c.pack_ready} · "
        f"mo_ready={c.mo.pack_ready} · "
        f"ceiling_approved={c.mo.ceiling_approved} · "
        f"{rec_str} · "
        f"twin_ready={c.twin_pack.pack_ready} · "
        f"stage={c.mo.stage} · "
        f"verdict={c.production_router_verdict} · "
        "live_execution_authorized=false · charge_executed=false · twin_written=false"
    )


__all__ = [
    "MoPriceCeilingRecursiveTwinNoteTakerTwinSearchCompose",
    "MoPriceCeilingRecursiveTwinNoteTakerTwinSearchComposeError",
    "compose_mo_price_ceiling_recursive_twin_note_taker_twin_search",
    "format_mo_price_ceiling_recursive_twin_note_taker_twin_search_summary",
]
