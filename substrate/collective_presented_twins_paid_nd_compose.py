"""Collective multi-select presented twins over paid-purchase ND pack.

live_dispatched / pack_dispatched / merge_executed / analysis_written always False.
purchase_executed / live_router_authorized always False.
production_router_verdict always REJECT.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.floating_multi_select_collective_cohesive_compose import (
    FloatingMultiSelectCollectiveCohesiveCompose,
    FloatingMultiSelectCollectiveCohesiveComposeError,
    compose_floating_multi_select_collective_cohesive,
)
from substrate.paid_purchase_nd_shadow_twin_presentation_compose import (
    PaidPurchaseNdShadowTwinPresentationCompose,
    PaidPurchaseNdShadowTwinPresentationComposeError,
    compose_paid_purchase_nd_shadow_twin_presentation,
)


class CollectivePresentedTwinsPaidNdComposeError(ValueError):
    """Fail-closed validation for collective presented twins + paid ND pack."""


@dataclass(frozen=True)
class CollectivePresentedTwinsPaidNdCompose:
    session_id: str
    parent_asset_id: str
    title: str
    account_id: str
    week_id: str
    asset_id: str
    collective: FloatingMultiSelectCollectiveCohesiveCompose
    paid_nd: PaidPurchaseNdShadowTwinPresentationCompose
    pack_ready: bool
    live_dispatched: bool
    pack_dispatched: bool
    merge_executed: bool
    analysis_written: bool
    purchase_executed: bool
    charge_executed: bool
    hosted: bool
    pdf_view_authorized: bool
    pdf_primary: bool
    live_router_authorized: bool
    twin_written: bool
    prompts_injected: bool
    live_dispatch_authorized: bool
    remote_fetched: bool
    backlog_mutated: bool
    secrets_stored: bool
    live_meter_read: bool
    store_mutated: bool
    suite_rewritten: bool
    live_execution_authorized: bool
    remote_index_queried: bool
    inventory_mutated: bool
    draft_written: bool
    record_persisted: bool
    production_router_verdict: str
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "parent_asset_id": self.parent_asset_id,
            "title": self.title,
            "account_id": self.account_id,
            "week_id": self.week_id,
            "asset_id": self.asset_id,
            "collective": self.collective.to_dict(),
            "paid_nd": self.paid_nd.to_dict(),
            "pack_ready": self.pack_ready,
            "live_dispatched": False,
            "pack_dispatched": False,
            "merge_executed": False,
            "analysis_written": False,
            "purchase_executed": False,
            "charge_executed": False,
            "hosted": False,
            "pdf_view_authorized": False,
            "pdf_primary": False,
            "live_router_authorized": False,
            "twin_written": False,
            "prompts_injected": False,
            "live_dispatch_authorized": False,
            "remote_fetched": False,
            "backlog_mutated": False,
            "secrets_stored": False,
            "live_meter_read": False,
            "store_mutated": False,
            "suite_rewritten": False,
            "live_execution_authorized": False,
            "remote_index_queried": False,
            "inventory_mutated": False,
            "draft_written": False,
            "record_persisted": False,
            "production_router_verdict": "REJECT",
            "notes": list(self.notes),
            "authority": "collective_presented_twins_paid_nd_compose_advisory",
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CollectivePresentedTwinsPaidNdComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_collective_presented_twins_paid_nd(
    *,
    collective: object,
    paid_nd: object,
    operator_ack: object,
    require_both: object | None = None,
) -> CollectivePresentedTwinsPaidNdCompose:
    """Collective multi-select + paid ND pack. Never dispatches/merges/purchases."""
    if not isinstance(operator_ack, bool):
        raise CollectivePresentedTwinsPaidNdComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(collective, dict):
        raise CollectivePresentedTwinsPaidNdComposeError(
            "collective must be an object"
        )
    if not isinstance(paid_nd, dict):
        raise CollectivePresentedTwinsPaidNdComposeError(
            "paid_nd must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise CollectivePresentedTwinsPaidNdComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "live_dispatched=false · pack_dispatched=false · merge_executed=false · "
        "analysis_written=false",
        "purchase_executed=false · live_router_authorized=false · twin_written=false",
        "production_router_verdict=REJECT",
    ]

    try:
        col = compose_floating_multi_select_collective_cohesive(
            session_id=collective.get("session_id"),
            parent_asset_id=collective.get("parent_asset_id"),
            members=collective.get("members"),
            selected_instance_ids=collective.get("selected_instance_ids"),
            pack_mode=collective.get("pack_mode"),
            cohesive_prompt=collective.get("cohesive_prompt"),
            operator_ack=operator_ack,
            extra_context=collective.get("extra_context"),
            analysis_kind=collective.get("analysis_kind"),
            extra_findings=collective.get("extra_findings"),
        )
    except FloatingMultiSelectCollectiveCohesiveComposeError as e:
        raise CollectivePresentedTwinsPaidNdComposeError(str(e)) from e
    notes.extend(f"[collective] {n}" for n in col.notes)

    try:
        paid = compose_paid_purchase_nd_shadow_twin_presentation(
            purchase=paid_nd.get("purchase"),
            nd_twin=paid_nd.get("nd_twin"),
            operator_ack=operator_ack,
            require_both=paid_nd.get("require_both"),
        )
    except PaidPurchaseNdShadowTwinPresentationComposeError as e:
        raise CollectivePresentedTwinsPaidNdComposeError(str(e)) from e
    notes.extend(f"[paid_nd] {n}" for n in paid.notes)

    session = _require_nonempty(col.session_id, field="session_id")
    parent = _require_nonempty(col.parent_asset_id, field="parent_asset_id")
    title = _require_nonempty(paid.title, field="title")
    account = _require_nonempty(paid.account_id, field="account_id")
    week = _require_nonempty(paid.week_id, field="week_id")
    asset = _require_nonempty(paid.asset_id, field="asset_id")

    session_aligned = paid.session_id == session
    parent_aligned = paid.parent_asset_id == parent
    if not session_aligned:
        notes.append(
            "session_id mismatch between collective and paid_nd — pack_ready blocked"
        )
    if not parent_aligned:
        notes.append(
            "parent_asset_id mismatch between collective and paid_nd — "
            "pack_ready blocked"
        )

    if require:
        pack_ready = (
            session_aligned
            and parent_aligned
            and col.pack_ready is True
            and paid.pack_ready is True
            and col.live_dispatched is False
            and col.pack_dispatched is False
            and col.merge_executed is False
            and col.analysis_written is False
            and paid.purchase_executed is False
            and paid.charge_executed is False
            and paid.hosted is False
            and paid.live_router_authorized is False
            and paid.twin_written is False
            and paid.production_router_verdict == "REJECT"
            and operator_ack is True
        )
    else:
        pack_ready = (
            session_aligned
            and parent_aligned
            and operator_ack is True
            and col.merge_executed is False
            and paid.purchase_executed is False
            and paid.production_router_verdict == "REJECT"
            and (col.pack_ready is True or paid.pack_ready is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — collective presented twins + paid-purchase ND "
            "pack ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — collective, paid_nd, alignment, or operator_ack "
            "gate open"
        )

    if (
        col.live_dispatched is not False
        or col.pack_dispatched is not False
        or col.merge_executed is not False
        or col.analysis_written is not False
        or paid.purchase_executed is not False
        or paid.charge_executed is not False
        or paid.hosted is not False
        or paid.live_router_authorized is not False
        or paid.twin_written is not False
        or paid.production_router_verdict != "REJECT"
    ):
        raise CollectivePresentedTwinsPaidNdComposeError(
            "invariant: honesty flags must remain false / REJECT"
        )

    notes.extend(
        (
            "live_dispatched=false",
            "pack_dispatched=false",
            "merge_executed=false",
            "analysis_written=false",
            "purchase_executed=false",
            "charge_executed=false",
            "hosted=false",
            "pdf_view_authorized=false",
            "pdf_primary=false",
            "live_router_authorized=false",
            "twin_written=false",
            "prompts_injected=false",
            "live_dispatch_authorized=false",
            "remote_fetched=false",
            "backlog_mutated=false",
            "secrets_stored=false",
            "live_meter_read=false",
            "store_mutated=false",
            "suite_rewritten=false",
            "live_execution_authorized=false",
            "remote_index_queried=false",
            "inventory_mutated=false",
            "draft_written=false",
            "record_persisted=false",
            "production_router_verdict=REJECT",
        )
    )

    return CollectivePresentedTwinsPaidNdCompose(
        session_id=session,
        parent_asset_id=parent,
        title=title,
        account_id=account,
        week_id=week,
        asset_id=asset,
        collective=col,
        paid_nd=paid,
        pack_ready=pack_ready,
        live_dispatched=False,
        pack_dispatched=False,
        merge_executed=False,
        analysis_written=False,
        purchase_executed=False,
        charge_executed=False,
        hosted=False,
        pdf_view_authorized=False,
        pdf_primary=False,
        live_router_authorized=False,
        twin_written=False,
        prompts_injected=False,
        live_dispatch_authorized=False,
        remote_fetched=False,
        backlog_mutated=False,
        secrets_stored=False,
        live_meter_read=False,
        store_mutated=False,
        suite_rewritten=False,
        live_execution_authorized=False,
        remote_index_queried=False,
        inventory_mutated=False,
        draft_written=False,
        record_persisted=False,
        production_router_verdict="REJECT",
        notes=tuple(notes),
        authority="collective_presented_twins_paid_nd_compose_advisory",
    )


def format_collective_presented_twins_paid_nd_summary(
    c: CollectivePresentedTwinsPaidNdCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"collective_ready={c.collective.pack_ready} · "
        f"mode={c.collective.pack_mode} · "
        f"paid_nd_ready={c.paid_nd.pack_ready} · "
        f"verdict={c.production_router_verdict} · "
        f"live_dispatched=false · merge_executed=false · purchase_executed=false"
    )


__all__ = [
    "CollectivePresentedTwinsPaidNdCompose",
    "CollectivePresentedTwinsPaidNdComposeError",
    "compose_collective_presented_twins_paid_nd",
    "format_collective_presented_twins_paid_nd_summary",
]
