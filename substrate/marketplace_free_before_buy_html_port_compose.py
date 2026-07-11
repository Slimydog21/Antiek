"""Marketplace free-before-buy HTML port compose (pure).

purchase_executed, hosted, pdf_view_authorized always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

FreeBeforeBuyPortPath = Literal[
    "prefer_free_html",
    "prefer_free_then_port",
    "purchase_then_port",
    "blocked_unknown_free",
    "incomplete",
]


class MarketplaceFreeBeforeBuyHtmlPortComposeError(ValueError):
    """Fail-closed validation for free-before-buy HTML port."""


@dataclass(frozen=True)
class MarketplaceFreeBeforeBuyHtmlPortCompose:
    title: str
    account_id: str
    path: FreeBeforeBuyPortPath
    port_ready: bool
    html_projection_sha: str | None
    purchase_executed: bool
    hosted: bool
    pdf_view_authorized: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "account_id": self.account_id,
            "path": self.path,
            "port_ready": self.port_ready,
            "html_projection_sha": self.html_projection_sha,
            "purchase_executed": False,
            "hosted": False,
            "pdf_view_authorized": False,
            "notes": list(self.notes),
            "authority": "marketplace_free_before_buy_html_port_compose_advisory",
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MarketplaceFreeBeforeBuyHtmlPortComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_marketplace_free_before_buy_html_port(
    *,
    title: object,
    account_id: object,
    free_copy_available: object,
    purchase_ack: object,
    port_requested: object,
    free_html_projection_sha: object | None = None,
    purchase_html_projection_sha: object | None = None,
) -> MarketplaceFreeBeforeBuyHtmlPortCompose:
    """Compose free-before-buy HTML port intent. Never purchases or hosts."""
    if not isinstance(purchase_ack, bool):
        raise MarketplaceFreeBeforeBuyHtmlPortComposeError(
            "purchase_ack must be an explicit boolean"
        )
    if not isinstance(port_requested, bool):
        raise MarketplaceFreeBeforeBuyHtmlPortComposeError(
            "port_requested must be an explicit boolean"
        )
    title_s = _require_nonempty(title, field="title")
    account = _require_nonempty(account_id, field="account_id")

    if free_copy_available is not None and not isinstance(
        free_copy_available, bool
    ):
        raise MarketplaceFreeBeforeBuyHtmlPortComposeError(
            "free_copy_available must be boolean or null"
        )

    free_sha = None
    if free_html_projection_sha is not None:
        free_sha = _require_nonempty(
            free_html_projection_sha, field="free_html_projection_sha"
        )
    purchase_sha = None
    if purchase_html_projection_sha is not None:
        purchase_sha = _require_nonempty(
            purchase_html_projection_sha, field="purchase_html_projection_sha"
        )

    notes: list[str] = [
        "purchase_executed=false — free-before-buy never auto-purchases",
        "hosted=false — pure layer never hosts account assets",
        "pdf_view_authorized=false — HTML-native port only",
    ]

    path: FreeBeforeBuyPortPath = "incomplete"
    html_projection_sha: str | None = None
    port_ready = False

    if free_copy_available is None:
        path = "blocked_unknown_free"
        notes.append(
            "free_copy_available=null — fail closed; resolve free availability before buy/port"
        )
    elif free_copy_available is True:
        if free_sha:
            path = "prefer_free_html"
            html_projection_sha = free_sha
            port_ready = port_requested
            notes.append(
                "path=prefer_free_html · port_ready=true (free HTML sha present)"
                if port_ready
                else "path=prefer_free_html · port_ready=false (port_requested=false)"
            )
        else:
            path = "prefer_free_then_port"
            notes.append(
                "path=prefer_free_then_port · free available but free_html_projection_sha absent (no invent)"
            )
    else:
        if not purchase_ack:
            path = "incomplete"
            notes.append(
                "free unavailable · purchase_ack=false — operator must ack purchase path"
            )
        elif purchase_sha:
            path = "purchase_then_port"
            html_projection_sha = purchase_sha
            port_ready = port_requested
            notes.append(
                "path=purchase_then_port · port_ready=true (purchase HTML sha; still purchase_executed=false)"
                if port_ready
                else "path=purchase_then_port · port_ready=false (port_requested=false)"
            )
        else:
            path = "purchase_then_port"
            notes.append(
                "path=purchase_then_port · purchase_ack=true but purchase_html_projection_sha absent (no invent)"
            )

    notes.extend(
        (
            "purchase_executed=false",
            "hosted=false",
            "pdf_view_authorized=false",
        )
    )

    return MarketplaceFreeBeforeBuyHtmlPortCompose(
        title=title_s,
        account_id=account,
        path=path,
        port_ready=port_ready,
        html_projection_sha=html_projection_sha,
        purchase_executed=False,
        hosted=False,
        pdf_view_authorized=False,
        notes=tuple(notes),
        authority="marketplace_free_before_buy_html_port_compose_advisory",
    )


__all__ = [
    "MarketplaceFreeBeforeBuyHtmlPortCompose",
    "MarketplaceFreeBeforeBuyHtmlPortComposeError",
    "compose_marketplace_free_before_buy_html_port",
]
