"""Marketplace free-before-buy over Antiek-bench recommend + MO unattended (pure).

purchase_executed / hosted always False.
pdf_view_authorized / pdf_primary always False.
live_router_authorized / live_execution_authorized / charge_executed False.
production_router_verdict always REJECT.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.marketplace_free_before_buy_html_port_compose import (
    MarketplaceFreeBeforeBuyHtmlPortCompose,
    MarketplaceFreeBeforeBuyHtmlPortComposeError,
    compose_marketplace_free_before_buy_html_port,
)
from substrate.antiek_bench_recommend_mo_unattended_compose import (
    AntiekBenchRecommendMoUnattendedCompose,
    AntiekBenchRecommendMoUnattendedComposeError,
    compose_antiek_bench_recommend_mo_unattended,
)


class MarketplaceFreeAntiekBenchRecommendMoComposeError(ValueError):
    """Fail-closed validation for marketplace free + bench recommend MO pack."""


@dataclass(frozen=True)
class MarketplaceFreeAntiekBenchRecommendMoCompose:
    title: str
    account_id: str
    week_id: str
    session_id: str
    parent_asset_id: str
    asset_id: str
    market: MarketplaceFreeBeforeBuyHtmlPortCompose
    bench_mo: AntiekBenchRecommendMoUnattendedCompose
    pack_ready: bool
    purchase_executed: bool
    hosted: bool
    pdf_view_authorized: bool
    pdf_primary: bool
    live_router_authorized: bool
    secrets_stored: bool
    live_meter_read: bool
    backlog_mutated: bool
    store_mutated: bool
    suite_rewritten: bool
    live_execution_authorized: bool
    charge_executed: bool
    remote_fetched: bool
    remote_index_queried: bool
    twin_written: bool
    prompts_injected: bool
    live_dispatch_authorized: bool
    inventory_mutated: bool
    live_dispatched: bool
    pack_dispatched: bool
    merge_executed: bool
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
            "week_id": self.week_id,
            "session_id": self.session_id,
            "parent_asset_id": self.parent_asset_id,
            "asset_id": self.asset_id,
            "market": self.market.to_dict(),
            "bench_mo": self.bench_mo.to_dict(),
            "pack_ready": self.pack_ready,
            "purchase_executed": False,
            "hosted": False,
            "pdf_view_authorized": False,
            "pdf_primary": False,
            "live_router_authorized": False,
            "secrets_stored": False,
            "live_meter_read": False,
            "backlog_mutated": False,
            "store_mutated": False,
            "suite_rewritten": False,
            "live_execution_authorized": False,
            "charge_executed": False,
            "remote_fetched": False,
            "remote_index_queried": False,
            "twin_written": False,
            "prompts_injected": False,
            "live_dispatch_authorized": False,
            "inventory_mutated": False,
            "live_dispatched": False,
            "pack_dispatched": False,
            "merge_executed": False,
            "draft_written": False,
            "record_persisted": False,
            "analysis_written": False,
            "production_router_verdict": "REJECT",
            "notes": list(self.notes),
            "authority": (
                "marketplace_free_antiek_bench_recommend_mo_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MarketplaceFreeAntiekBenchRecommendMoComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_marketplace_free_antiek_bench_recommend_mo(
    *,
    market: object,
    bench_mo: object,
    operator_ack: object,
    require_both: object | None = None,
) -> MarketplaceFreeAntiekBenchRecommendMoCompose:
    """Free-before-buy port + bench recommend MO. Never purchases/hosts."""
    if not isinstance(operator_ack, bool):
        raise MarketplaceFreeAntiekBenchRecommendMoComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(market, dict):
        raise MarketplaceFreeAntiekBenchRecommendMoComposeError(
            "market must be an object"
        )
    if not isinstance(bench_mo, dict):
        raise MarketplaceFreeAntiekBenchRecommendMoComposeError(
            "bench_mo must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise MarketplaceFreeAntiekBenchRecommendMoComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "purchase_executed=false · hosted=false",
        "pdf_view_authorized=false · pdf_primary=false",
        "live_router_authorized=false · live_execution_authorized=false",
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
        raise MarketplaceFreeAntiekBenchRecommendMoComposeError(str(e)) from e
    notes.extend(f"[market] {n}" for n in mkt.notes)

    try:
        bm = compose_antiek_bench_recommend_mo_unattended(
            bench=bench_mo.get("bench"),
            mo_pack=bench_mo.get("mo_pack"),
            operator_ack=operator_ack,
            require_both=bench_mo.get("require_both"),
        )
    except AntiekBenchRecommendMoUnattendedComposeError as e:
        raise MarketplaceFreeAntiekBenchRecommendMoComposeError(str(e)) from e
    notes.extend(f"[bench_mo] {n}" for n in bm.notes)

    title = _require_nonempty(mkt.title, field="title")
    account = _require_nonempty(mkt.account_id, field="account_id")
    week = _require_nonempty(bm.week_id, field="week_id")
    session = _require_nonempty(bm.session_id, field="session_id")
    parent = _require_nonempty(bm.parent_asset_id, field="parent_asset_id")
    asset = _require_nonempty(bm.asset_id, field="asset_id")

    if require:
        pack_ready = (
            mkt.port_ready is True
            and bm.pack_ready is True
            and mkt.purchase_executed is False
            and mkt.hosted is False
            and mkt.pdf_view_authorized is False
            and bm.live_router_authorized is False
            and bm.suite_rewritten is False
            and bm.live_execution_authorized is False
            and bm.charge_executed is False
            and bm.purchase_executed is False
            and bm.hosted is False
            and bm.pdf_primary is False
            and bm.production_router_verdict == "REJECT"
            and operator_ack is True
        )
    else:
        pack_ready = (
            operator_ack is True
            and mkt.purchase_executed is False
            and mkt.hosted is False
            and mkt.pdf_view_authorized is False
            and bm.production_router_verdict == "REJECT"
            and bm.pdf_primary is False
            and (mkt.port_ready is True or bm.pack_ready is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — free-before-buy port + Antiek-bench recommend MO "
            "ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — market, bench_mo, or operator_ack gate open"
        )

    if (
        mkt.purchase_executed is not False
        or mkt.hosted is not False
        or mkt.pdf_view_authorized is not False
        or bm.live_router_authorized is not False
        or bm.suite_rewritten is not False
        or bm.live_execution_authorized is not False
        or bm.charge_executed is not False
        or bm.purchase_executed is not False
        or bm.hosted is not False
        or bm.pdf_primary is not False
        or bm.production_router_verdict != "REJECT"
    ):
        raise MarketplaceFreeAntiekBenchRecommendMoComposeError(
            "invariant: honesty flags must remain false"
        )

    notes.extend(
        (
            "purchase_executed=false",
            "hosted=false",
            "pdf_view_authorized=false",
            "pdf_primary=false",
            "live_router_authorized=false",
            "secrets_stored=false",
            "live_meter_read=false",
            "backlog_mutated=false",
            "store_mutated=false",
            "suite_rewritten=false",
            "live_execution_authorized=false",
            "charge_executed=false",
            "remote_fetched=false",
            "remote_index_queried=false",
            "twin_written=false",
            "prompts_injected=false",
            "live_dispatch_authorized=false",
            "inventory_mutated=false",
            "live_dispatched=false",
            "pack_dispatched=false",
            "merge_executed=false",
            "draft_written=false",
            "record_persisted=false",
            "analysis_written=false",
            "production_router_verdict=REJECT",
        )
    )

    return MarketplaceFreeAntiekBenchRecommendMoCompose(
        title=title,
        account_id=account,
        week_id=week,
        session_id=session,
        parent_asset_id=parent,
        asset_id=asset,
        market=mkt,
        bench_mo=bm,
        pack_ready=pack_ready,
        purchase_executed=False,
        hosted=False,
        pdf_view_authorized=False,
        pdf_primary=False,
        live_router_authorized=False,
        secrets_stored=False,
        live_meter_read=False,
        backlog_mutated=False,
        store_mutated=False,
        suite_rewritten=False,
        live_execution_authorized=False,
        charge_executed=False,
        remote_fetched=False,
        remote_index_queried=False,
        twin_written=False,
        prompts_injected=False,
        live_dispatch_authorized=False,
        inventory_mutated=False,
        live_dispatched=False,
        pack_dispatched=False,
        merge_executed=False,
        draft_written=False,
        record_persisted=False,
        analysis_written=False,
        production_router_verdict="REJECT",
        notes=tuple(notes),
        authority=(
            "marketplace_free_antiek_bench_recommend_mo_compose_advisory"
        ),
    )


def format_marketplace_free_antiek_bench_recommend_mo_summary(
    c: MarketplaceFreeAntiekBenchRecommendMoCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"port_ready={c.market.port_ready} · "
        f"path={c.market.path} · "
        f"bench_mo_ready={c.bench_mo.pack_ready} · "
        f"week={c.week_id} · "
        f"verdict={c.production_router_verdict} · "
        f"purchase_executed=false · hosted=false · pdf_primary=false"
    )


__all__ = [
    "MarketplaceFreeAntiekBenchRecommendMoCompose",
    "MarketplaceFreeAntiekBenchRecommendMoComposeError",
    "compose_marketplace_free_antiek_bench_recommend_mo",
    "format_marketplace_free_antiek_bench_recommend_mo_summary",
]
