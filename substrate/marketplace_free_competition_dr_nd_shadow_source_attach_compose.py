"""Marketplace free-before-buy over competition DR ND shadow source-attach (pure).

purchase_executed / hosted always False.
pdf_view_authorized / pdf_primary always False.
live_dispatch_authorized / remote_fetched / backlog_mutated always False.
live_router_authorized / twin_written always False.
production_router_verdict always REJECT.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.competition_dr_nd_shadow_source_attach_weekly_learn_compose import (
    CompetitionDrNdShadowSourceAttachWeeklyLearnCompose,
    CompetitionDrNdShadowSourceAttachWeeklyLearnComposeError,
    compose_competition_dr_nd_shadow_source_attach_weekly_learn,
)
from substrate.marketplace_free_before_buy_html_port_compose import (
    MarketplaceFreeBeforeBuyHtmlPortCompose,
    MarketplaceFreeBeforeBuyHtmlPortComposeError,
    compose_marketplace_free_before_buy_html_port,
)


class MarketplaceFreeCompetitionDrNdShadowSourceAttachComposeError(ValueError):
    """Fail-closed validation for marketplace free + competition DR ND shadow pack."""


@dataclass(frozen=True)
class MarketplaceFreeCompetitionDrNdShadowSourceAttachCompose:
    title: str
    account_id: str
    session_id: str
    parent_asset_id: str
    week_id: str
    asset_id: str
    market: MarketplaceFreeBeforeBuyHtmlPortCompose
    competition_pack: CompetitionDrNdShadowSourceAttachWeeklyLearnCompose
    pack_ready: bool
    purchase_executed: bool
    hosted: bool
    pdf_view_authorized: bool
    pdf_primary: bool
    live_dispatch_authorized: bool
    remote_fetched: bool
    backlog_mutated: bool
    store_mutated: bool
    suite_rewritten: bool
    twin_written: bool
    prompts_injected: bool
    merge_executed: bool
    draft_written: bool
    analysis_written: bool
    live_dispatched: bool
    pack_dispatched: bool
    live_execution_authorized: bool
    live_router_authorized: bool
    secrets_stored: bool
    live_meter_read: bool
    remote_index_queried: bool
    inventory_mutated: bool
    charge_executed: bool
    record_persisted: bool
    production_router_verdict: str
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "account_id": self.account_id,
            "session_id": self.session_id,
            "parent_asset_id": self.parent_asset_id,
            "week_id": self.week_id,
            "asset_id": self.asset_id,
            "market": self.market.to_dict(),
            "competition_pack": self.competition_pack.to_dict(),
            "pack_ready": self.pack_ready,
            "purchase_executed": False,
            "hosted": False,
            "pdf_view_authorized": False,
            "pdf_primary": False,
            "live_dispatch_authorized": False,
            "remote_fetched": False,
            "backlog_mutated": False,
            "store_mutated": False,
            "suite_rewritten": False,
            "twin_written": False,
            "prompts_injected": False,
            "merge_executed": False,
            "draft_written": False,
            "analysis_written": False,
            "live_dispatched": False,
            "pack_dispatched": False,
            "live_execution_authorized": False,
            "live_router_authorized": False,
            "secrets_stored": False,
            "live_meter_read": False,
            "remote_index_queried": False,
            "inventory_mutated": False,
            "charge_executed": False,
            "record_persisted": False,
            "production_router_verdict": "REJECT",
            "notes": list(self.notes),
            "authority": (
                "marketplace_free_competition_dr_nd_shadow_source_attach_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MarketplaceFreeCompetitionDrNdShadowSourceAttachComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_marketplace_free_competition_dr_nd_shadow_source_attach(
    *,
    market: object,
    competition_pack: object,
    operator_ack: object,
    require_both: object | None = None,
) -> MarketplaceFreeCompetitionDrNdShadowSourceAttachCompose:
    """Free-before-buy HTML port + competition DR ND shadow pack. Never purchases."""
    if not isinstance(operator_ack, bool):
        raise MarketplaceFreeCompetitionDrNdShadowSourceAttachComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(market, dict):
        raise MarketplaceFreeCompetitionDrNdShadowSourceAttachComposeError(
            "market must be an object"
        )
    if not isinstance(competition_pack, dict):
        raise MarketplaceFreeCompetitionDrNdShadowSourceAttachComposeError(
            "competition_pack must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise MarketplaceFreeCompetitionDrNdShadowSourceAttachComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "purchase_executed=false · hosted=false",
        "pdf_view_authorized=false · pdf_primary=false",
        "live_dispatch_authorized=false · remote_fetched=false · backlog_mutated=false",
        "live_router_authorized=false · twin_written=false",
        "production_router_verdict=REJECT",
    ]

    try:
        mkt = compose_marketplace_free_before_buy_html_port(
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
        raise MarketplaceFreeCompetitionDrNdShadowSourceAttachComposeError(
            str(e)
        ) from e
    notes.extend(f"[market] {n}" for n in mkt.notes)

    try:
        cp = compose_competition_dr_nd_shadow_source_attach_weekly_learn(
            competition=competition_pack.get("competition"),
            nd_pack=competition_pack.get("nd_pack"),
            operator_ack=operator_ack,
            require_both=competition_pack.get("require_both"),
        )
    except CompetitionDrNdShadowSourceAttachWeeklyLearnComposeError as e:
        raise MarketplaceFreeCompetitionDrNdShadowSourceAttachComposeError(
            str(e)
        ) from e
    notes.extend(f"[competition_pack] {n}" for n in cp.notes)

    title = _require_nonempty(mkt.title, field="title")
    account = _require_nonempty(mkt.account_id, field="account_id")
    session = _require_nonempty(cp.session_id, field="session_id")
    parent = _require_nonempty(cp.parent_asset_id, field="parent_asset_id")
    week = _require_nonempty(cp.week_id, field="week_id")
    asset = _require_nonempty(cp.asset_id, field="asset_id")

    if require:
        pack_ready = (
            mkt.port_ready is True
            and cp.pack_ready is True
            and mkt.purchase_executed is False
            and mkt.hosted is False
            and mkt.pdf_view_authorized is False
            and cp.live_dispatch_authorized is False
            and cp.remote_fetched is False
            and cp.backlog_mutated is False
            and cp.live_router_authorized is False
            and cp.suite_rewritten is False
            and cp.twin_written is False
            and cp.merge_executed is False
            and cp.draft_written is False
            and cp.live_dispatched is False
            and cp.secrets_stored is False
            and cp.remote_index_queried is False
            and cp.pdf_primary is False
            and cp.purchase_executed is False
            and cp.hosted is False
            and cp.production_router_verdict == "REJECT"
            and cp.nd_pack.nd_shadow.production_router_verdict == "REJECT"
            and operator_ack is True
        )
    else:
        pack_ready = (
            operator_ack is True
            and mkt.purchase_executed is False
            and mkt.hosted is False
            and cp.live_dispatch_authorized is False
            and cp.remote_fetched is False
            and cp.production_router_verdict == "REJECT"
            and (mkt.port_ready is True or cp.pack_ready is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — marketplace free + competition DR ND shadow "
            "source-attach ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — market, competition_pack, or operator_ack gate open"
        )

    if (
        mkt.purchase_executed is not False
        or mkt.hosted is not False
        or mkt.pdf_view_authorized is not False
        or cp.live_dispatch_authorized is not False
        or cp.remote_fetched is not False
        or cp.backlog_mutated is not False
        or cp.live_router_authorized is not False
        or cp.suite_rewritten is not False
        or cp.twin_written is not False
        or cp.merge_executed is not False
        or cp.draft_written is not False
        or cp.live_dispatched is not False
        or cp.secrets_stored is not False
        or cp.remote_index_queried is not False
        or cp.pdf_primary is not False
        or cp.purchase_executed is not False
        or cp.hosted is not False
        or cp.production_router_verdict != "REJECT"
        or cp.nd_pack.nd_shadow.production_router_verdict != "REJECT"
    ):
        raise MarketplaceFreeCompetitionDrNdShadowSourceAttachComposeError(
            "invariant: honesty flags must remain false / REJECT"
        )

    notes.extend(
        (
            "purchase_executed=false",
            "hosted=false",
            "pdf_view_authorized=false",
            "pdf_primary=false",
            "live_dispatch_authorized=false",
            "remote_fetched=false",
            "backlog_mutated=false",
            "store_mutated=false",
            "suite_rewritten=false",
            "twin_written=false",
            "prompts_injected=false",
            "merge_executed=false",
            "draft_written=false",
            "analysis_written=false",
            "live_dispatched=false",
            "pack_dispatched=false",
            "live_execution_authorized=false",
            "live_router_authorized=false",
            "secrets_stored=false",
            "live_meter_read=false",
            "remote_index_queried=false",
            "inventory_mutated=false",
            "charge_executed=false",
            "record_persisted=false",
            "production_router_verdict=REJECT",
        )
    )

    return MarketplaceFreeCompetitionDrNdShadowSourceAttachCompose(
        title=title,
        account_id=account,
        session_id=session,
        parent_asset_id=parent,
        week_id=week,
        asset_id=asset,
        market=mkt,
        competition_pack=cp,
        pack_ready=pack_ready,
        purchase_executed=False,
        hosted=False,
        pdf_view_authorized=False,
        pdf_primary=False,
        live_dispatch_authorized=False,
        remote_fetched=False,
        backlog_mutated=False,
        store_mutated=False,
        suite_rewritten=False,
        twin_written=False,
        prompts_injected=False,
        merge_executed=False,
        draft_written=False,
        analysis_written=False,
        live_dispatched=False,
        pack_dispatched=False,
        live_execution_authorized=False,
        live_router_authorized=False,
        secrets_stored=False,
        live_meter_read=False,
        remote_index_queried=False,
        inventory_mutated=False,
        charge_executed=False,
        record_persisted=False,
        production_router_verdict="REJECT",
        notes=tuple(notes),
        authority=(
            "marketplace_free_competition_dr_nd_shadow_source_attach_compose_advisory"
        ),
    )


def format_marketplace_free_competition_dr_nd_shadow_source_attach_summary(
    c: MarketplaceFreeCompetitionDrNdShadowSourceAttachCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"port_ready={c.market.port_ready} · "
        f"competition_ready={c.competition_pack.pack_ready} · "
        f"path={c.market.path} · "
        f"verdict={c.production_router_verdict} · "
        "purchase_executed=false · hosted=false · live_dispatch_authorized=false"
    )


__all__ = [
    "MarketplaceFreeCompetitionDrNdShadowSourceAttachCompose",
    "MarketplaceFreeCompetitionDrNdShadowSourceAttachComposeError",
    "compose_marketplace_free_competition_dr_nd_shadow_source_attach",
    "format_marketplace_free_competition_dr_nd_shadow_source_attach_summary",
]
