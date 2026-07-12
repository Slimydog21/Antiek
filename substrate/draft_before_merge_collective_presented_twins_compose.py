"""Draft-before-full-merge over collective presented twins + paid ND pack.

draft_written / merge_executed / live_dispatched always False.
purchase_executed / live_router_authorized always False.
production_router_verdict always REJECT.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.collective_presented_twins_paid_nd_compose import (
    CollectivePresentedTwinsPaidNdCompose,
    CollectivePresentedTwinsPaidNdComposeError,
    compose_collective_presented_twins_paid_nd,
)
from substrate.floating_draft_before_full_merge_gate_compose import (
    FloatingDraftBeforeFullMergeGateCompose,
    FloatingDraftBeforeFullMergeGateComposeError,
    compose_floating_draft_before_full_merge_gate,
)


class DraftBeforeMergeCollectivePresentedTwinsComposeError(ValueError):
    """Fail-closed validation for draft-before-merge + collective pack."""


@dataclass(frozen=True)
class DraftBeforeMergeCollectivePresentedTwinsCompose:
    session_id: str
    parent_asset_id: str
    title: str
    account_id: str
    week_id: str
    asset_id: str
    draft_gate: FloatingDraftBeforeFullMergeGateCompose
    collective_pack: CollectivePresentedTwinsPaidNdCompose
    pack_ready: bool
    draft_written: bool
    merge_executed: bool
    live_dispatched: bool
    pack_dispatched: bool
    analysis_written: bool
    purchase_executed: bool
    charge_executed: bool
    hosted: bool
    pdf_view_authorized: bool
    pdf_primary: bool
    live_router_authorized: bool
    twin_written: bool
    prompts_injected: bool
    live_dispatch_authorized: bool
    remote_fetched: bool
    backlog_mutated: bool
    secrets_stored: bool
    live_meter_read: bool
    store_mutated: bool
    suite_rewritten: bool
    live_execution_authorized: bool
    remote_index_queried: bool
    inventory_mutated: bool
    record_persisted: bool
    production_router_verdict: str
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "parent_asset_id": self.parent_asset_id,
            "title": self.title,
            "account_id": self.account_id,
            "week_id": self.week_id,
            "asset_id": self.asset_id,
            "draft_gate": self.draft_gate.to_dict(),
            "collective_pack": self.collective_pack.to_dict(),
            "pack_ready": self.pack_ready,
            "draft_written": False,
            "merge_executed": False,
            "live_dispatched": False,
            "pack_dispatched": False,
            "analysis_written": False,
            "purchase_executed": False,
            "charge_executed": False,
            "hosted": False,
            "pdf_view_authorized": False,
            "pdf_primary": False,
            "live_router_authorized": False,
            "twin_written": False,
            "prompts_injected": False,
            "live_dispatch_authorized": False,
            "remote_fetched": False,
            "backlog_mutated": False,
            "secrets_stored": False,
            "live_meter_read": False,
            "store_mutated": False,
            "suite_rewritten": False,
            "live_execution_authorized": False,
            "remote_index_queried": False,
            "inventory_mutated": False,
            "record_persisted": False,
            "production_router_verdict": "REJECT",
            "notes": list(self.notes),
            "authority": (
                "draft_before_merge_collective_presented_twins_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DraftBeforeMergeCollectivePresentedTwinsComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_draft_before_merge_collective_presented_twins(
    *,
    draft_gate: object,
    collective_pack: object,
    operator_ack: object,
    require_both: object | None = None,
) -> DraftBeforeMergeCollectivePresentedTwinsCompose:
    """Draft-before-merge + collective pack. Never writes or merges."""
    if not isinstance(operator_ack, bool):
        raise DraftBeforeMergeCollectivePresentedTwinsComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(draft_gate, dict):
        raise DraftBeforeMergeCollectivePresentedTwinsComposeError(
            "draft_gate must be an object"
        )
    if not isinstance(collective_pack, dict):
        raise DraftBeforeMergeCollectivePresentedTwinsComposeError(
            "collective_pack must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise DraftBeforeMergeCollectivePresentedTwinsComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "draft_written=false · merge_executed=false · live_dispatched=false",
        "purchase_executed=false · live_router_authorized=false",
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
        raise DraftBeforeMergeCollectivePresentedTwinsComposeError(
            str(e)
        ) from e
    notes.extend(f"[draft_gate] {n}" for n in dg.notes)

    try:
        col = compose_collective_presented_twins_paid_nd(
            collective=collective_pack.get("collective"),
            paid_nd=collective_pack.get("paid_nd"),
            operator_ack=operator_ack,
            require_both=collective_pack.get("require_both"),
        )
    except CollectivePresentedTwinsPaidNdComposeError as e:
        raise DraftBeforeMergeCollectivePresentedTwinsComposeError(
            str(e)
        ) from e
    notes.extend(f"[collective_pack] {n}" for n in col.notes)

    session = _require_nonempty(dg.session_id, field="session_id")
    parent = _require_nonempty(dg.parent_asset_id, field="parent_asset_id")
    title = _require_nonempty(col.title, field="title")
    account = _require_nonempty(col.account_id, field="account_id")
    week = _require_nonempty(col.week_id, field="week_id")
    asset = _require_nonempty(col.asset_id, field="asset_id")

    session_aligned = col.session_id == session
    parent_aligned = col.parent_asset_id == parent
    if not session_aligned:
        notes.append(
            "session_id mismatch between draft_gate and collective_pack — "
            "pack_ready blocked"
        )
    if not parent_aligned:
        notes.append(
            "parent_asset_id mismatch between draft_gate and collective_pack — "
            "pack_ready blocked"
        )

    if require:
        pack_ready = (
            session_aligned
            and parent_aligned
            and dg.gate_ready is True
            and col.pack_ready is True
            and dg.draft_written is False
            and dg.merge_executed is False
            and dg.live_dispatched is False
            and col.live_dispatched is False
            and col.merge_executed is False
            and col.purchase_executed is False
            and col.live_router_authorized is False
            and col.production_router_verdict == "REJECT"
            and operator_ack is True
        )
    else:
        pack_ready = (
            session_aligned
            and parent_aligned
            and operator_ack is True
            and dg.merge_executed is False
            and col.purchase_executed is False
            and col.production_router_verdict == "REJECT"
            and (dg.gate_ready is True or col.pack_ready is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — draft-before-merge + collective presented twins "
            "ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — draft_gate, collective_pack, alignment, or "
            "operator_ack gate open"
        )

    if (
        dg.draft_written is not False
        or dg.merge_executed is not False
        or dg.live_dispatched is not False
        or col.live_dispatched is not False
        or col.merge_executed is not False
        or col.purchase_executed is not False
        or col.live_router_authorized is not False
        or col.production_router_verdict != "REJECT"
    ):
        raise DraftBeforeMergeCollectivePresentedTwinsComposeError(
            "invariant: honesty flags must remain false / REJECT"
        )

    notes.extend(
        (
            "draft_written=false",
            "merge_executed=false",
            "live_dispatched=false",
            "pack_dispatched=false",
            "analysis_written=false",
            "purchase_executed=false",
            "charge_executed=false",
            "hosted=false",
            "pdf_view_authorized=false",
            "pdf_primary=false",
            "live_router_authorized=false",
            "twin_written=false",
            "prompts_injected=false",
            "live_dispatch_authorized=false",
            "remote_fetched=false",
            "backlog_mutated=false",
            "secrets_stored=false",
            "live_meter_read=false",
            "store_mutated=false",
            "suite_rewritten=false",
            "live_execution_authorized=false",
            "remote_index_queried=false",
            "inventory_mutated=false",
            "record_persisted=false",
            "production_router_verdict=REJECT",
        )
    )

    return DraftBeforeMergeCollectivePresentedTwinsCompose(
        session_id=session,
        parent_asset_id=parent,
        title=title,
        account_id=account,
        week_id=week,
        asset_id=asset,
        draft_gate=dg,
        collective_pack=col,
        pack_ready=pack_ready,
        draft_written=False,
        merge_executed=False,
        live_dispatched=False,
        pack_dispatched=False,
        analysis_written=False,
        purchase_executed=False,
        charge_executed=False,
        hosted=False,
        pdf_view_authorized=False,
        pdf_primary=False,
        live_router_authorized=False,
        twin_written=False,
        prompts_injected=False,
        live_dispatch_authorized=False,
        remote_fetched=False,
        backlog_mutated=False,
        secrets_stored=False,
        live_meter_read=False,
        store_mutated=False,
        suite_rewritten=False,
        live_execution_authorized=False,
        remote_index_queried=False,
        inventory_mutated=False,
        record_persisted=False,
        production_router_verdict="REJECT",
        notes=tuple(notes),
        authority=(
            "draft_before_merge_collective_presented_twins_compose_advisory"
        ),
    )


def format_draft_before_merge_collective_presented_twins_summary(
    c: DraftBeforeMergeCollectivePresentedTwinsCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"gate_ready={c.draft_gate.gate_ready} · "
        f"stage={c.draft_gate.stage} · "
        f"collective_ready={c.collective_pack.pack_ready} · "
        f"verdict={c.production_router_verdict} · "
        f"draft_written=false · merge_executed=false · purchase_executed=false"
    )


__all__ = [
    "DraftBeforeMergeCollectivePresentedTwinsCompose",
    "DraftBeforeMergeCollectivePresentedTwinsComposeError",
    "compose_draft_before_merge_collective_presented_twins",
    "format_draft_before_merge_collective_presented_twins_summary",
]
