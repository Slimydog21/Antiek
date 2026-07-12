"""Floating fullscreen-open + Antiek-bench weekly ND multi-select pack (pure).

live_dispatched / merge_executed / pack_dispatched always False.
backlog_mutated / store_mutated always False.
production_router_verdict always REJECT; live_router_authorized always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.antiek_bench_weekly_nd_multiselect_mo_compose import (
    AntiekBenchWeeklyNdMultiselectMoCompose,
    AntiekBenchWeeklyNdMultiselectMoComposeError,
    compose_antiek_bench_weekly_nd_multiselect_mo,
)
from substrate.floating_fullscreen_open_compose import (
    FloatingFullscreenOpenCompose,
    FloatingFullscreenOpenComposeError,
    compose_floating_fullscreen_open,
)


class FloatingFullscreenAntiekBenchWeeklyNdMoComposeError(ValueError):
    """Fail-closed validation for fullscreen + weekly ND multi-select pack."""


@dataclass(frozen=True)
class FloatingFullscreenAntiekBenchWeeklyNdMoCompose:
    session_id: str
    parent_asset_id: str
    week_id: str
    fullscreen: FloatingFullscreenOpenCompose
    weekly_nd: AntiekBenchWeeklyNdMultiselectMoCompose
    pack_ready: bool
    live_dispatched: bool
    merge_executed: bool
    pack_dispatched: bool
    backlog_mutated: bool
    store_mutated: bool
    production_router_verdict: str
    live_router_authorized: bool
    purchase_executed: bool
    twin_written: bool
    live_execution_authorized: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "parent_asset_id": self.parent_asset_id,
            "week_id": self.week_id,
            "fullscreen": self.fullscreen.to_dict(),
            "weekly_nd": self.weekly_nd.to_dict(),
            "pack_ready": self.pack_ready,
            "live_dispatched": False,
            "merge_executed": False,
            "pack_dispatched": False,
            "backlog_mutated": False,
            "store_mutated": False,
            "production_router_verdict": "REJECT",
            "live_router_authorized": False,
            "purchase_executed": False,
            "twin_written": False,
            "live_execution_authorized": False,
            "notes": list(self.notes),
            "authority": (
                "floating_fullscreen_antiek_bench_weekly_nd_mo_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FloatingFullscreenAntiekBenchWeeklyNdMoComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_floating_fullscreen_antiek_bench_weekly_nd_mo(
    *,
    fullscreen: object,
    weekly_nd: object,
    operator_ack: object,
    require_both: object | None = None,
) -> FloatingFullscreenAntiekBenchWeeklyNdMoCompose:
    """Fullscreen float + weekly ND multi-select. Never live-dispatches."""
    if not isinstance(operator_ack, bool):
        raise FloatingFullscreenAntiekBenchWeeklyNdMoComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(fullscreen, dict):
        raise FloatingFullscreenAntiekBenchWeeklyNdMoComposeError(
            "fullscreen must be an object"
        )
    if not isinstance(weekly_nd, dict):
        raise FloatingFullscreenAntiekBenchWeeklyNdMoComposeError(
            "weekly_nd must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise FloatingFullscreenAntiekBenchWeeklyNdMoComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "live_dispatched=false · merge_executed=false · pack_dispatched=false",
        "backlog_mutated=false · store_mutated=false",
        "production_router_verdict=REJECT · live_router_authorized=false",
        "purchase_executed=false · twin_written=false · live_execution_authorized=false",
    ]

    try:
        fs = compose_floating_fullscreen_open(
            session_id=fullscreen.get("session_id"),
            parent_asset_id=fullscreen.get("parent_asset_id"),
            operator_ack=operator_ack,
            existing_instance=fullscreen.get("existing_instance"),
            highlight=fullscreen.get("highlight"),
            prompt=fullscreen.get("prompt"),
            gated=fullscreen.get("gated"),
            tray_siblings=fullscreen.get("tray_siblings"),
        )
    except FloatingFullscreenOpenComposeError as e:
        raise FloatingFullscreenAntiekBenchWeeklyNdMoComposeError(
            str(e)
        ) from e
    notes.extend(f"[fullscreen] {n}" for n in fs.notes)

    try:
        wn = compose_antiek_bench_weekly_nd_multiselect_mo(
            weekly_learn=weekly_nd.get("weekly_learn"),
            nd_research=weekly_nd.get("nd_research"),
            operator_ack=operator_ack,
            require_both=weekly_nd.get("require_both"),
        )
    except AntiekBenchWeeklyNdMultiselectMoComposeError as e:
        raise FloatingFullscreenAntiekBenchWeeklyNdMoComposeError(
            str(e)
        ) from e
    notes.extend(f"[weekly_nd] {n}" for n in wn.notes)

    session = _require_nonempty(fs.session_id, field="session_id")
    parent = _require_nonempty(fs.parent_asset_id, field="parent_asset_id")
    week = _require_nonempty(wn.week_id, field="week_id")

    if require:
        pack_ready = (
            fs.fullscreen_ready is True
            and wn.pack_ready is True
            and wn.production_router_verdict == "REJECT"
            and operator_ack is True
        )
    else:
        pack_ready = (
            operator_ack is True
            and wn.production_router_verdict == "REJECT"
            and (fs.fullscreen_ready is True or wn.pack_ready is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — fullscreen float + weekly ND multi-select ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — fullscreen, weekly_nd, or operator_ack gate open"
        )

    if (
        fs.live_dispatched is not False
        or fs.merge_executed is not False
        or fs.pack_dispatched is not False
        or wn.backlog_mutated is not False
        or wn.store_mutated is not False
        or wn.production_router_verdict != "REJECT"
        or wn.live_router_authorized is not False
        or wn.live_dispatched is not False
        or wn.live_execution_authorized is not False
    ):
        raise FloatingFullscreenAntiekBenchWeeklyNdMoComposeError(
            "invariant: honesty flags must remain false"
        )

    notes.extend(
        (
            "live_dispatched=false",
            "merge_executed=false",
            "pack_dispatched=false",
            "backlog_mutated=false",
            "store_mutated=false",
            "production_router_verdict=REJECT",
            "live_router_authorized=false",
            "purchase_executed=false",
            "twin_written=false",
            "live_execution_authorized=false",
        )
    )

    return FloatingFullscreenAntiekBenchWeeklyNdMoCompose(
        session_id=session,
        parent_asset_id=parent,
        week_id=week,
        fullscreen=fs,
        weekly_nd=wn,
        pack_ready=pack_ready,
        live_dispatched=False,
        merge_executed=False,
        pack_dispatched=False,
        backlog_mutated=False,
        store_mutated=False,
        production_router_verdict="REJECT",
        live_router_authorized=False,
        purchase_executed=False,
        twin_written=False,
        live_execution_authorized=False,
        notes=tuple(notes),
        authority=(
            "floating_fullscreen_antiek_bench_weekly_nd_mo_compose_advisory"
        ),
    )


def format_floating_fullscreen_antiek_bench_weekly_nd_mo_summary(
    c: FloatingFullscreenAntiekBenchWeeklyNdMoCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"fullscreen_ready={c.fullscreen.fullscreen_ready} · "
        f"weekly_nd_ready={c.weekly_nd.pack_ready} · "
        f"proposals={c.weekly_nd.weekly_learn.proposal_count} · "
        f"verdict={c.production_router_verdict} · "
        f"live_dispatched=false · backlog_mutated=false · live_router_authorized=false"
    )


__all__ = [
    "FloatingFullscreenAntiekBenchWeeklyNdMoCompose",
    "FloatingFullscreenAntiekBenchWeeklyNdMoComposeError",
    "compose_floating_fullscreen_antiek_bench_weekly_nd_mo",
    "format_floating_fullscreen_antiek_bench_weekly_nd_mo_summary",
]
