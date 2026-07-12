"""HTML-native source attach residual over Antiek-bench rewrite + model decision
marketplace (pure).

remote_fetched always False.
suite_rewritten / applied always False.
live_router_authorized / secrets_stored always False.
pdf_primary always False.
production_router_verdict always REJECT.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.antiek_bench_rewrite_model_decision_marketplace_compose import (
    AntiekBenchRewriteModelDecisionMarketplaceCompose,
    AntiekBenchRewriteModelDecisionMarketplaceComposeError,
    compose_antiek_bench_rewrite_model_decision_marketplace,
)
from substrate.html_native_source_attach_compose import (
    HtmlNativeSourceAttachCompose,
    HtmlNativeSourceAttachComposeError,
    compose_html_native_source_attach,
)


class SourceAttachAntiekBenchRewriteModelDecisionComposeError(ValueError):
    """Fail-closed validation for source-attach + rewrite model decision pack."""


@dataclass(frozen=True)
class SourceAttachAntiekBenchRewriteModelDecisionCompose:
    session_id: str
    parent_asset_id: str
    asset_id: str
    week_id: str
    week_label: str
    focus_task: str
    title: str
    account_id: str
    sources: HtmlNativeSourceAttachCompose
    rewrite_pack: AntiekBenchRewriteModelDecisionMarketplaceCompose
    pack_ready: bool
    attach_ready: bool
    remote_fetched: bool
    store_mutated: bool
    pdf_view_authorized: bool
    pdf_primary: bool
    suite_rewritten: bool
    applied: bool
    live_router_authorized: bool
    secrets_stored: bool
    live_meter_read: bool
    remote_index_queried: bool
    backlog_mutated: bool
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
            "week_label": self.week_label,
            "focus_task": self.focus_task,
            "title": self.title,
            "account_id": self.account_id,
            "sources": self.sources.to_dict(),
            "rewrite_pack": self.rewrite_pack.to_dict(),
            "pack_ready": self.pack_ready,
            "attach_ready": self.attach_ready,
            "remote_fetched": False,
            "store_mutated": False,
            "pdf_view_authorized": False,
            "pdf_primary": False,
            "suite_rewritten": False,
            "applied": False,
            "live_router_authorized": False,
            "secrets_stored": False,
            "live_meter_read": False,
            "remote_index_queried": False,
            "backlog_mutated": False,
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
                "source_attach_antiek_bench_rewrite_model_decision_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SourceAttachAntiekBenchRewriteModelDecisionComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_source_attach_antiek_bench_rewrite_model_decision(
    *,
    sources: object,
    rewrite_pack: object,
    operator_ack: object,
    require_both: object | None = None,
) -> SourceAttachAntiekBenchRewriteModelDecisionCompose:
    """Source attach residual over rewrite + model decision. Never remote-fetches."""
    if not isinstance(operator_ack, bool):
        raise SourceAttachAntiekBenchRewriteModelDecisionComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(sources, dict):
        raise SourceAttachAntiekBenchRewriteModelDecisionComposeError(
            "sources must be an object"
        )
    if not isinstance(rewrite_pack, dict):
        raise SourceAttachAntiekBenchRewriteModelDecisionComposeError(
            "rewrite_pack must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise SourceAttachAntiekBenchRewriteModelDecisionComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "remote_fetched=false — pure attach only (no live arxiv/substack)",
        "pdf_view_authorized=false · pdf_primary=false",
        "suite_rewritten=false · applied=false",
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
        raise SourceAttachAntiekBenchRewriteModelDecisionComposeError(
            str(e)
        ) from e
    notes.extend(f"[sources] {n}" for n in src.notes)

    try:
        rwp = compose_antiek_bench_rewrite_model_decision_marketplace(
            rewrite=rewrite_pack.get("rewrite"),
            model_decision_pack=rewrite_pack.get("model_decision_pack"),
            operator_ack=operator_ack,
            require_both=rewrite_pack.get("require_both"),
            block_if_applied=rewrite_pack.get("block_if_applied"),
        )
    except AntiekBenchRewriteModelDecisionMarketplaceComposeError as e:
        raise SourceAttachAntiekBenchRewriteModelDecisionComposeError(
            str(e)
        ) from e
    notes.extend(f"[rewrite_pack] {n}" for n in rwp.notes)

    session = _require_nonempty(src.session_id, field="session_id")
    parent = _require_nonempty(src.parent_asset_id, field="parent_asset_id")
    asset = _require_nonempty(rwp.asset_id, field="asset_id")
    week_id = _require_nonempty(rwp.week_id, field="week_id")
    week_label = _require_nonempty(rwp.week_label, field="week_label")
    focus = _require_nonempty(rwp.focus_task, field="focus_task")
    title = _require_nonempty(rwp.title, field="title")
    account = _require_nonempty(rwp.account_id, field="account_id")

    session_aligned = rwp.session_id == session
    parent_aligned = rwp.parent_asset_id == parent
    if not session_aligned:
        notes.append(
            "session_id mismatch between sources and rewrite_pack — pack_ready blocked"
        )
    if not parent_aligned:
        notes.append(
            "parent_asset_id mismatch between sources and rewrite_pack — "
            "pack_ready blocked"
        )

    if require:
        pack_ready = (
            session_aligned
            and parent_aligned
            and src.attach_ready is True
            and rwp.pack_ready is True
            and src.remote_fetched is False
            and src.pdf_view_authorized is False
            and src.store_mutated is False
            and rwp.suite_rewritten is False
            and rwp.applied is False
            and rwp.production_router_verdict == "REJECT"
            and rwp.pdf_primary is False
            and rwp.live_router_authorized is False
            and rwp.secrets_stored is False
            and rwp.remote_index_queried is False
            and rwp.purchase_executed is False
            and rwp.hosted is False
            and rwp.inventory_mutated is False
            and operator_ack is True
        )
    else:
        pack_ready = (
            session_aligned
            and parent_aligned
            and operator_ack is True
            and src.remote_fetched is False
            and src.pdf_view_authorized is False
            and rwp.production_router_verdict == "REJECT"
            and rwp.pdf_primary is False
            and rwp.suite_rewritten is False
            and (src.attach_ready is True or rwp.pack_ready is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — source attach + Antiek-bench rewrite model decision "
            "ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — sources, rewrite_pack, alignment, or operator_ack "
            "gate open"
        )

    if (
        src.remote_fetched is not False
        or src.pdf_view_authorized is not False
        or src.store_mutated is not False
        or rwp.suite_rewritten is not False
        or rwp.applied is not False
        or rwp.pdf_primary is not False
        or rwp.live_router_authorized is not False
        or rwp.secrets_stored is not False
        or rwp.remote_index_queried is not False
        or rwp.purchase_executed is not False
        or rwp.hosted is not False
        or rwp.inventory_mutated is not False
        or rwp.production_router_verdict != "REJECT"
    ):
        raise SourceAttachAntiekBenchRewriteModelDecisionComposeError(
            "invariant: honesty flags must remain false / REJECT"
        )

    notes.extend(
        (
            "remote_fetched=false",
            "store_mutated=false",
            "pdf_view_authorized=false",
            "pdf_primary=false",
            "suite_rewritten=false",
            "applied=false",
            "live_router_authorized=false",
            "secrets_stored=false",
            "live_meter_read=false",
            "remote_index_queried=false",
            "backlog_mutated=false",
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

    return SourceAttachAntiekBenchRewriteModelDecisionCompose(
        session_id=session,
        parent_asset_id=parent,
        asset_id=asset,
        week_id=week_id,
        week_label=week_label,
        focus_task=focus,
        title=title,
        account_id=account,
        sources=src,
        rewrite_pack=rwp,
        pack_ready=pack_ready,
        attach_ready=src.attach_ready,
        remote_fetched=False,
        store_mutated=False,
        pdf_view_authorized=False,
        pdf_primary=False,
        suite_rewritten=False,
        applied=False,
        live_router_authorized=False,
        secrets_stored=False,
        live_meter_read=False,
        remote_index_queried=False,
        backlog_mutated=False,
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
            "source_attach_antiek_bench_rewrite_model_decision_compose_advisory"
        ),
    )


def format_source_attach_antiek_bench_rewrite_model_decision_summary(
    c: SourceAttachAntiekBenchRewriteModelDecisionCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · attach_ready={c.attach_ready} · "
        f"sources={c.sources.source_count} · "
        f"html_ready={c.sources.html_ready_count} · "
        f"proposals={c.rewrite_pack.proposal_count} · "
        f"suite_rewritten=false · applied=false · "
        f"week={c.week_label} · task={c.focus_task} · "
        f"verdict={c.production_router_verdict} · "
        "remote_fetched=false · live_router_authorized=false · "
        "secrets_stored=false"
    )


__all__ = [
    "SourceAttachAntiekBenchRewriteModelDecisionCompose",
    "SourceAttachAntiekBenchRewriteModelDecisionComposeError",
    "compose_source_attach_antiek_bench_rewrite_model_decision",
    "format_source_attach_antiek_bench_rewrite_model_decision_summary",
]
