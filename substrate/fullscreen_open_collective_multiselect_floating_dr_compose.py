"""Fullscreen-open over collective multiselect floating DR draft-before-merge (pure).

live_dispatched / pack_dispatched / merge_executed always False.
live_execution_authorized / charge_executed / analysis_written always False.
production_router_verdict always REJECT.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.collective_multiselect_floating_dr_draft_before_merge_compose import (
    CollectiveMultiselectFloatingDrDraftBeforeMergeCompose,
    CollectiveMultiselectFloatingDrDraftBeforeMergeComposeError,
    compose_collective_multiselect_floating_dr_draft_before_merge,
)
from substrate.floating_fullscreen_open_compose import (
    FloatingFullscreenOpenCompose,
    FloatingFullscreenOpenComposeError,
    compose_floating_fullscreen_open,
)


class FullscreenOpenCollectiveMultiselectFloatingDrComposeError(ValueError):
    """Fail-closed validation for fullscreen + collective multiselect pack."""


@dataclass(frozen=True)
class FullscreenOpenCollectiveMultiselectFloatingDrCompose:
    session_id: str
    parent_asset_id: str
    week_id: str
    asset_id: str
    title: str
    account_id: str
    fullscreen: FloatingFullscreenOpenCompose
    collective_pack: CollectiveMultiselectFloatingDrDraftBeforeMergeCompose
    session_aligned: bool
    parent_aligned: bool
    pack_ready: bool
    live_dispatched: bool
    pack_dispatched: bool
    merge_executed: bool
    live_execution_authorized: bool
    charge_executed: bool
    draft_written: bool
    analysis_written: bool
    twin_written: bool
    prompts_injected: bool
    record_persisted: bool
    remote_index_queried: bool
    production_router_verdict: str
    live_router_authorized: bool
    secrets_stored: bool
    live_meter_read: bool
    purchase_executed: bool
    hosted: bool
    store_mutated: bool
    backlog_mutated: bool
    suite_rewritten: bool
    pdf_view_authorized: bool
    pdf_primary: bool
    live_dispatch_authorized: bool
    inventory_mutated: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "parent_asset_id": self.parent_asset_id,
            "week_id": self.week_id,
            "asset_id": self.asset_id,
            "title": self.title,
            "account_id": self.account_id,
            "fullscreen": self.fullscreen.to_dict(),
            "collective_pack": self.collective_pack.to_dict(),
            "session_aligned": self.session_aligned,
            "parent_aligned": self.parent_aligned,
            "pack_ready": self.pack_ready,
            "live_dispatched": False,
            "pack_dispatched": False,
            "merge_executed": False,
            "live_execution_authorized": False,
            "charge_executed": False,
            "draft_written": False,
            "analysis_written": False,
            "twin_written": False,
            "prompts_injected": False,
            "record_persisted": False,
            "remote_index_queried": False,
            "production_router_verdict": "REJECT",
            "live_router_authorized": False,
            "secrets_stored": False,
            "live_meter_read": False,
            "purchase_executed": False,
            "hosted": False,
            "store_mutated": False,
            "backlog_mutated": False,
            "suite_rewritten": False,
            "pdf_view_authorized": False,
            "pdf_primary": False,
            "live_dispatch_authorized": False,
            "inventory_mutated": False,
            "notes": list(self.notes),
            "authority": (
                "fullscreen_open_collective_multiselect_floating_dr_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FullscreenOpenCollectiveMultiselectFloatingDrComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_fullscreen_open_collective_multiselect_floating_dr(
    *,
    fullscreen: object,
    collective_pack: object,
    operator_ack: object,
    require_both: object | None = None,
) -> FullscreenOpenCollectiveMultiselectFloatingDrCompose:
    """Fullscreen on collective multiselect floating DR. Never dispatches."""
    if not isinstance(operator_ack, bool):
        raise FullscreenOpenCollectiveMultiselectFloatingDrComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(fullscreen, dict):
        raise FullscreenOpenCollectiveMultiselectFloatingDrComposeError(
            "fullscreen must be an object"
        )
    if not isinstance(collective_pack, dict):
        raise FullscreenOpenCollectiveMultiselectFloatingDrComposeError(
            "collective_pack must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise FullscreenOpenCollectiveMultiselectFloatingDrComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "live_dispatched=false · pack_dispatched=false · merge_executed=false",
        "live_execution_authorized=false · charge_executed=false · analysis_written=false",
        "production_router_verdict=REJECT",
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
        raise FullscreenOpenCollectiveMultiselectFloatingDrComposeError(
            str(e)
        ) from e
    notes.extend(f"[fullscreen] {n}" for n in fs.notes)

    try:
        cp = compose_collective_multiselect_floating_dr_draft_before_merge(
            multiselect=collective_pack.get("multiselect"),
            floating_dr_pack=collective_pack.get("floating_dr_pack"),
            operator_ack=operator_ack,
            require_both=collective_pack.get("require_both"),
        )
    except CollectiveMultiselectFloatingDrDraftBeforeMergeComposeError as e:
        raise FullscreenOpenCollectiveMultiselectFloatingDrComposeError(
            str(e)
        ) from e
    notes.extend(f"[collective_pack] {n}" for n in cp.notes)

    session = _require_nonempty(fs.session_id, field="session_id")
    parent = _require_nonempty(fs.parent_asset_id, field="parent_asset_id")
    week = _require_nonempty(cp.week_id, field="week_id")
    asset = _require_nonempty(cp.asset_id, field="asset_id")
    title = _require_nonempty(cp.title, field="title")
    account = _require_nonempty(cp.account_id, field="account_id")

    session_aligned = cp.session_id == session
    parent_aligned = cp.parent_asset_id == parent or cp.asset_id == parent
    if not session_aligned:
        notes.append(
            "session_id mismatch between fullscreen and collective_pack — "
            "pack_ready blocked"
        )
    else:
        notes.append("session_aligned=true")
    if not parent_aligned:
        notes.append(
            "parent_asset_id mismatch between fullscreen and collective_pack — "
            "pack_ready blocked"
        )
    else:
        notes.append("parent_aligned=true")

    if require:
        pack_ready = (
            session_aligned is True
            and parent_aligned is True
            and fs.fullscreen_ready is True
            and cp.pack_ready is True
            and cp.production_router_verdict == "REJECT"
            and fs.live_dispatched is False
            and fs.merge_executed is False
            and fs.pack_dispatched is False
            and cp.live_dispatched is False
            and cp.pack_dispatched is False
            and cp.merge_executed is False
            and cp.analysis_written is False
            and cp.twin_written is False
            and cp.draft_written is False
            and cp.live_execution_authorized is False
            and cp.charge_executed is False
            and cp.remote_index_queried is False
            and cp.pdf_primary is False
            and cp.live_router_authorized is False
            and cp.secrets_stored is False
            and operator_ack is True
        )
    else:
        pack_ready = (
            session_aligned is True
            and parent_aligned is True
            and operator_ack is True
            and cp.production_router_verdict == "REJECT"
            and cp.pdf_primary is False
            and fs.live_dispatched is False
            and (fs.fullscreen_ready is True or cp.pack_ready is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — fullscreen + collective multiselect floating DR "
            "ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — fullscreen, collective_pack, alignment, or "
            "operator_ack gate open"
        )

    if (
        fs.live_dispatched is not False
        or fs.merge_executed is not False
        or fs.pack_dispatched is not False
        or cp.live_dispatched is not False
        or cp.pack_dispatched is not False
        or cp.merge_executed is not False
        or cp.analysis_written is not False
        or cp.twin_written is not False
        or cp.draft_written is not False
        or cp.live_execution_authorized is not False
        or cp.charge_executed is not False
        or cp.remote_index_queried is not False
        or cp.pdf_primary is not False
        or cp.live_router_authorized is not False
        or cp.secrets_stored is not False
        or cp.production_router_verdict != "REJECT"
    ):
        raise FullscreenOpenCollectiveMultiselectFloatingDrComposeError(
            "invariant: honesty flags must remain false / REJECT"
        )

    notes.extend(
        (
            "live_dispatched=false",
            "pack_dispatched=false",
            "merge_executed=false",
            "live_execution_authorized=false",
            "charge_executed=false",
            "draft_written=false",
            "analysis_written=false",
            "twin_written=false",
            "prompts_injected=false",
            "record_persisted=false",
            "remote_index_queried=false",
            "production_router_verdict=REJECT",
            "live_router_authorized=false",
            "secrets_stored=false",
            "live_meter_read=false",
            "purchase_executed=false",
            "hosted=false",
            "store_mutated=false",
            "backlog_mutated=false",
            "suite_rewritten=false",
            "pdf_view_authorized=false",
            "pdf_primary=false",
            "live_dispatch_authorized=false",
            "inventory_mutated=false",
        )
    )

    return FullscreenOpenCollectiveMultiselectFloatingDrCompose(
        session_id=session,
        parent_asset_id=parent,
        week_id=week,
        asset_id=asset,
        title=title,
        account_id=account,
        fullscreen=fs,
        collective_pack=cp,
        session_aligned=session_aligned,
        parent_aligned=parent_aligned,
        pack_ready=pack_ready,
        live_dispatched=False,
        pack_dispatched=False,
        merge_executed=False,
        live_execution_authorized=False,
        charge_executed=False,
        draft_written=False,
        analysis_written=False,
        twin_written=False,
        prompts_injected=False,
        record_persisted=False,
        remote_index_queried=False,
        production_router_verdict="REJECT",
        live_router_authorized=False,
        secrets_stored=False,
        live_meter_read=False,
        purchase_executed=False,
        hosted=False,
        store_mutated=False,
        backlog_mutated=False,
        suite_rewritten=False,
        pdf_view_authorized=False,
        pdf_primary=False,
        live_dispatch_authorized=False,
        inventory_mutated=False,
        notes=tuple(notes),
        authority=(
            "fullscreen_open_collective_multiselect_floating_dr_compose_advisory"
        ),
    )


def format_fullscreen_open_collective_multiselect_floating_dr_summary(
    c: FullscreenOpenCollectiveMultiselectFloatingDrCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"fullscreen_ready={c.fullscreen.fullscreen_ready} · "
        f"collective_ready={c.collective_pack.pack_ready} · "
        f"session_aligned={c.session_aligned} · "
        f"parent_aligned={c.parent_aligned} · "
        f"verdict={c.production_router_verdict} · "
        "live_dispatched=false · charge_executed=false · "
        "live_execution_authorized=false"
    )


__all__ = [
    "FullscreenOpenCollectiveMultiselectFloatingDrCompose",
    "FullscreenOpenCollectiveMultiselectFloatingDrComposeError",
    "compose_fullscreen_open_collective_multiselect_floating_dr",
    "format_fullscreen_open_collective_multiselect_floating_dr_summary",
]
