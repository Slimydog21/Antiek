"""Marketplace paid purchase gate compose (pure).

purchase_executed, charge_executed, hosted, pdf_view_authorized always False.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from substrate.marketplace_free_before_buy_html_port_compose import (
    MarketplaceFreeBeforeBuyHtmlPortCompose,
    MarketplaceFreeBeforeBuyHtmlPortComposeError,
    compose_marketplace_free_before_buy_html_port,
)


class MarketplacePaidPurchaseGateComposeError(ValueError):
    """Fail-closed validation for paid purchase gate."""


@dataclass(frozen=True)
class MarketplacePaidPurchaseGateCompose:
    free_port: MarketplaceFreeBeforeBuyHtmlPortCompose
    list_price_usd: float | None
    approved_spend_usd: float | None
    remaining_budget_usd: float | None
    purchase_ready: bool
    would_exceed_budget: bool | None
    gate_ready: bool
    purchase_executed: bool
    charge_executed: bool
    hosted: bool
    pdf_view_authorized: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "free_port": self.free_port.to_dict(),
            "list_price_usd": self.list_price_usd,
            "approved_spend_usd": self.approved_spend_usd,
            "remaining_budget_usd": self.remaining_budget_usd,
            "purchase_ready": self.purchase_ready,
            "would_exceed_budget": self.would_exceed_budget,
            "gate_ready": self.gate_ready,
            "purchase_executed": False,
            "charge_executed": False,
            "hosted": False,
            "pdf_view_authorized": False,
            "notes": list(self.notes),
            "authority": "marketplace_paid_purchase_gate_compose_advisory",
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MarketplacePaidPurchaseGateComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def _finite_money(value: object, *, field: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MarketplacePaidPurchaseGateComposeError(
            f"{field} must be finite number or null"
        )
    f = float(value)
    if not math.isfinite(f):
        raise MarketplacePaidPurchaseGateComposeError(
            f"{field} must be finite number or null"
        )
    if f < 0:
        raise MarketplacePaidPurchaseGateComposeError(f"{field} must be >= 0")
    return f


def compose_marketplace_paid_purchase_gate(
    *,
    title: object,
    account_id: object,
    free_copy_available: object,
    purchase_ack: object,
    port_requested: object,
    list_price_usd: object,
    approved_spend_usd: object,
    remaining_budget_usd: object,
    operator_ack: object,
    free_html_projection_sha: object | None = None,
    purchase_html_projection_sha: object | None = None,
) -> MarketplacePaidPurchaseGateCompose:
    """Compose paid purchase gate over free-before-buy. Never charges/hosts."""
    if not isinstance(operator_ack, bool):
        raise MarketplacePaidPurchaseGateComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(purchase_ack, bool):
        raise MarketplacePaidPurchaseGateComposeError(
            "purchase_ack must be an explicit boolean"
        )
    if not isinstance(port_requested, bool):
        raise MarketplacePaidPurchaseGateComposeError(
            "port_requested must be an explicit boolean"
        )

    title_s = _require_nonempty(title, field="title")
    account = _require_nonempty(account_id, field="account_id")
    list_price = _finite_money(list_price_usd, field="list_price_usd")
    approved = _finite_money(approved_spend_usd, field="approved_spend_usd")
    remaining = _finite_money(remaining_budget_usd, field="remaining_budget_usd")

    notes: list[str] = [
        "purchase_executed=false — paid gate never charges",
        "charge_executed=false — no payment processor call",
        "hosted=false — pure layer never hosts account assets",
        "pdf_view_authorized=false — HTML-native port only",
    ]

    try:
        free_port = compose_marketplace_free_before_buy_html_port(
            title=title_s,
            account_id=account,
            free_copy_available=free_copy_available,
            purchase_ack=purchase_ack,
            port_requested=port_requested,
            free_html_projection_sha=free_html_projection_sha,
            purchase_html_projection_sha=purchase_html_projection_sha,
        )
    except MarketplaceFreeBeforeBuyHtmlPortComposeError as e:
        raise MarketplacePaidPurchaseGateComposeError(str(e)) from e
    notes.extend(free_port.notes)

    would_exceed: bool | None
    if list_price is None or remaining is None:
        would_exceed = None
        notes.append(
            "would_exceed_budget=null — list_price or remaining_budget unknown (no invent false)"
        )
    else:
        would_exceed = list_price > remaining
        notes.append(
            f"would_exceed_budget=true (list={list_price} > remaining={remaining})"
            if would_exceed
            else f"would_exceed_budget=false (list={list_price} <= remaining={remaining})"
        )

    purchase_ready = False
    if free_copy_available is True:
        notes.append(
            "purchase_ready=false — free copy available; free path preferred (no paid path)"
        )
    elif free_copy_available is None:
        notes.append(
            "purchase_ready=false — free availability unknown; resolve free before buy"
        )
    elif not purchase_ack:
        notes.append(
            "purchase_ready=false — purchase_ack required when free unavailable"
        )
    elif not operator_ack:
        notes.append(
            "purchase_ready=false — operator_ack required for paid gate"
        )
    elif list_price is None:
        notes.append(
            "purchase_ready=false — list_price_usd unknown (no invent $0)"
        )
    elif approved is None:
        notes.append(
            "purchase_ready=false — approved_spend_usd unknown (operator ceiling required)"
        )
    elif approved < list_price:
        notes.append(
            f"purchase_ready=false — approved_spend {approved} < list {list_price}"
        )
    elif would_exceed is True:
        notes.append("purchase_ready=false — would exceed remaining budget")
    elif would_exceed is None:
        notes.append(
            "purchase_ready=false — remaining_budget_usd unknown (fail closed)"
        )
    else:
        purchase_ready = True
        notes.append(
            "purchase_ready=true — paid intent only; still purchase_executed=false · charge_executed=false"
        )

    gate_ready = False
    if free_copy_available is True and free_port.port_ready:
        gate_ready = True
        notes.append("gate_ready=true via free HTML port path")
    elif (
        purchase_ready
        and free_port.port_ready
        and free_port.html_projection_sha is not None
    ):
        gate_ready = True
        notes.append(
            "gate_ready=true via paid port intent (sha present; still not charged/hosted)"
        )
    elif purchase_ready and not free_port.port_ready:
        notes.append(
            "gate_ready=false — purchase_ready but port not ready (sha/port_requested)"
        )
    else:
        notes.append("gate_ready=false")

    if (
        free_port.purchase_executed is not False
        or free_port.hosted is not False
        or free_port.pdf_view_authorized is not False
    ):
        raise MarketplacePaidPurchaseGateComposeError(
            "invariant: free_port honesty flags must remain false"
        )

    notes.extend(
        (
            "purchase_executed=false",
            "charge_executed=false",
            "hosted=false",
            "pdf_view_authorized=false",
        )
    )

    return MarketplacePaidPurchaseGateCompose(
        free_port=free_port,
        list_price_usd=list_price,
        approved_spend_usd=approved,
        remaining_budget_usd=remaining,
        purchase_ready=purchase_ready,
        would_exceed_budget=would_exceed,
        gate_ready=gate_ready,
        purchase_executed=False,
        charge_executed=False,
        hosted=False,
        pdf_view_authorized=False,
        notes=tuple(notes),
        authority="marketplace_paid_purchase_gate_compose_advisory",
    )


def format_marketplace_paid_purchase_gate_summary(
    c: MarketplacePaidPurchaseGateCompose,
) -> str:
    w = (
        "would_exceed_budget=null"
        if c.would_exceed_budget is None
        else f"would_exceed_budget={c.would_exceed_budget}"
    )
    return (
        f"gate_ready={c.gate_ready} · purchase_ready={c.purchase_ready} · "
        f"path={c.free_port.path} · {w} · "
        f"purchase_executed=false · charge_executed=false · hosted=false · pdf_view_authorized=false"
    )


__all__ = [
    "MarketplacePaidPurchaseGateCompose",
    "MarketplacePaidPurchaseGateComposeError",
    "compose_marketplace_paid_purchase_gate",
    "format_marketplace_paid_purchase_gate_summary",
]
