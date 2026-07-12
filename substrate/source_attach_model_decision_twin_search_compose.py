"""HTML-native source attach over model decision + twin search weekly (pure).

remote_fetched always False.
pdf_view_authorized / pdf_primary always False.
live_router_authorized / secrets_stored always False.
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
from substrate.model_decision_twin_search_weekly_html_native_compose import (
    ModelDecisionTwinSearchWeeklyHtmlNativeCompose,
    ModelDecisionTwinSearchWeeklyHtmlNativeComposeError,
    compose_model_decision_twin_search_weekly_html_native,
)


class SourceAttachModelDecisionTwinSearchComposeError(ValueError):
    """Fail-closed validation for source attach + model decision twin search."""


@dataclass(frozen=True)
class SourceAttachModelDecisionTwinSearchCompose:
    session_id: str
    parent_asset_id: str
    asset_id: str
    week_id: str
    sources: HtmlNativeSourceAttachCompose
    decision_pack: ModelDecisionTwinSearchWeeklyHtmlNativeCompose
    pack_ready: bool
    attach_ready: bool
    remote_fetched: bool
    store_mutated: bool
    pdf_view_authorized: bool
    pdf_primary: bool
    live_router_authorized: bool
    secrets_stored: bool
    live_meter_read: bool
    remote_index_queried: bool
    backlog_mutated: bool
    suite_rewritten: bool
    twin_written: bool
    prompts_injected: bool
    live_dispatch_authorized: bool
    inventory_mutated: bool
    live_dispatched: bool
    pack_dispatched: bool
    merge_executed: bool
    live_execution_authorized: bool
    charge_executed: bool
    draft_written: bool
    record_persisted: bool
    analysis_written: bool
    production_router_verdict: str
    purchase_executed: bool
    hosted: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "parent_asset_id": self.parent_asset_id,
            "asset_id": self.asset_id,
            "week_id": self.week_id,
            "sources": self.sources.to_dict(),
            "decision_pack": self.decision_pack.to_dict(),
            "pack_ready": self.pack_ready,
            "attach_ready": self.attach_ready,
            "remote_fetched": False,
            "store_mutated": False,
            "pdf_view_authorized": False,
            "pdf_primary": False,
            "live_router_authorized": False,
            "secrets_stored": False,
            "live_meter_read": False,
            "remote_index_queried": False,
            "backlog_mutated": False,
            "suite_rewritten": False,
            "twin_written": False,
            "prompts_injected": False,
            "live_dispatch_authorized": False,
            "inventory_mutated": False,
            "live_dispatched": False,
            "pack_dispatched": False,
            "merge_executed": False,
            "live_execution_authorized": False,
            "charge_executed": False,
            "draft_written": False,
            "record_persisted": False,
            "analysis_written": False,
            "production_router_verdict": "REJECT",
            "purchase_executed": False,
            "hosted": False,
            "notes": list(self.notes),
            "authority": (
                "source_attach_model_decision_twin_search_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SourceAttachModelDecisionTwinSearchComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_source_attach_model_decision_twin_search(
    *,
    sources: object,
    decision_pack: object,
    operator_ack: object,
    require_both: object | None = None,
) -> SourceAttachModelDecisionTwinSearchCompose:
    """HTML-native source attach + model decision twin search. Never remote-fetches."""
    if not isinstance(operator_ack, bool):
        raise SourceAttachModelDecisionTwinSearchComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(sources, dict):
        raise SourceAttachModelDecisionTwinSearchComposeError(
            "sources must be an object"
        )
    if not isinstance(decision_pack, dict):
        raise SourceAttachModelDecisionTwinSearchComposeError(
            "decision_pack must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise SourceAttachModelDecisionTwinSearchComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "remote_fetched=false — pure attach only (no live arxiv/substack)",
        "pdf_view_authorized=false · pdf_primary=false",
        "live_router_authorized=false · secrets_stored=false",
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
        raise SourceAttachModelDecisionTwinSearchComposeError(str(e)) from e
    notes.extend(f"[sources] {n}" for n in src.notes)

    try:
        dp = compose_model_decision_twin_search_weekly_html_native(
            decision=decision_pack.get("decision"),
            twin_search_pack=decision_pack.get("twin_search_pack"),
            operator_ack=operator_ack,
            require_both=decision_pack.get("require_both"),
            block_on_budget_exceed=decision_pack.get("block_on_budget_exceed"),
        )
    except ModelDecisionTwinSearchWeeklyHtmlNativeComposeError as e:
        raise SourceAttachModelDecisionTwinSearchComposeError(str(e)) from e
    notes.extend(f"[decision_pack] {n}" for n in dp.notes)

    session = _require_nonempty(src.session_id, field="session_id")
    parent = _require_nonempty(src.parent_asset_id, field="parent_asset_id")
    asset = _require_nonempty(dp.asset_id, field="asset_id")
    week = _require_nonempty(dp.week_id, field="week_id")

    session_aligned = dp.session_id == session
    parent_aligned = dp.parent_asset_id == parent
    if not session_aligned:
        notes.append(
            "session_id mismatch between sources and decision_pack — pack_ready blocked"
        )
    if not parent_aligned:
        notes.append(
            "parent_asset_id mismatch between sources and decision_pack — pack_ready blocked"
        )

    if require:
        pack_ready = (
            session_aligned
            and parent_aligned
            and src.attach_ready is True
            and dp.pack_ready is True
            and src.remote_fetched is False
            and src.pdf_view_authorized is False
            and src.store_mutated is False
            and dp.production_router_verdict == "REJECT"
            and dp.pdf_primary is False
            and dp.live_router_authorized is False
            and dp.secrets_stored is False
            and dp.charge_executed is False
            and dp.suite_rewritten is False
            and dp.remote_index_queried is False
            and operator_ack is True
        )
    else:
        pack_ready = (
            session_aligned
            and parent_aligned
            and operator_ack is True
            and src.remote_fetched is False
            and src.pdf_view_authorized is False
            and dp.production_router_verdict == "REJECT"
            and dp.pdf_primary is False
            and (src.attach_ready is True or dp.pack_ready is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — source attach + model decision twin search weekly "
            "ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — sources, decision_pack, alignment, or operator_ack "
            "gate open"
        )

    if (
        src.remote_fetched is not False
        or src.pdf_view_authorized is not False
        or src.store_mutated is not False
        or dp.pdf_primary is not False
        or dp.live_router_authorized is not False
        or dp.secrets_stored is not False
        or dp.charge_executed is not False
        or dp.suite_rewritten is not False
        or dp.remote_index_queried is not False
        or dp.production_router_verdict != "REJECT"
    ):
        raise SourceAttachModelDecisionTwinSearchComposeError(
            "invariant: honesty flags must remain false"
        )

    notes.extend(
        (
            "remote_fetched=false",
            "store_mutated=false",
            "pdf_view_authorized=false",
            "pdf_primary=false",
            "live_router_authorized=false",
            "secrets_stored=false",
            "live_meter_read=false",
            "remote_index_queried=false",
            "backlog_mutated=false",
            "suite_rewritten=false",
            "twin_written=false",
            "prompts_injected=false",
            "live_dispatch_authorized=false",
            "inventory_mutated=false",
            "live_dispatched=false",
            "pack_dispatched=false",
            "merge_executed=false",
            "live_execution_authorized=false",
            "charge_executed=false",
            "draft_written=false",
            "record_persisted=false",
            "analysis_written=false",
            "production_router_verdict=REJECT",
            "purchase_executed=false",
            "hosted=false",
        )
    )

    return SourceAttachModelDecisionTwinSearchCompose(
        session_id=session,
        parent_asset_id=parent,
        asset_id=asset,
        week_id=week,
        sources=src,
        decision_pack=dp,
        pack_ready=pack_ready,
        attach_ready=src.attach_ready,
        remote_fetched=False,
        store_mutated=False,
        pdf_view_authorized=False,
        pdf_primary=False,
        live_router_authorized=False,
        secrets_stored=False,
        live_meter_read=False,
        remote_index_queried=False,
        backlog_mutated=False,
        suite_rewritten=False,
        twin_written=False,
        prompts_injected=False,
        live_dispatch_authorized=False,
        inventory_mutated=False,
        live_dispatched=False,
        pack_dispatched=False,
        merge_executed=False,
        live_execution_authorized=False,
        charge_executed=False,
        draft_written=False,
        record_persisted=False,
        analysis_written=False,
        production_router_verdict="REJECT",
        purchase_executed=False,
        hosted=False,
        notes=tuple(notes),
        authority=(
            "source_attach_model_decision_twin_search_compose_advisory"
        ),
    )


def format_source_attach_model_decision_twin_search_summary(
    c: SourceAttachModelDecisionTwinSearchCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"attach_ready={c.attach_ready} · "
        f"decision_ready={c.decision_pack.pack_ready} · "
        f"sources={c.sources.source_count} · "
        f"html_ready={c.sources.html_ready_count} · "
        f"week={c.week_id} · "
        f"verdict={c.production_router_verdict} · "
        f"remote_fetched=false · pdf_primary=false · suite_rewritten=false"
    )


__all__ = [
    "SourceAttachModelDecisionTwinSearchCompose",
    "SourceAttachModelDecisionTwinSearchComposeError",
    "compose_source_attach_model_decision_twin_search",
    "format_source_attach_model_decision_twin_search_summary",
]
