"""NotDiamond shadow REJECT re-affirmation over twin presentation pack.

live_router_authorized always False.
twin_written / merge_executed / purchase_executed always False.
production_router_verdict always REJECT.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.notdiamond_shadow_advisory_compose import (
    NotDiamondShadowAdvisoryCompose,
    NotDiamondShadowAdvisoryComposeError,
    compose_notdiamond_shadow_advisory,
)
from substrate.recursive_twin_presentation_competition_dr_source_attach_compose import (
    RecursiveTwinPresentationCompetitionDrSourceAttachCompose,
    RecursiveTwinPresentationCompetitionDrSourceAttachComposeError,
    compose_recursive_twin_presentation_competition_dr_source_attach,
)


class NdShadowTwinPresentationCompetitionDrSourceAttachComposeError(ValueError):
    """Fail-closed validation for ND shadow + twin presentation pack."""


@dataclass(frozen=True)
class NdShadowTwinPresentationCompetitionDrSourceAttachCompose:
    parent_asset_id: str
    session_id: str
    title: str
    account_id: str
    week_id: str
    asset_id: str
    nd_shadow: NotDiamondShadowAdvisoryCompose
    twin_presentation: RecursiveTwinPresentationCompetitionDrSourceAttachCompose
    pack_ready: bool
    live_router_authorized: bool
    twin_written: bool
    prompts_injected: bool
    merge_executed: bool
    live_dispatch_authorized: bool
    remote_fetched: bool
    backlog_mutated: bool
    purchase_executed: bool
    hosted: bool
    pdf_view_authorized: bool
    pdf_primary: bool
    secrets_stored: bool
    live_meter_read: bool
    store_mutated: bool
    suite_rewritten: bool
    live_execution_authorized: bool
    charge_executed: bool
    remote_index_queried: bool
    inventory_mutated: bool
    live_dispatched: bool
    pack_dispatched: bool
    draft_written: bool
    record_persisted: bool
    analysis_written: bool
    production_router_verdict: str
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "parent_asset_id": self.parent_asset_id,
            "session_id": self.session_id,
            "title": self.title,
            "account_id": self.account_id,
            "week_id": self.week_id,
            "asset_id": self.asset_id,
            "nd_shadow": self.nd_shadow.to_dict(),
            "twin_presentation": self.twin_presentation.to_dict(),
            "pack_ready": self.pack_ready,
            "live_router_authorized": False,
            "twin_written": False,
            "prompts_injected": False,
            "merge_executed": False,
            "live_dispatch_authorized": False,
            "remote_fetched": False,
            "backlog_mutated": False,
            "purchase_executed": False,
            "hosted": False,
            "pdf_view_authorized": False,
            "pdf_primary": False,
            "secrets_stored": False,
            "live_meter_read": False,
            "store_mutated": False,
            "suite_rewritten": False,
            "live_execution_authorized": False,
            "charge_executed": False,
            "remote_index_queried": False,
            "inventory_mutated": False,
            "live_dispatched": False,
            "pack_dispatched": False,
            "draft_written": False,
            "record_persisted": False,
            "analysis_written": False,
            "production_router_verdict": "REJECT",
            "notes": list(self.notes),
            "authority": (
                "nd_shadow_twin_presentation_competition_dr_source_attach_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise NdShadowTwinPresentationCompetitionDrSourceAttachComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_nd_shadow_twin_presentation_competition_dr_source_attach(
    *,
    nd_shadow: object,
    twin_presentation: object,
    operator_ack: object,
    require_both: object | None = None,
) -> NdShadowTwinPresentationCompetitionDrSourceAttachCompose:
    """ND shadow REJECT on twin presentation pack. Never live-routes."""
    if not isinstance(operator_ack, bool):
        raise NdShadowTwinPresentationCompetitionDrSourceAttachComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(nd_shadow, dict):
        raise NdShadowTwinPresentationCompetitionDrSourceAttachComposeError(
            "nd_shadow must be an object"
        )
    if not isinstance(twin_presentation, dict):
        raise NdShadowTwinPresentationCompetitionDrSourceAttachComposeError(
            "twin_presentation must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise NdShadowTwinPresentationCompetitionDrSourceAttachComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "production_router_verdict=REJECT — NotDiamond is not production "
        "router (§16)",
        "live_router_authorized=false · twin_written=false · "
        "merge_executed=false",
        "purchase_executed=false · remote_fetched=false",
    ]

    try:
        nd = compose_notdiamond_shadow_advisory(
            selected_model_id=nd_shadow.get("selected_model_id"),
            nd_recommended_model_id=nd_shadow.get("nd_recommended_model_id"),
            kill_switch_on=nd_shadow.get("kill_switch_on"),
            confidence=nd_shadow.get("confidence"),
            task=nd_shadow.get("task"),
            inventory_model_ids=nd_shadow.get("inventory_model_ids"),
        )
    except NotDiamondShadowAdvisoryComposeError as e:
        raise NdShadowTwinPresentationCompetitionDrSourceAttachComposeError(str(e)) from e
    notes.extend(f"[nd_shadow] {n}" for n in nd.notes)

    if nd.production_router_verdict != "REJECT":
        raise NdShadowTwinPresentationCompetitionDrSourceAttachComposeError(
            "invariant: production_router_verdict must be REJECT"
        )
    if nd.live_router_authorized is not False:
        raise NdShadowTwinPresentationCompetitionDrSourceAttachComposeError(
            "invariant: live_router_authorized must be false"
        )

    try:
        twin = compose_recursive_twin_presentation_competition_dr_source_attach(
            twin=twin_presentation.get("twin"),
            presentation=twin_presentation.get("presentation"),
            competition_pack=twin_presentation.get("competition_pack"),
            operator_ack=operator_ack,
            require_both=twin_presentation.get("require_both"),
        )
    except RecursiveTwinPresentationCompetitionDrSourceAttachComposeError as e:
        raise NdShadowTwinPresentationCompetitionDrSourceAttachComposeError(str(e)) from e
    notes.extend(f"[twin_presentation] {n}" for n in twin.notes)

    parent = _require_nonempty(twin.parent_asset_id, field="parent_asset_id")
    session = _require_nonempty(twin.session_id, field="session_id")
    title = _require_nonempty(twin.title, field="title")
    account = _require_nonempty(twin.account_id, field="account_id")
    week = _require_nonempty(twin.week_id, field="week_id")
    asset = _require_nonempty(twin.asset_id, field="asset_id")

    nd_gate = (
        nd.production_router_verdict == "REJECT"
        and nd.live_router_authorized is False
    )

    if require:
        pack_ready = (
            nd_gate
            and twin.pack_ready is True
            and twin.twin_written is False
            and twin.merge_executed is False
            and twin.purchase_executed is False
            and twin.live_dispatch_authorized is False
            and twin.production_router_verdict == "REJECT"
            and operator_ack is True
        )
    else:
        pack_ready = (
            nd_gate
            and operator_ack is True
            and twin.purchase_executed is False
            and twin.production_router_verdict == "REJECT"
            and (twin.pack_ready is True or nd.shadow_visible is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — ND shadow REJECT re-affirmed on twin "
            "presentation pack; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — nd_shadow, twin_presentation, or operator_ack "
            "gate open"
        )

    if (
        nd.live_router_authorized is not False
        or nd.production_router_verdict != "REJECT"
        or twin.twin_written is not False
        or twin.merge_executed is not False
        or twin.purchase_executed is not False
        or twin.live_dispatch_authorized is not False
        or twin.production_router_verdict != "REJECT"
    ):
        raise NdShadowTwinPresentationCompetitionDrSourceAttachComposeError(
            "invariant: honesty flags must remain false / REJECT"
        )

    notes.extend(
        (
            "live_router_authorized=false",
            "twin_written=false",
            "prompts_injected=false",
            "merge_executed=false",
            "live_dispatch_authorized=false",
            "remote_fetched=false",
            "backlog_mutated=false",
            "purchase_executed=false",
            "hosted=false",
            "pdf_view_authorized=false",
            "pdf_primary=false",
            "secrets_stored=false",
            "live_meter_read=false",
            "store_mutated=false",
            "suite_rewritten=false",
            "live_execution_authorized=false",
            "charge_executed=false",
            "remote_index_queried=false",
            "inventory_mutated=false",
            "live_dispatched=false",
            "pack_dispatched=false",
            "draft_written=false",
            "record_persisted=false",
            "analysis_written=false",
            "production_router_verdict=REJECT",
        )
    )

    return NdShadowTwinPresentationCompetitionDrSourceAttachCompose(
        parent_asset_id=parent,
        session_id=session,
        title=title,
        account_id=account,
        week_id=week,
        asset_id=asset,
        nd_shadow=nd,
        twin_presentation=twin,
        pack_ready=pack_ready,
        live_router_authorized=False,
        twin_written=False,
        prompts_injected=False,
        merge_executed=False,
        live_dispatch_authorized=False,
        remote_fetched=False,
        backlog_mutated=False,
        purchase_executed=False,
        hosted=False,
        pdf_view_authorized=False,
        pdf_primary=False,
        secrets_stored=False,
        live_meter_read=False,
        store_mutated=False,
        suite_rewritten=False,
        live_execution_authorized=False,
        charge_executed=False,
        remote_index_queried=False,
        inventory_mutated=False,
        live_dispatched=False,
        pack_dispatched=False,
        draft_written=False,
        record_persisted=False,
        analysis_written=False,
        production_router_verdict="REJECT",
        notes=tuple(notes),
        authority="nd_shadow_twin_presentation_competition_dr_source_attach_compose_advisory",
    )


def format_nd_shadow_twin_presentation_competition_dr_source_attach_summary(
    c: NdShadowTwinPresentationCompetitionDrSourceAttachCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"nd_visible={c.nd_shadow.shadow_visible} · "
        f"suggested={c.nd_shadow.suggested_model_id} · "
        f"twin_presentation_ready={c.twin_presentation.pack_ready} · "
        f"view_mode={c.twin_presentation.presentation.view_mode} · "
        f"verdict={c.production_router_verdict} · "
        f"live_router_authorized=false · twin_written=false · "
        f"purchase_executed=false"
    )


__all__ = [
    "NdShadowTwinPresentationCompetitionDrSourceAttachCompose",
    "NdShadowTwinPresentationCompetitionDrSourceAttachComposeError",
    "compose_nd_shadow_twin_presentation_competition_dr_source_attach",
    "format_nd_shadow_twin_presentation_competition_dr_source_attach_summary",
]
