"""Paid purchase → HTML view session compose (pure).

purchase_executed, charge_executed, hosted, pdf_view_authorized, store_mutated
always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.html_asset_view_session_compose import (
    HtmlAssetViewSessionCompose,
    HtmlAssetViewSessionComposeError,
    compose_html_asset_view_session,
)
from substrate.marketplace_paid_purchase_gate_compose import (
    MarketplacePaidPurchaseGateCompose,
    MarketplacePaidPurchaseGateComposeError,
    compose_marketplace_paid_purchase_gate,
)


class PaidPurchaseHtmlViewSessionComposeError(ValueError):
    """Fail-closed validation for paid purchase HTML view session."""


@dataclass(frozen=True)
class PaidPurchaseHtmlViewSessionCompose:
    purchase_gate: MarketplacePaidPurchaseGateCompose
    view: HtmlAssetViewSessionCompose | None
    session_package_ready: bool
    purchase_executed: bool
    charge_executed: bool
    hosted: bool
    pdf_view_authorized: bool
    store_mutated: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "purchase_gate": self.purchase_gate.to_dict(),
            "view": self.view.to_dict() if self.view is not None else None,
            "session_package_ready": self.session_package_ready,
            "purchase_executed": False,
            "charge_executed": False,
            "hosted": False,
            "pdf_view_authorized": False,
            "store_mutated": False,
            "notes": list(self.notes),
            "authority": "paid_purchase_html_view_session_compose_advisory",
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PaidPurchaseHtmlViewSessionComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_paid_purchase_html_view_session(
    *,
    session_id: object,
    asset_id: object,
    title: object,
    account_id: object,
    free_copy_available: object,
    port_requested: object,
    purchase_ack: object,
    list_price_usd: object,
    approved_spend_usd: object,
    remaining_budget_usd: object,
    operator_ack: object,
    view_requested: object,
    free_html_projection_sha: object | None = None,
    purchase_html_projection_sha: object | None = None,
    twin_bound: object | None = None,
    twin_substrate_ready: object | None = None,
    claimed_format: object | None = None,
) -> PaidPurchaseHtmlViewSessionCompose:
    """Compose marketplace gate + HTML view session. Never charges/hosts/PDF."""
    if not isinstance(operator_ack, bool):
        raise PaidPurchaseHtmlViewSessionComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(view_requested, bool):
        raise PaidPurchaseHtmlViewSessionComposeError(
            "view_requested must be an explicit boolean"
        )

    session = _require_nonempty(session_id, field="session_id")
    asset = _require_nonempty(asset_id, field="asset_id")

    notes: list[str] = [
        "purchase_executed=false · charge_executed=false · hosted=false",
        "pdf_view_authorized=false — HTML-native only",
        "store_mutated=false — pure session pack",
    ]

    try:
        purchase_gate = compose_marketplace_paid_purchase_gate(
            title=title,
            account_id=account_id,
            free_copy_available=free_copy_available,
            free_html_projection_sha=free_html_projection_sha,
            purchase_html_projection_sha=purchase_html_projection_sha,
            port_requested=port_requested,
            purchase_ack=purchase_ack,
            list_price_usd=list_price_usd,
            approved_spend_usd=approved_spend_usd,
            remaining_budget_usd=remaining_budget_usd,
            operator_ack=operator_ack,
        )
    except MarketplacePaidPurchaseGateComposeError as e:
        raise PaidPurchaseHtmlViewSessionComposeError(str(e)) from e
    notes.extend(purchase_gate.notes)

    sha = purchase_gate.free_port.html_projection_sha
    if sha is None:
        if purchase_html_projection_sha is not None:
            sha = purchase_html_projection_sha  # type: ignore[assignment]
        elif free_html_projection_sha is not None:
            sha = free_html_projection_sha  # type: ignore[assignment]

    view: HtmlAssetViewSessionCompose | None = None
    if purchase_gate.gate_ready or view_requested:
        try:
            view = compose_html_asset_view_session(
                session_id=session,
                asset_id=asset,
                html_projection_sha=sha,
                view_requested=view_requested,
                twin_bound=True if twin_bound is True else False,
                twin_substrate_ready=twin_substrate_ready,
                claimed_format=claimed_format,
            )
        except HtmlAssetViewSessionComposeError as e:
            raise PaidPurchaseHtmlViewSessionComposeError(str(e)) from e
        notes.extend(view.notes)
    else:
        notes.append(
            "view session not composed — gate not ready and view not requested"
        )

    session_package_ready = (
        purchase_gate.gate_ready
        and view is not None
        and view.session_ready is True
        and view.pdf_view_authorized is False
    )
    if not purchase_gate.gate_ready:
        notes.append("session_package_ready=false — marketplace gate not ready")
    elif view is None or not view.session_ready:
        notes.append(
            "session_package_ready=false — HTML view session not ready"
        )
    else:
        notes.append(
            "session_package_ready=true — HTML open intent; still not purchased/hosted"
        )

    if (
        purchase_gate.purchase_executed is not False
        or purchase_gate.charge_executed is not False
        or purchase_gate.hosted is not False
        or purchase_gate.pdf_view_authorized is not False
    ):
        raise PaidPurchaseHtmlViewSessionComposeError(
            "invariant: purchase gate honesty flags must remain false"
        )
    if view is not None and (
        view.pdf_view_authorized is not False or view.store_mutated is not False
    ):
        raise PaidPurchaseHtmlViewSessionComposeError(
            "invariant: view honesty flags must remain false"
        )

    notes.extend(
        (
            "purchase_executed=false",
            "charge_executed=false",
            "hosted=false",
            "pdf_view_authorized=false",
            "store_mutated=false",
        )
    )

    return PaidPurchaseHtmlViewSessionCompose(
        purchase_gate=purchase_gate,
        view=view,
        session_package_ready=session_package_ready,
        purchase_executed=False,
        charge_executed=False,
        hosted=False,
        pdf_view_authorized=False,
        store_mutated=False,
        notes=tuple(notes),
        authority="paid_purchase_html_view_session_compose_advisory",
    )


def format_paid_purchase_html_view_session_summary(
    c: PaidPurchaseHtmlViewSessionCompose,
) -> str:
    html_ready = c.view.html_view_ready if c.view is not None else "n/a"
    return (
        f"session_package_ready={c.session_package_ready} · "
        f"gate_ready={c.purchase_gate.gate_ready} · "
        f"html_view_ready={html_ready} · "
        f"purchase_executed=false · charge_executed=false · hosted=false · "
        f"pdf_view_authorized=false · store_mutated=false"
    )


__all__ = [
    "PaidPurchaseHtmlViewSessionCompose",
    "PaidPurchaseHtmlViewSessionComposeError",
    "compose_paid_purchase_html_view_session",
    "format_paid_purchase_html_view_session_summary",
]
