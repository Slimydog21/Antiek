"""Marketplace HTML book → highlight float → recursive twin MO (pure).

purchase_executed / charge_executed / hosted / pdf_view_authorized always False.
live_dispatched / twin_written / live_execution_authorized always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.highlight_float_recursive_twin_mo_competition_compose import (
    HighlightFloatRecursiveTwinMoCompetitionCompose,
    HighlightFloatRecursiveTwinMoCompetitionComposeError,
    compose_highlight_float_recursive_twin_mo_competition,
)
from substrate.marketplace_html_view_twin_session_compose import (
    MarketplaceHtmlViewTwinSessionCompose,
    MarketplaceHtmlViewTwinSessionComposeError,
    compose_marketplace_html_view_twin_session,
)


class MarketplaceHighlightFloatRecursiveTwinMoComposeError(ValueError):
    """Fail-closed validation for marketplace → highlight twin MO pack."""


@dataclass(frozen=True)
class MarketplaceHighlightFloatRecursiveTwinMoCompose:
    session_id: str
    asset_id: str
    market: MarketplaceHtmlViewTwinSessionCompose
    research: HighlightFloatRecursiveTwinMoCompetitionCompose
    pack_ready: bool
    purchase_executed: bool
    charge_executed: bool
    hosted: bool
    pdf_view_authorized: bool
    live_dispatched: bool
    merge_executed: bool
    pack_dispatched: bool
    twin_written: bool
    record_persisted: bool
    live_execution_authorized: bool
    prompts_injected: bool
    live_router_authorized: bool
    store_mutated: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "asset_id": self.asset_id,
            "market": self.market.to_dict(),
            "research": self.research.to_dict(),
            "pack_ready": self.pack_ready,
            "purchase_executed": False,
            "charge_executed": False,
            "hosted": False,
            "pdf_view_authorized": False,
            "live_dispatched": False,
            "merge_executed": False,
            "pack_dispatched": False,
            "twin_written": False,
            "record_persisted": False,
            "live_execution_authorized": False,
            "prompts_injected": False,
            "live_router_authorized": False,
            "store_mutated": False,
            "notes": list(self.notes),
            "authority": (
                "marketplace_highlight_float_recursive_twin_mo_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MarketplaceHighlightFloatRecursiveTwinMoComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_marketplace_highlight_float_recursive_twin_mo(
    *,
    market: object,
    research: object,
    operator_ack: object,
    seed_highlight_from_title: object | None = None,
    require_both: object | None = None,
) -> MarketplaceHighlightFloatRecursiveTwinMoCompose:
    """Marketplace HTML session + highlight float twin MO. Never charges/hosts."""
    if not isinstance(operator_ack, bool):
        raise MarketplaceHighlightFloatRecursiveTwinMoComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(market, dict):
        raise MarketplaceHighlightFloatRecursiveTwinMoComposeError(
            "market must be an object"
        )
    if not isinstance(research, dict):
        raise MarketplaceHighlightFloatRecursiveTwinMoComposeError(
            "research must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise MarketplaceHighlightFloatRecursiveTwinMoComposeError(
            "require_both must be boolean when set"
        )
    seed_title = (
        True if seed_highlight_from_title is None else seed_highlight_from_title
    )
    if not isinstance(seed_title, bool):
        raise MarketplaceHighlightFloatRecursiveTwinMoComposeError(
            "seed_highlight_from_title must be boolean when set"
        )

    notes: list[str] = [
        "purchase_executed=false · charge_executed=false · hosted=false",
        "pdf_view_authorized=false — HTML-native marketplace + reading",
        "live_dispatched=false · twin_written=false · live_execution_authorized=false",
        "prompts_injected=false · live_router_authorized=false · store_mutated=false",
    ]

    try:
        market_pack = compose_marketplace_html_view_twin_session(
            session_id=market.get("session_id"),
            asset_id=market.get("asset_id"),
            title=market.get("title"),
            account_id=market.get("account_id"),
            free_copy_available=market.get("free_copy_available"),
            port_requested=market.get("port_requested"),
            purchase_ack=market.get("purchase_ack"),
            list_price_usd=market.get("list_price_usd"),
            approved_spend_usd=market.get("approved_spend_usd"),
            remaining_budget_usd=market.get("remaining_budget_usd"),
            operator_ack=operator_ack,
            view_requested=market.get("view_requested"),
            free_html_projection_sha=market.get("free_html_projection_sha"),
            purchase_html_projection_sha=market.get(
                "purchase_html_projection_sha"
            ),
            twin_bound=market.get("twin_bound"),
            twin_substrate_ready=market.get("twin_substrate_ready"),
            claimed_format=market.get("claimed_format"),
            twin_findings=market.get("twin_findings"),
            existing_twin_asset_id=market.get("existing_twin_asset_id"),
            mark_for_prompt_context=market.get("mark_for_prompt_context"),
            include_twin_feed=market.get("include_twin_feed"),
        )
    except MarketplaceHtmlViewTwinSessionComposeError as e:
        raise MarketplaceHighlightFloatRecursiveTwinMoComposeError(
            str(e)
        ) from e
    notes.extend(f"[market] {n}" for n in market_pack.notes)

    session = _require_nonempty(market_pack.session_id, field="session_id")
    asset = _require_nonempty(market_pack.asset_id, field="asset_id")

    hs = research.get("highlight_surface")
    if not isinstance(hs, dict):
        raise MarketplaceHighlightFloatRecursiveTwinMoComposeError(
            "research.highlight_surface must be an object"
        )

    hl = hs.get("highlight")
    if isinstance(hl, str) and hl.strip():
        highlight = hl.strip()
    elif seed_title:
        title = _require_nonempty(market.get("title"), field="market.title")
        highlight = f"from book: {title}"
        notes.append("highlight seeded from marketplace book title")
    else:
        raise MarketplaceHighlightFloatRecursiveTwinMoComposeError(
            "research.highlight_surface.highlight must be non-empty when "
            "seed_highlight_from_title=false"
        )

    highlight_surface = {
        **hs,
        "session_id": (
            str(hs["session_id"]).strip()
            if hs.get("session_id")
            else session
        ),
        "parent_asset_id": (
            str(hs["parent_asset_id"]).strip()
            if hs.get("parent_asset_id")
            else asset
        ),
        "highlight": highlight,
        "operator_ack": operator_ack,
    }

    mo_competition = research.get("mo_competition")
    if not isinstance(mo_competition, dict):
        raise MarketplaceHighlightFloatRecursiveTwinMoComposeError(
            "research.mo_competition must be an object"
        )
    mo_competition = {
        **mo_competition,
        "parent_asset_id": (
            str(mo_competition["parent_asset_id"]).strip()
            if mo_competition.get("parent_asset_id")
            else asset
        ),
    }

    try:
        research_pack = compose_highlight_float_recursive_twin_mo_competition(
            highlight_surface=highlight_surface,
            mo_competition=mo_competition,
            operator_ack=operator_ack,
            seed_excerpt_from_highlight=research.get(
                "seed_excerpt_from_highlight"
            ),
            require_both=research.get("require_both"),
        )
    except HighlightFloatRecursiveTwinMoCompetitionComposeError as e:
        raise MarketplaceHighlightFloatRecursiveTwinMoComposeError(
            str(e)
        ) from e
    notes.extend(f"[research] {n}" for n in research_pack.notes)

    if require:
        pack_ready = (
            market_pack.session_ready is True
            and research_pack.pack_ready is True
            and operator_ack is True
        )
    else:
        pack_ready = operator_ack is True and (
            market_pack.session_ready is True or research_pack.pack_ready is True
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — marketplace HTML book + highlight float twin MO ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — market, research, or operator_ack gate open"
        )

    if (
        market_pack.purchase_executed is not False
        or market_pack.charge_executed is not False
        or market_pack.hosted is not False
        or market_pack.pdf_view_authorized is not False
        or market_pack.twin_written is not False
        or research_pack.live_dispatched is not False
        or research_pack.twin_written is not False
        or research_pack.live_execution_authorized is not False
        or research_pack.prompts_injected is not False
    ):
        raise MarketplaceHighlightFloatRecursiveTwinMoComposeError(
            "invariant: honesty flags must remain false"
        )

    notes.extend(
        (
            "purchase_executed=false",
            "charge_executed=false",
            "hosted=false",
            "pdf_view_authorized=false",
            "live_dispatched=false",
            "merge_executed=false",
            "pack_dispatched=false",
            "twin_written=false",
            "record_persisted=false",
            "live_execution_authorized=false",
            "prompts_injected=false",
            "live_router_authorized=false",
            "store_mutated=false",
        )
    )

    return MarketplaceHighlightFloatRecursiveTwinMoCompose(
        session_id=session,
        asset_id=asset,
        market=market_pack,
        research=research_pack,
        pack_ready=pack_ready,
        purchase_executed=False,
        charge_executed=False,
        hosted=False,
        pdf_view_authorized=False,
        live_dispatched=False,
        merge_executed=False,
        pack_dispatched=False,
        twin_written=False,
        record_persisted=False,
        live_execution_authorized=False,
        prompts_injected=False,
        live_router_authorized=False,
        store_mutated=False,
        notes=tuple(notes),
        authority=(
            "marketplace_highlight_float_recursive_twin_mo_compose_advisory"
        ),
    )


def format_marketplace_highlight_float_recursive_twin_mo_summary(
    c: MarketplaceHighlightFloatRecursiveTwinMoCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"market_ready={c.market.session_ready} · "
        f"research_ready={c.research.pack_ready} · "
        f"purchase_executed=false · hosted=false · pdf_view_authorized=false · "
        f"live_dispatched=false · twin_written=false · live_execution_authorized=false"
    )


__all__ = [
    "MarketplaceHighlightFloatRecursiveTwinMoCompose",
    "MarketplaceHighlightFloatRecursiveTwinMoComposeError",
    "compose_marketplace_highlight_float_recursive_twin_mo",
    "format_marketplace_highlight_float_recursive_twin_mo_summary",
]
