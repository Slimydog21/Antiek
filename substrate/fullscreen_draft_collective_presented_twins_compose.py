"""Fullscreen-open over draft-before-merge collective presented twins pack.

live_dispatched / merge_executed / draft_written always False.
purchase_executed / live_router_authorized always False.
production_router_verdict always REJECT.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.draft_before_merge_collective_presented_twins_compose import (
    DraftBeforeMergeCollectivePresentedTwinsCompose,
    DraftBeforeMergeCollectivePresentedTwinsComposeError,
    compose_draft_before_merge_collective_presented_twins,
)
from substrate.floating_fullscreen_open_compose import (
    FloatingFullscreenOpenCompose,
    FloatingFullscreenOpenComposeError,
    compose_floating_fullscreen_open,
)


class FullscreenDraftCollectivePresentedTwinsComposeError(ValueError):
    """Fail-closed validation for fullscreen + draft collective pack."""


@dataclass(frozen=True)
class FullscreenDraftCollectivePresentedTwinsCompose:
    session_id: str
    parent_asset_id: str
    title: str
    account_id: str
    week_id: str
    asset_id: str
    fullscreen: FloatingFullscreenOpenCompose
    draft_collective: DraftBeforeMergeCollectivePresentedTwinsCompose
    pack_ready: bool
    live_dispatched: bool
    pack_dispatched: bool
    merge_executed: bool
    draft_written: bool
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
    live_execution_authorized: bool
    remote_fetched: bool
    backlog_mutated: bool
    secrets_stored: bool
    live_meter_read: bool
    store_mutated: bool
    suite_rewritten: bool
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
            "fullscreen": self.fullscreen.to_dict(),
            "draft_collective": self.draft_collective.to_dict(),
            "pack_ready": self.pack_ready,
            "live_dispatched": False,
            "pack_dispatched": False,
            "merge_executed": False,
            "draft_written": False,
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
            "live_execution_authorized": False,
            "remote_fetched": False,
            "backlog_mutated": False,
            "secrets_stored": False,
            "live_meter_read": False,
            "store_mutated": False,
            "suite_rewritten": False,
            "remote_index_queried": False,
            "inventory_mutated": False,
            "record_persisted": False,
            "production_router_verdict": "REJECT",
            "notes": list(self.notes),
            "authority": (
                "fullscreen_draft_collective_presented_twins_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FullscreenDraftCollectivePresentedTwinsComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_fullscreen_draft_collective_presented_twins(
    *,
    fullscreen: object,
    draft_collective: object,
    operator_ack: object,
    require_both: object | None = None,
) -> FullscreenDraftCollectivePresentedTwinsCompose:
    """Fullscreen-open + draft collective pack. Never dispatches/merges."""
    if not isinstance(operator_ack, bool):
        raise FullscreenDraftCollectivePresentedTwinsComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(fullscreen, dict):
        raise FullscreenDraftCollectivePresentedTwinsComposeError(
            "fullscreen must be an object"
        )
    if not isinstance(draft_collective, dict):
        raise FullscreenDraftCollectivePresentedTwinsComposeError(
            "draft_collective must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise FullscreenDraftCollectivePresentedTwinsComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "live_dispatched=false · merge_executed=false · draft_written=false",
        "purchase_executed=false · live_router_authorized=false",
        "production_router_verdict=REJECT",
    ]

    try:
        fs = compose_floating_fullscreen_open(
            session_id=fullscreen.get("session_id"),
            parent_asset_id=fullscreen.get("parent_asset_id"),
            operator_ack=operator_ack,
            existing_instance=fullscreen.get("existing_instance"),
            highlight=fullscreen.get("highlight"),
            prompt=fullscreen.get("prompt"),
            gated=fullscreen.get("gated"),
            tray_siblings=fullscreen.get("tray_siblings"),
        )
    except FloatingFullscreenOpenComposeError as e:
        raise FullscreenDraftCollectivePresentedTwinsComposeError(
            str(e)
        ) from e
    notes.extend(f"[fullscreen] {n}" for n in fs.notes)

    try:
        dc = compose_draft_before_merge_collective_presented_twins(
            draft_gate=draft_collective.get("draft_gate"),
            collective_pack=draft_collective.get("collective_pack"),
            operator_ack=operator_ack,
            require_both=draft_collective.get("require_both"),
        )
    except DraftBeforeMergeCollectivePresentedTwinsComposeError as e:
        raise FullscreenDraftCollectivePresentedTwinsComposeError(
            str(e)
        ) from e
    notes.extend(f"[draft_collective] {n}" for n in dc.notes)

    session = _require_nonempty(fs.session_id, field="session_id")
    parent = _require_nonempty(fs.parent_asset_id, field="parent_asset_id")
    title = _require_nonempty(dc.title, field="title")
    account = _require_nonempty(dc.account_id, field="account_id")
    week = _require_nonempty(dc.week_id, field="week_id")
    asset = _require_nonempty(dc.asset_id, field="asset_id")

    session_aligned = dc.session_id == session
    parent_aligned = dc.parent_asset_id == parent
    if not session_aligned:
        notes.append(
            "session_id mismatch between fullscreen and draft_collective — "
            "pack_ready blocked"
        )
    if not parent_aligned:
        notes.append(
            "parent_asset_id mismatch between fullscreen and draft_collective — "
            "pack_ready blocked"
        )

    if require:
        pack_ready = (
            session_aligned
            and parent_aligned
            and fs.fullscreen_ready is True
            and dc.pack_ready is True
            and fs.live_dispatched is False
            and fs.merge_executed is False
            and fs.pack_dispatched is False
            and dc.draft_written is False
            and dc.merge_executed is False
            and dc.live_dispatched is False
            and dc.purchase_executed is False
            and dc.live_router_authorized is False
            and dc.production_router_verdict == "REJECT"
            and operator_ack is True
        )
    else:
        pack_ready = (
            session_aligned
            and parent_aligned
            and operator_ack is True
            and fs.merge_executed is False
            and dc.purchase_executed is False
            and dc.production_router_verdict == "REJECT"
            and (fs.fullscreen_ready is True or dc.pack_ready is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — fullscreen + draft-before-merge collective pack "
            "ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — fullscreen, draft_collective, alignment, or "
            "operator_ack gate open"
        )

    if (
        fs.live_dispatched is not False
        or fs.merge_executed is not False
        or fs.pack_dispatched is not False
        or dc.draft_written is not False
        or dc.merge_executed is not False
        or dc.live_dispatched is not False
        or dc.purchase_executed is not False
        or dc.live_router_authorized is not False
        or dc.production_router_verdict != "REJECT"
    ):
        raise FullscreenDraftCollectivePresentedTwinsComposeError(
            "invariant: honesty flags must remain false / REJECT"
        )

    notes.extend(
        (
            "live_dispatched=false",
            "pack_dispatched=false",
            "merge_executed=false",
            "draft_written=false",
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
            "live_execution_authorized=false",
            "remote_fetched=false",
            "backlog_mutated=false",
            "secrets_stored=false",
            "live_meter_read=false",
            "store_mutated=false",
            "suite_rewritten=false",
            "remote_index_queried=false",
            "inventory_mutated=false",
            "record_persisted=false",
            "production_router_verdict=REJECT",
        )
    )

    return FullscreenDraftCollectivePresentedTwinsCompose(
        session_id=session,
        parent_asset_id=parent,
        title=title,
        account_id=account,
        week_id=week,
        asset_id=asset,
        fullscreen=fs,
        draft_collective=dc,
        pack_ready=pack_ready,
        live_dispatched=False,
        pack_dispatched=False,
        merge_executed=False,
        draft_written=False,
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
        live_execution_authorized=False,
        remote_fetched=False,
        backlog_mutated=False,
        secrets_stored=False,
        live_meter_read=False,
        store_mutated=False,
        suite_rewritten=False,
        remote_index_queried=False,
        inventory_mutated=False,
        record_persisted=False,
        production_router_verdict="REJECT",
        notes=tuple(notes),
        authority=(
            "fullscreen_draft_collective_presented_twins_compose_advisory"
        ),
    )


def format_fullscreen_draft_collective_presented_twins_summary(
    c: FullscreenDraftCollectivePresentedTwinsCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"fullscreen_ready={c.fullscreen.fullscreen_ready} · "
        f"draft_collective_ready={c.draft_collective.pack_ready} · "
        f"verdict={c.production_router_verdict} · "
        f"live_dispatched=false · merge_executed=false · draft_written=false"
    )


__all__ = [
    "FullscreenDraftCollectivePresentedTwinsCompose",
    "FullscreenDraftCollectivePresentedTwinsComposeError",
    "compose_fullscreen_draft_collective_presented_twins",
    "format_fullscreen_draft_collective_presented_twins_summary",
]
