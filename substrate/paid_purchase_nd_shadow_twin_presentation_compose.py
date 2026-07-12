"""Paid-purchase free-first honesty over ND shadow twin presentation pack.

purchase_executed / charge_executed / hosted always False.
live_router_authorized / twin_written always False.
production_router_verdict always REJECT.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.marketplace_paid_purchase_gate_compose import (
    MarketplacePaidPurchaseGateCompose,
    MarketplacePaidPurchaseGateComposeError,
    compose_marketplace_paid_purchase_gate,
)
from substrate.nd_shadow_twin_presentation_competition_compose import (
    NdShadowTwinPresentationCompetitionCompose,
    NdShadowTwinPresentationCompetitionComposeError,
    compose_nd_shadow_twin_presentation_competition,
)


class PaidPurchaseNdShadowTwinPresentationComposeError(ValueError):
    """Fail-closed validation for paid-purchase + ND twin presentation pack."""


@dataclass(frozen=True)
class PaidPurchaseNdShadowTwinPresentationCompose:
    title: str
    account_id: str
    session_id: str
    parent_asset_id: str
    asset_id: str
    week_id: str
    purchase: MarketplacePaidPurchaseGateCompose
    nd_twin: NdShadowTwinPresentationCompetitionCompose
    pack_ready: bool
    purchase_executed: bool
    charge_executed: bool
    hosted: bool
    pdf_view_authorized: bool
    pdf_primary: bool
    live_router_authorized: bool
    twin_written: bool
    prompts_injected: bool
    merge_executed: bool
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
    live_dispatched: bool
    pack_dispatched: bool
    draft_written: bool
    record_persisted: bool
    analysis_written: bool
    production_router_verdict: str
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "account_id": self.account_id,
            "session_id": self.session_id,
            "parent_asset_id": self.parent_asset_id,
            "asset_id": self.asset_id,
            "week_id": self.week_id,
            "purchase": self.purchase.to_dict(),
            "nd_twin": self.nd_twin.to_dict(),
            "pack_ready": self.pack_ready,
            "purchase_executed": False,
            "charge_executed": False,
            "hosted": False,
            "pdf_view_authorized": False,
            "pdf_primary": False,
            "live_router_authorized": False,
            "twin_written": False,
            "prompts_injected": False,
            "merge_executed": False,
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
            "live_dispatched": False,
            "pack_dispatched": False,
            "draft_written": False,
            "record_persisted": False,
            "analysis_written": False,
            "production_router_verdict": "REJECT",
            "notes": list(self.notes),
            "authority": (
                "paid_purchase_nd_shadow_twin_presentation_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PaidPurchaseNdShadowTwinPresentationComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_paid_purchase_nd_shadow_twin_presentation(
    *,
    purchase: object,
    nd_twin: object,
    operator_ack: object,
    require_both: object | None = None,
) -> PaidPurchaseNdShadowTwinPresentationCompose:
    """Free-first paid purchase + ND twin presentation. Never charges."""
    if not isinstance(operator_ack, bool):
        raise PaidPurchaseNdShadowTwinPresentationComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(purchase, dict):
        raise PaidPurchaseNdShadowTwinPresentationComposeError(
            "purchase must be an object"
        )
    if not isinstance(nd_twin, dict):
        raise PaidPurchaseNdShadowTwinPresentationComposeError(
            "nd_twin must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise PaidPurchaseNdShadowTwinPresentationComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "purchase_executed=false · charge_executed=false · hosted=false",
        "live_router_authorized=false · twin_written=false",
        "production_router_verdict=REJECT",
    ]

    try:
        pur = compose_marketplace_paid_purchase_gate(
            title=purchase.get("title"),
            account_id=purchase.get("account_id"),
            free_copy_available=purchase.get("free_copy_available"),
            purchase_ack=purchase.get("purchase_ack"),
            port_requested=purchase.get("port_requested"),
            list_price_usd=purchase.get("list_price_usd"),
            approved_spend_usd=purchase.get("approved_spend_usd"),
            remaining_budget_usd=purchase.get("remaining_budget_usd"),
            operator_ack=operator_ack,
            free_html_projection_sha=purchase.get("free_html_projection_sha"),
            purchase_html_projection_sha=purchase.get(
                "purchase_html_projection_sha"
            ),
        )
    except MarketplacePaidPurchaseGateComposeError as e:
        raise PaidPurchaseNdShadowTwinPresentationComposeError(str(e)) from e
    notes.extend(f"[purchase] {n}" for n in pur.notes)

    try:
        nd = compose_nd_shadow_twin_presentation_competition(
            nd_shadow=nd_twin.get("nd_shadow"),
            twin_presentation=nd_twin.get("twin_presentation"),
            operator_ack=operator_ack,
            require_both=nd_twin.get("require_both"),
        )
    except NdShadowTwinPresentationCompetitionComposeError as e:
        raise PaidPurchaseNdShadowTwinPresentationComposeError(str(e)) from e
    notes.extend(f"[nd_twin] {n}" for n in nd.notes)

    title = _require_nonempty(pur.free_port.title, field="title")
    account = _require_nonempty(pur.free_port.account_id, field="account_id")
    session = _require_nonempty(nd.session_id, field="session_id")
    parent = _require_nonempty(nd.parent_asset_id, field="parent_asset_id")
    asset = _require_nonempty(nd.asset_id, field="asset_id")
    week = _require_nonempty(nd.week_id, field="week_id")

    free_first_honest = (
        pur.purchase_executed is False
        and pur.charge_executed is False
        and pur.hosted is False
        and pur.pdf_view_authorized is False
    )

    if require:
        pack_ready = (
            free_first_honest
            and pur.gate_ready is True
            and nd.pack_ready is True
            and nd.live_router_authorized is False
            and nd.twin_written is False
            and nd.purchase_executed is False
            and nd.production_router_verdict == "REJECT"
            and operator_ack is True
        )
    else:
        pack_ready = (
            free_first_honest
            and operator_ack is True
            and pur.purchase_executed is False
            and nd.production_router_verdict == "REJECT"
            and (pur.gate_ready is True or nd.pack_ready is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — paid-purchase free-first + ND shadow twin "
            "presentation ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — purchase gate, nd_twin, free-first honesty, "
            "or operator_ack gate open"
        )

    if (
        pur.purchase_executed is not False
        or pur.charge_executed is not False
        or pur.hosted is not False
        or nd.live_router_authorized is not False
        or nd.twin_written is not False
        or nd.purchase_executed is not False
        or nd.production_router_verdict != "REJECT"
    ):
        raise PaidPurchaseNdShadowTwinPresentationComposeError(
            "invariant: honesty flags must remain false / REJECT"
        )

    notes.extend(
        (
            "purchase_executed=false",
            "charge_executed=false",
            "hosted=false",
            "pdf_view_authorized=false",
            "pdf_primary=false",
            "live_router_authorized=false",
            "twin_written=false",
            "prompts_injected=false",
            "merge_executed=false",
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
            "live_dispatched=false",
            "pack_dispatched=false",
            "draft_written=false",
            "record_persisted=false",
            "analysis_written=false",
            "production_router_verdict=REJECT",
        )
    )

    return PaidPurchaseNdShadowTwinPresentationCompose(
        title=title,
        account_id=account,
        session_id=session,
        parent_asset_id=parent,
        asset_id=asset,
        week_id=week,
        purchase=pur,
        nd_twin=nd,
        pack_ready=pack_ready,
        purchase_executed=False,
        charge_executed=False,
        hosted=False,
        pdf_view_authorized=False,
        pdf_primary=False,
        live_router_authorized=False,
        twin_written=False,
        prompts_injected=False,
        merge_executed=False,
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
        live_dispatched=False,
        pack_dispatched=False,
        draft_written=False,
        record_persisted=False,
        analysis_written=False,
        production_router_verdict="REJECT",
        notes=tuple(notes),
        authority="paid_purchase_nd_shadow_twin_presentation_compose_advisory",
    )


def format_paid_purchase_nd_shadow_twin_presentation_summary(
    c: PaidPurchaseNdShadowTwinPresentationCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"gate_ready={c.purchase.gate_ready} · "
        f"purchase_ready={c.purchase.purchase_ready} · "
        f"path={c.purchase.free_port.path} · "
        f"nd_twin_ready={c.nd_twin.pack_ready} · "
        f"verdict={c.production_router_verdict} · "
        f"purchase_executed=false · charge_executed=false · "
        f"live_router_authorized=false"
    )


__all__ = [
    "PaidPurchaseNdShadowTwinPresentationCompose",
    "PaidPurchaseNdShadowTwinPresentationComposeError",
    "compose_paid_purchase_nd_shadow_twin_presentation",
    "format_paid_purchase_nd_shadow_twin_presentation_summary",
]
