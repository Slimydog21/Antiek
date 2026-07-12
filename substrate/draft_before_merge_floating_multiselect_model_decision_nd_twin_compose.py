"""Draft-before-full-merge over floating multi-select model decision ND twin (pure).

draft_written / merge_executed always False.
live_dispatched / pack_dispatched always False.
live_router_authorized / secrets_stored / live_meter_read always False.
remote_index_queried / pdf_primary always False.
production_router_verdict always REJECT.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.floating_draft_before_full_merge_gate_compose import (
    FloatingDraftBeforeFullMergeGateCompose,
    FloatingDraftBeforeFullMergeGateComposeError,
    compose_floating_draft_before_full_merge_gate,
)
from substrate.floating_multiselect_model_decision_nd_twin_compose import (
    FloatingMultiselectModelDecisionNdTwinCompose,
    FloatingMultiselectModelDecisionNdTwinComposeError,
    compose_floating_multiselect_model_decision_nd_twin,
)


class DraftBeforeMergeFloatingMultiselectModelDecisionNdTwinComposeError(ValueError):
    """Fail-closed validation for draft-before-merge + multi-select model decision pack."""


@dataclass(frozen=True)
class DraftBeforeMergeFloatingMultiselectModelDecisionNdTwinCompose:
    session_id: str
    parent_asset_id: str
    week_id: str
    asset_id: str
    title: str
    account_id: str
    draft_gate: FloatingDraftBeforeFullMergeGateCompose
    multi_pack: FloatingMultiselectModelDecisionNdTwinCompose
    session_aligned: bool
    parent_aligned: bool
    pack_ready: bool
    draft_written: bool
    merge_executed: bool
    live_dispatched: bool
    pack_dispatched: bool
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
    live_execution_authorized: bool
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
            "draft_gate": self.draft_gate.to_dict(),
            "multi_pack": self.multi_pack.to_dict(),
            "session_aligned": self.session_aligned,
            "parent_aligned": self.parent_aligned,
            "pack_ready": self.pack_ready,
            "draft_written": False,
            "merge_executed": False,
            "live_dispatched": False,
            "pack_dispatched": False,
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
            "live_execution_authorized": False,
            "charge_executed": False,
            "record_persisted": False,
            "purchase_executed": False,
            "hosted": False,
            "remote_fetched": False,
            "production_router_verdict": "REJECT",
            "notes": list(self.notes),
            "authority": (
                "draft_before_merge_floating_multiselect_model_decision_nd_twin_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DraftBeforeMergeFloatingMultiselectModelDecisionNdTwinComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_draft_before_merge_floating_multiselect_model_decision_nd_twin(
    *,
    draft_gate: object,
    multi_pack: object,
    operator_ack: object,
    require_both: object | None = None,
) -> DraftBeforeMergeFloatingMultiselectModelDecisionNdTwinCompose:
    """Draft-before-merge + floating multi-select model decision. Never writes/merges."""
    if not isinstance(operator_ack, bool):
        raise DraftBeforeMergeFloatingMultiselectModelDecisionNdTwinComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(draft_gate, dict):
        raise DraftBeforeMergeFloatingMultiselectModelDecisionNdTwinComposeError(
            "draft_gate must be an object"
        )
    if not isinstance(multi_pack, dict):
        raise DraftBeforeMergeFloatingMultiselectModelDecisionNdTwinComposeError(
            "multi_pack must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise DraftBeforeMergeFloatingMultiselectModelDecisionNdTwinComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "draft_written=false · merge_executed=false · live_dispatched=false",
        "pack_dispatched=false · live_router_authorized=false · secrets_stored=false",
        "remote_index_queried=false · pdf_primary=false",
        "production_router_verdict=REJECT",
    ]

    try:
        dg = compose_floating_draft_before_full_merge_gate(
            session_id=draft_gate.get("session_id"),
            parent_asset_id=draft_gate.get("parent_asset_id"),
            sources=draft_gate.get("sources"),
            stage=draft_gate.get("stage"),
            operator_ack=operator_ack,
            parent_excerpt=draft_gate.get("parent_excerpt"),
            full_merge_ack=draft_gate.get("full_merge_ack"),
        )
    except FloatingDraftBeforeFullMergeGateComposeError as e:
        raise DraftBeforeMergeFloatingMultiselectModelDecisionNdTwinComposeError(
            str(e)
        ) from e
    notes.extend(f"[draft_gate] {n}" for n in dg.notes)

    try:
        mp = compose_floating_multiselect_model_decision_nd_twin(
            multiselect=multi_pack.get("multiselect"),
            decision_pack=multi_pack.get("decision_pack"),
            operator_ack=operator_ack,
            require_both=multi_pack.get("require_both"),
        )
    except FloatingMultiselectModelDecisionNdTwinComposeError as e:
        raise DraftBeforeMergeFloatingMultiselectModelDecisionNdTwinComposeError(
            str(e)
        ) from e
    notes.extend(f"[multi_pack] {n}" for n in mp.notes)

    session = _require_nonempty(dg.session_id, field="session_id")
    parent = _require_nonempty(dg.parent_asset_id, field="parent_asset_id")
    week = _require_nonempty(mp.week_id, field="week_id")
    asset = _require_nonempty(mp.asset_id, field="asset_id")
    title = _require_nonempty(mp.title, field="title")
    account = _require_nonempty(mp.account_id, field="account_id")

    session_aligned = mp.session_id == session
    parent_aligned = (
        mp.parent_asset_id == parent or mp.asset_id == parent
    )
    if not session_aligned:
        notes.append(
            "session_id mismatch between draft_gate and multi_pack — pack_ready blocked"
        )
    if not parent_aligned:
        notes.append(
            "parent_asset_id mismatch between draft_gate and multi_pack — pack_ready blocked"
        )

    if require:
        pack_ready = (
            session_aligned
            and parent_aligned
            and dg.gate_ready is True
            and mp.pack_ready is True
            and mp.production_router_verdict == "REJECT"
            and dg.draft_written is False
            and dg.merge_executed is False
            and mp.live_dispatched is False
            and mp.pack_dispatched is False
            and mp.live_router_authorized is False
            and mp.secrets_stored is False
            and mp.remote_index_queried is False
            and mp.pdf_primary is False
            and operator_ack is True
        )
    else:
        pack_ready = (
            session_aligned
            and parent_aligned
            and operator_ack is True
            and mp.production_router_verdict == "REJECT"
            and mp.pdf_primary is False
            and (dg.gate_ready is True or mp.pack_ready is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — draft-before-merge + floating multi-select model "
            "decision ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — draft_gate, multi_pack, alignment, or operator_ack gate open"
        )

    if (
        dg.draft_written is not False
        or dg.merge_executed is not False
        or dg.live_dispatched is not False
        or mp.live_dispatched is not False
        or mp.pack_dispatched is not False
        or mp.live_router_authorized is not False
        or mp.secrets_stored is not False
        or mp.remote_index_queried is not False
        or mp.pdf_primary is not False
        or mp.production_router_verdict != "REJECT"
    ):
        raise DraftBeforeMergeFloatingMultiselectModelDecisionNdTwinComposeError(
            "invariant: honesty flags must remain false / REJECT"
        )

    notes.extend(
        (
            "draft_written=false",
            "merge_executed=false",
            "live_dispatched=false",
            "pack_dispatched=false",
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
            "live_execution_authorized=false",
            "charge_executed=false",
            "record_persisted=false",
            "purchase_executed=false",
            "hosted=false",
            "remote_fetched=false",
            "production_router_verdict=REJECT",
        )
    )

    return DraftBeforeMergeFloatingMultiselectModelDecisionNdTwinCompose(
        session_id=session,
        parent_asset_id=parent,
        week_id=week,
        asset_id=asset,
        title=title,
        account_id=account,
        draft_gate=dg,
        multi_pack=mp,
        session_aligned=session_aligned,
        parent_aligned=parent_aligned,
        pack_ready=pack_ready,
        draft_written=False,
        merge_executed=False,
        live_dispatched=False,
        pack_dispatched=False,
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
        live_execution_authorized=False,
        charge_executed=False,
        record_persisted=False,
        purchase_executed=False,
        hosted=False,
        remote_fetched=False,
        production_router_verdict="REJECT",
        notes=tuple(notes),
        authority=(
            "draft_before_merge_floating_multiselect_model_decision_nd_twin_compose_advisory"
        ),
    )


def format_draft_before_merge_floating_multiselect_model_decision_nd_twin_summary(
    c: DraftBeforeMergeFloatingMultiselectModelDecisionNdTwinCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"draft_gate_ready={c.draft_gate.gate_ready} · "
        f"multi_pack_ready={c.multi_pack.pack_ready} · "
        f"session_aligned={c.session_aligned} · "
        f"parent_aligned={c.parent_aligned} · "
        f"verdict={c.production_router_verdict} · "
        "draft_written=false · merge_executed=false · live_dispatched=false"
    )


__all__ = [
    "DraftBeforeMergeFloatingMultiselectModelDecisionNdTwinCompose",
    "DraftBeforeMergeFloatingMultiselectModelDecisionNdTwinComposeError",
    "compose_draft_before_merge_floating_multiselect_model_decision_nd_twin",
    "format_draft_before_merge_floating_multiselect_model_decision_nd_twin_summary",
]
