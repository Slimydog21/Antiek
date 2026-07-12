"""Antiek-bench weekly learn over recursive twin presentation write collective (pure).

backlog_mutated / store_mutated / suite_rewritten always False.
twin_written / merge_executed / draft_written always False.
live_router_authorized / secrets_stored always False.
production_router_verdict always REJECT.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.antiek_bench_weekly_usage_learn_compose import (
    AntiekBenchWeeklyUsageLearnCompose,
    AntiekBenchWeeklyUsageLearnComposeError,
    compose_antiek_bench_weekly_usage_learn,
)
from substrate.recursive_twin_presentation_write_twin_collective_fullscreen_mo_nd_twin_compose import (
    RecursiveTwinPresentationWriteTwinCollectiveFullscreenMoNdTwinCompose,
    RecursiveTwinPresentationWriteTwinCollectiveFullscreenMoNdTwinComposeError,
    compose_recursive_twin_presentation_write_twin_collective_fullscreen_mo_nd_twin,
)


class AntiekBenchWeeklyLearnRecursiveTwinPresentationWriteCollectiveComposeError(
    ValueError
):
    """Fail-closed validation for weekly learn + twin presentation write collective."""


@dataclass(frozen=True)
class AntiekBenchWeeklyLearnRecursiveTwinPresentationWriteCollectiveCompose:
    week_id: str
    session_id: str
    parent_asset_id: str
    asset_id: str
    title: str
    account_id: str
    weekly_learn: AntiekBenchWeeklyUsageLearnCompose
    twin_presentation_pack: RecursiveTwinPresentationWriteTwinCollectiveFullscreenMoNdTwinCompose
    pack_ready: bool
    learn_ready: bool
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
    pdf_view_authorized: bool
    pdf_primary: bool
    inventory_mutated: bool
    charge_executed: bool
    record_persisted: bool
    purchase_executed: bool
    hosted: bool
    remote_fetched: bool
    live_dispatch_authorized: bool
    production_router_verdict: str
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "week_id": self.week_id,
            "session_id": self.session_id,
            "parent_asset_id": self.parent_asset_id,
            "asset_id": self.asset_id,
            "title": self.title,
            "account_id": self.account_id,
            "weekly_learn": self.weekly_learn.to_dict(),
            "twin_presentation_pack": self.twin_presentation_pack.to_dict(),
            "pack_ready": self.pack_ready,
            "learn_ready": self.learn_ready,
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
            "pdf_view_authorized": False,
            "pdf_primary": False,
            "inventory_mutated": False,
            "charge_executed": False,
            "record_persisted": False,
            "purchase_executed": False,
            "hosted": False,
            "remote_fetched": False,
            "live_dispatch_authorized": False,
            "production_router_verdict": "REJECT",
            "notes": list(self.notes),
            "authority": (
                "antiek_bench_weekly_learn_recursive_twin_presentation_write_collective_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AntiekBenchWeeklyLearnRecursiveTwinPresentationWriteCollectiveComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_antiek_bench_weekly_learn_recursive_twin_presentation_write_collective(
    *,
    weekly_learn: object,
    twin_presentation_pack: object,
    operator_ack: object,
    require_both: object | None = None,
) -> AntiekBenchWeeklyLearnRecursiveTwinPresentationWriteCollectiveCompose:
    """Weekly bench learn + recursive twin presentation write collective. Never mutates bench."""
    if not isinstance(operator_ack, bool):
        raise AntiekBenchWeeklyLearnRecursiveTwinPresentationWriteCollectiveComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(weekly_learn, dict):
        raise AntiekBenchWeeklyLearnRecursiveTwinPresentationWriteCollectiveComposeError(
            "weekly_learn must be an object"
        )
    if not isinstance(twin_presentation_pack, dict):
        raise AntiekBenchWeeklyLearnRecursiveTwinPresentationWriteCollectiveComposeError(
            "twin_presentation_pack must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise AntiekBenchWeeklyLearnRecursiveTwinPresentationWriteCollectiveComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "backlog_mutated=false · store_mutated=false · suite_rewritten=false",
        "twin_written=false · merge_executed=false · draft_written=false",
        "live_router_authorized=false · secrets_stored=false",
        "production_router_verdict=REJECT",
    ]

    try:
        wl = compose_antiek_bench_weekly_usage_learn(
            week_id=weekly_learn.get("week_id"),
            events=weekly_learn.get("events"),
            operator_ack=operator_ack,
            min_events_per_task=weekly_learn.get("min_events_per_task"),
        )
    except AntiekBenchWeeklyUsageLearnComposeError as e:
        raise AntiekBenchWeeklyLearnRecursiveTwinPresentationWriteCollectiveComposeError(
            str(e)
        ) from e
    notes.extend(f"[weekly_learn] {n}" for n in wl.notes)

    try:
        tp = compose_recursive_twin_presentation_write_twin_collective_fullscreen_mo_nd_twin(
            twin=twin_presentation_pack.get("twin"),
            presentation=twin_presentation_pack.get("presentation"),
            write_pack=twin_presentation_pack.get("write_pack"),
            operator_ack=operator_ack,
            require_both=twin_presentation_pack.get("require_both"),
        )
    except RecursiveTwinPresentationWriteTwinCollectiveFullscreenMoNdTwinComposeError as e:
        raise AntiekBenchWeeklyLearnRecursiveTwinPresentationWriteCollectiveComposeError(
            str(e)
        ) from e
    notes.extend(f"[twin_presentation_pack] {n}" for n in tp.notes)

    week = _require_nonempty(wl.week_id, field="week_id")
    session = _require_nonempty(tp.session_id, field="session_id")
    parent = _require_nonempty(tp.parent_asset_id, field="parent_asset_id")
    asset = _require_nonempty(tp.asset_id, field="asset_id")
    title = _require_nonempty(tp.title, field="title")
    account = _require_nonempty(tp.account_id, field="account_id")

    if require:
        pack_ready = (
            wl.learn_ready is True
            and tp.pack_ready is True
            and wl.backlog_mutated is False
            and wl.store_mutated is False
            and tp.twin_written is False
            and tp.merge_executed is False
            and tp.draft_written is False
            and tp.analysis_written is False
            and tp.live_dispatched is False
            and tp.live_execution_authorized is False
            and tp.live_router_authorized is False
            and tp.secrets_stored is False
            and tp.remote_index_queried is False
            and tp.pdf_primary is False
            and tp.production_router_verdict == "REJECT"
            and operator_ack is True
        )
    else:
        pack_ready = (
            operator_ack is True
            and wl.backlog_mutated is False
            and wl.store_mutated is False
            and tp.production_router_verdict == "REJECT"
            and tp.pdf_primary is False
            and tp.twin_written is False
            and (wl.learn_ready is True or tp.pack_ready is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — weekly bench learn + recursive twin presentation write "
            "collective ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — weekly_learn, twin_presentation_pack, or operator_ack gate open"
        )

    if (
        wl.backlog_mutated is not False
        or wl.store_mutated is not False
        or tp.twin_written is not False
        or tp.merge_executed is not False
        or tp.draft_written is not False
        or tp.analysis_written is not False
        or tp.live_dispatched is not False
        or tp.live_execution_authorized is not False
        or tp.live_router_authorized is not False
        or tp.secrets_stored is not False
        or tp.remote_index_queried is not False
        or tp.pdf_primary is not False
        or tp.production_router_verdict != "REJECT"
    ):
        raise AntiekBenchWeeklyLearnRecursiveTwinPresentationWriteCollectiveComposeError(
            "invariant: honesty flags must remain false / REJECT"
        )

    notes.extend(
        (
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
            "pdf_view_authorized=false",
            "pdf_primary=false",
            "inventory_mutated=false",
            "charge_executed=false",
            "record_persisted=false",
            "purchase_executed=false",
            "hosted=false",
            "remote_fetched=false",
            "live_dispatch_authorized=false",
            "production_router_verdict=REJECT",
        )
    )

    return AntiekBenchWeeklyLearnRecursiveTwinPresentationWriteCollectiveCompose(
        week_id=week,
        session_id=session,
        parent_asset_id=parent,
        asset_id=asset,
        title=title,
        account_id=account,
        weekly_learn=wl,
        twin_presentation_pack=tp,
        pack_ready=pack_ready,
        learn_ready=wl.learn_ready,
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
        pdf_view_authorized=False,
        pdf_primary=False,
        inventory_mutated=False,
        charge_executed=False,
        record_persisted=False,
        purchase_executed=False,
        hosted=False,
        remote_fetched=False,
        live_dispatch_authorized=False,
        production_router_verdict="REJECT",
        notes=tuple(notes),
        authority=(
            "antiek_bench_weekly_learn_recursive_twin_presentation_write_collective_compose_advisory"
        ),
    )


def format_antiek_bench_weekly_learn_recursive_twin_presentation_write_collective_summary(
    c: AntiekBenchWeeklyLearnRecursiveTwinPresentationWriteCollectiveCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"learn_ready={c.learn_ready} · "
        f"proposals={c.weekly_learn.proposal_count} · "
        f"twin_presentation_ready={c.twin_presentation_pack.pack_ready} · "
        f"week={c.week_id} · "
        f"verdict={c.production_router_verdict} · "
        "backlog_mutated=false · twin_written=false · suite_rewritten=false"
    )


__all__ = [
    "AntiekBenchWeeklyLearnRecursiveTwinPresentationWriteCollectiveCompose",
    "AntiekBenchWeeklyLearnRecursiveTwinPresentationWriteCollectiveComposeError",
    "compose_antiek_bench_weekly_learn_recursive_twin_presentation_write_collective",
    "format_antiek_bench_weekly_learn_recursive_twin_presentation_write_collective_summary",
]
