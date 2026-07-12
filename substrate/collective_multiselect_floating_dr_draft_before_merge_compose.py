"""Collective multiselect over floating DR draft-before-merge MO price-ceiling (pure).

live_dispatched / pack_dispatched / merge_executed / analysis_written always False.
twin_written / draft_written / live_execution_authorized always False.
production_router_verdict always REJECT.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.floating_dr_draft_before_merge_mo_price_ceiling_compose import (
    FloatingDrDraftBeforeMergeMoPriceCeilingCompose,
    FloatingDrDraftBeforeMergeMoPriceCeilingComposeError,
    compose_floating_dr_draft_before_merge_mo_price_ceiling,
)
from substrate.floating_multi_select_collective_cohesive_compose import (
    FloatingMultiSelectCollectiveCohesiveCompose,
    FloatingMultiSelectCollectiveCohesiveComposeError,
    compose_floating_multi_select_collective_cohesive,
)


class CollectiveMultiselectFloatingDrDraftBeforeMergeComposeError(ValueError):
    """Fail-closed validation for collective multiselect + floating DR pack."""


@dataclass(frozen=True)
class CollectiveMultiselectFloatingDrDraftBeforeMergeCompose:
    session_id: str
    parent_asset_id: str
    week_id: str
    asset_id: str
    title: str
    account_id: str
    multiselect: FloatingMultiSelectCollectiveCohesiveCompose
    floating_dr_pack: FloatingDrDraftBeforeMergeMoPriceCeilingCompose
    session_aligned: bool
    parent_aligned: bool
    pack_ready: bool
    live_dispatched: bool
    pack_dispatched: bool
    merge_executed: bool
    analysis_written: bool
    twin_written: bool
    draft_written: bool
    live_execution_authorized: bool
    charge_executed: bool
    prompts_injected: bool
    live_router_authorized: bool
    secrets_stored: bool
    live_meter_read: bool
    remote_index_queried: bool
    backlog_mutated: bool
    store_mutated: bool
    suite_rewritten: bool
    pdf_view_authorized: bool
    pdf_primary: bool
    live_dispatch_authorized: bool
    inventory_mutated: bool
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
            "multiselect": self.multiselect.to_dict(),
            "floating_dr_pack": self.floating_dr_pack.to_dict(),
            "session_aligned": self.session_aligned,
            "parent_aligned": self.parent_aligned,
            "pack_ready": self.pack_ready,
            "live_dispatched": False,
            "pack_dispatched": False,
            "merge_executed": False,
            "analysis_written": False,
            "twin_written": False,
            "draft_written": False,
            "live_execution_authorized": False,
            "charge_executed": False,
            "prompts_injected": False,
            "live_router_authorized": False,
            "secrets_stored": False,
            "live_meter_read": False,
            "remote_index_queried": False,
            "backlog_mutated": False,
            "store_mutated": False,
            "suite_rewritten": False,
            "pdf_view_authorized": False,
            "pdf_primary": False,
            "live_dispatch_authorized": False,
            "inventory_mutated": False,
            "record_persisted": False,
            "purchase_executed": False,
            "hosted": False,
            "remote_fetched": False,
            "production_router_verdict": "REJECT",
            "notes": list(self.notes),
            "authority": (
                "collective_multiselect_floating_dr_draft_before_merge_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CollectiveMultiselectFloatingDrDraftBeforeMergeComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_collective_multiselect_floating_dr_draft_before_merge(
    *,
    multiselect: object,
    floating_dr_pack: object,
    operator_ack: object,
    require_both: object | None = None,
) -> CollectiveMultiselectFloatingDrDraftBeforeMergeCompose:
    """Collective multiselect on floating DR draft-before-merge. Never dispatches."""
    if not isinstance(operator_ack, bool):
        raise CollectiveMultiselectFloatingDrDraftBeforeMergeComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(multiselect, dict):
        raise CollectiveMultiselectFloatingDrDraftBeforeMergeComposeError(
            "multiselect must be an object"
        )
    if not isinstance(floating_dr_pack, dict):
        raise CollectiveMultiselectFloatingDrDraftBeforeMergeComposeError(
            "floating_dr_pack must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise CollectiveMultiselectFloatingDrDraftBeforeMergeComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "live_dispatched=false · pack_dispatched=false · merge_executed=false",
        "analysis_written=false · twin_written=false · draft_written=false",
        "production_router_verdict=REJECT",
    ]

    try:
        ms = compose_floating_multi_select_collective_cohesive(
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
        raise CollectiveMultiselectFloatingDrDraftBeforeMergeComposeError(
            str(e)
        ) from e
    notes.extend(f"[multiselect] {n}" for n in ms.notes)

    try:
        fdr = compose_floating_dr_draft_before_merge_mo_price_ceiling(
            highlight_surface=floating_dr_pack.get("highlight_surface"),
            draft_pack=floating_dr_pack.get("draft_pack"),
            operator_ack=operator_ack,
            require_both=floating_dr_pack.get("require_both"),
        )
    except FloatingDrDraftBeforeMergeMoPriceCeilingComposeError as e:
        raise CollectiveMultiselectFloatingDrDraftBeforeMergeComposeError(
            str(e)
        ) from e
    notes.extend(f"[floating_dr_pack] {n}" for n in fdr.notes)

    session = _require_nonempty(ms.session_id, field="session_id")
    parent = _require_nonempty(ms.parent_asset_id, field="parent_asset_id")
    week = _require_nonempty(fdr.week_id, field="week_id")
    asset = _require_nonempty(fdr.asset_id, field="asset_id")
    title = _require_nonempty(fdr.title, field="title")
    account = _require_nonempty(fdr.account_id, field="account_id")

    session_aligned = fdr.session_id == session
    parent_aligned = fdr.parent_asset_id == parent or fdr.asset_id == parent
    if not session_aligned:
        notes.append(
            "session_id mismatch between multiselect and floating_dr_pack — "
            "pack_ready blocked"
        )
    else:
        notes.append("session_aligned=true")
    if not parent_aligned:
        notes.append(
            "parent_asset_id mismatch between multiselect and floating_dr_pack — "
            "pack_ready blocked"
        )
    else:
        notes.append("parent_aligned=true")

    if require:
        pack_ready = (
            session_aligned is True
            and parent_aligned is True
            and ms.pack_ready is True
            and fdr.pack_ready is True
            and fdr.production_router_verdict == "REJECT"
            and ms.live_dispatched is False
            and ms.pack_dispatched is False
            and ms.merge_executed is False
            and ms.analysis_written is False
            and fdr.live_dispatched is False
            and fdr.merge_executed is False
            and fdr.twin_written is False
            and fdr.draft_written is False
            and fdr.live_execution_authorized is False
            and fdr.charge_executed is False
            and fdr.remote_index_queried is False
            and fdr.pdf_primary is False
            and fdr.live_router_authorized is False
            and fdr.secrets_stored is False
            and operator_ack is True
        )
    else:
        pack_ready = (
            session_aligned is True
            and parent_aligned is True
            and operator_ack is True
            and fdr.production_router_verdict == "REJECT"
            and fdr.pdf_primary is False
            and ms.live_dispatched is False
            and (ms.pack_ready is True or fdr.pack_ready is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — collective multiselect + floating DR "
            "draft-before-merge ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — multiselect, floating_dr_pack, alignment, or "
            "operator_ack gate open"
        )

    if (
        ms.live_dispatched is not False
        or ms.pack_dispatched is not False
        or ms.merge_executed is not False
        or ms.analysis_written is not False
        or fdr.live_dispatched is not False
        or fdr.merge_executed is not False
        or fdr.twin_written is not False
        or fdr.draft_written is not False
        or fdr.live_execution_authorized is not False
        or fdr.charge_executed is not False
        or fdr.remote_index_queried is not False
        or fdr.pdf_primary is not False
        or fdr.live_router_authorized is not False
        or fdr.secrets_stored is not False
        or fdr.production_router_verdict != "REJECT"
    ):
        raise CollectiveMultiselectFloatingDrDraftBeforeMergeComposeError(
            "invariant: honesty flags must remain false / REJECT"
        )

    notes.extend(
        (
            "live_dispatched=false",
            "pack_dispatched=false",
            "merge_executed=false",
            "analysis_written=false",
            "twin_written=false",
            "draft_written=false",
            "live_execution_authorized=false",
            "charge_executed=false",
            "prompts_injected=false",
            "live_router_authorized=false",
            "secrets_stored=false",
            "live_meter_read=false",
            "remote_index_queried=false",
            "backlog_mutated=false",
            "store_mutated=false",
            "suite_rewritten=false",
            "pdf_view_authorized=false",
            "pdf_primary=false",
            "live_dispatch_authorized=false",
            "inventory_mutated=false",
            "record_persisted=false",
            "purchase_executed=false",
            "hosted=false",
            "remote_fetched=false",
            "production_router_verdict=REJECT",
        )
    )

    return CollectiveMultiselectFloatingDrDraftBeforeMergeCompose(
        session_id=session,
        parent_asset_id=parent,
        week_id=week,
        asset_id=asset,
        title=title,
        account_id=account,
        multiselect=ms,
        floating_dr_pack=fdr,
        session_aligned=session_aligned,
        parent_aligned=parent_aligned,
        pack_ready=pack_ready,
        live_dispatched=False,
        pack_dispatched=False,
        merge_executed=False,
        analysis_written=False,
        twin_written=False,
        draft_written=False,
        live_execution_authorized=False,
        charge_executed=False,
        prompts_injected=False,
        live_router_authorized=False,
        secrets_stored=False,
        live_meter_read=False,
        remote_index_queried=False,
        backlog_mutated=False,
        store_mutated=False,
        suite_rewritten=False,
        pdf_view_authorized=False,
        pdf_primary=False,
        live_dispatch_authorized=False,
        inventory_mutated=False,
        record_persisted=False,
        purchase_executed=False,
        hosted=False,
        remote_fetched=False,
        production_router_verdict="REJECT",
        notes=tuple(notes),
        authority=(
            "collective_multiselect_floating_dr_draft_before_merge_compose_advisory"
        ),
    )


def format_collective_multiselect_floating_dr_draft_before_merge_summary(
    c: CollectiveMultiselectFloatingDrDraftBeforeMergeCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"multi_ready={c.multiselect.pack_ready} · "
        f"float_ready={c.floating_dr_pack.pack_ready} · "
        f"mode={c.multiselect.pack_mode} · "
        f"session_aligned={c.session_aligned} · "
        f"parent_aligned={c.parent_aligned} · "
        f"verdict={c.production_router_verdict} · "
        "live_dispatched=false · pack_dispatched=false · analysis_written=false"
    )


__all__ = [
    "CollectiveMultiselectFloatingDrDraftBeforeMergeCompose",
    "CollectiveMultiselectFloatingDrDraftBeforeMergeComposeError",
    "compose_collective_multiselect_floating_dr_draft_before_merge",
    "format_collective_multiselect_floating_dr_draft_before_merge_summary",
]
