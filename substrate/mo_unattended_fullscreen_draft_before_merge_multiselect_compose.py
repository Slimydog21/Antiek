"""MO unattended package over fullscreen draft multi-select model decision (pure).

live_execution_authorized always False.
live_dispatched / merge_executed / draft_written always False.
live_router_authorized / secrets_stored / remote_index_queried always False.
pdf_primary always False.
production_router_verdict always REJECT.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.fullscreen_draft_before_merge_floating_multiselect_compose import (
    FullscreenDraftBeforeMergeFloatingMultiselectCompose,
    FullscreenDraftBeforeMergeFloatingMultiselectComposeError,
    compose_fullscreen_draft_before_merge_floating_multiselect,
)
from substrate.midnight_oil_unattended_package_compose import (
    MidnightOilUnattendedPackageCompose,
    MidnightOilUnattendedPackageComposeError,
    compose_midnight_oil_unattended_package,
)


class MoUnattendedFullscreenDraftBeforeMergeMultiselectComposeError(ValueError):
    """Fail-closed validation for MO unattended + fullscreen draft multi-select pack."""


@dataclass(frozen=True)
class MoUnattendedFullscreenDraftBeforeMergeMultiselectCompose:
    session_id: str
    parent_asset_id: str
    week_id: str
    asset_id: str
    title: str
    account_id: str
    mo: MidnightOilUnattendedPackageCompose
    fullscreen_pack: FullscreenDraftBeforeMergeFloatingMultiselectCompose
    pack_ready: bool
    live_execution_authorized: bool
    live_dispatched: bool
    pack_dispatched: bool
    merge_executed: bool
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
            "mo": self.mo.to_dict(),
            "fullscreen_pack": self.fullscreen_pack.to_dict(),
            "pack_ready": self.pack_ready,
            "live_execution_authorized": False,
            "live_dispatched": False,
            "pack_dispatched": False,
            "merge_executed": False,
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
                "mo_unattended_fullscreen_draft_before_merge_multiselect_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MoUnattendedFullscreenDraftBeforeMergeMultiselectComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_mo_unattended_fullscreen_draft_before_merge_multiselect(
    *,
    mo: object,
    fullscreen_pack: object,
    operator_ack: object,
    require_both: object | None = None,
) -> MoUnattendedFullscreenDraftBeforeMergeMultiselectCompose:
    """MO unattended + fullscreen draft multi-select. Never live-executes."""
    if not isinstance(operator_ack, bool):
        raise MoUnattendedFullscreenDraftBeforeMergeMultiselectComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(mo, dict):
        raise MoUnattendedFullscreenDraftBeforeMergeMultiselectComposeError(
            "mo must be an object"
        )
    if not isinstance(fullscreen_pack, dict):
        raise MoUnattendedFullscreenDraftBeforeMergeMultiselectComposeError(
            "fullscreen_pack must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise MoUnattendedFullscreenDraftBeforeMergeMultiselectComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "live_execution_authorized=false — unattended package never launches workers",
        "live_dispatched=false · merge_executed=false · draft_written=false",
        "live_router_authorized=false · secrets_stored=false · remote_index_queried=false",
        "production_router_verdict=REJECT",
    ]

    try:
        mo_c = compose_midnight_oil_unattended_package(
            operator_id=mo.get("operator_id"),
            work_minutes=mo.get("work_minutes"),
            goals=mo.get("goals"),
            operator_ack=operator_ack,
            unattended_ack=mo.get("unattended_ack"),
            spend_consent=mo.get("spend_consent"),
            usd_per_hour=mo.get("usd_per_hour"),
            approved_ceiling_usd=mo.get("approved_ceiling_usd"),
            brief_dispatch_ready=mo.get("brief_dispatch_ready"),
        )
    except MidnightOilUnattendedPackageComposeError as e:
        raise MoUnattendedFullscreenDraftBeforeMergeMultiselectComposeError(
            str(e)
        ) from e
    notes.extend(f"[mo] {n}" for n in mo_c.notes)

    try:
        fs = compose_fullscreen_draft_before_merge_floating_multiselect(
            fullscreen=fullscreen_pack.get("fullscreen"),
            draft_pack=fullscreen_pack.get("draft_pack"),
            operator_ack=operator_ack,
            require_both=fullscreen_pack.get("require_both"),
        )
    except FullscreenDraftBeforeMergeFloatingMultiselectComposeError as e:
        raise MoUnattendedFullscreenDraftBeforeMergeMultiselectComposeError(
            str(e)
        ) from e
    notes.extend(f"[fullscreen_pack] {n}" for n in fs.notes)

    session = _require_nonempty(fs.session_id, field="session_id")
    parent = _require_nonempty(fs.parent_asset_id, field="parent_asset_id")
    week = _require_nonempty(fs.week_id, field="week_id")
    asset = _require_nonempty(fs.asset_id, field="asset_id")
    title = _require_nonempty(fs.title, field="title")
    account = _require_nonempty(fs.account_id, field="account_id")

    if require:
        pack_ready = (
            mo_c.unattended_package_ready is True
            and fs.pack_ready is True
            and mo_c.live_execution_authorized is False
            and fs.live_dispatched is False
            and fs.merge_executed is False
            and fs.draft_written is False
            and fs.live_router_authorized is False
            and fs.secrets_stored is False
            and fs.remote_index_queried is False
            and fs.pdf_primary is False
            and fs.production_router_verdict == "REJECT"
            and operator_ack is True
        )
    else:
        pack_ready = (
            operator_ack is True
            and mo_c.live_execution_authorized is False
            and fs.production_router_verdict == "REJECT"
            and fs.pdf_primary is False
            and (
                mo_c.unattended_package_ready is True or fs.pack_ready is True
            )
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — MO unattended + fullscreen draft multi-select "
            "ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — mo, fullscreen_pack, or operator_ack gate open"
        )

    if (
        mo_c.live_execution_authorized is not False
        or fs.live_dispatched is not False
        or fs.merge_executed is not False
        or fs.draft_written is not False
        or fs.live_router_authorized is not False
        or fs.secrets_stored is not False
        or fs.remote_index_queried is not False
        or fs.pdf_primary is not False
        or fs.production_router_verdict != "REJECT"
    ):
        raise MoUnattendedFullscreenDraftBeforeMergeMultiselectComposeError(
            "invariant: honesty flags must remain false / REJECT"
        )

    notes.extend(
        (
            "live_execution_authorized=false",
            "live_dispatched=false",
            "pack_dispatched=false",
            "merge_executed=false",
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

    return MoUnattendedFullscreenDraftBeforeMergeMultiselectCompose(
        session_id=session,
        parent_asset_id=parent,
        week_id=week,
        asset_id=asset,
        title=title,
        account_id=account,
        mo=mo_c,
        fullscreen_pack=fs,
        pack_ready=pack_ready,
        live_execution_authorized=False,
        live_dispatched=False,
        pack_dispatched=False,
        merge_executed=False,
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
            "mo_unattended_fullscreen_draft_before_merge_multiselect_compose_advisory"
        ),
    )


def format_mo_unattended_fullscreen_draft_before_merge_multiselect_summary(
    c: MoUnattendedFullscreenDraftBeforeMergeMultiselectCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"mo_ready={c.mo.unattended_package_ready} · "
        f"fullscreen_ready={c.fullscreen_pack.pack_ready} · "
        f"verdict={c.production_router_verdict} · "
        "live_execution_authorized=false · merge_executed=false · draft_written=false"
    )


__all__ = [
    "MoUnattendedFullscreenDraftBeforeMergeMultiselectCompose",
    "MoUnattendedFullscreenDraftBeforeMergeMultiselectComposeError",
    "compose_mo_unattended_fullscreen_draft_before_merge_multiselect",
    "format_mo_unattended_fullscreen_draft_before_merge_multiselect_summary",
]
