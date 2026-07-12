"""HTML-native source attach over settings decision + MO unattended pack.

remote_fetched / pdf_primary always False.
live_router_authorized / live_execution_authorized always False.
production_router_verdict always REJECT.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.html_native_source_attach_compose import (
    HtmlNativeSourceAttachCompose,
    HtmlNativeSourceAttachComposeError,
    compose_html_native_source_attach,
)
from substrate.settings_decision_mo_unattended_fullscreen_compose import (
    SettingsDecisionMoUnattendedFullscreenCompose,
    SettingsDecisionMoUnattendedFullscreenComposeError,
    compose_settings_decision_mo_unattended_fullscreen,
)


class SourceAttachSettingsDecisionMoComposeError(ValueError):
    """Fail-closed validation for source attach + settings decision MO pack."""


@dataclass(frozen=True)
class SourceAttachSettingsDecisionMoCompose:
    session_id: str
    parent_asset_id: str
    title: str
    account_id: str
    week_id: str
    asset_id: str
    sources: HtmlNativeSourceAttachCompose
    settings_mo: SettingsDecisionMoUnattendedFullscreenCompose
    pack_ready: bool
    remote_fetched: bool
    pdf_view_authorized: bool
    pdf_primary: bool
    store_mutated: bool
    live_router_authorized: bool
    secrets_stored: bool
    live_meter_read: bool
    live_execution_authorized: bool
    live_dispatched: bool
    pack_dispatched: bool
    merge_executed: bool
    draft_written: bool
    analysis_written: bool
    purchase_executed: bool
    charge_executed: bool
    hosted: bool
    twin_written: bool
    prompts_injected: bool
    live_dispatch_authorized: bool
    backlog_mutated: bool
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
            "sources": self.sources.to_dict(),
            "settings_mo": self.settings_mo.to_dict(),
            "pack_ready": self.pack_ready,
            "remote_fetched": False,
            "pdf_view_authorized": False,
            "pdf_primary": False,
            "store_mutated": False,
            "live_router_authorized": False,
            "secrets_stored": False,
            "live_meter_read": False,
            "live_execution_authorized": False,
            "live_dispatched": False,
            "pack_dispatched": False,
            "merge_executed": False,
            "draft_written": False,
            "analysis_written": False,
            "purchase_executed": False,
            "charge_executed": False,
            "hosted": False,
            "twin_written": False,
            "prompts_injected": False,
            "live_dispatch_authorized": False,
            "backlog_mutated": False,
            "suite_rewritten": False,
            "remote_index_queried": False,
            "inventory_mutated": False,
            "record_persisted": False,
            "production_router_verdict": "REJECT",
            "notes": list(self.notes),
            "authority": "source_attach_settings_decision_mo_compose_advisory",
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SourceAttachSettingsDecisionMoComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_source_attach_settings_decision_mo(
    *,
    sources: object,
    settings_mo: object,
    operator_ack: object,
    require_both: object | None = None,
) -> SourceAttachSettingsDecisionMoCompose:
    """Source attach + settings decision MO. Never remote-fetches."""
    if not isinstance(operator_ack, bool):
        raise SourceAttachSettingsDecisionMoComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(sources, dict):
        raise SourceAttachSettingsDecisionMoComposeError(
            "sources must be an object"
        )
    if not isinstance(settings_mo, dict):
        raise SourceAttachSettingsDecisionMoComposeError(
            "settings_mo must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise SourceAttachSettingsDecisionMoComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "remote_fetched=false · pdf_primary=false · store_mutated=false",
        "live_router_authorized=false · live_execution_authorized=false",
        "production_router_verdict=REJECT",
    ]

    try:
        src = compose_html_native_source_attach(
            session_id=sources.get("session_id"),
            parent_asset_id=sources.get("parent_asset_id"),
            requested_families=sources.get("requested_families"),
            sources=sources.get("sources"),
            operator_ack=operator_ack,
        )
    except HtmlNativeSourceAttachComposeError as e:
        raise SourceAttachSettingsDecisionMoComposeError(str(e)) from e
    notes.extend(f"[sources] {n}" for n in src.notes)

    try:
        sm = compose_settings_decision_mo_unattended_fullscreen(
            decision=settings_mo.get("decision"),
            mo_pack=settings_mo.get("mo_pack"),
            operator_ack=operator_ack,
            require_both=settings_mo.get("require_both"),
        )
    except SettingsDecisionMoUnattendedFullscreenComposeError as e:
        raise SourceAttachSettingsDecisionMoComposeError(str(e)) from e
    notes.extend(f"[settings_mo] {n}" for n in sm.notes)

    session = _require_nonempty(src.session_id, field="session_id")
    parent = _require_nonempty(src.parent_asset_id, field="parent_asset_id")
    title = _require_nonempty(sm.title, field="title")
    account = _require_nonempty(sm.account_id, field="account_id")
    week = _require_nonempty(sm.week_id, field="week_id")
    asset = _require_nonempty(sm.asset_id, field="asset_id")

    session_aligned = sm.session_id == session
    parent_aligned = sm.parent_asset_id == parent
    if not session_aligned:
        notes.append(
            "session_id mismatch between sources and settings_mo — pack_ready blocked"
        )
    if not parent_aligned:
        notes.append(
            "parent_asset_id mismatch between sources and settings_mo — "
            "pack_ready blocked"
        )

    if require:
        pack_ready = (
            session_aligned
            and parent_aligned
            and src.attach_ready is True
            and sm.pack_ready is True
            and src.remote_fetched is False
            and src.pdf_view_authorized is False
            and src.store_mutated is False
            and sm.live_router_authorized is False
            and sm.live_execution_authorized is False
            and sm.purchase_executed is False
            and sm.production_router_verdict == "REJECT"
            and operator_ack is True
        )
    else:
        pack_ready = (
            session_aligned
            and parent_aligned
            and operator_ack is True
            and src.remote_fetched is False
            and sm.purchase_executed is False
            and sm.production_router_verdict == "REJECT"
            and (src.attach_ready is True or sm.pack_ready is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — source attach + settings decision MO pack ready; "
            "still pure"
        )
    else:
        notes.append(
            "pack_ready=false — sources, settings_mo, alignment, or operator_ack "
            "gate open"
        )

    if (
        src.remote_fetched is not False
        or src.pdf_view_authorized is not False
        or src.store_mutated is not False
        or sm.live_router_authorized is not False
        or sm.live_execution_authorized is not False
        or sm.purchase_executed is not False
        or sm.production_router_verdict != "REJECT"
    ):
        raise SourceAttachSettingsDecisionMoComposeError(
            "invariant: honesty flags must remain false / REJECT"
        )

    notes.extend(
        (
            "remote_fetched=false",
            "pdf_view_authorized=false",
            "pdf_primary=false",
            "store_mutated=false",
            "live_router_authorized=false",
            "secrets_stored=false",
            "live_meter_read=false",
            "live_execution_authorized=false",
            "live_dispatched=false",
            "pack_dispatched=false",
            "merge_executed=false",
            "draft_written=false",
            "analysis_written=false",
            "purchase_executed=false",
            "charge_executed=false",
            "hosted=false",
            "twin_written=false",
            "prompts_injected=false",
            "live_dispatch_authorized=false",
            "backlog_mutated=false",
            "suite_rewritten=false",
            "remote_index_queried=false",
            "inventory_mutated=false",
            "record_persisted=false",
            "production_router_verdict=REJECT",
        )
    )

    return SourceAttachSettingsDecisionMoCompose(
        session_id=session,
        parent_asset_id=parent,
        title=title,
        account_id=account,
        week_id=week,
        asset_id=asset,
        sources=src,
        settings_mo=sm,
        pack_ready=pack_ready,
        remote_fetched=False,
        pdf_view_authorized=False,
        pdf_primary=False,
        store_mutated=False,
        live_router_authorized=False,
        secrets_stored=False,
        live_meter_read=False,
        live_execution_authorized=False,
        live_dispatched=False,
        pack_dispatched=False,
        merge_executed=False,
        draft_written=False,
        analysis_written=False,
        purchase_executed=False,
        charge_executed=False,
        hosted=False,
        twin_written=False,
        prompts_injected=False,
        live_dispatch_authorized=False,
        backlog_mutated=False,
        suite_rewritten=False,
        remote_index_queried=False,
        inventory_mutated=False,
        record_persisted=False,
        production_router_verdict="REJECT",
        notes=tuple(notes),
        authority="source_attach_settings_decision_mo_compose_advisory",
    )


def format_source_attach_settings_decision_mo_summary(
    c: SourceAttachSettingsDecisionMoCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"attach_ready={c.sources.attach_ready} · "
        f"html_ready={c.sources.html_ready_count} · "
        f"settings_mo_ready={c.settings_mo.pack_ready} · "
        f"verdict={c.production_router_verdict} · "
        f"remote_fetched=false · live_router_authorized=false · "
        f"live_execution_authorized=false"
    )


__all__ = [
    "SourceAttachSettingsDecisionMoCompose",
    "SourceAttachSettingsDecisionMoComposeError",
    "compose_source_attach_settings_decision_mo",
    "format_source_attach_settings_decision_mo_summary",
]
