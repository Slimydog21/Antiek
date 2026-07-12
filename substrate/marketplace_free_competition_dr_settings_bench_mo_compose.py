"""Marketplace free-before-buy over competition DR + settings add-model pack (pure).

purchase_executed / hosted / pdf_view_authorized always False.
live_dispatch_authorized / remote_fetched / backlog_mutated always False.
secrets_stored / inventory_mutated / live_router_authorized always False.
production_router_verdict always REJECT.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.competition_dr_settings_add_model_bench_source_mo_compose import (
    CompetitionDrSettingsAddModelBenchSourceMoCompose,
    CompetitionDrSettingsAddModelBenchSourceMoComposeError,
    compose_competition_dr_settings_add_model_bench_source_mo,
)
from substrate.marketplace_free_before_buy_html_port_compose import (
    MarketplaceFreeBeforeBuyHtmlPortCompose,
    MarketplaceFreeBeforeBuyHtmlPortComposeError,
    compose_marketplace_free_before_buy_html_port,
)


class MarketplaceFreeCompetitionDrSettingsBenchMoComposeError(ValueError):
    """Fail-closed validation for marketplace free + competition DR pack."""


@dataclass(frozen=True)
class MarketplaceFreeCompetitionDrSettingsBenchMoCompose:
    title: str
    account_id: str
    session_id: str
    week_id: str
    focus_task: str
    parent_asset_id: str
    asset_id: str
    market: MarketplaceFreeBeforeBuyHtmlPortCompose
    competition_pack: CompetitionDrSettingsAddModelBenchSourceMoCompose
    pack_ready: bool
    purchase_executed: bool
    hosted: bool
    pdf_view_authorized: bool
    pdf_primary: bool
    live_dispatch_authorized: bool
    remote_fetched: bool
    backlog_mutated: bool
    secrets_stored: bool
    inventory_mutated: bool
    live_router_authorized: bool
    suite_rewritten: bool
    store_mutated: bool
    live_execution_authorized: bool
    charge_executed: bool
    remote_index_queried: bool
    twin_written: bool
    prompts_injected: bool
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
            "session_id": self.session_id,
            "week_id": self.week_id,
            "focus_task": self.focus_task,
            "parent_asset_id": self.parent_asset_id,
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
            "secrets_stored": False,
            "inventory_mutated": False,
            "live_router_authorized": False,
            "suite_rewritten": False,
            "store_mutated": False,
            "live_execution_authorized": False,
            "charge_executed": False,
            "remote_index_queried": False,
            "twin_written": False,
            "prompts_injected": False,
            "live_dispatched": False,
            "pack_dispatched": False,
            "merge_executed": False,
            "draft_written": False,
            "record_persisted": False,
            "analysis_written": False,
            "production_router_verdict": "REJECT",
            "notes": list(self.notes),
            "authority": (
                "marketplace_free_competition_dr_settings_bench_mo_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MarketplaceFreeCompetitionDrSettingsBenchMoComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_marketplace_free_competition_dr_settings_bench_mo(
    *,
    market: object,
    competition_pack: object,
    operator_ack: object,
    require_both: object | None = None,
) -> MarketplaceFreeCompetitionDrSettingsBenchMoCompose:
    """Free-before-buy on competition DR settings pack. Never purchases/hosts."""
    if not isinstance(operator_ack, bool):
        raise MarketplaceFreeCompetitionDrSettingsBenchMoComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(market, dict):
        raise MarketplaceFreeCompetitionDrSettingsBenchMoComposeError(
            "market must be an object"
        )
    if not isinstance(competition_pack, dict):
        raise MarketplaceFreeCompetitionDrSettingsBenchMoComposeError(
            "competition_pack must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise MarketplaceFreeCompetitionDrSettingsBenchMoComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "purchase_executed=false · hosted=false",
        "pdf_view_authorized=false · pdf_primary=false",
        "live_dispatch_authorized=false · remote_fetched=false · backlog_mutated=false",
        "secrets_stored=false · inventory_mutated=false · live_router_authorized=false",
        "production_router_verdict=REJECT",
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
        raise MarketplaceFreeCompetitionDrSettingsBenchMoComposeError(
            str(e)
        ) from e
    notes.extend(f"[market] {n}" for n in m.notes)

    try:
        cp = compose_competition_dr_settings_add_model_bench_source_mo(
            competition=competition_pack.get("competition"),
            settings_pack=competition_pack.get("settings_pack"),
            operator_ack=operator_ack,
            require_both=competition_pack.get("require_both"),
        )
    except CompetitionDrSettingsAddModelBenchSourceMoComposeError as e:
        raise MarketplaceFreeCompetitionDrSettingsBenchMoComposeError(
            str(e)
        ) from e
    notes.extend(f"[competition_pack] {n}" for n in cp.notes)

    title = _require_nonempty(m.title, field="title")
    account = _require_nonempty(m.account_id, field="account_id")
    session = _require_nonempty(cp.session_id, field="session_id")
    week = _require_nonempty(cp.week_id, field="week_id")
    focus = _require_nonempty(cp.focus_task, field="focus_task")
    parent = _require_nonempty(cp.parent_asset_id, field="parent_asset_id")
    asset = _require_nonempty(cp.asset_id, field="asset_id")

    if require:
        pack_ready = (
            m.port_ready is True
            and cp.pack_ready is True
            and m.purchase_executed is False
            and m.hosted is False
            and m.pdf_view_authorized is False
            and cp.live_dispatch_authorized is False
            and cp.remote_fetched is False
            and cp.backlog_mutated is False
            and cp.inventory_mutated is False
            and cp.secrets_stored is False
            and cp.live_router_authorized is False
            and cp.suite_rewritten is False
            and cp.live_execution_authorized is False
            and cp.purchase_executed is False
            and cp.production_router_verdict == "REJECT"
            and operator_ack is True
        )
    else:
        pack_ready = (
            operator_ack is True
            and m.purchase_executed is False
            and m.hosted is False
            and cp.live_dispatch_authorized is False
            and cp.remote_fetched is False
            and cp.production_router_verdict == "REJECT"
            and (m.port_ready is True or cp.pack_ready is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — marketplace free + competition DR settings bench "
            "MO ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — market, competition_pack, or operator_ack gate open"
        )

    if (
        m.purchase_executed is not False
        or m.hosted is not False
        or m.pdf_view_authorized is not False
        or cp.live_dispatch_authorized is not False
        or cp.remote_fetched is not False
        or cp.backlog_mutated is not False
        or cp.inventory_mutated is not False
        or cp.secrets_stored is not False
        or cp.live_router_authorized is not False
        or cp.suite_rewritten is not False
        or cp.live_execution_authorized is not False
        or cp.purchase_executed is not False
        or cp.production_router_verdict != "REJECT"
    ):
        raise MarketplaceFreeCompetitionDrSettingsBenchMoComposeError(
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
            "secrets_stored=false",
            "inventory_mutated=false",
            "live_router_authorized=false",
            "suite_rewritten=false",
            "store_mutated=false",
            "live_execution_authorized=false",
            "charge_executed=false",
            "remote_index_queried=false",
            "twin_written=false",
            "prompts_injected=false",
            "live_dispatched=false",
            "pack_dispatched=false",
            "merge_executed=false",
            "draft_written=false",
            "record_persisted=false",
            "analysis_written=false",
            "production_router_verdict=REJECT",
        )
    )

    return MarketplaceFreeCompetitionDrSettingsBenchMoCompose(
        title=title,
        account_id=account,
        session_id=session,
        week_id=week,
        focus_task=focus,
        parent_asset_id=parent,
        asset_id=asset,
        market=m,
        competition_pack=cp,
        pack_ready=pack_ready,
        purchase_executed=False,
        hosted=False,
        pdf_view_authorized=False,
        pdf_primary=False,
        live_dispatch_authorized=False,
        remote_fetched=False,
        backlog_mutated=False,
        secrets_stored=False,
        inventory_mutated=False,
        live_router_authorized=False,
        suite_rewritten=False,
        store_mutated=False,
        live_execution_authorized=False,
        charge_executed=False,
        remote_index_queried=False,
        twin_written=False,
        prompts_injected=False,
        live_dispatched=False,
        pack_dispatched=False,
        merge_executed=False,
        draft_written=False,
        record_persisted=False,
        analysis_written=False,
        production_router_verdict="REJECT",
        notes=tuple(notes),
        authority=(
            "marketplace_free_competition_dr_settings_bench_mo_compose_advisory"
        ),
    )


def format_marketplace_free_competition_dr_settings_bench_mo_summary(
    c: MarketplaceFreeCompetitionDrSettingsBenchMoCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"market_path={c.market.path} · port_ready={c.market.port_ready} · "
        f"comp_ready={c.competition_pack.pack_ready} · "
        f"session_aligned={c.competition_pack.session_aligned} · "
        f"week={c.week_id} · task={c.focus_task} · "
        f"verdict={c.production_router_verdict} · "
        "purchase_executed=false · hosted=false · "
        "live_dispatch_authorized=false · inventory_mutated=false"
    )


__all__ = [
    "MarketplaceFreeCompetitionDrSettingsBenchMoCompose",
    "MarketplaceFreeCompetitionDrSettingsBenchMoComposeError",
    "compose_marketplace_free_competition_dr_settings_bench_mo",
    "format_marketplace_free_competition_dr_settings_bench_mo_summary",
]
