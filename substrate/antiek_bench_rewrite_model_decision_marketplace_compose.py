"""Antiek-bench recursive rewrite residual over model decision + twin search
HTML-native recursive twin marketplace (pure).

suite_rewritten / applied always False (proposal only).
live_router_authorized / secrets_stored / live_meter_read always False.
remote_index_queried / pdf_primary always False.
production_router_verdict always REJECT.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.antiek_bench_recursive_rewrite import (
    AntiekBenchRewriteError,
    BenchRewriteProposal,
    propose_antiek_bench_recursive_rewrite,
)
from substrate.model_decision_twin_search_html_native_marketplace_compose import (
    ModelDecisionTwinSearchHtmlNativeMarketplaceCompose,
    ModelDecisionTwinSearchHtmlNativeMarketplaceComposeError,
    compose_model_decision_twin_search_html_native_marketplace,
)


class AntiekBenchRewriteModelDecisionMarketplaceComposeError(ValueError):
    """Fail-closed validation for bench rewrite + model decision marketplace pack."""


@dataclass(frozen=True)
class AntiekBenchRewriteModelDecisionMarketplaceCompose:
    week_id: str
    week_label: str
    session_id: str
    parent_asset_id: str
    asset_id: str
    title: str
    account_id: str
    focus_task: str
    rewrite: BenchRewriteProposal
    model_decision_pack: ModelDecisionTwinSearchHtmlNativeMarketplaceCompose
    proposal_count: int
    pack_ready: bool
    suite_rewritten: bool
    applied: bool
    live_router_authorized: bool
    secrets_stored: bool
    live_meter_read: bool
    remote_index_queried: bool
    backlog_mutated: bool
    store_mutated: bool
    pdf_view_authorized: bool
    pdf_primary: bool
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
    purchase_executed: bool
    hosted: bool
    remote_fetched: bool
    production_router_verdict: str
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "week_id": self.week_id,
            "week_label": self.week_label,
            "session_id": self.session_id,
            "parent_asset_id": self.parent_asset_id,
            "asset_id": self.asset_id,
            "title": self.title,
            "account_id": self.account_id,
            "focus_task": self.focus_task,
            "rewrite": self.rewrite.to_dict(),
            "model_decision_pack": self.model_decision_pack.to_dict(),
            "proposal_count": self.proposal_count,
            "pack_ready": self.pack_ready,
            "suite_rewritten": False,
            "applied": False,
            "live_router_authorized": False,
            "secrets_stored": False,
            "live_meter_read": False,
            "remote_index_queried": False,
            "backlog_mutated": False,
            "store_mutated": False,
            "pdf_view_authorized": False,
            "pdf_primary": False,
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
            "purchase_executed": False,
            "hosted": False,
            "remote_fetched": False,
            "production_router_verdict": "REJECT",
            "notes": list(self.notes),
            "authority": (
                "antiek_bench_rewrite_model_decision_marketplace_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AntiekBenchRewriteModelDecisionMarketplaceComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_antiek_bench_rewrite_model_decision_marketplace(
    *,
    rewrite: object,
    model_decision_pack: object,
    operator_ack: object,
    require_both: object | None = None,
    block_if_applied: object | None = None,
) -> AntiekBenchRewriteModelDecisionMarketplaceCompose:
    """Bench rewrite residual over model-decision marketplace. Never rewrites suite."""
    if not isinstance(operator_ack, bool):
        raise AntiekBenchRewriteModelDecisionMarketplaceComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(rewrite, dict):
        raise AntiekBenchRewriteModelDecisionMarketplaceComposeError(
            "rewrite must be an object"
        )
    if not isinstance(model_decision_pack, dict):
        raise AntiekBenchRewriteModelDecisionMarketplaceComposeError(
            "model_decision_pack must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise AntiekBenchRewriteModelDecisionMarketplaceComposeError(
            "require_both must be boolean when set"
        )
    block_applied = True if block_if_applied is None else block_if_applied
    if not isinstance(block_applied, bool):
        raise AntiekBenchRewriteModelDecisionMarketplaceComposeError(
            "block_if_applied must be boolean when set"
        )

    notes: list[str] = [
        "suite_rewritten=false · applied=false — rewrite proposal only",
        "live_router_authorized=false · secrets_stored=false · live_meter_read=false",
        "remote_index_queried=false · pdf_primary=false",
        "production_router_verdict=REJECT",
    ]

    try:
        rw = propose_antiek_bench_recursive_rewrite(
            week_label=rewrite.get("week_label"),
            patterns=rewrite.get("patterns"),
        )
    except AntiekBenchRewriteError as e:
        raise AntiekBenchRewriteModelDecisionMarketplaceComposeError(str(e)) from e
    notes.extend(f"[rewrite] {n}" for n in rw.notes)

    if rw.applied is not False:
        raise AntiekBenchRewriteModelDecisionMarketplaceComposeError(
            "invariant: rewrite.applied must be false"
        )

    try:
        mdp = compose_model_decision_twin_search_html_native_marketplace(
            decision=model_decision_pack.get("decision"),
            twin_search_pack=model_decision_pack.get("twin_search_pack"),
            operator_ack=operator_ack,
            require_both=model_decision_pack.get("require_both"),
            block_on_budget_exceed=model_decision_pack.get(
                "block_on_budget_exceed"
            ),
        )
    except ModelDecisionTwinSearchHtmlNativeMarketplaceComposeError as e:
        raise AntiekBenchRewriteModelDecisionMarketplaceComposeError(
            str(e)
        ) from e
    notes.extend(f"[model_decision_pack] {n}" for n in mdp.notes)

    week_label = _require_nonempty(rw.week_label, field="week_label")
    week_id = _require_nonempty(mdp.week_id, field="week_id")
    session = _require_nonempty(mdp.session_id, field="session_id")
    asset = _require_nonempty(mdp.asset_id, field="asset_id")
    parent = _require_nonempty(mdp.parent_asset_id, field="parent_asset_id")
    title = _require_nonempty(mdp.title, field="title")
    account = _require_nonempty(mdp.account_id, field="account_id")
    focus = _require_nonempty(mdp.focus_task, field="focus_task")

    proposal_count = len(rw.proposals)
    rewrite_ready = proposal_count >= 1
    applied_ok = (not block_applied) or (rw.applied is False)

    if require:
        pack_ready = (
            rewrite_ready
            and applied_ok
            and mdp.pack_ready is True
            and mdp.suite_rewritten is False
            and mdp.live_router_authorized is False
            and mdp.secrets_stored is False
            and mdp.live_meter_read is False
            and mdp.remote_index_queried is False
            and mdp.pdf_primary is False
            and mdp.pdf_view_authorized is False
            and mdp.twin_written is False
            and mdp.purchase_executed is False
            and mdp.hosted is False
            and mdp.inventory_mutated is False
            and mdp.production_router_verdict == "REJECT"
            and operator_ack is True
        )
    else:
        pack_ready = (
            operator_ack is True
            and applied_ok
            and mdp.live_router_authorized is False
            and mdp.suite_rewritten is False
            and mdp.production_router_verdict == "REJECT"
            and mdp.pdf_primary is False
            and (rewrite_ready or mdp.pack_ready is True)
        )

    if not rewrite_ready and require:
        notes.append(
            "rewrite has zero proposals — pack_ready blocked "
            "(need fail/mixed usage signal)"
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — Antiek-bench rewrite residual + model decision "
            "marketplace ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — rewrite, model_decision_pack, or operator_ack "
            "gate open"
        )

    if (
        rw.applied is not False
        or mdp.suite_rewritten is not False
        or mdp.live_router_authorized is not False
        or mdp.secrets_stored is not False
        or mdp.live_meter_read is not False
        or mdp.remote_index_queried is not False
        or mdp.pdf_primary is not False
        or mdp.pdf_view_authorized is not False
        or mdp.twin_written is not False
        or mdp.purchase_executed is not False
        or mdp.hosted is not False
        or mdp.inventory_mutated is not False
        or mdp.production_router_verdict != "REJECT"
    ):
        raise AntiekBenchRewriteModelDecisionMarketplaceComposeError(
            "invariant: honesty flags must remain false / REJECT"
        )

    notes.extend(
        (
            "suite_rewritten=false",
            "applied=false",
            "live_router_authorized=false",
            "secrets_stored=false",
            "live_meter_read=false",
            "remote_index_queried=false",
            "backlog_mutated=false",
            "store_mutated=false",
            "pdf_view_authorized=false",
            "pdf_primary=false",
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
            "purchase_executed=false",
            "hosted=false",
            "remote_fetched=false",
            "production_router_verdict=REJECT",
        )
    )

    return AntiekBenchRewriteModelDecisionMarketplaceCompose(
        week_id=week_id,
        week_label=week_label,
        session_id=session,
        parent_asset_id=parent,
        asset_id=asset,
        title=title,
        account_id=account,
        focus_task=focus,
        rewrite=rw,
        model_decision_pack=mdp,
        proposal_count=proposal_count,
        pack_ready=pack_ready,
        suite_rewritten=False,
        applied=False,
        live_router_authorized=False,
        secrets_stored=False,
        live_meter_read=False,
        remote_index_queried=False,
        backlog_mutated=False,
        store_mutated=False,
        pdf_view_authorized=False,
        pdf_primary=False,
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
        purchase_executed=False,
        hosted=False,
        remote_fetched=False,
        production_router_verdict="REJECT",
        notes=tuple(notes),
        authority=(
            "antiek_bench_rewrite_model_decision_marketplace_compose_advisory"
        ),
    )


def format_antiek_bench_rewrite_model_decision_marketplace_summary(
    c: AntiekBenchRewriteModelDecisionMarketplaceCompose,
) -> str:
    budget = (
        "would_exceed=null"
        if c.model_decision_pack.decision.would_exceed is None
        else f"would_exceed={c.model_decision_pack.decision.would_exceed}"
    )
    return (
        f"pack_ready={c.pack_ready} · "
        f"proposals={c.proposal_count} · applied=false · suite_rewritten=false · "
        f"decision_ready={c.model_decision_pack.decision.decision_ready} · "
        f"model={c.model_decision_pack.decision.driver.decision.selected_model_id} · "
        f"{budget} · "
        f"hits={c.model_decision_pack.twin_search_pack.hit_count} · "
        f"week={c.week_label} · task={c.focus_task} · "
        f"verdict={c.production_router_verdict} · "
        "live_router_authorized=false · secrets_stored=false · "
        "remote_index_queried=false"
    )


__all__ = [
    "AntiekBenchRewriteModelDecisionMarketplaceCompose",
    "AntiekBenchRewriteModelDecisionMarketplaceComposeError",
    "compose_antiek_bench_rewrite_model_decision_marketplace",
    "format_antiek_bench_rewrite_model_decision_marketplace_summary",
]
