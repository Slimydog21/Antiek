"""Floating multi-select → workstation marketplace MO pack (pure).

live_dispatched / pack_dispatched / merge_executed / analysis_written always False.
record_persisted / prompts_injected / purchase_executed / live_execution always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.floating_multi_select_collective_cohesive_compose import (
    FloatingMultiSelectCollectiveCohesiveCompose,
    FloatingMultiSelectCollectiveCohesiveComposeError,
    compose_floating_multi_select_collective_cohesive,
)
from substrate.workstation_insight_marketplace_highlight_mo_compose import (
    WorkstationInsightMarketplaceHighlightMoCompose,
    WorkstationInsightMarketplaceHighlightMoComposeError,
    compose_workstation_insight_marketplace_highlight_mo,
)


class FloatingMultiselectWorkstationMarketplaceMoComposeError(ValueError):
    """Fail-closed validation for multi-select → workstation marketplace MO."""


@dataclass(frozen=True)
class FloatingMultiselectWorkstationMarketplaceMoCompose:
    session_id: str
    parent_asset_id: str
    multiselect: FloatingMultiSelectCollectiveCohesiveCompose
    workstation_marketplace: WorkstationInsightMarketplaceHighlightMoCompose
    pack_ready: bool
    live_dispatched: bool
    pack_dispatched: bool
    merge_executed: bool
    analysis_written: bool
    record_persisted: bool
    prompts_injected: bool
    purchase_executed: bool
    charge_executed: bool
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
            "multiselect": self.multiselect.to_dict(),
            "workstation_marketplace": self.workstation_marketplace.to_dict(),
            "pack_ready": self.pack_ready,
            "live_dispatched": False,
            "pack_dispatched": False,
            "merge_executed": False,
            "analysis_written": False,
            "record_persisted": False,
            "prompts_injected": False,
            "purchase_executed": False,
            "charge_executed": False,
            "hosted": False,
            "pdf_view_authorized": False,
            "twin_written": False,
            "live_execution_authorized": False,
            "store_mutated": False,
            "notes": list(self.notes),
            "authority": (
                "floating_multiselect_workstation_marketplace_mo_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FloatingMultiselectWorkstationMarketplaceMoComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_floating_multiselect_workstation_marketplace_mo(
    *,
    multiselect: object,
    workstation_marketplace: object,
    operator_ack: object,
    require_both: object | None = None,
) -> FloatingMultiselectWorkstationMarketplaceMoCompose:
    """Multi-select cohesive + workstation marketplace MO. Never live-dispatches."""
    if not isinstance(operator_ack, bool):
        raise FloatingMultiselectWorkstationMarketplaceMoComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(multiselect, dict):
        raise FloatingMultiselectWorkstationMarketplaceMoComposeError(
            "multiselect must be an object"
        )
    if not isinstance(workstation_marketplace, dict):
        raise FloatingMultiselectWorkstationMarketplaceMoComposeError(
            "workstation_marketplace must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise FloatingMultiselectWorkstationMarketplaceMoComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "live_dispatched=false · pack_dispatched=false · merge_executed=false · analysis_written=false",
        "record_persisted=false · prompts_injected=false",
        "purchase_executed=false · hosted=false · pdf_view_authorized=false",
        "twin_written=false · live_execution_authorized=false · store_mutated=false",
    ]

    try:
        multi_pack = compose_floating_multi_select_collective_cohesive(
            session_id=multiselect.get("session_id"),
            parent_asset_id=multiselect.get("parent_asset_id"),
            members=multiselect.get("members"),
            selected_instance_ids=multiselect.get("selected_instance_ids"),
            pack_mode=multiselect.get("pack_mode"),
            cohesive_prompt=multiselect.get("cohesive_prompt"),
            operator_ack=operator_ack,
            extra_context=multiselect.get("extra_context"),
            analysis_kind=multiselect.get("analysis_kind"),
            extra_findings=multiselect.get("extra_findings"),
        )
    except FloatingMultiSelectCollectiveCohesiveComposeError as e:
        raise FloatingMultiselectWorkstationMarketplaceMoComposeError(
            str(e)
        ) from e
    notes.extend(f"[multiselect] {n}" for n in multi_pack.notes)

    try:
        wm_pack = compose_workstation_insight_marketplace_highlight_mo(
            records=workstation_marketplace.get("records"),
            marketplace_research=workstation_marketplace.get(
                "marketplace_research"
            ),
            operator_ack=operator_ack,
            require_both=workstation_marketplace.get("require_both"),
        )
    except WorkstationInsightMarketplaceHighlightMoComposeError as e:
        raise FloatingMultiselectWorkstationMarketplaceMoComposeError(
            str(e)
        ) from e
    notes.extend(f"[workstation_marketplace] {n}" for n in wm_pack.notes)

    session = _require_nonempty(multi_pack.session_id, field="session_id")
    parent = _require_nonempty(
        multi_pack.parent_asset_id, field="parent_asset_id"
    )

    if require:
        pack_ready = (
            multi_pack.pack_ready is True
            and wm_pack.pack_ready is True
            and operator_ack is True
        )
    else:
        pack_ready = operator_ack is True and (
            multi_pack.pack_ready is True or wm_pack.pack_ready is True
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — multi-select cohesive + workstation marketplace MO ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — multiselect, workstation_marketplace, or operator_ack gate open"
        )

    if (
        multi_pack.live_dispatched is not False
        or multi_pack.pack_dispatched is not False
        or multi_pack.merge_executed is not False
        or multi_pack.analysis_written is not False
        or wm_pack.record_persisted is not False
        or wm_pack.prompts_injected is not False
        or wm_pack.purchase_executed is not False
        or wm_pack.hosted is not False
        or wm_pack.live_execution_authorized is not False
        or wm_pack.twin_written is not False
    ):
        raise FloatingMultiselectWorkstationMarketplaceMoComposeError(
            "invariant: honesty flags must remain false"
        )

    notes.extend(
        (
            "live_dispatched=false",
            "pack_dispatched=false",
            "merge_executed=false",
            "analysis_written=false",
            "record_persisted=false",
            "prompts_injected=false",
            "purchase_executed=false",
            "charge_executed=false",
            "hosted=false",
            "pdf_view_authorized=false",
            "twin_written=false",
            "live_execution_authorized=false",
            "store_mutated=false",
        )
    )

    return FloatingMultiselectWorkstationMarketplaceMoCompose(
        session_id=session,
        parent_asset_id=parent,
        multiselect=multi_pack,
        workstation_marketplace=wm_pack,
        pack_ready=pack_ready,
        live_dispatched=False,
        pack_dispatched=False,
        merge_executed=False,
        analysis_written=False,
        record_persisted=False,
        prompts_injected=False,
        purchase_executed=False,
        charge_executed=False,
        hosted=False,
        pdf_view_authorized=False,
        twin_written=False,
        live_execution_authorized=False,
        store_mutated=False,
        notes=tuple(notes),
        authority=(
            "floating_multiselect_workstation_marketplace_mo_compose_advisory"
        ),
    )


def format_floating_multiselect_workstation_marketplace_mo_summary(
    c: FloatingMultiselectWorkstationMarketplaceMoCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"multiselect_ready={c.multiselect.pack_ready} · "
        f"workstation_marketplace_ready={c.workstation_marketplace.pack_ready} · "
        f"selected={c.multiselect.tray.selected_count} · "
        f"live_dispatched=false · pack_dispatched=false · "
        f"record_persisted=false · purchase_executed=false · live_execution_authorized=false"
    )


__all__ = [
    "FloatingMultiselectWorkstationMarketplaceMoCompose",
    "FloatingMultiselectWorkstationMarketplaceMoComposeError",
    "compose_floating_multiselect_workstation_marketplace_mo",
    "format_floating_multiselect_workstation_marketplace_mo_summary",
]
