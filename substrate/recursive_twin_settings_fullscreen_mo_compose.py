"""Recursive twin note-taker over settings fullscreen MO draft multi pack (pure).

twin_written / prompts_injected / live_dispatch_authorized always False.
secrets_stored / inventory_mutated / charge_executed always False.
production_router_verdict always REJECT.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.recursive_twin_note_taker_compose import (
    RecursiveTwinNoteTakerCompose,
    RecursiveTwinNoteTakerComposeError,
    compose_recursive_twin_note_taker,
)
from substrate.settings_add_model_fullscreen_mo_draft_multi_compose import (
    SettingsAddModelFullscreenMoDraftMultiCompose,
    SettingsAddModelFullscreenMoDraftMultiComposeError,
    compose_settings_add_model_fullscreen_mo_draft_multi,
)


class RecursiveTwinSettingsFullscreenMoComposeError(ValueError):
    """Fail-closed validation for recursive twin + settings fullscreen MO pack."""


@dataclass(frozen=True)
class RecursiveTwinSettingsFullscreenMoCompose:
    session_id: str
    parent_asset_id: str
    twin: RecursiveTwinNoteTakerCompose
    settings_pack: SettingsAddModelFullscreenMoDraftMultiCompose
    pack_ready: bool
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
    remote_index_queried: bool
    analysis_written: bool
    production_router_verdict: str
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
            "twin": self.twin.to_dict(),
            "settings_pack": self.settings_pack.to_dict(),
            "pack_ready": self.pack_ready,
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
            "remote_index_queried": False,
            "analysis_written": False,
            "production_router_verdict": "REJECT",
            "purchase_executed": False,
            "hosted": False,
            "store_mutated": False,
            "backlog_mutated": False,
            "notes": list(self.notes),
            "authority": "recursive_twin_settings_fullscreen_mo_compose_advisory",
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RecursiveTwinSettingsFullscreenMoComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_recursive_twin_settings_fullscreen_mo(
    *,
    twin: object,
    settings_pack: object,
    operator_ack: object,
    require_both: object | None = None,
) -> RecursiveTwinSettingsFullscreenMoCompose:
    """Recursive twin + settings fullscreen MO pack. Never writes twins."""
    if not isinstance(operator_ack, bool):
        raise RecursiveTwinSettingsFullscreenMoComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(twin, dict):
        raise RecursiveTwinSettingsFullscreenMoComposeError(
            "twin must be an object"
        )
    if not isinstance(settings_pack, dict):
        raise RecursiveTwinSettingsFullscreenMoComposeError(
            "settings_pack must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise RecursiveTwinSettingsFullscreenMoComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "twin_written=false · prompts_injected=false · live_dispatch_authorized=false",
        "secrets_stored=false · inventory_mutated=false · charge_executed=false",
        "production_router_verdict=REJECT",
    ]

    try:
        tw = compose_recursive_twin_note_taker(
            parent_asset_id=twin.get("parent_asset_id"),
            source_excerpt=twin.get("source_excerpt"),
            operator_ack=operator_ack,
            existing_twin_asset_id=twin.get("existing_twin_asset_id"),
            focus_questions=twin.get("focus_questions"),
        )
    except RecursiveTwinNoteTakerComposeError as e:
        raise RecursiveTwinSettingsFullscreenMoComposeError(str(e)) from e
    notes.extend(f"[twin] {n}" for n in tw.notes)

    try:
        sp = compose_settings_add_model_fullscreen_mo_draft_multi(
            settings=settings_pack.get("settings"),
            fullscreen_mo=settings_pack.get("fullscreen_mo"),
            operator_ack=operator_ack,
            require_both=settings_pack.get("require_both"),
        )
    except SettingsAddModelFullscreenMoDraftMultiComposeError as e:
        raise RecursiveTwinSettingsFullscreenMoComposeError(str(e)) from e
    notes.extend(f"[settings_pack] {n}" for n in sp.notes)

    parent = _require_nonempty(tw.parent_asset_id, field="parent_asset_id")
    session = _require_nonempty(sp.session_id, field="session_id")

    parent_aligned = sp.parent_asset_id == parent
    if not parent_aligned:
        notes.append(
            "parent_asset_id mismatch between twin and settings_pack — pack_ready blocked"
        )

    if require:
        pack_ready = (
            parent_aligned
            and tw.twin_propose_ready is True
            and sp.pack_ready is True
            and sp.production_router_verdict == "REJECT"
            and tw.twin_written is False
            and tw.prompts_injected is False
            and tw.live_dispatch_authorized is False
            and sp.secrets_stored is False
            and sp.inventory_mutated is False
            and sp.charge_executed is False
            and operator_ack is True
        )
    else:
        pack_ready = (
            parent_aligned
            and operator_ack is True
            and sp.production_router_verdict == "REJECT"
            and tw.twin_written is False
            and (tw.twin_propose_ready is True or sp.pack_ready is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — recursive twin note-taker + settings fullscreen MO pack ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — twin, settings_pack, alignment, or operator_ack gate open"
        )

    if (
        tw.twin_written is not False
        or tw.prompts_injected is not False
        or tw.live_dispatch_authorized is not False
        or sp.secrets_stored is not False
        or sp.inventory_mutated is not False
        or sp.charge_executed is not False
        or sp.live_execution_authorized is not False
        or sp.production_router_verdict != "REJECT"
    ):
        raise RecursiveTwinSettingsFullscreenMoComposeError(
            "invariant: honesty flags must remain false"
        )

    notes.extend(
        (
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
            "remote_index_queried=false",
            "analysis_written=false",
            "production_router_verdict=REJECT",
            "purchase_executed=false",
            "hosted=false",
            "store_mutated=false",
            "backlog_mutated=false",
        )
    )

    return RecursiveTwinSettingsFullscreenMoCompose(
        session_id=session,
        parent_asset_id=parent,
        twin=tw,
        settings_pack=sp,
        pack_ready=pack_ready,
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
        remote_index_queried=False,
        analysis_written=False,
        production_router_verdict="REJECT",
        purchase_executed=False,
        hosted=False,
        store_mutated=False,
        backlog_mutated=False,
        notes=tuple(notes),
        authority="recursive_twin_settings_fullscreen_mo_compose_advisory",
    )


def format_recursive_twin_settings_fullscreen_mo_summary(
    c: RecursiveTwinSettingsFullscreenMoCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"twin_propose_ready={c.twin.twin_propose_ready} · "
        f"settings_ready={c.settings_pack.pack_ready} · "
        f"focus_q={c.twin.focus_question_count} · "
        f"verdict={c.production_router_verdict} · "
        f"twin_written=false · prompts_injected=false · secrets_stored=false"
    )


__all__ = [
    "RecursiveTwinSettingsFullscreenMoCompose",
    "RecursiveTwinSettingsFullscreenMoComposeError",
    "compose_recursive_twin_settings_fullscreen_mo",
    "format_recursive_twin_settings_fullscreen_mo_summary",
]
