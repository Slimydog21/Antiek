"""Floating DR highlight over draft-before-merge MO price-ceiling recursive twin (pure).

live_dispatched / merge_executed / pack_dispatched / twin_written always False.
draft_written / live_execution_authorized / charge_executed always False.
production_router_verdict always REJECT.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.draft_before_merge_mo_price_ceiling_recursive_twin_compose import (
    DraftBeforeMergeMoPriceCeilingRecursiveTwinCompose,
    DraftBeforeMergeMoPriceCeilingRecursiveTwinComposeError,
    compose_draft_before_merge_mo_price_ceiling_recursive_twin,
)
from substrate.reading_highlight_float_twin_feed_compose import (
    ReadingHighlightFloatTwinFeedCompose,
    ReadingHighlightFloatTwinFeedComposeError,
    compose_reading_highlight_float_twin_feed,
)


class FloatingDrDraftBeforeMergeMoPriceCeilingComposeError(ValueError):
    """Fail-closed validation for floating DR + draft-before-merge MO pack."""


@dataclass(frozen=True)
class FloatingDrDraftBeforeMergeMoPriceCeilingCompose:
    session_id: str
    parent_asset_id: str
    week_id: str
    asset_id: str
    title: str
    account_id: str
    highlight_surface: ReadingHighlightFloatTwinFeedCompose
    draft_pack: DraftBeforeMergeMoPriceCeilingRecursiveTwinCompose
    session_aligned: bool
    parent_aligned: bool
    pack_ready: bool
    live_dispatched: bool
    merge_executed: bool
    pack_dispatched: bool
    twin_written: bool
    record_persisted: bool
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
    analysis_written: bool
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
            "highlight_surface": self.highlight_surface.to_dict(),
            "draft_pack": self.draft_pack.to_dict(),
            "session_aligned": self.session_aligned,
            "parent_aligned": self.parent_aligned,
            "pack_ready": self.pack_ready,
            "live_dispatched": False,
            "merge_executed": False,
            "pack_dispatched": False,
            "twin_written": False,
            "record_persisted": False,
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
            "analysis_written": False,
            "purchase_executed": False,
            "hosted": False,
            "remote_fetched": False,
            "production_router_verdict": "REJECT",
            "notes": list(self.notes),
            "authority": (
                "floating_dr_draft_before_merge_mo_price_ceiling_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FloatingDrDraftBeforeMergeMoPriceCeilingComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_floating_dr_draft_before_merge_mo_price_ceiling(
    *,
    highlight_surface: object,
    draft_pack: object,
    operator_ack: object,
    require_both: object | None = None,
) -> FloatingDrDraftBeforeMergeMoPriceCeilingCompose:
    """Highlight floating DR on draft-before-merge MO pack. Never dispatches."""
    if not isinstance(operator_ack, bool):
        raise FloatingDrDraftBeforeMergeMoPriceCeilingComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(highlight_surface, dict):
        raise FloatingDrDraftBeforeMergeMoPriceCeilingComposeError(
            "highlight_surface must be an object"
        )
    if not isinstance(draft_pack, dict):
        raise FloatingDrDraftBeforeMergeMoPriceCeilingComposeError(
            "draft_pack must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise FloatingDrDraftBeforeMergeMoPriceCeilingComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "live_dispatched=false · merge_executed=false · pack_dispatched=false",
        "twin_written=false · draft_written=false · live_execution_authorized=false",
        "production_router_verdict=REJECT",
    ]

    try:
        hs = compose_reading_highlight_float_twin_feed(
            session_id=highlight_surface.get("session_id"),
            parent_asset_id=highlight_surface.get("parent_asset_id"),
            highlight=highlight_surface.get("highlight"),
            gated=highlight_surface.get("gated"),
            would_exceed=highlight_surface.get("would_exceed"),
            surface_action=highlight_surface.get("surface_action"),
            operator_ack=operator_ack,
            prompt=highlight_surface.get("prompt"),
            preferred_view_mode=highlight_surface.get("preferred_view_mode"),
            operator_override=highlight_surface.get("operator_override"),
            selected_model_id=highlight_surface.get("selected_model_id"),
            source_families=highlight_surface.get("source_families"),
            existing_members=highlight_surface.get("existing_members"),
            selected_instance_ids=highlight_surface.get("selected_instance_ids"),
            twin_findings=highlight_surface.get("twin_findings"),
            existing_twin_asset_id=highlight_surface.get(
                "existing_twin_asset_id"
            ),
            mark_for_prompt_context=highlight_surface.get(
                "mark_for_prompt_context"
            ),
            include_twin_feed=highlight_surface.get("include_twin_feed"),
        )
    except ReadingHighlightFloatTwinFeedComposeError as e:
        raise FloatingDrDraftBeforeMergeMoPriceCeilingComposeError(
            str(e)
        ) from e
    notes.extend(f"[highlight_surface] {n}" for n in hs.notes)

    try:
        dp = compose_draft_before_merge_mo_price_ceiling_recursive_twin(
            draft_gate=draft_pack.get("draft_gate"),
            mo_pack=draft_pack.get("mo_pack"),
            operator_ack=operator_ack,
            require_both=draft_pack.get("require_both"),
        )
    except DraftBeforeMergeMoPriceCeilingRecursiveTwinComposeError as e:
        raise FloatingDrDraftBeforeMergeMoPriceCeilingComposeError(
            str(e)
        ) from e
    notes.extend(f"[draft_pack] {n}" for n in dp.notes)

    session = _require_nonempty(hs.session_id, field="session_id")
    parent = _require_nonempty(
        highlight_surface.get("parent_asset_id"), field="parent_asset_id"
    )
    week = _require_nonempty(dp.week_id, field="week_id")
    asset = _require_nonempty(dp.asset_id, field="asset_id")
    title = _require_nonempty(dp.title, field="title")
    account = _require_nonempty(dp.account_id, field="account_id")

    session_aligned = dp.session_id == session
    parent_aligned = dp.parent_asset_id == parent or dp.asset_id == parent
    if not session_aligned:
        notes.append(
            "session_id mismatch between highlight_surface and draft_pack — "
            "pack_ready blocked"
        )
    else:
        notes.append("session_aligned=true")
    if not parent_aligned:
        notes.append(
            "parent_asset_id mismatch between highlight_surface and draft_pack "
            "— pack_ready blocked"
        )
    else:
        notes.append("parent_aligned=true")

    if require:
        pack_ready = (
            session_aligned is True
            and parent_aligned is True
            and hs.pack_ready is True
            and dp.pack_ready is True
            and dp.production_router_verdict == "REJECT"
            and hs.live_dispatched is False
            and hs.merge_executed is False
            and hs.pack_dispatched is False
            and hs.twin_written is False
            and dp.draft_written is False
            and dp.merge_executed is False
            and dp.live_dispatched is False
            and dp.live_execution_authorized is False
            and dp.charge_executed is False
            and dp.twin_written is False
            and dp.remote_index_queried is False
            and dp.pdf_primary is False
            and dp.live_router_authorized is False
            and dp.secrets_stored is False
            and operator_ack is True
        )
    else:
        pack_ready = (
            session_aligned is True
            and parent_aligned is True
            and operator_ack is True
            and dp.production_router_verdict == "REJECT"
            and dp.pdf_primary is False
            and hs.live_dispatched is False
            and (hs.pack_ready is True or dp.pack_ready is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — floating DR highlight + draft-before-merge MO "
            "price-ceiling ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — highlight_surface, draft_pack, alignment, or "
            "operator_ack gate open"
        )

    if (
        hs.live_dispatched is not False
        or hs.merge_executed is not False
        or hs.pack_dispatched is not False
        or hs.twin_written is not False
        or dp.draft_written is not False
        or dp.merge_executed is not False
        or dp.live_dispatched is not False
        or dp.live_execution_authorized is not False
        or dp.charge_executed is not False
        or dp.twin_written is not False
        or dp.remote_index_queried is not False
        or dp.pdf_primary is not False
        or dp.live_router_authorized is not False
        or dp.secrets_stored is not False
        or dp.production_router_verdict != "REJECT"
    ):
        raise FloatingDrDraftBeforeMergeMoPriceCeilingComposeError(
            "invariant: honesty flags must remain false / REJECT"
        )

    notes.extend(
        (
            "live_dispatched=false",
            "merge_executed=false",
            "pack_dispatched=false",
            "twin_written=false",
            "record_persisted=false",
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
            "analysis_written=false",
            "purchase_executed=false",
            "hosted=false",
            "remote_fetched=false",
            "production_router_verdict=REJECT",
        )
    )

    return FloatingDrDraftBeforeMergeMoPriceCeilingCompose(
        session_id=session,
        parent_asset_id=parent,
        week_id=week,
        asset_id=asset,
        title=title,
        account_id=account,
        highlight_surface=hs,
        draft_pack=dp,
        session_aligned=session_aligned,
        parent_aligned=parent_aligned,
        pack_ready=pack_ready,
        live_dispatched=False,
        merge_executed=False,
        pack_dispatched=False,
        twin_written=False,
        record_persisted=False,
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
        analysis_written=False,
        purchase_executed=False,
        hosted=False,
        remote_fetched=False,
        production_router_verdict="REJECT",
        notes=tuple(notes),
        authority=(
            "floating_dr_draft_before_merge_mo_price_ceiling_compose_advisory"
        ),
    )


def format_floating_dr_draft_before_merge_mo_price_ceiling_summary(
    c: FloatingDrDraftBeforeMergeMoPriceCeilingCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"highlight_ready={c.highlight_surface.pack_ready} · "
        f"draft_ready={c.draft_pack.pack_ready} · "
        f"session_aligned={c.session_aligned} · "
        f"parent_aligned={c.parent_aligned} · "
        f"verdict={c.production_router_verdict} · "
        "live_dispatched=false · twin_written=false · draft_written=false · "
        "live_execution_authorized=false"
    )


__all__ = [
    "FloatingDrDraftBeforeMergeMoPriceCeilingCompose",
    "FloatingDrDraftBeforeMergeMoPriceCeilingComposeError",
    "compose_floating_dr_draft_before_merge_mo_price_ceiling",
    "format_floating_dr_draft_before_merge_mo_price_ceiling_summary",
]
