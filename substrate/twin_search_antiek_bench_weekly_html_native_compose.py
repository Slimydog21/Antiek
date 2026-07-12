"""Twin intelligent search over Antiek-bench weekly + HTML-native recursive twin (pure).

remote_index_queried always False.
backlog_mutated / store_mutated / suite_rewritten always False.
pdf_view_authorized / pdf_primary always False.
twin_written / secrets_stored / charge_executed always False.
production_router_verdict always REJECT.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.antiek_bench_weekly_html_native_recursive_twin_compose import (
    AntiekBenchWeeklyHtmlNativeRecursiveTwinCompose,
    AntiekBenchWeeklyHtmlNativeRecursiveTwinComposeError,
    compose_antiek_bench_weekly_html_native_recursive_twin,
)
from substrate.recursive_twin_intelligent_search import (
    TwinIntelligentSearchError,
    TwinSearchResult,
    search_twin_substrate,
)


class TwinSearchAntiekBenchWeeklyHtmlNativeComposeError(ValueError):
    """Fail-closed validation for twin search + weekly HTML-native pack."""


@dataclass(frozen=True)
class TwinSearchAntiekBenchWeeklyHtmlNativeCompose:
    week_id: str
    session_id: str
    parent_asset_id: str
    asset_id: str
    search: TwinSearchResult
    weekly_html: AntiekBenchWeeklyHtmlNativeRecursiveTwinCompose
    pack_ready: bool
    hit_count: int
    remote_index_queried: bool
    backlog_mutated: bool
    store_mutated: bool
    suite_rewritten: bool
    pdf_view_authorized: bool
    pdf_primary: bool
    twin_written: bool
    prompts_injected: bool
    live_dispatch_authorized: bool
    secrets_stored: bool
    inventory_mutated: bool
    live_router_authorized: bool
    live_dispatched: bool
    pack_dispatched: bool
    merge_executed: bool
    live_execution_authorized: bool
    charge_executed: bool
    draft_written: bool
    record_persisted: bool
    analysis_written: bool
    production_router_verdict: str
    purchase_executed: bool
    hosted: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "week_id": self.week_id,
            "session_id": self.session_id,
            "parent_asset_id": self.parent_asset_id,
            "asset_id": self.asset_id,
            "search": self.search.to_dict(),
            "weekly_html": self.weekly_html.to_dict(),
            "pack_ready": self.pack_ready,
            "hit_count": self.hit_count,
            "remote_index_queried": False,
            "backlog_mutated": False,
            "store_mutated": False,
            "suite_rewritten": False,
            "pdf_view_authorized": False,
            "pdf_primary": False,
            "twin_written": False,
            "prompts_injected": False,
            "live_dispatch_authorized": False,
            "secrets_stored": False,
            "inventory_mutated": False,
            "live_router_authorized": False,
            "live_dispatched": False,
            "pack_dispatched": False,
            "merge_executed": False,
            "live_execution_authorized": False,
            "charge_executed": False,
            "draft_written": False,
            "record_persisted": False,
            "analysis_written": False,
            "production_router_verdict": "REJECT",
            "purchase_executed": False,
            "hosted": False,
            "notes": list(self.notes),
            "authority": (
                "twin_search_antiek_bench_weekly_html_native_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TwinSearchAntiekBenchWeeklyHtmlNativeComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_twin_search_antiek_bench_weekly_html_native(
    *,
    search_query: object,
    twin_records: object,
    weekly_html: object,
    operator_ack: object,
    search_limit: object | None = None,
    require_both: object | None = None,
) -> TwinSearchAntiekBenchWeeklyHtmlNativeCompose:
    """Twin search + weekly HTML-native recursive twin. Never remote-indexes."""
    if not isinstance(operator_ack, bool):
        raise TwinSearchAntiekBenchWeeklyHtmlNativeComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(weekly_html, dict):
        raise TwinSearchAntiekBenchWeeklyHtmlNativeComposeError(
            "weekly_html must be an object"
        )
    if not isinstance(twin_records, list):
        raise TwinSearchAntiekBenchWeeklyHtmlNativeComposeError(
            "twin_records must be an array"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise TwinSearchAntiekBenchWeeklyHtmlNativeComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "remote_index_queried=false — pure substrate scan only",
        "backlog_mutated=false · store_mutated=false · suite_rewritten=false",
        "pdf_view_authorized=false · pdf_primary=false",
        "twin_written=false · secrets_stored=false · charge_executed=false",
        "production_router_verdict=REJECT",
    ]

    try:
        search = search_twin_substrate(
            query=search_query,
            records=twin_records,
            limit=20 if search_limit is None else search_limit,
        )
    except TwinIntelligentSearchError as e:
        raise TwinSearchAntiekBenchWeeklyHtmlNativeComposeError(str(e)) from e
    notes.extend(f"[search] {n}" for n in search.notes)

    try:
        wh = compose_antiek_bench_weekly_html_native_recursive_twin(
            weekly_learn=weekly_html.get("weekly_learn"),
            html_pack=weekly_html.get("html_pack"),
            operator_ack=operator_ack,
            require_both=weekly_html.get("require_both"),
        )
    except AntiekBenchWeeklyHtmlNativeRecursiveTwinComposeError as e:
        raise TwinSearchAntiekBenchWeeklyHtmlNativeComposeError(str(e)) from e
    notes.extend(f"[weekly_html] {n}" for n in wh.notes)

    week = _require_nonempty(wh.week_id, field="week_id")
    session = _require_nonempty(wh.session_id, field="session_id")
    asset = _require_nonempty(wh.asset_id, field="asset_id")
    parent = _require_nonempty(wh.parent_asset_id, field="parent_asset_id")
    hit_count = len(search.hits)

    if require:
        pack_ready = (
            hit_count >= 1
            and wh.pack_ready is True
            and search.remote_index_queried is False
            and wh.backlog_mutated is False
            and wh.store_mutated is False
            and wh.suite_rewritten is False
            and wh.production_router_verdict == "REJECT"
            and wh.pdf_view_authorized is False
            and wh.pdf_primary is False
            and wh.twin_written is False
            and wh.secrets_stored is False
            and wh.charge_executed is False
            and operator_ack is True
        )
    else:
        pack_ready = (
            operator_ack is True
            and search.remote_index_queried is False
            and wh.production_router_verdict == "REJECT"
            and wh.pdf_primary is False
            and (hit_count >= 1 or wh.pack_ready is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — twin search + weekly HTML-native recursive twin "
            "ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — search hits, weekly_html, or operator_ack gate open"
        )

    if (
        search.remote_index_queried is not False
        or wh.backlog_mutated is not False
        or wh.store_mutated is not False
        or wh.suite_rewritten is not False
        or wh.pdf_view_authorized is not False
        or wh.pdf_primary is not False
        or wh.twin_written is not False
        or wh.secrets_stored is not False
        or wh.charge_executed is not False
        or wh.production_router_verdict != "REJECT"
    ):
        raise TwinSearchAntiekBenchWeeklyHtmlNativeComposeError(
            "invariant: honesty flags must remain false"
        )

    notes.extend(
        (
            "remote_index_queried=false",
            "backlog_mutated=false",
            "store_mutated=false",
            "suite_rewritten=false",
            "pdf_view_authorized=false",
            "pdf_primary=false",
            "twin_written=false",
            "prompts_injected=false",
            "live_dispatch_authorized=false",
            "secrets_stored=false",
            "inventory_mutated=false",
            "live_router_authorized=false",
            "live_dispatched=false",
            "pack_dispatched=false",
            "merge_executed=false",
            "live_execution_authorized=false",
            "charge_executed=false",
            "draft_written=false",
            "record_persisted=false",
            "analysis_written=false",
            "production_router_verdict=REJECT",
            "purchase_executed=false",
            "hosted=false",
        )
    )

    return TwinSearchAntiekBenchWeeklyHtmlNativeCompose(
        week_id=week,
        session_id=session,
        parent_asset_id=parent,
        asset_id=asset,
        search=search,
        weekly_html=wh,
        pack_ready=pack_ready,
        hit_count=hit_count,
        remote_index_queried=False,
        backlog_mutated=False,
        store_mutated=False,
        suite_rewritten=False,
        pdf_view_authorized=False,
        pdf_primary=False,
        twin_written=False,
        prompts_injected=False,
        live_dispatch_authorized=False,
        secrets_stored=False,
        inventory_mutated=False,
        live_router_authorized=False,
        live_dispatched=False,
        pack_dispatched=False,
        merge_executed=False,
        live_execution_authorized=False,
        charge_executed=False,
        draft_written=False,
        record_persisted=False,
        analysis_written=False,
        production_router_verdict="REJECT",
        purchase_executed=False,
        hosted=False,
        notes=tuple(notes),
        authority=(
            "twin_search_antiek_bench_weekly_html_native_compose_advisory"
        ),
    )


def format_twin_search_antiek_bench_weekly_html_native_summary(
    c: TwinSearchAntiekBenchWeeklyHtmlNativeCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"hits={c.hit_count} · "
        f"weekly_ready={c.weekly_html.pack_ready} · "
        f"week={c.week_id} · "
        f"verdict={c.production_router_verdict} · "
        f"remote_index_queried=false · suite_rewritten=false · pdf_primary=false"
    )


__all__ = [
    "TwinSearchAntiekBenchWeeklyHtmlNativeCompose",
    "TwinSearchAntiekBenchWeeklyHtmlNativeComposeError",
    "compose_twin_search_antiek_bench_weekly_html_native",
    "format_twin_search_antiek_bench_weekly_html_native_summary",
]
