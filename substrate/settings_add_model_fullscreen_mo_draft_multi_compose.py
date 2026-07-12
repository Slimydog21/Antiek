"""Settings add-model over fullscreen MO price-ceiling draft multi pack (pure).

secrets_stored / inventory_mutated always False.
live_dispatched / charge_executed / live_execution_authorized always False.
production_router_verdict always REJECT.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.fullscreen_mo_price_ceiling_draft_multi_compose import (
    FullscreenMoPriceCeilingDraftMultiCompose,
    FullscreenMoPriceCeilingDraftMultiComposeError,
    compose_fullscreen_mo_price_ceiling_draft_multi,
)
from substrate.settings_add_model_inventory_compose import (
    SettingsAddModelInventoryCompose,
    SettingsAddModelInventoryComposeError,
    compose_settings_add_model_inventory,
)


class SettingsAddModelFullscreenMoDraftMultiComposeError(ValueError):
    """Fail-closed validation for settings add-model + fullscreen MO pack."""


@dataclass(frozen=True)
class SettingsAddModelFullscreenMoDraftMultiCompose:
    session_id: str
    parent_asset_id: str
    settings: SettingsAddModelInventoryCompose
    fullscreen_mo: FullscreenMoPriceCeilingDraftMultiCompose
    pack_ready: bool
    secrets_stored: bool
    inventory_mutated: bool
    live_router_authorized: bool
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
            "settings": self.settings.to_dict(),
            "fullscreen_mo": self.fullscreen_mo.to_dict(),
            "pack_ready": self.pack_ready,
            "secrets_stored": False,
            "inventory_mutated": False,
            "live_router_authorized": False,
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
            "purchase_executed": False,
            "hosted": False,
            "store_mutated": False,
            "backlog_mutated": False,
            "notes": list(self.notes),
            "authority": "settings_add_model_fullscreen_mo_draft_multi_compose_advisory",
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SettingsAddModelFullscreenMoDraftMultiComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_settings_add_model_fullscreen_mo_draft_multi(
    *,
    settings: object,
    fullscreen_mo: object,
    operator_ack: object,
    require_both: object | None = None,
) -> SettingsAddModelFullscreenMoDraftMultiCompose:
    """Settings add-model + fullscreen MO pack. Never stores secrets."""
    if not isinstance(operator_ack, bool):
        raise SettingsAddModelFullscreenMoDraftMultiComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(settings, dict):
        raise SettingsAddModelFullscreenMoDraftMultiComposeError(
            "settings must be an object"
        )
    if not isinstance(fullscreen_mo, dict):
        raise SettingsAddModelFullscreenMoDraftMultiComposeError(
            "fullscreen_mo must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise SettingsAddModelFullscreenMoDraftMultiComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "secrets_stored=false · inventory_mutated=false · live_router_authorized=false",
        "live_dispatched=false · charge_executed=false · live_execution_authorized=false",
        "production_router_verdict=REJECT",
    ]

    try:
        st = compose_settings_add_model_inventory(
            models=settings.get("models"),
            pending_add_model_ids=settings.get("pending_add_model_ids"),
            action=settings.get("action"),
            daily_cap_usd=settings.get("daily_cap_usd"),
            spent_usd=settings.get("spent_usd"),
            operator_ack=operator_ack,
            selected_model_id=settings.get("selected_model_id"),
            projected_cost_usd_high=settings.get("projected_cost_usd_high"),
            projected_cost_usd_low=settings.get("projected_cost_usd_low"),
        )
    except SettingsAddModelInventoryComposeError as e:
        raise SettingsAddModelFullscreenMoDraftMultiComposeError(str(e)) from e
    notes.extend(f"[settings] {n}" for n in st.notes)

    try:
        fm = compose_fullscreen_mo_price_ceiling_draft_multi(
            fullscreen=fullscreen_mo.get("fullscreen"),
            mo_pack=fullscreen_mo.get("mo_pack"),
            operator_ack=operator_ack,
            require_both=fullscreen_mo.get("require_both"),
        )
    except FullscreenMoPriceCeilingDraftMultiComposeError as e:
        raise SettingsAddModelFullscreenMoDraftMultiComposeError(str(e)) from e
    notes.extend(f"[fullscreen_mo] {n}" for n in fm.notes)

    session = _require_nonempty(fm.session_id, field="session_id")
    parent = _require_nonempty(fm.parent_asset_id, field="parent_asset_id")

    if require:
        pack_ready = (
            st.pack_ready is True
            and fm.pack_ready is True
            and fm.production_router_verdict == "REJECT"
            and st.secrets_stored is False
            and st.inventory_mutated is False
            and st.live_router_authorized is False
            and fm.live_dispatched is False
            and fm.charge_executed is False
            and fm.live_execution_authorized is False
            and operator_ack is True
        )
    else:
        pack_ready = (
            operator_ack is True
            and fm.production_router_verdict == "REJECT"
            and st.secrets_stored is False
            and (st.pack_ready is True or fm.pack_ready is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — settings add-model + fullscreen MO draft multi ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — settings, fullscreen_mo, or operator_ack gate open"
        )

    if (
        st.secrets_stored is not False
        or st.inventory_mutated is not False
        or st.live_router_authorized is not False
        or fm.live_dispatched is not False
        or fm.charge_executed is not False
        or fm.live_execution_authorized is not False
        or fm.production_router_verdict != "REJECT"
    ):
        raise SettingsAddModelFullscreenMoDraftMultiComposeError(
            "invariant: honesty flags must remain false"
        )

    notes.extend(
        (
            "secrets_stored=false",
            "inventory_mutated=false",
            "live_router_authorized=false",
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
            "purchase_executed=false",
            "hosted=false",
            "store_mutated=false",
            "backlog_mutated=false",
        )
    )

    return SettingsAddModelFullscreenMoDraftMultiCompose(
        session_id=session,
        parent_asset_id=parent,
        settings=st,
        fullscreen_mo=fm,
        pack_ready=pack_ready,
        secrets_stored=False,
        inventory_mutated=False,
        live_router_authorized=False,
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
        purchase_executed=False,
        hosted=False,
        store_mutated=False,
        backlog_mutated=False,
        notes=tuple(notes),
        authority="settings_add_model_fullscreen_mo_draft_multi_compose_advisory",
    )


def format_settings_add_model_fullscreen_mo_draft_multi_summary(
    c: SettingsAddModelFullscreenMoDraftMultiCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"settings_ready={c.settings.pack_ready} · "
        f"proposed_new={c.settings.proposed_new_count} · "
        f"fullscreen_mo_ready={c.fullscreen_mo.pack_ready} · "
        f"verdict={c.production_router_verdict} · "
        f"secrets_stored=false · inventory_mutated=false · charge_executed=false"
    )


__all__ = [
    "SettingsAddModelFullscreenMoDraftMultiCompose",
    "SettingsAddModelFullscreenMoDraftMultiComposeError",
    "compose_settings_add_model_fullscreen_mo_draft_multi",
    "format_settings_add_model_fullscreen_mo_draft_multi_summary",
]
