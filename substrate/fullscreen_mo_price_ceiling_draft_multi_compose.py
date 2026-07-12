"""Fullscreen-open over MO price-ceiling draft multi-select pack (pure).

live_dispatched / pack_dispatched / merge_executed always False.
live_execution_authorized / charge_executed always False.
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
from substrate.mo_price_ceiling_draft_multi_select_record_write_compose import (
    MoPriceCeilingDraftMultiSelectRecordWriteCompose,
    MoPriceCeilingDraftMultiSelectRecordWriteComposeError,
    compose_mo_price_ceiling_draft_multi_select_record_write,
)


class FullscreenMoPriceCeilingDraftMultiComposeError(ValueError):
    """Fail-closed validation for fullscreen + MO draft multi pack."""


@dataclass(frozen=True)
class FullscreenMoPriceCeilingDraftMultiCompose:
    session_id: str
    parent_asset_id: str
    fullscreen: FloatingFullscreenOpenCompose
    mo_pack: MoPriceCeilingDraftMultiSelectRecordWriteCompose
    pack_ready: bool
    live_dispatched: bool
    pack_dispatched: bool
    merge_executed: bool
    live_execution_authorized: bool
    charge_executed: bool
    draft_written: bool
    prompts_injected: bool
    record_persisted: bool
    remote_index_queried: bool
    twin_written: bool
    analysis_written: bool
    production_router_verdict: str
    live_router_authorized: bool
    purchase_executed: bool
    hosted: bool
    store_mutated: bool
    backlog_mutated: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "parent_asset_id": self.parent_asset_id,
            "fullscreen": self.fullscreen.to_dict(),
            "mo_pack": self.mo_pack.to_dict(),
            "pack_ready": self.pack_ready,
            "live_dispatched": False,
            "pack_dispatched": False,
            "merge_executed": False,
            "live_execution_authorized": False,
            "charge_executed": False,
            "draft_written": False,
            "prompts_injected": False,
            "record_persisted": False,
            "remote_index_queried": False,
            "twin_written": False,
            "analysis_written": False,
            "production_router_verdict": "REJECT",
            "live_router_authorized": False,
            "purchase_executed": False,
            "hosted": False,
            "store_mutated": False,
            "backlog_mutated": False,
            "notes": list(self.notes),
            "authority": "fullscreen_mo_price_ceiling_draft_multi_compose_advisory",
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FullscreenMoPriceCeilingDraftMultiComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_fullscreen_mo_price_ceiling_draft_multi(
    *,
    fullscreen: object,
    mo_pack: object,
    operator_ack: object,
    require_both: object | None = None,
) -> FullscreenMoPriceCeilingDraftMultiCompose:
    """Fullscreen + MO price-ceiling draft multi. Never dispatches."""
    if not isinstance(operator_ack, bool):
        raise FullscreenMoPriceCeilingDraftMultiComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(fullscreen, dict):
        raise FullscreenMoPriceCeilingDraftMultiComposeError(
            "fullscreen must be an object"
        )
    if not isinstance(mo_pack, dict):
        raise FullscreenMoPriceCeilingDraftMultiComposeError(
            "mo_pack must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise FullscreenMoPriceCeilingDraftMultiComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "live_dispatched=false · pack_dispatched=false · merge_executed=false",
        "live_execution_authorized=false · charge_executed=false",
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
        raise FullscreenMoPriceCeilingDraftMultiComposeError(str(e)) from e
    notes.extend(f"[fullscreen] {n}" for n in fs.notes)

    try:
        mp = compose_mo_price_ceiling_draft_multi_select_record_write(
            mo=mo_pack.get("mo"),
            draft_multi=mo_pack.get("draft_multi"),
            operator_ack=operator_ack,
            require_both=mo_pack.get("require_both"),
        )
    except MoPriceCeilingDraftMultiSelectRecordWriteComposeError as e:
        raise FullscreenMoPriceCeilingDraftMultiComposeError(str(e)) from e
    notes.extend(f"[mo_pack] {n}" for n in mp.notes)

    session = _require_nonempty(fs.session_id, field="session_id")
    parent = _require_nonempty(fs.parent_asset_id, field="parent_asset_id")

    session_aligned = mp.session_id == session
    parent_aligned = mp.parent_asset_id == parent
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
            and mp.charge_executed is False
            and operator_ack is True
        )
    else:
        pack_ready = (
            session_aligned
            and parent_aligned
            and operator_ack is True
            and mp.production_router_verdict == "REJECT"
            and (fs.fullscreen_ready is True or mp.pack_ready is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — fullscreen + MO price-ceiling draft multi pack ready; still pure"
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
        or mp.charge_executed is not False
        or mp.production_router_verdict != "REJECT"
    ):
        raise FullscreenMoPriceCeilingDraftMultiComposeError(
            "invariant: honesty flags must remain false"
        )

    notes.extend(
        (
            "live_dispatched=false",
            "pack_dispatched=false",
            "merge_executed=false",
            "live_execution_authorized=false",
            "charge_executed=false",
            "draft_written=false",
            "prompts_injected=false",
            "record_persisted=false",
            "remote_index_queried=false",
            "twin_written=false",
            "analysis_written=false",
            "production_router_verdict=REJECT",
            "live_router_authorized=false",
            "purchase_executed=false",
            "hosted=false",
            "store_mutated=false",
            "backlog_mutated=false",
        )
    )

    return FullscreenMoPriceCeilingDraftMultiCompose(
        session_id=session,
        parent_asset_id=parent,
        fullscreen=fs,
        mo_pack=mp,
        pack_ready=pack_ready,
        live_dispatched=False,
        pack_dispatched=False,
        merge_executed=False,
        live_execution_authorized=False,
        charge_executed=False,
        draft_written=False,
        prompts_injected=False,
        record_persisted=False,
        remote_index_queried=False,
        twin_written=False,
        analysis_written=False,
        production_router_verdict="REJECT",
        live_router_authorized=False,
        purchase_executed=False,
        hosted=False,
        store_mutated=False,
        backlog_mutated=False,
        notes=tuple(notes),
        authority="fullscreen_mo_price_ceiling_draft_multi_compose_advisory",
    )


def format_fullscreen_mo_price_ceiling_draft_multi_summary(
    c: FullscreenMoPriceCeilingDraftMultiCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"fullscreen_ready={c.fullscreen.fullscreen_ready} · "
        f"mo_pack_ready={c.mo_pack.pack_ready} · "
        f"verdict={c.production_router_verdict} · "
        f"live_dispatched=false · charge_executed=false · live_execution_authorized=false"
    )


__all__ = [
    "FullscreenMoPriceCeilingDraftMultiCompose",
    "FullscreenMoPriceCeilingDraftMultiComposeError",
    "compose_fullscreen_mo_price_ceiling_draft_multi",
    "format_fullscreen_mo_price_ceiling_draft_multi_summary",
]
