"""Antiek-bench weekly learn + marketplace free source-attach pack (pure).

backlog_mutated / store_mutated always False.
purchase_executed / hosted / remote_fetched always False.
production_router_verdict always REJECT; live_router_authorized always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.antiek_bench_weekly_usage_learn_compose import (
    AntiekBenchWeeklyUsageLearnCompose,
    AntiekBenchWeeklyUsageLearnComposeError,
    compose_antiek_bench_weekly_usage_learn,
)
from substrate.marketplace_free_source_attach_record_prompt_compose import (
    MarketplaceFreeSourceAttachRecordPromptCompose,
    MarketplaceFreeSourceAttachRecordPromptComposeError,
    compose_marketplace_free_source_attach_record_prompt,
)


class AntiekBenchWeeklyMarketplaceFreeSourceComposeError(ValueError):
    """Fail-closed validation for weekly learn + marketplace free source pack."""


@dataclass(frozen=True)
class AntiekBenchWeeklyMarketplaceFreeSourceCompose:
    week_id: str
    session_id: str
    parent_asset_id: str
    weekly_learn: AntiekBenchWeeklyUsageLearnCompose
    market_research: MarketplaceFreeSourceAttachRecordPromptCompose
    pack_ready: bool
    backlog_mutated: bool
    store_mutated: bool
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
    production_router_verdict: str
    live_router_authorized: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "week_id": self.week_id,
            "session_id": self.session_id,
            "parent_asset_id": self.parent_asset_id,
            "weekly_learn": self.weekly_learn.to_dict(),
            "market_research": self.market_research.to_dict(),
            "pack_ready": self.pack_ready,
            "backlog_mutated": False,
            "store_mutated": False,
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
            "production_router_verdict": "REJECT",
            "live_router_authorized": False,
            "notes": list(self.notes),
            "authority": (
                "antiek_bench_weekly_marketplace_free_source_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AntiekBenchWeeklyMarketplaceFreeSourceComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_antiek_bench_weekly_marketplace_free_source(
    *,
    weekly_learn: object,
    market_research: object,
    operator_ack: object,
    require_both: object | None = None,
) -> AntiekBenchWeeklyMarketplaceFreeSourceCompose:
    """Weekly bench learn + marketplace free source pack. Never mutates store."""
    if not isinstance(operator_ack, bool):
        raise AntiekBenchWeeklyMarketplaceFreeSourceComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(weekly_learn, dict):
        raise AntiekBenchWeeklyMarketplaceFreeSourceComposeError(
            "weekly_learn must be an object"
        )
    if not isinstance(market_research, dict):
        raise AntiekBenchWeeklyMarketplaceFreeSourceComposeError(
            "market_research must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise AntiekBenchWeeklyMarketplaceFreeSourceComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "backlog_mutated=false · store_mutated=false",
        "purchase_executed=false · hosted=false · remote_fetched=false",
        "production_router_verdict=REJECT · live_router_authorized=false",
    ]

    try:
        wl = compose_antiek_bench_weekly_usage_learn(
            week_id=weekly_learn.get("week_id"),
            events=weekly_learn.get("events"),
            operator_ack=operator_ack,
            min_events_per_task=weekly_learn.get("min_events_per_task"),
        )
    except AntiekBenchWeeklyUsageLearnComposeError as e:
        raise AntiekBenchWeeklyMarketplaceFreeSourceComposeError(
            str(e)
        ) from e
    notes.extend(f"[weekly_learn] {n}" for n in wl.notes)

    try:
        mr = compose_marketplace_free_source_attach_record_prompt(
            market=market_research.get("market"),
            research=market_research.get("research"),
            operator_ack=operator_ack,
            require_both=market_research.get("require_both"),
        )
    except MarketplaceFreeSourceAttachRecordPromptComposeError as e:
        raise AntiekBenchWeeklyMarketplaceFreeSourceComposeError(
            str(e)
        ) from e
    notes.extend(f"[market_research] {n}" for n in mr.notes)

    week = _require_nonempty(wl.week_id, field="week_id")
    session = _require_nonempty(mr.session_id, field="session_id")
    parent = _require_nonempty(mr.parent_asset_id, field="parent_asset_id")

    if require:
        pack_ready = (
            wl.learn_ready is True
            and mr.pack_ready is True
            and mr.production_router_verdict == "REJECT"
            and wl.backlog_mutated is False
            and wl.store_mutated is False
            and mr.purchase_executed is False
            and mr.hosted is False
            and operator_ack is True
        )
    else:
        pack_ready = (
            operator_ack is True
            and mr.production_router_verdict == "REJECT"
            and wl.store_mutated is False
            and (wl.learn_ready is True or mr.pack_ready is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — weekly bench learn + marketplace free source pack ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — weekly_learn, market_research, or operator_ack gate open"
        )

    if (
        wl.backlog_mutated is not False
        or wl.store_mutated is not False
        or mr.purchase_executed is not False
        or mr.hosted is not False
        or mr.remote_fetched is not False
        or mr.production_router_verdict != "REJECT"
        or mr.live_router_authorized is not False
    ):
        raise AntiekBenchWeeklyMarketplaceFreeSourceComposeError(
            "invariant: honesty flags must remain false"
        )

    notes.extend(
        (
            "backlog_mutated=false",
            "store_mutated=false",
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
            "production_router_verdict=REJECT",
            "live_router_authorized=false",
        )
    )

    return AntiekBenchWeeklyMarketplaceFreeSourceCompose(
        week_id=week,
        session_id=session,
        parent_asset_id=parent,
        weekly_learn=wl,
        market_research=mr,
        pack_ready=pack_ready,
        backlog_mutated=False,
        store_mutated=False,
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
        production_router_verdict="REJECT",
        live_router_authorized=False,
        notes=tuple(notes),
        authority=(
            "antiek_bench_weekly_marketplace_free_source_compose_advisory"
        ),
    )


def format_antiek_bench_weekly_marketplace_free_source_summary(
    c: AntiekBenchWeeklyMarketplaceFreeSourceCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"learn_ready={c.weekly_learn.learn_ready} · "
        f"proposals={c.weekly_learn.proposal_count} · "
        f"market_research_ready={c.market_research.pack_ready} · "
        f"verdict={c.production_router_verdict} · "
        f"backlog_mutated=false · store_mutated=false · purchase_executed=false"
    )


__all__ = [
    "AntiekBenchWeeklyMarketplaceFreeSourceCompose",
    "AntiekBenchWeeklyMarketplaceFreeSourceComposeError",
    "compose_antiek_bench_weekly_marketplace_free_source",
    "format_antiek_bench_weekly_marketplace_free_source_summary",
]
