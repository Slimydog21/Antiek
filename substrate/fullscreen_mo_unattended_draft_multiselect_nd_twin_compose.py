"""Floating fullscreen-open over MO unattended draft multiselect ND twin (pure).

live_dispatched / pack_dispatched / merge_executed always False.
live_execution_authorized / draft_written always False.
live_router_authorized / secrets_stored / remote_index_queried always False.
pdf_primary always False.
production_router_verdict always REJECT.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.floating_fullscreen_open_compose import (
    FloatingFullscreenOpenCompose,
    FloatingFullscreenOpenComposeError,
    compose_floating_fullscreen_open,
)
from substrate.mo_unattended_draft_before_merge_floating_multiselect_nd_twin_compose import (
    MoUnattendedDraftBeforeMergeFloatingMultiselectNdTwinCompose,
    MoUnattendedDraftBeforeMergeFloatingMultiselectNdTwinComposeError,
    compose_mo_unattended_draft_before_merge_floating_multiselect_nd_twin,
)


class FullscreenMoUnattendedDraftMultiselectNdTwinComposeError(ValueError):
    """Fail-closed validation for fullscreen + MO unattended draft ND twin pack."""


@dataclass(frozen=True)
class FullscreenMoUnattendedDraftMultiselectNdTwinCompose:
    session_id: str
    parent_asset_id: str
    week_id: str
    asset_id: str
    title: str
    account_id: str
    fullscreen: FloatingFullscreenOpenCompose
    mo_pack: MoUnattendedDraftBeforeMergeFloatingMultiselectNdTwinCompose
    session_aligned: bool
    parent_aligned: bool
    pack_ready: bool
    live_dispatched: bool
    pack_dispatched: bool
    merge_executed: bool
    live_execution_authorized: bool
    draft_written: bool
    analysis_written: bool
    live_router_authorized: bool
    secrets_stored: bool
    live_meter_read: bool
    remote_index_queried: bool
    backlog_mutated: bool
    store_mutated: bool
    suite_rewritten: bool
    pdf_view_authorized: bool
    pdf_primary: bool
    twin_written: bool
    prompts_injected: bool
    live_dispatch_authorized: bool
    inventory_mutated: bool
    charge_executed: bool
    record_persisted: bool
    purchase_executed: bool
    hosted: bool
    remote_fetched: bool
    production_router_verdict: str
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
            "mo_pack": self.mo_pack.to_dict(),
            "session_aligned": self.session_aligned,
            "parent_aligned": self.parent_aligned,
            "pack_ready": self.pack_ready,
            "live_dispatched": False,
            "pack_dispatched": False,
            "merge_executed": False,
            "live_execution_authorized": False,
            "draft_written": False,
            "analysis_written": False,
            "live_router_authorized": False,
            "secrets_stored": False,
            "live_meter_read": False,
            "remote_index_queried": False,
            "backlog_mutated": False,
            "store_mutated": False,
            "suite_rewritten": False,
            "pdf_view_authorized": False,
            "pdf_primary": False,
            "twin_written": False,
            "prompts_injected": False,
            "live_dispatch_authorized": False,
            "inventory_mutated": False,
            "charge_executed": False,
            "record_persisted": False,
            "purchase_executed": False,
            "hosted": False,
            "remote_fetched": False,
            "production_router_verdict": "REJECT",
            "notes": list(self.notes),
            "authority": (
                "fullscreen_mo_unattended_draft_multiselect_nd_twin_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FullscreenMoUnattendedDraftMultiselectNdTwinComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_fullscreen_mo_unattended_draft_multiselect_nd_twin(
    *,
    fullscreen: object,
    mo_pack: object,
    operator_ack: object,
    require_both: object | None = None,
) -> FullscreenMoUnattendedDraftMultiselectNdTwinCompose:
    """Fullscreen-open + MO unattended draft multiselect ND twin. Never dispatches."""
    if not isinstance(operator_ack, bool):
        raise FullscreenMoUnattendedDraftMultiselectNdTwinComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(fullscreen, dict):
        raise FullscreenMoUnattendedDraftMultiselectNdTwinComposeError(
            "fullscreen must be an object"
        )
    if not isinstance(mo_pack, dict):
        raise FullscreenMoUnattendedDraftMultiselectNdTwinComposeError(
            "mo_pack must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise FullscreenMoUnattendedDraftMultiselectNdTwinComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "live_dispatched=false · pack_dispatched=false · merge_executed=false",
        "live_execution_authorized=false · draft_written=false",
        "live_router_authorized=false · secrets_stored=false · remote_index_queried=false",
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
        raise FullscreenMoUnattendedDraftMultiselectNdTwinComposeError(str(e)) from e
    notes.extend(f"[fullscreen] {n}" for n in fs.notes)

    try:
        mp = compose_mo_unattended_draft_before_merge_floating_multiselect_nd_twin(
            mo=mo_pack.get("mo"),
            draft_pack=mo_pack.get("draft_pack"),
            operator_ack=operator_ack,
            require_both=mo_pack.get("require_both"),
        )
    except MoUnattendedDraftBeforeMergeFloatingMultiselectNdTwinComposeError as e:
        raise FullscreenMoUnattendedDraftMultiselectNdTwinComposeError(str(e)) from e
    notes.extend(f"[mo_pack] {n}" for n in mp.notes)

    session = _require_nonempty(fs.session_id, field="session_id")
    parent = _require_nonempty(fs.parent_asset_id, field="parent_asset_id")
    week = _require_nonempty(mp.week_id, field="week_id")
    asset = _require_nonempty(mp.asset_id, field="asset_id")
    title = _require_nonempty(mp.title, field="title")
    account = _require_nonempty(mp.account_id, field="account_id")

    session_aligned = mp.session_id == session
    parent_aligned = mp.parent_asset_id == parent or mp.asset_id == parent
    if not session_aligned:
        notes.append(
            "session_id mismatch between fullscreen and mo_pack — pack_ready blocked"
        )
    if not parent_aligned:
        notes.append(
            "parent_asset_id mismatch between fullscreen and mo_pack — pack_ready blocked"
        )

    if require:
        pack_ready = (
            session_aligned
            and parent_aligned
            and fs.fullscreen_ready is True
            and mp.pack_ready is True
            and mp.production_router_verdict == "REJECT"
            and fs.live_dispatched is False
            and mp.live_execution_authorized is False
            and mp.live_dispatched is False
            and mp.merge_executed is False
            and mp.draft_written is False
            and mp.live_router_authorized is False
            and mp.secrets_stored is False
            and mp.remote_index_queried is False
            and mp.pdf_primary is False
            and operator_ack is True
        )
    else:
        pack_ready = (
            session_aligned
            and parent_aligned
            and operator_ack is True
            and mp.production_router_verdict == "REJECT"
            and mp.pdf_primary is False
            and (fs.fullscreen_ready is True or mp.pack_ready is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — fullscreen + MO unattended draft multiselect ND twin "
            "ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — fullscreen, mo_pack, alignment, or operator_ack gate open"
        )

    if (
        fs.live_dispatched is not False
        or fs.merge_executed is not False
        or fs.pack_dispatched is not False
        or mp.live_execution_authorized is not False
        or mp.live_dispatched is not False
        or mp.merge_executed is not False
        or mp.draft_written is not False
        or mp.live_router_authorized is not False
        or mp.secrets_stored is not False
        or mp.remote_index_queried is not False
        or mp.pdf_primary is not False
        or mp.production_router_verdict != "REJECT"
    ):
        raise FullscreenMoUnattendedDraftMultiselectNdTwinComposeError(
            "invariant: honesty flags must remain false / REJECT"
        )

    notes.extend(
        (
            "live_dispatched=false",
            "pack_dispatched=false",
            "merge_executed=false",
            "live_execution_authorized=false",
            "draft_written=false",
            "analysis_written=false",
            "live_router_authorized=false",
            "secrets_stored=false",
            "live_meter_read=false",
            "remote_index_queried=false",
            "backlog_mutated=false",
            "store_mutated=false",
            "suite_rewritten=false",
            "pdf_view_authorized=false",
            "pdf_primary=false",
            "twin_written=false",
            "prompts_injected=false",
            "live_dispatch_authorized=false",
            "inventory_mutated=false",
            "charge_executed=false",
            "record_persisted=false",
            "purchase_executed=false",
            "hosted=false",
            "remote_fetched=false",
            "production_router_verdict=REJECT",
        )
    )

    return FullscreenMoUnattendedDraftMultiselectNdTwinCompose(
        session_id=session,
        parent_asset_id=parent,
        week_id=week,
        asset_id=asset,
        title=title,
        account_id=account,
        fullscreen=fs,
        mo_pack=mp,
        session_aligned=session_aligned,
        parent_aligned=parent_aligned,
        pack_ready=pack_ready,
        live_dispatched=False,
        pack_dispatched=False,
        merge_executed=False,
        live_execution_authorized=False,
        draft_written=False,
        analysis_written=False,
        live_router_authorized=False,
        secrets_stored=False,
        live_meter_read=False,
        remote_index_queried=False,
        backlog_mutated=False,
        store_mutated=False,
        suite_rewritten=False,
        pdf_view_authorized=False,
        pdf_primary=False,
        twin_written=False,
        prompts_injected=False,
        live_dispatch_authorized=False,
        inventory_mutated=False,
        charge_executed=False,
        record_persisted=False,
        purchase_executed=False,
        hosted=False,
        remote_fetched=False,
        production_router_verdict="REJECT",
        notes=tuple(notes),
        authority=(
            "fullscreen_mo_unattended_draft_multiselect_nd_twin_compose_advisory"
        ),
    )


def format_fullscreen_mo_unattended_draft_multiselect_nd_twin_summary(
    c: FullscreenMoUnattendedDraftMultiselectNdTwinCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"fullscreen_ready={c.fullscreen.fullscreen_ready} · "
        f"mo_ready={c.mo_pack.pack_ready} · "
        f"session_aligned={c.session_aligned} · "
        f"parent_aligned={c.parent_aligned} · "
        f"verdict={c.production_router_verdict} · "
        "live_dispatched=false · live_execution_authorized=false · draft_written=false"
    )


__all__ = [
    "FullscreenMoUnattendedDraftMultiselectNdTwinCompose",
    "FullscreenMoUnattendedDraftMultiselectNdTwinComposeError",
    "compose_fullscreen_mo_unattended_draft_multiselect_nd_twin",
    "format_fullscreen_mo_unattended_draft_multiselect_nd_twin_summary",
]
