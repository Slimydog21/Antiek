"""Recursive twin note-taker + MO price-ceiling write pack (pure).

twin_written / prompts_injected / live_dispatch_authorized always False.
charge_executed / live_execution_authorized always False.
draft_written / analysis_written / merge_executed always False.
production_router_verdict always REJECT; live_router_authorized always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.mo_price_ceiling_write_twin_settings_draft_compose import (
    MoPriceCeilingWriteTwinSettingsDraftCompose,
    MoPriceCeilingWriteTwinSettingsDraftComposeError,
    compose_mo_price_ceiling_write_twin_settings_draft,
)
from substrate.recursive_twin_note_taker_compose import (
    RecursiveTwinNoteTakerCompose,
    RecursiveTwinNoteTakerComposeError,
    compose_recursive_twin_note_taker,
)


class RecursiveTwinMoPriceCeilingWritePackComposeError(ValueError):
    """Fail-closed validation for recursive twin + MO write pack."""


@dataclass(frozen=True)
class RecursiveTwinMoPriceCeilingWritePackCompose:
    session_id: str
    parent_asset_id: str
    week_id: str
    twin: RecursiveTwinNoteTakerCompose
    mo_write: MoPriceCeilingWriteTwinSettingsDraftCompose
    pack_ready: bool
    twin_written: bool
    prompts_injected: bool
    live_dispatch_authorized: bool
    charge_executed: bool
    live_execution_authorized: bool
    draft_written: bool
    analysis_written: bool
    merge_executed: bool
    secrets_stored: bool
    inventory_mutated: bool
    live_dispatched: bool
    pack_dispatched: bool
    backlog_mutated: bool
    store_mutated: bool
    production_router_verdict: str
    live_router_authorized: bool
    purchase_executed: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "parent_asset_id": self.parent_asset_id,
            "week_id": self.week_id,
            "twin": self.twin.to_dict(),
            "mo_write": self.mo_write.to_dict(),
            "pack_ready": self.pack_ready,
            "twin_written": False,
            "prompts_injected": False,
            "live_dispatch_authorized": False,
            "charge_executed": False,
            "live_execution_authorized": False,
            "draft_written": False,
            "analysis_written": False,
            "merge_executed": False,
            "secrets_stored": False,
            "inventory_mutated": False,
            "live_dispatched": False,
            "pack_dispatched": False,
            "backlog_mutated": False,
            "store_mutated": False,
            "production_router_verdict": "REJECT",
            "live_router_authorized": False,
            "purchase_executed": False,
            "notes": list(self.notes),
            "authority": (
                "recursive_twin_mo_price_ceiling_write_pack_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RecursiveTwinMoPriceCeilingWritePackComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_recursive_twin_mo_price_ceiling_write_pack(
    *,
    twin: object,
    mo_write: object,
    operator_ack: object,
    require_both: object | None = None,
) -> RecursiveTwinMoPriceCeilingWritePackCompose:
    """Recursive twin bind on MO price-ceiling write pack. Never writes twin."""
    if not isinstance(operator_ack, bool):
        raise RecursiveTwinMoPriceCeilingWritePackComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(twin, dict):
        raise RecursiveTwinMoPriceCeilingWritePackComposeError(
            "twin must be an object"
        )
    if not isinstance(mo_write, dict):
        raise RecursiveTwinMoPriceCeilingWritePackComposeError(
            "mo_write must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise RecursiveTwinMoPriceCeilingWritePackComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "twin_written=false · prompts_injected=false · live_dispatch_authorized=false",
        "charge_executed=false · live_execution_authorized=false",
        "draft_written=false · analysis_written=false · merge_executed=false",
        "production_router_verdict=REJECT · live_router_authorized=false",
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
        raise RecursiveTwinMoPriceCeilingWritePackComposeError(str(e)) from e
    notes.extend(f"[twin] {n}" for n in t.notes)

    try:
        mw = compose_mo_price_ceiling_write_twin_settings_draft(
            mo=mo_write.get("mo"),
            research_write=mo_write.get("research_write"),
            operator_ack=operator_ack,
            require_both=mo_write.get("require_both"),
        )
    except MoPriceCeilingWriteTwinSettingsDraftComposeError as e:
        raise RecursiveTwinMoPriceCeilingWritePackComposeError(str(e)) from e
    notes.extend(f"[mo_write] {n}" for n in mw.notes)

    session = _require_nonempty(mw.session_id, field="session_id")
    parent = _require_nonempty(t.parent_asset_id, field="parent_asset_id")
    week = _require_nonempty(mw.week_id, field="week_id")

    aligned = mw.parent_asset_id == parent
    if not aligned:
        notes.append(
            "parent_asset_id mismatch between twin and mo_write — pack_ready blocked"
        )

    if require:
        pack_ready = (
            aligned
            and t.twin_propose_ready is True
            and mw.pack_ready is True
            and mw.production_router_verdict == "REJECT"
            and t.twin_written is False
            and mw.charge_executed is False
            and operator_ack is True
        )
    else:
        pack_ready = (
            aligned
            and operator_ack is True
            and mw.production_router_verdict == "REJECT"
            and t.twin_written is False
            and (t.twin_propose_ready is True or mw.pack_ready is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — recursive twin + MO price-ceiling write pack ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — twin, mo_write, alignment, or operator_ack gate open"
        )

    if (
        t.twin_written is not False
        or t.prompts_injected is not False
        or t.live_dispatch_authorized is not False
        or mw.charge_executed is not False
        or mw.live_execution_authorized is not False
        or mw.draft_written is not False
        or mw.analysis_written is not False
        or mw.merge_executed is not False
        or mw.production_router_verdict != "REJECT"
        or mw.live_router_authorized is not False
    ):
        raise RecursiveTwinMoPriceCeilingWritePackComposeError(
            "invariant: honesty flags must remain false"
        )

    notes.extend(
        (
            "twin_written=false",
            "prompts_injected=false",
            "live_dispatch_authorized=false",
            "charge_executed=false",
            "live_execution_authorized=false",
            "draft_written=false",
            "analysis_written=false",
            "merge_executed=false",
            "secrets_stored=false",
            "inventory_mutated=false",
            "live_dispatched=false",
            "pack_dispatched=false",
            "backlog_mutated=false",
            "store_mutated=false",
            "production_router_verdict=REJECT",
            "live_router_authorized=false",
            "purchase_executed=false",
        )
    )

    return RecursiveTwinMoPriceCeilingWritePackCompose(
        session_id=session,
        parent_asset_id=parent,
        week_id=week,
        twin=t,
        mo_write=mw,
        pack_ready=pack_ready,
        twin_written=False,
        prompts_injected=False,
        live_dispatch_authorized=False,
        charge_executed=False,
        live_execution_authorized=False,
        draft_written=False,
        analysis_written=False,
        merge_executed=False,
        secrets_stored=False,
        inventory_mutated=False,
        live_dispatched=False,
        pack_dispatched=False,
        backlog_mutated=False,
        store_mutated=False,
        production_router_verdict="REJECT",
        live_router_authorized=False,
        purchase_executed=False,
        notes=tuple(notes),
        authority="recursive_twin_mo_price_ceiling_write_pack_compose_advisory",
    )


def format_recursive_twin_mo_price_ceiling_write_pack_summary(
    c: RecursiveTwinMoPriceCeilingWritePackCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"twin_propose_ready={c.twin.twin_propose_ready} · "
        f"mo_write_ready={c.mo_write.pack_ready} · "
        f"verdict={c.production_router_verdict} · "
        f"twin_written=false · charge_executed=false · live_dispatch_authorized=false"
    )


__all__ = [
    "RecursiveTwinMoPriceCeilingWritePackCompose",
    "RecursiveTwinMoPriceCeilingWritePackComposeError",
    "compose_recursive_twin_mo_price_ceiling_write_pack",
    "format_recursive_twin_mo_price_ceiling_write_pack_summary",
]
