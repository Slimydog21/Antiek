"""Marketplace HTML+twin → workstation interrogation compose (pure).

purchase/charge/hosted/pdf/twin_written/record/live_dispatch/prompts always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.marketplace_html_view_twin_session_compose import (
    MarketplaceHtmlViewTwinSessionCompose,
    MarketplaceHtmlViewTwinSessionComposeError,
    compose_marketplace_html_view_twin_session,
)
from substrate.research_workstation_interrogation_loop_compose import (
    ResearchWorkstationInterrogationLoopCompose,
    ResearchWorkstationInterrogationLoopComposeError,
    compose_research_workstation_interrogation_loop,
)


class MarketplaceHtmlTwinInterrogationComposeError(ValueError):
    """Fail-closed validation for marketplace HTML twin interrogation pack."""


@dataclass(frozen=True)
class MarketplaceHtmlTwinInterrogationCompose:
    session_id: str
    asset_id: str
    market_twin: MarketplaceHtmlViewTwinSessionCompose
    interrogation: ResearchWorkstationInterrogationLoopCompose | None
    pack_ready: bool
    purchase_executed: bool
    charge_executed: bool
    hosted: bool
    pdf_view_authorized: bool
    twin_written: bool
    record_persisted: bool
    live_dispatched: bool
    prompts_injected: bool
    live_router_authorized: bool
    store_mutated: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "asset_id": self.asset_id,
            "market_twin": self.market_twin.to_dict(),
            "interrogation": (
                self.interrogation.to_dict() if self.interrogation else None
            ),
            "pack_ready": self.pack_ready,
            "purchase_executed": False,
            "charge_executed": False,
            "hosted": False,
            "pdf_view_authorized": False,
            "twin_written": False,
            "record_persisted": False,
            "live_dispatched": False,
            "prompts_injected": False,
            "live_router_authorized": False,
            "store_mutated": False,
            "notes": list(self.notes),
            "authority": (
                "marketplace_html_twin_interrogation_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MarketplaceHtmlTwinInterrogationComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_marketplace_html_twin_interrogation(
    *,
    session_id: object,
    asset_id: object,
    title: object,
    account_id: object,
    free_copy_available: object,
    port_requested: object,
    purchase_ack: object,
    list_price_usd: object,
    approved_spend_usd: object,
    remaining_budget_usd: object,
    operator_ack: object,
    view_requested: object,
    free_html_projection_sha: object | None = None,
    purchase_html_projection_sha: object | None = None,
    twin_bound: object | None = None,
    twin_substrate_ready: object | None = None,
    claimed_format: object | None = None,
    twin_findings: object | None = None,
    existing_twin_asset_id: object | None = None,
    mark_for_prompt_context: object | None = None,
    include_twin_feed: object | None = None,
    include_interrogation: object | None = None,
    questions: object | None = None,
    chase_mode: object | None = None,
    prior_records: object | None = None,
    user_prompt: object | None = None,
    selected_model_id: object | None = None,
    models: object | None = None,
    daily_cap_usd: object | None = None,
    spent_usd: object | None = None,
    projected_cost_usd_high: object | None = None,
    projected_cost_usd_low: object | None = None,
    would_exceed: object | None = None,
    operator_override: object | None = None,
    source_families: object | None = None,
    bench_bests: object | None = None,
    focus_task: object | None = None,
    nd_shadow: object | None = None,
) -> MarketplaceHtmlTwinInterrogationCompose:
    """Market HTML+twin + optional interrogation. Never charges/dispatches."""
    if not isinstance(operator_ack, bool):
        raise MarketplaceHtmlTwinInterrogationComposeError(
            "operator_ack must be an explicit boolean"
        )
    session = _require_nonempty(session_id, field="session_id")
    asset = _require_nonempty(asset_id, field="asset_id")

    include_i = True if include_interrogation is None else include_interrogation
    if not isinstance(include_i, bool):
        raise MarketplaceHtmlTwinInterrogationComposeError(
            "include_interrogation must be boolean when set"
        )

    notes: list[str] = [
        "purchase_executed=false · charge_executed=false · hosted=false",
        "pdf_view_authorized=false — HTML-native book/research surface",
        "twin_written=false · record_persisted=false · live_dispatched=false",
        "prompts_injected=false · live_router_authorized=false · store_mutated=false",
    ]

    try:
        market_twin = compose_marketplace_html_view_twin_session(
            session_id=session,
            asset_id=asset,
            title=title,
            account_id=account_id,
            free_copy_available=free_copy_available,
            port_requested=port_requested,
            purchase_ack=purchase_ack,
            list_price_usd=list_price_usd,
            approved_spend_usd=approved_spend_usd,
            remaining_budget_usd=remaining_budget_usd,
            operator_ack=operator_ack,
            view_requested=view_requested,
            free_html_projection_sha=free_html_projection_sha,
            purchase_html_projection_sha=purchase_html_projection_sha,
            twin_bound=twin_bound,
            twin_substrate_ready=twin_substrate_ready,
            claimed_format=claimed_format,
            twin_findings=twin_findings,
            existing_twin_asset_id=existing_twin_asset_id,
            mark_for_prompt_context=mark_for_prompt_context,
            include_twin_feed=include_twin_feed,
        )
    except MarketplaceHtmlViewTwinSessionComposeError as e:
        raise MarketplaceHtmlTwinInterrogationComposeError(str(e)) from e
    notes.extend(f"[market_twin] {n}" for n in market_twin.notes)

    interrogation: ResearchWorkstationInterrogationLoopCompose | None = None
    if not include_i:
        notes.append("interrogation skipped — include_interrogation=false")
    elif not market_twin.session_ready:
        notes.append(
            "interrogation deferred — marketplace HTML+twin session not ready"
        )
    else:
        if not isinstance(questions, list) or len(questions) == 0:
            raise MarketplaceHtmlTwinInterrogationComposeError(
                "questions must be a non-empty array when include_interrogation=true "
                "and market session ready"
            )
        if not isinstance(models, list) or len(models) == 0:
            raise MarketplaceHtmlTwinInterrogationComposeError(
                "models must be a non-empty array when include_interrogation=true"
            )
        if selected_model_id is not None and str(selected_model_id).strip():
            selected = _require_nonempty(
                selected_model_id, field="selected_model_id"
            )
        else:
            first = models[0]
            if not isinstance(first, dict):
                raise MarketplaceHtmlTwinInterrogationComposeError(
                    "models[0] must be an object"
                )
            selected = _require_nonempty(
                first.get("model_id"), field="models[0].model_id"
            )
        title_s = _require_nonempty(title, field="title")
        if user_prompt is not None and str(user_prompt).strip():
            prompt = _require_nonempty(user_prompt, field="user_prompt")
        else:
            prompt = f"Interrogate hosted HTML asset: {title_s}"

        prior: list[dict[str, Any]] = []
        if prior_records is not None:
            if not isinstance(prior_records, list):
                raise MarketplaceHtmlTwinInterrogationComposeError(
                    "prior_records must be an array when set"
                )
            for r in prior_records:
                if isinstance(r, dict):
                    prior.append(dict(r))
        prior.append(
            {
                "record_id": f"book-title-{asset}",
                "kind": "insight",
                "body": title_s,
                "source_ref": asset,
            }
        )

        try:
            interrogation = compose_research_workstation_interrogation_loop(
                session_id=session,
                parent_asset_id=asset,
                questions=questions,
                chase_mode=chase_mode if chase_mode is not None else "swarm_fanout",
                user_prompt=prompt,
                selected_model_id=selected,
                models=models,
                daily_cap_usd=daily_cap_usd,
                spent_usd=spent_usd,
                operator_ack=operator_ack,
                prior_records=prior,
                projected_cost_usd_high=projected_cost_usd_high,
                projected_cost_usd_low=projected_cost_usd_low,
                would_exceed=would_exceed,
                operator_override=operator_override,
                source_families=source_families,
                bench_bests=bench_bests,
                focus_task=(
                    "deep_research" if focus_task is None else focus_task
                ),
                nd_shadow=nd_shadow,
                mark_for_twin_record=True,
            )
        except ResearchWorkstationInterrogationLoopComposeError as e:
            raise MarketplaceHtmlTwinInterrogationComposeError(str(e)) from e
        notes.extend(f"[interrogation] {n}" for n in interrogation.notes)

    if not include_i:
        pack_ready = market_twin.session_ready is True and operator_ack is True
    elif not market_twin.session_ready:
        pack_ready = False
        notes.append("pack_ready=false — market HTML+twin not ready")
    else:
        pack_ready = (
            interrogation is not None
            and interrogation.loop_ready is True
            and operator_ack is True
        )
        if not pack_ready:
            notes.append(
                "pack_ready=false — interrogation loop or operator_ack gate open"
            )

    if pack_ready:
        notes.append(
            "pack_ready=true — marketplace HTML+twin"
            + ("+interrogation" if include_i else "")
            + " ready; still pure"
        )

    if (
        market_twin.purchase_executed is not False
        or market_twin.charge_executed is not False
        or market_twin.hosted is not False
        or market_twin.pdf_view_authorized is not False
        or market_twin.twin_written is not False
        or market_twin.record_persisted is not False
        or market_twin.store_mutated is not False
        or (
            interrogation is not None
            and (
                interrogation.live_dispatched is not False
                or interrogation.record_persisted is not False
                or interrogation.prompts_injected is not False
                or interrogation.live_router_authorized is not False
            )
        )
    ):
        raise MarketplaceHtmlTwinInterrogationComposeError(
            "invariant: honesty flags must remain false"
        )

    notes.extend(
        (
            "purchase_executed=false",
            "charge_executed=false",
            "hosted=false",
            "pdf_view_authorized=false",
            "twin_written=false",
            "record_persisted=false",
            "live_dispatched=false",
            "prompts_injected=false",
            "live_router_authorized=false",
            "store_mutated=false",
        )
    )

    return MarketplaceHtmlTwinInterrogationCompose(
        session_id=session,
        asset_id=asset,
        market_twin=market_twin,
        interrogation=interrogation,
        pack_ready=pack_ready,
        purchase_executed=False,
        charge_executed=False,
        hosted=False,
        pdf_view_authorized=False,
        twin_written=False,
        record_persisted=False,
        live_dispatched=False,
        prompts_injected=False,
        live_router_authorized=False,
        store_mutated=False,
        notes=tuple(notes),
        authority="marketplace_html_twin_interrogation_compose_advisory",
    )


def format_marketplace_html_twin_interrogation_summary(
    c: MarketplaceHtmlTwinInterrogationCompose,
) -> str:
    loop = (
        c.interrogation.loop_ready if c.interrogation is not None else "n/a"
    )
    return (
        f"pack_ready={c.pack_ready} · market_session={c.market_twin.session_ready} · "
        f"loop_ready={loop} · "
        f"purchase_executed=false · pdf_view_authorized=false · "
        f"live_dispatched=false · twin_written=false"
    )


__all__ = [
    "MarketplaceHtmlTwinInterrogationCompose",
    "MarketplaceHtmlTwinInterrogationComposeError",
    "compose_marketplace_html_twin_interrogation",
    "format_marketplace_html_twin_interrogation_summary",
]
