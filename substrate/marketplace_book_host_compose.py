"""Marketplace free-copy → purchase → HTML host compose (pure).

Never invents free miss, purchase_executed, or hosted=true.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

MarketplacePath = Literal[
    "free_copy",
    "purchase_intent",
    "html_host",
    "blocked",
    "incomplete",
]


class MarketplaceBookHostComposeError(ValueError):
    """Fail-closed validation for marketplace compose."""


@dataclass(frozen=True)
class MarketplaceBookHostComposeDecision:
    title: str
    path: MarketplacePath
    free_copy_available: bool | None
    purchase_intent_allowed: bool
    purchase_executed: bool
    hostable: bool
    hosted: bool
    html_projection_sha: str | None
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "path": self.path,
            "free_copy_available": self.free_copy_available,
            "purchase_intent_allowed": self.purchase_intent_allowed,
            "purchase_executed": False,
            "hostable": self.hostable,
            "hosted": False,
            "html_projection_sha": self.html_projection_sha,
            "notes": list(self.notes),
            "authority": "marketplace_book_host_compose_advisory",
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MarketplaceBookHostComposeError(f"{field} must be a non-empty string")
    return value.strip()


def compose_marketplace_book_host(
    *,
    title: object,
    free_copy_available: object,
    skip_free_copy: object = False,
    operator_skip_acknowledged: object = False,
    purchase_intent_allowed: object | None = None,
    html_projection_sha: object | None = None,
    host_requested: object = True,
) -> MarketplaceBookHostComposeDecision:
    """Compose free-copy → purchase → HTML host decision."""
    t = _require_nonempty(title, field="title")
    if free_copy_available is not None and not isinstance(free_copy_available, bool):
        raise MarketplaceBookHostComposeError(
            "free_copy_available must be boolean or null"
        )
    for name, val in (
        ("skip_free_copy", skip_free_copy),
        ("operator_skip_acknowledged", operator_skip_acknowledged),
        ("host_requested", host_requested),
    ):
        if not isinstance(val, bool):
            raise MarketplaceBookHostComposeError(
                f"{name} must be an explicit boolean"
            )

    html_sha: str | None = None
    if html_projection_sha is not None:
        if not isinstance(html_projection_sha, str):
            raise MarketplaceBookHostComposeError(
                "html_projection_sha must be string or null"
            )
        html_sha = html_projection_sha.strip() or None

    notes: list[str] = [
        "purchase_executed=false — pure compose never charges",
        "hosted=false — pure compose never hosts bytes",
    ]

    if free_copy_available is True:
        notes.append("free_copy_available=true — path free_copy (purchase blocked)")
        hostable = host_requested is True and html_sha is not None
        if hostable:
            notes.append("HTML projection ready — hostable on free path")
        elif not html_sha:
            notes.append(
                "free path but html_projection_sha missing — hostable=false"
            )
        return MarketplaceBookHostComposeDecision(
            title=t,
            path="html_host" if hostable else "free_copy",
            free_copy_available=True,
            purchase_intent_allowed=False,
            purchase_executed=False,
            hostable=hostable,
            hosted=False,
            html_projection_sha=html_sha,
            notes=tuple(notes),
            authority="marketplace_book_host_compose_advisory",
        )

    if free_copy_available is None:
        notes.append(
            "free_copy_available=null — path incomplete (no invent free miss)"
        )
        return MarketplaceBookHostComposeDecision(
            title=t,
            path="incomplete",
            free_copy_available=None,
            purchase_intent_allowed=False,
            purchase_executed=False,
            hostable=False,
            hosted=False,
            html_projection_sha=html_sha,
            notes=tuple(notes),
            authority="marketplace_book_host_compose_advisory",
        )

    notes.append("free_copy_available=false — free miss")

    if skip_free_copy is True and operator_skip_acknowledged is not True:
        notes.append(
            "skip_free_copy without operator_skip_acknowledged — path blocked"
        )
        return MarketplaceBookHostComposeDecision(
            title=t,
            path="blocked",
            free_copy_available=False,
            purchase_intent_allowed=False,
            purchase_executed=False,
            hostable=False,
            hosted=False,
            html_projection_sha=html_sha,
            notes=tuple(notes),
            authority="marketplace_book_host_compose_advisory",
        )

    intent_allowed = True
    if purchase_intent_allowed is not None:
        if not isinstance(purchase_intent_allowed, bool):
            raise MarketplaceBookHostComposeError(
                "purchase_intent_allowed must be boolean or null"
            )
        intent_allowed = purchase_intent_allowed
    notes.append(
        "purchase_intent_allowed=true (intent only, not executed)"
        if intent_allowed
        else "purchase_intent_allowed=false"
    )

    if not intent_allowed:
        notes.append("purchase intent denied — path blocked")
        return MarketplaceBookHostComposeDecision(
            title=t,
            path="blocked",
            free_copy_available=False,
            purchase_intent_allowed=False,
            purchase_executed=False,
            hostable=False,
            hosted=False,
            html_projection_sha=html_sha,
            notes=tuple(notes),
            authority="marketplace_book_host_compose_advisory",
        )

    hostable = host_requested is True and html_sha is not None
    if hostable:
        notes.append(
            "purchase intent open + HTML projection ready — path html_host "
            "(still not hosted/purchased)"
        )
        return MarketplaceBookHostComposeDecision(
            title=t,
            path="html_host",
            free_copy_available=False,
            purchase_intent_allowed=True,
            purchase_executed=False,
            hostable=True,
            hosted=False,
            html_projection_sha=html_sha,
            notes=tuple(notes),
            authority="marketplace_book_host_compose_advisory",
        )

    notes.append(
        "host_requested=false — path purchase_intent"
        if html_sha
        else "html_projection_sha missing — path purchase_intent (hostable=false)"
    )
    return MarketplaceBookHostComposeDecision(
        title=t,
        path="purchase_intent",
        free_copy_available=False,
        purchase_intent_allowed=True,
        purchase_executed=False,
        hostable=False,
        hosted=False,
        html_projection_sha=html_sha,
        notes=tuple(notes),
        authority="marketplace_book_host_compose_advisory",
    )


__all__ = [
    "MarketplaceBookHostComposeDecision",
    "MarketplaceBookHostComposeError",
    "compose_marketplace_book_host",
]
