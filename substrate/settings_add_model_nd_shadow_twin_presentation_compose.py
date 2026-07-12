"""Settings add-model + draft-before-merge fullscreen weekly ND pack (pure).

secrets_stored / inventory_mutated always False.
draft_written / merge_executed / live_dispatched / pack_dispatched always False.
backlog_mutated / store_mutated always False.
production_router_verdict always REJECT; live_router_authorized always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.nd_shadow_twin_presentation_competition_dr_source_attach_compose import (
    NdShadowTwinPresentationCompetitionDrSourceAttachCompose,
    NdShadowTwinPresentationCompetitionDrSourceAttachComposeError,
    compose_nd_shadow_twin_presentation_competition_dr_source_attach,
)
from substrate.settings_add_model_inventory_compose import (
    SettingsAddModelInventoryCompose,
    SettingsAddModelInventoryComposeError,
    compose_settings_add_model_inventory,
)


class SettingsAddModelNdShadowTwinPresentationComposeError(ValueError):
    """Fail-closed validation for settings + draft fullscreen weekly ND pack."""


@dataclass(frozen=True)
class SettingsAddModelNdShadowTwinPresentationCompose:
    session_id: str
    parent_asset_id: str
    week_id: str
    settings: SettingsAddModelInventoryCompose
    nd_pack: NdShadowTwinPresentationCompetitionDrSourceAttachCompose
    pack_ready: bool
    secrets_stored: bool
    inventory_mutated: bool
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
            "settings": self.settings.to_dict(),
            "nd_pack": self.nd_pack.to_dict(),
            "pack_ready": self.pack_ready,
            "secrets_stored": False,
            "inventory_mutated": False,
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
                "settings_add_model_nd_shadow_twin_presentation_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SettingsAddModelNdShadowTwinPresentationComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_settings_add_model_nd_shadow_twin_presentation(
    *,
    settings: object,
    nd_pack: object,
    operator_ack: object,
    require_both: object | None = None,
) -> SettingsAddModelNdShadowTwinPresentationCompose:
    """Settings add-model overlay on draft fullscreen weekly ND. Never mutates."""
    if not isinstance(operator_ack, bool):
        raise SettingsAddModelNdShadowTwinPresentationComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(settings, dict):
        raise SettingsAddModelNdShadowTwinPresentationComposeError(
            "settings must be an object"
        )
    if not isinstance(nd_pack, dict):
        raise SettingsAddModelNdShadowTwinPresentationComposeError(
            "nd_pack must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise SettingsAddModelNdShadowTwinPresentationComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "secrets_stored=false · inventory_mutated=false",
        "draft_written=false · merge_executed=false · live_dispatched=false · pack_dispatched=false",
        "backlog_mutated=false · store_mutated=false",
        "production_router_verdict=REJECT · live_router_authorized=false",
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
        raise SettingsAddModelNdShadowTwinPresentationComposeError(
            str(e)
        ) from e
    notes.extend(f"[settings] {n}" for n in st.notes)

    try:
        rp = compose_nd_shadow_twin_presentation_competition_dr_source_attach(
            nd_shadow=nd_pack.get("nd_shadow"),
            twin_presentation=nd_pack.get("twin_presentation"),
            operator_ack=operator_ack,
            require_both=nd_pack.get("require_both"),
        )
    except NdShadowTwinPresentationCompetitionDrSourceAttachComposeError as e:
        raise SettingsAddModelNdShadowTwinPresentationComposeError(
            str(e)
        ) from e
    notes.extend(f"[nd_pack] {n}" for n in rp.notes)

    session = _require_nonempty(rp.session_id, field="session_id")
    parent = _require_nonempty(rp.parent_asset_id, field="parent_asset_id")
    week = _require_nonempty(rp.week_id, field="week_id")

    if require:
        pack_ready = (
            st.pack_ready is True
            and rp.pack_ready is True
            and rp.production_router_verdict == "REJECT"
            and rp.live_router_authorized is False
            and st.secrets_stored is False
            and st.inventory_mutated is False
            and rp.twin_written is False
            and rp.merge_executed is False
            and rp.purchase_executed is False
            and rp.remote_fetched is False
            and operator_ack is True
        )
    else:
        pack_ready = (
            operator_ack is True
            and rp.production_router_verdict == "REJECT"
            and st.secrets_stored is False
            and (st.pack_ready is True or rp.pack_ready is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — settings add-model + ND shadow twin presentation "
            "ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — settings, nd_pack, or operator_ack gate open"
        )

    if (
        st.secrets_stored is not False
        or st.inventory_mutated is not False
        or st.live_router_authorized is not False
        or rp.twin_written is not False
        or rp.merge_executed is not False
        or rp.purchase_executed is not False
        or rp.remote_fetched is not False
        or rp.production_router_verdict != "REJECT"
        or rp.live_router_authorized is not False
    ):
        raise SettingsAddModelNdShadowTwinPresentationComposeError(
            "invariant: honesty flags must remain false / REJECT"
        )

    notes.extend(
        (
            "secrets_stored=false",
            "inventory_mutated=false",
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

    return SettingsAddModelNdShadowTwinPresentationCompose(
        session_id=session,
        parent_asset_id=parent,
        week_id=week,
        settings=st,
        nd_pack=rp,
        pack_ready=pack_ready,
        secrets_stored=False,
        inventory_mutated=False,
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
            "settings_add_model_nd_shadow_twin_presentation_compose_advisory"
        ),
    )


def format_settings_add_model_nd_shadow_twin_presentation_summary(
    c: SettingsAddModelNdShadowTwinPresentationCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"settings_ready={c.settings.pack_ready} · "
        f"proposed_new={c.settings.proposed_new_count} · "
        f"nd_pack_ready={c.nd_pack.pack_ready} · "
        f"verdict={c.production_router_verdict} · "
        f"secrets_stored=false · inventory_mutated=false · merge_executed=false"
    )


__all__ = [
    "SettingsAddModelNdShadowTwinPresentationCompose",
    "SettingsAddModelNdShadowTwinPresentationComposeError",
    "compose_settings_add_model_nd_shadow_twin_presentation",
    "format_settings_add_model_nd_shadow_twin_presentation_summary",
]
