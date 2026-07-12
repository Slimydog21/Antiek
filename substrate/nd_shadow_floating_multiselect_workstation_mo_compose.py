"""NotDiamond shadow REJECT + multi-select workstation marketplace MO (pure).

production_router_verdict always REJECT.
live_router_authorized always False.
All multi-select / marketplace honesty flags always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.floating_multiselect_workstation_marketplace_mo_compose import (
    FloatingMultiselectWorkstationMarketplaceMoCompose,
    FloatingMultiselectWorkstationMarketplaceMoComposeError,
    compose_floating_multiselect_workstation_marketplace_mo,
)
from substrate.notdiamond_shadow_advisory_compose import (
    NotDiamondShadowAdvisoryCompose,
    NotDiamondShadowAdvisoryComposeError,
    compose_notdiamond_shadow_advisory,
)


class NdShadowFloatingMultiselectWorkstationMoComposeError(ValueError):
    """Fail-closed validation for ND shadow + multi-select workstation MO."""


@dataclass(frozen=True)
class NdShadowFloatingMultiselectWorkstationMoCompose:
    session_id: str
    parent_asset_id: str
    nd_shadow: NotDiamondShadowAdvisoryCompose
    research_pack: FloatingMultiselectWorkstationMarketplaceMoCompose
    pack_ready: bool
    production_router_verdict: str
    live_router_authorized: bool
    live_dispatched: bool
    pack_dispatched: bool
    merge_executed: bool
    analysis_written: bool
    record_persisted: bool
    prompts_injected: bool
    purchase_executed: bool
    hosted: bool
    pdf_view_authorized: bool
    twin_written: bool
    live_execution_authorized: bool
    store_mutated: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "parent_asset_id": self.parent_asset_id,
            "nd_shadow": self.nd_shadow.to_dict(),
            "research_pack": self.research_pack.to_dict(),
            "pack_ready": self.pack_ready,
            "production_router_verdict": "REJECT",
            "live_router_authorized": False,
            "live_dispatched": False,
            "pack_dispatched": False,
            "merge_executed": False,
            "analysis_written": False,
            "record_persisted": False,
            "prompts_injected": False,
            "purchase_executed": False,
            "hosted": False,
            "pdf_view_authorized": False,
            "twin_written": False,
            "live_execution_authorized": False,
            "store_mutated": False,
            "notes": list(self.notes),
            "authority": (
                "nd_shadow_floating_multiselect_workstation_mo_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise NdShadowFloatingMultiselectWorkstationMoComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_nd_shadow_floating_multiselect_workstation_mo(
    *,
    nd_shadow: object,
    research_pack: object,
    operator_ack: object,
    require_both: object | None = None,
) -> NdShadowFloatingMultiselectWorkstationMoCompose:
    """ND shadow REJECT + multi-select workstation MO. Never live-routes."""
    if not isinstance(operator_ack, bool):
        raise NdShadowFloatingMultiselectWorkstationMoComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(nd_shadow, dict):
        raise NdShadowFloatingMultiselectWorkstationMoComposeError(
            "nd_shadow must be an object"
        )
    if not isinstance(research_pack, dict):
        raise NdShadowFloatingMultiselectWorkstationMoComposeError(
            "research_pack must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise NdShadowFloatingMultiselectWorkstationMoComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "production_router_verdict=REJECT — NotDiamond not production router (§16)",
        "live_router_authorized=false",
        "live_dispatched=false · pack_dispatched=false · merge_executed=false",
        "record_persisted=false · prompts_injected=false · purchase_executed=false",
        "live_execution_authorized=false · twin_written=false · store_mutated=false",
    ]

    try:
        shadow = compose_notdiamond_shadow_advisory(
            selected_model_id=nd_shadow.get("selected_model_id"),
            nd_recommended_model_id=nd_shadow.get("nd_recommended_model_id"),
            kill_switch_on=nd_shadow.get("kill_switch_on"),
            confidence=nd_shadow.get("confidence"),
            task=nd_shadow.get("task"),
            inventory_model_ids=nd_shadow.get("inventory_model_ids"),
        )
    except NotDiamondShadowAdvisoryComposeError as e:
        raise NdShadowFloatingMultiselectWorkstationMoComposeError(
            str(e)
        ) from e
    notes.extend(f"[nd_shadow] {n}" for n in shadow.notes)

    if shadow.production_router_verdict != "REJECT":
        raise NdShadowFloatingMultiselectWorkstationMoComposeError(
            "invariant: production_router_verdict must be REJECT"
        )
    if shadow.live_router_authorized is not False:
        raise NdShadowFloatingMultiselectWorkstationMoComposeError(
            "invariant: live_router_authorized must remain false"
        )

    try:
        research = compose_floating_multiselect_workstation_marketplace_mo(
            multiselect=research_pack.get("multiselect"),
            workstation_marketplace=research_pack.get(
                "workstation_marketplace"
            ),
            operator_ack=operator_ack,
            require_both=research_pack.get("require_both"),
        )
    except FloatingMultiselectWorkstationMarketplaceMoComposeError as e:
        raise NdShadowFloatingMultiselectWorkstationMoComposeError(
            str(e)
        ) from e
    notes.extend(f"[research_pack] {n}" for n in research.notes)

    session = _require_nonempty(research.session_id, field="session_id")
    parent = _require_nonempty(
        research.parent_asset_id, field="parent_asset_id"
    )

    if require:
        pack_ready = (
            research.pack_ready is True
            and shadow.live_router_authorized is False
            and shadow.production_router_verdict == "REJECT"
            and operator_ack is True
        )
    else:
        pack_ready = (
            operator_ack is True
            and shadow.production_router_verdict == "REJECT"
            and (research.pack_ready is True or shadow.shadow_visible is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — research pack ready + ND production REJECT held; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — research_pack, ND invariant, or operator_ack gate open"
        )

    if (
        research.live_dispatched is not False
        or research.live_execution_authorized is not False
        or research.purchase_executed is not False
        or research.record_persisted is not False
        or research.pack_dispatched is not False
        or research.prompts_injected is not False
    ):
        raise NdShadowFloatingMultiselectWorkstationMoComposeError(
            "invariant: honesty flags must remain false"
        )

    notes.extend(
        (
            "production_router_verdict=REJECT",
            "live_router_authorized=false",
            "live_dispatched=false",
            "pack_dispatched=false",
            "merge_executed=false",
            "analysis_written=false",
            "record_persisted=false",
            "prompts_injected=false",
            "purchase_executed=false",
            "hosted=false",
            "pdf_view_authorized=false",
            "twin_written=false",
            "live_execution_authorized=false",
            "store_mutated=false",
        )
    )

    return NdShadowFloatingMultiselectWorkstationMoCompose(
        session_id=session,
        parent_asset_id=parent,
        nd_shadow=shadow,
        research_pack=research,
        pack_ready=pack_ready,
        production_router_verdict="REJECT",
        live_router_authorized=False,
        live_dispatched=False,
        pack_dispatched=False,
        merge_executed=False,
        analysis_written=False,
        record_persisted=False,
        prompts_injected=False,
        purchase_executed=False,
        hosted=False,
        pdf_view_authorized=False,
        twin_written=False,
        live_execution_authorized=False,
        store_mutated=False,
        notes=tuple(notes),
        authority=(
            "nd_shadow_floating_multiselect_workstation_mo_compose_advisory"
        ),
    )


def format_nd_shadow_floating_multiselect_workstation_mo_summary(
    c: NdShadowFloatingMultiselectWorkstationMoCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"research_ready={c.research_pack.pack_ready} · "
        f"shadow_visible={c.nd_shadow.shadow_visible} · "
        f"verdict={c.production_router_verdict} · "
        f"live_router_authorized=false · live_dispatched=false · "
        f"purchase_executed=false · live_execution_authorized=false"
    )


__all__ = [
    "NdShadowFloatingMultiselectWorkstationMoCompose",
    "NdShadowFloatingMultiselectWorkstationMoComposeError",
    "compose_nd_shadow_floating_multiselect_workstation_mo",
    "format_nd_shadow_floating_multiselect_workstation_mo_summary",
]
