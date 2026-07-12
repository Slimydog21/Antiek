"""MO price-ceiling + write twin settings draft pack (pure).

live_execution_authorized / charge_executed always False.
draft_written / analysis_written / merge_executed always False.
secrets_stored / inventory_mutated always False.
production_router_verdict always REJECT; live_router_authorized always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.midnight_oil_price_ceiling_approval_compose import (
    MidnightOilPriceCeilingApprovalCompose,
    MidnightOilPriceCeilingApprovalComposeError,
    compose_midnight_oil_price_ceiling_approval,
)
from substrate.write_twin_collective_settings_draft_fullscreen_nd_mo_compose import (
    WriteTwinCollectiveSettingsDraftFullscreenNdMoCompose,
    WriteTwinCollectiveSettingsDraftFullscreenNdMoComposeError,
    compose_write_twin_collective_settings_draft_fullscreen_nd_mo,
)


class MoPriceCeilingWriteTwinSettingsDraftComposeError(ValueError):
    """Fail-closed validation for MO price-ceiling + write twin settings pack."""


@dataclass(frozen=True)
class MoPriceCeilingWriteTwinSettingsDraftCompose:
    session_id: str
    parent_asset_id: str
    week_id: str
    operator_id: str
    mo: MidnightOilPriceCeilingApprovalCompose
    research_write: WriteTwinCollectiveSettingsDraftFullscreenNdMoCompose
    pack_ready: bool
    live_execution_authorized: bool
    charge_executed: bool
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
    twin_written: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "parent_asset_id": self.parent_asset_id,
            "week_id": self.week_id,
            "operator_id": self.operator_id,
            "mo": self.mo.to_dict(),
            "research_write": self.research_write.to_dict(),
            "pack_ready": self.pack_ready,
            "live_execution_authorized": False,
            "charge_executed": False,
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
            "twin_written": False,
            "notes": list(self.notes),
            "authority": (
                "mo_price_ceiling_write_twin_settings_draft_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MoPriceCeilingWriteTwinSettingsDraftComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_mo_price_ceiling_write_twin_settings_draft(
    *,
    mo: object,
    research_write: object,
    operator_ack: object,
    require_both: object | None = None,
) -> MoPriceCeilingWriteTwinSettingsDraftCompose:
    """MO price-ceiling + write twin settings pack. Never charges or launches."""
    if not isinstance(operator_ack, bool):
        raise MoPriceCeilingWriteTwinSettingsDraftComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(mo, dict):
        raise MoPriceCeilingWriteTwinSettingsDraftComposeError(
            "mo must be an object"
        )
    if not isinstance(research_write, dict):
        raise MoPriceCeilingWriteTwinSettingsDraftComposeError(
            "research_write must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise MoPriceCeilingWriteTwinSettingsDraftComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "live_execution_authorized=false · charge_executed=false",
        "draft_written=false · analysis_written=false · merge_executed=false",
        "secrets_stored=false · inventory_mutated=false",
        "production_router_verdict=REJECT · live_router_authorized=false",
    ]

    try:
        m = compose_midnight_oil_price_ceiling_approval(
            operator_id=mo.get("operator_id"),
            work_minutes=mo.get("work_minutes"),
            goals=mo.get("goals"),
            price_ceiling_ack=mo.get("price_ceiling_ack"),
            operator_ack=operator_ack,
            stage=mo.get("stage"),
            usd_per_hour=mo.get("usd_per_hour"),
            goal_intensity=mo.get("goal_intensity"),
            approved_ceiling_usd=mo.get("approved_ceiling_usd"),
            below_recommend_override=mo.get("below_recommend_override"),
            unattended_ack=mo.get("unattended_ack"),
            spend_consent=mo.get("spend_consent"),
        )
    except MidnightOilPriceCeilingApprovalComposeError as e:
        raise MoPriceCeilingWriteTwinSettingsDraftComposeError(str(e)) from e
    notes.extend(f"[mo] {n}" for n in m.notes)

    try:
        rw = compose_write_twin_collective_settings_draft_fullscreen_nd_mo(
            write=research_write.get("write"),
            settings_research=research_write.get("settings_research"),
            operator_ack=operator_ack,
            require_both=research_write.get("require_both"),
        )
    except WriteTwinCollectiveSettingsDraftFullscreenNdMoComposeError as e:
        raise MoPriceCeilingWriteTwinSettingsDraftComposeError(str(e)) from e
    notes.extend(f"[research_write] {n}" for n in rw.notes)

    session = _require_nonempty(rw.session_id, field="session_id")
    parent = _require_nonempty(rw.parent_asset_id, field="parent_asset_id")
    week = _require_nonempty(rw.week_id, field="week_id")
    operator = _require_nonempty(m.operator_id, field="operator_id")

    if require:
        pack_ready = (
            m.pack_ready is True
            and rw.pack_ready is True
            and rw.production_router_verdict == "REJECT"
            and m.live_execution_authorized is False
            and m.charge_executed is False
            and operator_ack is True
        )
    else:
        pack_ready = (
            operator_ack is True
            and rw.production_router_verdict == "REJECT"
            and m.charge_executed is False
            and (m.pack_ready is True or rw.pack_ready is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — MO price-ceiling + write twin settings draft ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — mo, research_write, or operator_ack gate open"
        )

    if (
        m.live_execution_authorized is not False
        or m.charge_executed is not False
        or rw.draft_written is not False
        or rw.analysis_written is not False
        or rw.merge_executed is not False
        or rw.secrets_stored is not False
        or rw.inventory_mutated is not False
        or rw.production_router_verdict != "REJECT"
        or rw.live_router_authorized is not False
    ):
        raise MoPriceCeilingWriteTwinSettingsDraftComposeError(
            "invariant: honesty flags must remain false"
        )

    notes.extend(
        (
            "live_execution_authorized=false",
            "charge_executed=false",
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
            "twin_written=false",
        )
    )

    return MoPriceCeilingWriteTwinSettingsDraftCompose(
        session_id=session,
        parent_asset_id=parent,
        week_id=week,
        operator_id=operator,
        mo=m,
        research_write=rw,
        pack_ready=pack_ready,
        live_execution_authorized=False,
        charge_executed=False,
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
        twin_written=False,
        notes=tuple(notes),
        authority="mo_price_ceiling_write_twin_settings_draft_compose_advisory",
    )


def format_mo_price_ceiling_write_twin_settings_draft_summary(
    c: MoPriceCeilingWriteTwinSettingsDraftCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"mo_ready={c.mo.pack_ready} · "
        f"ceiling_approved={c.mo.ceiling_approved} · "
        f"research_write_ready={c.research_write.pack_ready} · "
        f"verdict={c.production_router_verdict} · "
        f"charge_executed=false · live_execution_authorized=false"
    )


__all__ = [
    "MoPriceCeilingWriteTwinSettingsDraftCompose",
    "MoPriceCeilingWriteTwinSettingsDraftComposeError",
    "compose_mo_price_ceiling_write_twin_settings_draft",
    "format_mo_price_ceiling_write_twin_settings_draft_summary",
]
