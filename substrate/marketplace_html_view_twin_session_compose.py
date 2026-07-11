"""Marketplace HTML view + twin session compose (pure).

purchase_executed, charge_executed, hosted, pdf_view_authorized,
twin_written, record_persisted, store_mutated always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.paid_purchase_html_view_session_compose import (
    PaidPurchaseHtmlViewSessionCompose,
    PaidPurchaseHtmlViewSessionComposeError,
    compose_paid_purchase_html_view_session,
)
from substrate.twin_chase_analysis_feed_compose import (
    TwinChaseAnalysisFeedCompose,
    TwinChaseAnalysisFeedComposeError,
    compose_twin_chase_analysis_feed,
)


class MarketplaceHtmlViewTwinSessionComposeError(ValueError):
    """Fail-closed validation for marketplace HTML+twin session."""


@dataclass(frozen=True)
class MarketplaceHtmlViewTwinSessionCompose:
    session_id: str
    asset_id: str
    market_view: PaidPurchaseHtmlViewSessionCompose
    twin_feed: TwinChaseAnalysisFeedCompose | None
    session_ready: bool
    purchase_executed: bool
    charge_executed: bool
    hosted: bool
    pdf_view_authorized: bool
    twin_written: bool
    record_persisted: bool
    store_mutated: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "asset_id": self.asset_id,
            "market_view": self.market_view.to_dict(),
            "twin_feed": self.twin_feed.to_dict() if self.twin_feed else None,
            "session_ready": self.session_ready,
            "purchase_executed": False,
            "charge_executed": False,
            "hosted": False,
            "pdf_view_authorized": False,
            "twin_written": False,
            "record_persisted": False,
            "store_mutated": False,
            "notes": list(self.notes),
            "authority": "marketplace_html_view_twin_session_compose_advisory",
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MarketplaceHtmlViewTwinSessionComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_marketplace_html_view_twin_session(
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
    twin_findings: object | None = None,
    existing_twin_asset_id: object | None = None,
    mark_for_prompt_context: object | None = None,
    include_twin_feed: object | None = None,
) -> MarketplaceHtmlViewTwinSessionCompose:
    """Compose marketplace→HTML view→twin. Never charges/hosts/PDF/writes twin."""
    if not isinstance(operator_ack, bool):
        raise MarketplaceHtmlViewTwinSessionComposeError(
            "operator_ack must be an explicit boolean"
        )
    session = _require_nonempty(session_id, field="session_id")
    asset = _require_nonempty(asset_id, field="asset_id")
    include_twin = True if include_twin_feed is None else include_twin_feed
    if not isinstance(include_twin, bool):
        raise MarketplaceHtmlViewTwinSessionComposeError(
            "include_twin_feed must be boolean when set"
        )

    notes: list[str] = [
        "purchase_executed=false · charge_executed=false · hosted=false",
        "pdf_view_authorized=false — HTML-native only",
        "twin_written=false · record_persisted=false · store_mutated=false",
    ]

    twin_bound_val = include_twin if twin_bound is None else twin_bound
    try:
        market_view = compose_paid_purchase_html_view_session(
            session_id=session,
            asset_id=asset,
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
            view_requested=view_requested,
            twin_bound=twin_bound_val,
            twin_substrate_ready=twin_substrate_ready,
            claimed_format=claimed_format,
        )
    except PaidPurchaseHtmlViewSessionComposeError as e:
        raise MarketplaceHtmlViewTwinSessionComposeError(str(e)) from e
    notes.extend(market_view.notes)

    twin_feed: TwinChaseAnalysisFeedCompose | None = None
    if include_twin:
        title_s = _require_nonempty(title, field="title")
        findings: list[dict[str, Any]] = [
            {
                "source_id": f"book_title_{asset}",
                "body": title_s,
                "kind": "data",
            }
        ]
        if twin_findings is not None:
            if not isinstance(twin_findings, list):
                raise MarketplaceHtmlViewTwinSessionComposeError(
                    "twin_findings must be an array when set"
                )
            for f in twin_findings:
                if not isinstance(f, dict):
                    raise MarketplaceHtmlViewTwinSessionComposeError(
                        "twin_findings entries must be objects"
                    )
                findings.append(dict(f))
        try:
            twin_feed = compose_twin_chase_analysis_feed(
                session_id=session,
                parent_asset_id=asset,
                findings=findings,
                analysis_excerpt=f"HTML reading session for: {title_s}",
                existing_twin_asset_id=existing_twin_asset_id,
                operator_ack=operator_ack,
                mark_for_prompt_context=mark_for_prompt_context,
            )
        except TwinChaseAnalysisFeedComposeError as e:
            raise MarketplaceHtmlViewTwinSessionComposeError(str(e)) from e
        notes.extend(twin_feed.notes)
    else:
        notes.append("twin_feed skipped — include_twin_feed=false")

    twin_ok = (not include_twin) or (
        twin_feed is not None and twin_feed.feed_ready
    )
    session_ready = market_view.session_package_ready and twin_ok
    if not market_view.session_package_ready:
        notes.append(
            "session_ready=false — marketplace/HTML view package not ready"
        )
    elif not twin_ok:
        notes.append("session_ready=false — twin feed not ready")
    else:
        notes.append(
            "session_ready=true — marketplace HTML+twin intent only; still pure"
        )

    if (
        market_view.purchase_executed is not False
        or market_view.charge_executed is not False
        or market_view.hosted is not False
        or market_view.pdf_view_authorized is not False
        or market_view.store_mutated is not False
    ):
        raise MarketplaceHtmlViewTwinSessionComposeError(
            "invariant: market_view honesty flags must remain false"
        )
    if twin_feed is not None and (
        twin_feed.twin_written is not False
        or twin_feed.record_persisted is not False
        or twin_feed.live_dispatch_authorized is not False
    ):
        raise MarketplaceHtmlViewTwinSessionComposeError(
            "invariant: twin_feed honesty flags must remain false"
        )

    notes.extend(
        (
            "purchase_executed=false",
            "charge_executed=false",
            "hosted=false",
            "pdf_view_authorized=false",
            "twin_written=false",
            "record_persisted=false",
            "store_mutated=false",
        )
    )

    return MarketplaceHtmlViewTwinSessionCompose(
        session_id=session,
        asset_id=asset,
        market_view=market_view,
        twin_feed=twin_feed,
        session_ready=session_ready,
        purchase_executed=False,
        charge_executed=False,
        hosted=False,
        pdf_view_authorized=False,
        twin_written=False,
        record_persisted=False,
        store_mutated=False,
        notes=tuple(notes),
        authority="marketplace_html_view_twin_session_compose_advisory",
    )


def format_marketplace_html_view_twin_session_summary(
    c: MarketplaceHtmlViewTwinSessionCompose,
) -> str:
    feed = c.twin_feed.feed_ready if c.twin_feed is not None else "n/a"
    return (
        f"session_ready={c.session_ready} · "
        f"market_package_ready={c.market_view.session_package_ready} · "
        f"feed_ready={feed} · "
        f"purchase_executed=false · charge_executed=false · hosted=false · "
        f"pdf_view_authorized=false · twin_written=false · record_persisted=false"
    )


__all__ = [
    "MarketplaceHtmlViewTwinSessionCompose",
    "MarketplaceHtmlViewTwinSessionComposeError",
    "compose_marketplace_html_view_twin_session",
    "format_marketplace_html_view_twin_session_summary",
]
