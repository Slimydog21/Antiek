"""Marketplace free-before-buy + source-attach record→prompt pack (pure).

purchase_executed / hosted always False.
remote_fetched / prompts_injected always False.
pdf_view_authorized / pdf_primary always False.
production_router_verdict always REJECT; live_router_authorized always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.marketplace_free_before_buy_html_port_compose import (
    MarketplaceFreeBeforeBuyHtmlPortCompose,
    MarketplaceFreeBeforeBuyHtmlPortComposeError,
    compose_marketplace_free_before_buy_html_port,
)
from substrate.source_attach_record_prompt_html_native_mo_compose import (
    SourceAttachRecordPromptHtmlNativeMoCompose,
    SourceAttachRecordPromptHtmlNativeMoComposeError,
    compose_source_attach_record_prompt_html_native_mo,
)


class MarketplaceFreeSourceAttachRecordPromptComposeError(ValueError):
    """Fail-closed validation for marketplace free + source-attach pack."""


@dataclass(frozen=True)
class MarketplaceFreeSourceAttachRecordPromptCompose:
    session_id: str
    parent_asset_id: str
    week_id: str
    account_id: str
    market: MarketplaceFreeBeforeBuyHtmlPortCompose
    research: SourceAttachRecordPromptHtmlNativeMoCompose
    pack_ready: bool
    purchase_executed: bool
    hosted: bool
    remote_fetched: bool
    prompts_injected: bool
    pdf_view_authorized: bool
    pdf_primary: bool
    twin_written: bool
    charge_executed: bool
    live_execution_authorized: bool
    draft_written: bool
    analysis_written: bool
    merge_executed: bool
    record_persisted: bool
    live_dispatch_authorized: bool
    secrets_stored: bool
    inventory_mutated: bool
    live_dispatched: bool
    pack_dispatched: bool
    backlog_mutated: bool
    store_mutated: bool
    production_router_verdict: str
    live_router_authorized: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "parent_asset_id": self.parent_asset_id,
            "week_id": self.week_id,
            "account_id": self.account_id,
            "market": self.market.to_dict(),
            "research": self.research.to_dict(),
            "pack_ready": self.pack_ready,
            "purchase_executed": False,
            "hosted": False,
            "remote_fetched": False,
            "prompts_injected": False,
            "pdf_view_authorized": False,
            "pdf_primary": False,
            "twin_written": False,
            "charge_executed": False,
            "live_execution_authorized": False,
            "draft_written": False,
            "analysis_written": False,
            "merge_executed": False,
            "record_persisted": False,
            "live_dispatch_authorized": False,
            "secrets_stored": False,
            "inventory_mutated": False,
            "live_dispatched": False,
            "pack_dispatched": False,
            "backlog_mutated": False,
            "store_mutated": False,
            "production_router_verdict": "REJECT",
            "live_router_authorized": False,
            "notes": list(self.notes),
            "authority": (
                "marketplace_free_source_attach_record_prompt_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MarketplaceFreeSourceAttachRecordPromptComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_marketplace_free_source_attach_record_prompt(
    *,
    market: object,
    research: object,
    operator_ack: object,
    require_both: object | None = None,
) -> MarketplaceFreeSourceAttachRecordPromptCompose:
    """Free-before-buy market + source-attach research. Never purchases/hosts."""
    if not isinstance(operator_ack, bool):
        raise MarketplaceFreeSourceAttachRecordPromptComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(market, dict):
        raise MarketplaceFreeSourceAttachRecordPromptComposeError(
            "market must be an object"
        )
    if not isinstance(research, dict):
        raise MarketplaceFreeSourceAttachRecordPromptComposeError(
            "research must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise MarketplaceFreeSourceAttachRecordPromptComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "purchase_executed=false · hosted=false",
        "remote_fetched=false · prompts_injected=false",
        "pdf_view_authorized=false · pdf_primary=false",
        "production_router_verdict=REJECT · live_router_authorized=false",
    ]

    try:
        m = compose_marketplace_free_before_buy_html_port(
            title=market.get("title"),
            account_id=market.get("account_id"),
            free_copy_available=market.get("free_copy_available"),
            purchase_ack=market.get("purchase_ack"),
            port_requested=market.get("port_requested"),
            free_html_projection_sha=market.get("free_html_projection_sha"),
            purchase_html_projection_sha=market.get(
                "purchase_html_projection_sha"
            ),
        )
    except MarketplaceFreeBeforeBuyHtmlPortComposeError as e:
        raise MarketplaceFreeSourceAttachRecordPromptComposeError(
            str(e)
        ) from e
    notes.extend(f"[market] {n}" for n in m.notes)

    try:
        r = compose_source_attach_record_prompt_html_native_mo(
            sources=research.get("sources"),
            record_html=research.get("record_html"),
            operator_ack=operator_ack,
            require_both=research.get("require_both"),
        )
    except SourceAttachRecordPromptHtmlNativeMoComposeError as e:
        raise MarketplaceFreeSourceAttachRecordPromptComposeError(
            str(e)
        ) from e
    notes.extend(f"[research] {n}" for n in r.notes)

    session = _require_nonempty(r.session_id, field="session_id")
    parent = _require_nonempty(r.parent_asset_id, field="parent_asset_id")
    week = _require_nonempty(r.week_id, field="week_id")
    account = _require_nonempty(m.account_id, field="account_id")

    if require:
        pack_ready = (
            m.port_ready is True
            and r.pack_ready is True
            and r.production_router_verdict == "REJECT"
            and m.purchase_executed is False
            and m.hosted is False
            and r.remote_fetched is False
            and operator_ack is True
        )
    else:
        pack_ready = (
            operator_ack is True
            and r.production_router_verdict == "REJECT"
            and m.purchase_executed is False
            and (m.port_ready is True or r.pack_ready is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — free-before-buy HTML port + source-attach research ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — market, research, or operator_ack gate open"
        )

    if (
        m.purchase_executed is not False
        or m.hosted is not False
        or m.pdf_view_authorized is not False
        or r.remote_fetched is not False
        or r.prompts_injected is not False
        or r.pdf_primary is not False
        or r.production_router_verdict != "REJECT"
        or r.live_router_authorized is not False
    ):
        raise MarketplaceFreeSourceAttachRecordPromptComposeError(
            "invariant: honesty flags must remain false"
        )

    notes.extend(
        (
            "purchase_executed=false",
            "hosted=false",
            "remote_fetched=false",
            "prompts_injected=false",
            "pdf_view_authorized=false",
            "pdf_primary=false",
            "twin_written=false",
            "charge_executed=false",
            "live_execution_authorized=false",
            "draft_written=false",
            "analysis_written=false",
            "merge_executed=false",
            "record_persisted=false",
            "live_dispatch_authorized=false",
            "secrets_stored=false",
            "inventory_mutated=false",
            "live_dispatched=false",
            "pack_dispatched=false",
            "backlog_mutated=false",
            "store_mutated=false",
            "production_router_verdict=REJECT",
            "live_router_authorized=false",
        )
    )

    return MarketplaceFreeSourceAttachRecordPromptCompose(
        session_id=session,
        parent_asset_id=parent,
        week_id=week,
        account_id=account,
        market=m,
        research=r,
        pack_ready=pack_ready,
        purchase_executed=False,
        hosted=False,
        remote_fetched=False,
        prompts_injected=False,
        pdf_view_authorized=False,
        pdf_primary=False,
        twin_written=False,
        charge_executed=False,
        live_execution_authorized=False,
        draft_written=False,
        analysis_written=False,
        merge_executed=False,
        record_persisted=False,
        live_dispatch_authorized=False,
        secrets_stored=False,
        inventory_mutated=False,
        live_dispatched=False,
        pack_dispatched=False,
        backlog_mutated=False,
        store_mutated=False,
        production_router_verdict="REJECT",
        live_router_authorized=False,
        notes=tuple(notes),
        authority=(
            "marketplace_free_source_attach_record_prompt_compose_advisory"
        ),
    )


def format_marketplace_free_source_attach_record_prompt_summary(
    c: MarketplaceFreeSourceAttachRecordPromptCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"market_path={c.market.path} · "
        f"port_ready={c.market.port_ready} · "
        f"research_ready={c.research.pack_ready} · "
        f"verdict={c.production_router_verdict} · "
        f"purchase_executed=false · hosted=false · remote_fetched=false"
    )


__all__ = [
    "MarketplaceFreeSourceAttachRecordPromptCompose",
    "MarketplaceFreeSourceAttachRecordPromptComposeError",
    "compose_marketplace_free_source_attach_record_prompt",
    "format_marketplace_free_source_attach_record_prompt_summary",
]
