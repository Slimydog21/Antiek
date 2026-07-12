"""Draft-before-full-merge + floating fullscreen weekly ND MO pack (pure).

draft_written / merge_executed / live_dispatched / pack_dispatched always False.
backlog_mutated / store_mutated always False.
production_router_verdict always REJECT; live_router_authorized always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.floating_draft_before_full_merge_gate_compose import (
    FloatingDraftBeforeFullMergeGateCompose,
    FloatingDraftBeforeFullMergeGateComposeError,
    compose_floating_draft_before_full_merge_gate,
)
from substrate.floating_fullscreen_antiek_bench_weekly_nd_mo_compose import (
    FloatingFullscreenAntiekBenchWeeklyNdMoCompose,
    FloatingFullscreenAntiekBenchWeeklyNdMoComposeError,
    compose_floating_fullscreen_antiek_bench_weekly_nd_mo,
)


class FloatingDraftBeforeFullMergeFullscreenWeeklyNdMoComposeError(ValueError):
    """Fail-closed validation for draft-before-merge + fullscreen weekly ND pack."""


@dataclass(frozen=True)
class FloatingDraftBeforeFullMergeFullscreenWeeklyNdMoCompose:
    session_id: str
    parent_asset_id: str
    week_id: str
    draft_gate: FloatingDraftBeforeFullMergeGateCompose
    fullscreen_pack: FloatingFullscreenAntiekBenchWeeklyNdMoCompose
    pack_ready: bool
    draft_written: bool
    merge_executed: bool
    live_dispatched: bool
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
            "draft_gate": self.draft_gate.to_dict(),
            "fullscreen_pack": self.fullscreen_pack.to_dict(),
            "pack_ready": self.pack_ready,
            "draft_written": False,
            "merge_executed": False,
            "live_dispatched": False,
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
                "floating_draft_before_full_merge_fullscreen_weekly_nd_mo_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FloatingDraftBeforeFullMergeFullscreenWeeklyNdMoComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_floating_draft_before_full_merge_fullscreen_weekly_nd_mo(
    *,
    draft_gate: object,
    fullscreen_pack: object,
    operator_ack: object,
    require_both: object | None = None,
) -> FloatingDraftBeforeFullMergeFullscreenWeeklyNdMoCompose:
    """Draft-before-merge + fullscreen weekly ND pack. Never writes or merges."""
    if not isinstance(operator_ack, bool):
        raise FloatingDraftBeforeFullMergeFullscreenWeeklyNdMoComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(draft_gate, dict):
        raise FloatingDraftBeforeFullMergeFullscreenWeeklyNdMoComposeError(
            "draft_gate must be an object"
        )
    if not isinstance(fullscreen_pack, dict):
        raise FloatingDraftBeforeFullMergeFullscreenWeeklyNdMoComposeError(
            "fullscreen_pack must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise FloatingDraftBeforeFullMergeFullscreenWeeklyNdMoComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "draft_written=false · merge_executed=false · live_dispatched=false · pack_dispatched=false",
        "backlog_mutated=false · store_mutated=false",
        "production_router_verdict=REJECT · live_router_authorized=false",
        "purchase_executed=false · twin_written=false · live_execution_authorized=false",
    ]

    try:
        dg = compose_floating_draft_before_full_merge_gate(
            session_id=draft_gate.get("session_id"),
            parent_asset_id=draft_gate.get("parent_asset_id"),
            sources=draft_gate.get("sources"),
            stage=draft_gate.get("stage"),
            operator_ack=operator_ack,
            parent_excerpt=draft_gate.get("parent_excerpt"),
            full_merge_ack=draft_gate.get("full_merge_ack"),
        )
    except FloatingDraftBeforeFullMergeGateComposeError as e:
        raise FloatingDraftBeforeFullMergeFullscreenWeeklyNdMoComposeError(
            str(e)
        ) from e
    notes.extend(f"[draft_gate] {n}" for n in dg.notes)

    try:
        fp = compose_floating_fullscreen_antiek_bench_weekly_nd_mo(
            fullscreen=fullscreen_pack.get("fullscreen"),
            weekly_nd=fullscreen_pack.get("weekly_nd"),
            operator_ack=operator_ack,
            require_both=fullscreen_pack.get("require_both"),
        )
    except FloatingFullscreenAntiekBenchWeeklyNdMoComposeError as e:
        raise FloatingDraftBeforeFullMergeFullscreenWeeklyNdMoComposeError(
            str(e)
        ) from e
    notes.extend(f"[fullscreen_pack] {n}" for n in fp.notes)

    session = _require_nonempty(dg.session_id, field="session_id")
    parent = _require_nonempty(dg.parent_asset_id, field="parent_asset_id")
    week = _require_nonempty(fp.week_id, field="week_id")

    aligned = fp.session_id == session and fp.parent_asset_id == parent
    if not aligned:
        notes.append(
            "session/parent mismatch between draft_gate and fullscreen_pack — pack_ready blocked"
        )

    if require:
        pack_ready = (
            aligned
            and dg.gate_ready is True
            and fp.pack_ready is True
            and fp.production_router_verdict == "REJECT"
            and operator_ack is True
        )
    else:
        pack_ready = (
            aligned
            and operator_ack is True
            and fp.production_router_verdict == "REJECT"
            and (dg.gate_ready is True or fp.pack_ready is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — draft-before-merge + fullscreen weekly ND pack ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — draft_gate, fullscreen_pack, alignment, or operator_ack gate open"
        )

    if (
        dg.draft_written is not False
        or dg.merge_executed is not False
        or dg.live_dispatched is not False
        or fp.live_dispatched is not False
        or fp.merge_executed is not False
        or fp.pack_dispatched is not False
        or fp.backlog_mutated is not False
        or fp.store_mutated is not False
        or fp.production_router_verdict != "REJECT"
        or fp.live_router_authorized is not False
        or fp.live_execution_authorized is not False
    ):
        raise FloatingDraftBeforeFullMergeFullscreenWeeklyNdMoComposeError(
            "invariant: honesty flags must remain false"
        )

    notes.extend(
        (
            "draft_written=false",
            "merge_executed=false",
            "live_dispatched=false",
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

    return FloatingDraftBeforeFullMergeFullscreenWeeklyNdMoCompose(
        session_id=session,
        parent_asset_id=parent,
        week_id=week,
        draft_gate=dg,
        fullscreen_pack=fp,
        pack_ready=pack_ready,
        draft_written=False,
        merge_executed=False,
        live_dispatched=False,
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
            "floating_draft_before_full_merge_fullscreen_weekly_nd_mo_compose_advisory"
        ),
    )


def format_floating_draft_before_full_merge_fullscreen_weekly_nd_mo_summary(
    c: FloatingDraftBeforeFullMergeFullscreenWeeklyNdMoCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"gate_ready={c.draft_gate.gate_ready} · "
        f"stage={c.draft_gate.stage} · "
        f"fullscreen_ready={c.fullscreen_pack.fullscreen.fullscreen_ready} · "
        f"weekly_nd_ready={c.fullscreen_pack.weekly_nd.pack_ready} · "
        f"verdict={c.production_router_verdict} · "
        f"draft_written=false · merge_executed=false · live_dispatched=false"
    )


__all__ = [
    "FloatingDraftBeforeFullMergeFullscreenWeeklyNdMoCompose",
    "FloatingDraftBeforeFullMergeFullscreenWeeklyNdMoComposeError",
    "compose_floating_draft_before_full_merge_fullscreen_weekly_nd_mo",
    "format_floating_draft_before_full_merge_fullscreen_weekly_nd_mo_summary",
]
