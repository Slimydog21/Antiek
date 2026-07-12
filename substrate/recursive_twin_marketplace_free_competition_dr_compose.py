"""Recursive twin note-taker over marketplace free + competition DR pack (pure).

twin_written / prompts_injected / live_dispatch_authorized always False.
purchase_executed / hosted always False.
secrets_stored / inventory_mutated / live_router_authorized always False.
production_router_verdict always REJECT.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.marketplace_free_competition_dr_settings_bench_mo_compose import (
    MarketplaceFreeCompetitionDrSettingsBenchMoCompose,
    MarketplaceFreeCompetitionDrSettingsBenchMoComposeError,
    compose_marketplace_free_competition_dr_settings_bench_mo,
)
from substrate.recursive_twin_note_taker_compose import (
    RecursiveTwinNoteTakerCompose,
    RecursiveTwinNoteTakerComposeError,
    compose_recursive_twin_note_taker,
)


class RecursiveTwinMarketplaceFreeCompetitionDrComposeError(ValueError):
    """Fail-closed validation for recursive twin + marketplace free pack."""


@dataclass(frozen=True)
class RecursiveTwinMarketplaceFreeCompetitionDrCompose:
    session_id: str
    parent_asset_id: str
    title: str
    account_id: str
    week_id: str
    focus_task: str
    asset_id: str
    twin: RecursiveTwinNoteTakerCompose
    market_pack: MarketplaceFreeCompetitionDrSettingsBenchMoCompose
    parent_aligned: bool
    pack_ready: bool
    twin_written: bool
    prompts_injected: bool
    live_dispatch_authorized: bool
    purchase_executed: bool
    hosted: bool
    pdf_view_authorized: bool
    pdf_primary: bool
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
            "session_id": self.session_id,
            "parent_asset_id": self.parent_asset_id,
            "title": self.title,
            "account_id": self.account_id,
            "week_id": self.week_id,
            "focus_task": self.focus_task,
            "asset_id": self.asset_id,
            "twin": self.twin.to_dict(),
            "market_pack": self.market_pack.to_dict(),
            "parent_aligned": self.parent_aligned,
            "pack_ready": self.pack_ready,
            "twin_written": False,
            "prompts_injected": False,
            "live_dispatch_authorized": False,
            "purchase_executed": False,
            "hosted": False,
            "pdf_view_authorized": False,
            "pdf_primary": False,
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
            "live_dispatched": False,
            "pack_dispatched": False,
            "merge_executed": False,
            "draft_written": False,
            "record_persisted": False,
            "analysis_written": False,
            "production_router_verdict": "REJECT",
            "notes": list(self.notes),
            "authority": (
                "recursive_twin_marketplace_free_competition_dr_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RecursiveTwinMarketplaceFreeCompetitionDrComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_recursive_twin_marketplace_free_competition_dr(
    *,
    twin: object,
    market_pack: object,
    operator_ack: object,
    require_both: object | None = None,
) -> RecursiveTwinMarketplaceFreeCompetitionDrCompose:
    """Recursive twin on marketplace free competition pack. Never writes/dispatches."""
    if not isinstance(operator_ack, bool):
        raise RecursiveTwinMarketplaceFreeCompetitionDrComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(twin, dict):
        raise RecursiveTwinMarketplaceFreeCompetitionDrComposeError(
            "twin must be an object"
        )
    if not isinstance(market_pack, dict):
        raise RecursiveTwinMarketplaceFreeCompetitionDrComposeError(
            "market_pack must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise RecursiveTwinMarketplaceFreeCompetitionDrComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "twin_written=false — twin document not created/updated",
        "prompts_injected=false — no live LLM note-taker prompt injection",
        "live_dispatch_authorized=false — no automatic twin agent dispatch",
        "purchase_executed=false · hosted=false",
        "production_router_verdict=REJECT",
    ]

    try:
        t = compose_recursive_twin_note_taker(
            parent_asset_id=twin.get("parent_asset_id"),
            source_excerpt=twin.get("source_excerpt"),
            operator_ack=operator_ack,
            existing_twin_asset_id=twin.get("existing_twin_asset_id"),
            focus_questions=twin.get("focus_questions"),
        )
    except RecursiveTwinNoteTakerComposeError as e:
        raise RecursiveTwinMarketplaceFreeCompetitionDrComposeError(
            str(e)
        ) from e
    notes.extend(f"[twin] {n}" for n in t.notes)

    try:
        mp = compose_marketplace_free_competition_dr_settings_bench_mo(
            market=market_pack.get("market"),
            competition_pack=market_pack.get("competition_pack"),
            operator_ack=operator_ack,
            require_both=market_pack.get("require_both"),
        )
    except MarketplaceFreeCompetitionDrSettingsBenchMoComposeError as e:
        raise RecursiveTwinMarketplaceFreeCompetitionDrComposeError(
            str(e)
        ) from e
    notes.extend(f"[market_pack] {n}" for n in mp.notes)

    parent = _require_nonempty(t.parent_asset_id, field="parent_asset_id")
    session = _require_nonempty(mp.session_id, field="session_id")
    title = _require_nonempty(mp.title, field="title")
    account = _require_nonempty(mp.account_id, field="account_id")
    week = _require_nonempty(mp.week_id, field="week_id")
    focus = _require_nonempty(mp.focus_task, field="focus_task")
    asset = _require_nonempty(mp.asset_id, field="asset_id")
    market_parent = _require_nonempty(
        mp.parent_asset_id, field="market_pack.parent_asset_id"
    )

    parent_aligned = parent == market_parent
    if not parent_aligned:
        notes.append(
            f"parent_aligned=false — twin.parent={parent} "
            f"market_pack.parent={market_parent}"
        )
    else:
        notes.append("parent_aligned=true")

    if require:
        pack_ready = (
            t.twin_propose_ready is True
            and mp.pack_ready is True
            and parent_aligned is True
            and t.twin_written is False
            and t.prompts_injected is False
            and t.live_dispatch_authorized is False
            and mp.purchase_executed is False
            and mp.hosted is False
            and mp.pdf_view_authorized is False
            and mp.live_dispatch_authorized is False
            and mp.remote_fetched is False
            and mp.backlog_mutated is False
            and mp.inventory_mutated is False
            and mp.secrets_stored is False
            and mp.live_router_authorized is False
            and mp.suite_rewritten is False
            and mp.live_execution_authorized is False
            and mp.production_router_verdict == "REJECT"
            and operator_ack is True
        )
    else:
        pack_ready = (
            operator_ack is True
            and t.twin_written is False
            and t.prompts_injected is False
            and t.live_dispatch_authorized is False
            and mp.purchase_executed is False
            and mp.hosted is False
            and mp.production_router_verdict == "REJECT"
            and (t.twin_propose_ready is True or mp.pack_ready is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — recursive twin + marketplace free competition DR "
            "ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — twin, market_pack, parent align, or operator_ack "
            "gate open"
        )

    if (
        t.twin_written is not False
        or t.prompts_injected is not False
        or t.live_dispatch_authorized is not False
        or mp.purchase_executed is not False
        or mp.hosted is not False
        or mp.pdf_view_authorized is not False
        or mp.live_dispatch_authorized is not False
        or mp.remote_fetched is not False
        or mp.backlog_mutated is not False
        or mp.inventory_mutated is not False
        or mp.secrets_stored is not False
        or mp.live_router_authorized is not False
        or mp.suite_rewritten is not False
        or mp.live_execution_authorized is not False
        or mp.production_router_verdict != "REJECT"
    ):
        raise RecursiveTwinMarketplaceFreeCompetitionDrComposeError(
            "invariant: honesty flags must remain false / REJECT"
        )

    notes.extend(
        (
            "twin_written=false",
            "prompts_injected=false",
            "live_dispatch_authorized=false",
            "purchase_executed=false",
            "hosted=false",
            "pdf_view_authorized=false",
            "pdf_primary=false",
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
            "live_dispatched=false",
            "pack_dispatched=false",
            "merge_executed=false",
            "draft_written=false",
            "record_persisted=false",
            "analysis_written=false",
            "production_router_verdict=REJECT",
        )
    )

    return RecursiveTwinMarketplaceFreeCompetitionDrCompose(
        session_id=session,
        parent_asset_id=parent,
        title=title,
        account_id=account,
        week_id=week,
        focus_task=focus,
        asset_id=asset,
        twin=t,
        market_pack=mp,
        parent_aligned=parent_aligned,
        pack_ready=pack_ready,
        twin_written=False,
        prompts_injected=False,
        live_dispatch_authorized=False,
        purchase_executed=False,
        hosted=False,
        pdf_view_authorized=False,
        pdf_primary=False,
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
        live_dispatched=False,
        pack_dispatched=False,
        merge_executed=False,
        draft_written=False,
        record_persisted=False,
        analysis_written=False,
        production_router_verdict="REJECT",
        notes=tuple(notes),
        authority=(
            "recursive_twin_marketplace_free_competition_dr_compose_advisory"
        ),
    )


def format_recursive_twin_marketplace_free_competition_dr_summary(
    c: RecursiveTwinMarketplaceFreeCompetitionDrCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"twin_propose={c.twin.twin_propose_ready} · "
        f"market_ready={c.market_pack.pack_ready} · "
        f"parent_aligned={c.parent_aligned} · "
        f"week={c.week_id} · task={c.focus_task} · "
        f"verdict={c.production_router_verdict} · "
        "twin_written=false · purchase_executed=false · hosted=false · "
        "live_dispatch_authorized=false"
    )


__all__ = [
    "RecursiveTwinMarketplaceFreeCompetitionDrCompose",
    "RecursiveTwinMarketplaceFreeCompetitionDrComposeError",
    "compose_recursive_twin_marketplace_free_competition_dr",
    "format_recursive_twin_marketplace_free_competition_dr_summary",
]
