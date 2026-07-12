"""Marketplace HTML+twin session → write twin collective analysis (pure).

purchase/charge/hosted/pdf/twin_written/draft_written/analysis_written
always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.marketplace_html_view_twin_session_compose import (
    MarketplaceHtmlViewTwinSessionCompose,
    MarketplaceHtmlViewTwinSessionComposeError,
    compose_marketplace_html_view_twin_session,
)
from substrate.write_mode_twin_collective_analysis_compose import (
    WriteModeTwinCollectiveAnalysisCompose,
    WriteModeTwinCollectiveAnalysisComposeError,
    compose_write_mode_twin_collective_analysis,
)


class MarketplaceHtmlTwinWriteComposeError(ValueError):
    """Fail-closed validation for marketplace HTML twin write pack."""


@dataclass(frozen=True)
class MarketplaceHtmlTwinWriteCompose:
    session_id: str
    asset_id: str
    draft_id: str
    market_twin: MarketplaceHtmlViewTwinSessionCompose
    write_pack: WriteModeTwinCollectiveAnalysisCompose
    pack_ready: bool
    purchase_executed: bool
    charge_executed: bool
    hosted: bool
    pdf_view_authorized: bool
    twin_written: bool
    draft_written: bool
    analysis_written: bool
    merge_executed: bool
    store_mutated: bool
    live_dispatched: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "asset_id": self.asset_id,
            "draft_id": self.draft_id,
            "market_twin": self.market_twin.to_dict(),
            "write_pack": self.write_pack.to_dict(),
            "pack_ready": self.pack_ready,
            "purchase_executed": False,
            "charge_executed": False,
            "hosted": False,
            "pdf_view_authorized": False,
            "twin_written": False,
            "draft_written": False,
            "analysis_written": False,
            "merge_executed": False,
            "store_mutated": False,
            "live_dispatched": False,
            "notes": list(self.notes),
            "authority": "marketplace_html_twin_write_compose_advisory",
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MarketplaceHtmlTwinWriteComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def _findings_to_slices_and_slots(
    parent_asset_id: str,
    title: str,
    findings: object | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    insights: list[str] = [title]
    questions: list[str] = []
    slots: list[dict[str, Any]] = []
    if findings is not None:
        if not isinstance(findings, list):
            raise MarketplaceHtmlTwinWriteComposeError(
                "twin_findings must be an array when set"
            )
        for f in findings:
            if not isinstance(f, dict):
                continue
            sid = str(f.get("source_id", "")).strip() or "f"
            body = str(f.get("body", "")).strip()
            if not body:
                continue
            kind = str(f.get("kind") or "insight")
            if kind == "question":
                questions.append(body)
                slots.append(
                    {
                        "slot_id": f"mk-{sid}",
                        "question_id": sid,
                        "parent_asset_id": parent_asset_id,
                        "status": "open",
                        "findings": [body],
                        "body": body,
                    }
                )
            else:
                insights.append(body)
                slots.append(
                    {
                        "slot_id": f"mk-{sid}",
                        "question_id": sid,
                        "parent_asset_id": parent_asset_id,
                        "status": "completed",
                        "findings": [body],
                        "body": body,
                    }
                )
    if not questions:
        questions.append(f'What does "{title}" claim?')
    while len(slots) < 2:
        i = len(slots)
        slots.append(
            {
                "slot_id": f"mk-pad-{i}",
                "question_id": f"pad-{i}",
                "parent_asset_id": parent_asset_id,
                "status": "completed" if i == 0 else "open",
                "findings": [f"padding-{i}: {title}"],
                "body": f"padding-{i}: {title}",
            }
        )
    return (
        [
            {
                "parent_asset_id": parent_asset_id,
                "insights": insights,
                "questions": questions,
            }
        ],
        slots,
    )


def compose_marketplace_html_twin_write(
    *,
    session_id: object,
    asset_id: object,
    draft_id: object,
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
    analysis_kind: object | None = None,
    twin_slices: object | None = None,
    chase_slots: object | None = None,
    base_draft_html: object | None = None,
    extra_write_findings: object | None = None,
    require_both_with_write: object | None = None,
) -> MarketplaceHtmlTwinWriteCompose:
    """Marketplace HTML+twin + write pack. Never charges/hosts/writes."""
    if not isinstance(operator_ack, bool):
        raise MarketplaceHtmlTwinWriteComposeError(
            "operator_ack must be an explicit boolean"
        )
    session = _require_nonempty(session_id, field="session_id")
    asset = _require_nonempty(asset_id, field="asset_id")
    draft = _require_nonempty(draft_id, field="draft_id")
    title_s = _require_nonempty(title, field="title")

    require_write = (
        True if require_both_with_write is None else require_both_with_write
    )
    if not isinstance(require_write, bool):
        raise MarketplaceHtmlTwinWriteComposeError(
            "require_both_with_write must be boolean when set"
        )

    notes: list[str] = [
        "purchase_executed=false · charge_executed=false · hosted=false",
        "pdf_view_authorized=false — HTML-native book surface",
        "twin_written=false · draft_written=false · analysis_written=false",
        "merge_executed=false · store_mutated=false · live_dispatched=false",
    ]

    try:
        market_twin = compose_marketplace_html_view_twin_session(
            session_id=session,
            asset_id=asset,
            title=title_s,
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
        raise MarketplaceHtmlTwinWriteComposeError(str(e)) from e
    notes.extend(f"[market_twin] {n}" for n in market_twin.notes)

    if twin_slices is not None and chase_slots is not None:
        if not isinstance(twin_slices, list) or not isinstance(chase_slots, list):
            raise MarketplaceHtmlTwinWriteComposeError(
                "twin_slices and chase_slots must be arrays when set"
            )
        slices = [s for s in twin_slices if isinstance(s, dict)]
        slots = [s for s in chase_slots if isinstance(s, dict)]
        notes.append("twin_slices/chase_slots caller-supplied")
    else:
        d_slices, d_slots = _findings_to_slices_and_slots(
            asset, title_s, twin_findings
        )
        slices = (
            [s for s in twin_slices if isinstance(s, dict)]
            if isinstance(twin_slices, list)
            else d_slices
        )
        slots = (
            [s for s in chase_slots if isinstance(s, dict)]
            if isinstance(chase_slots, list)
            else d_slots
        )
        notes.append(
            f"derived twin_slices={len(slices)} slots={len(slots)} "
            "from book twin findings"
        )

    while len(slots) < 2:
        i = len(slots)
        slots.append(
            {
                "slot_id": f"mk-pad-{i}",
                "question_id": f"pad-{i}",
                "parent_asset_id": asset,
                "status": "open",
                "findings": [f"padding-{i}"],
                "body": f"padding-{i}",
            }
        )
        notes.append("chase_slots padded to ≥2 for write collective analysis")

    kind = "draft_analysis" if analysis_kind is None else analysis_kind
    if kind not in ("draft_analysis", "full_analysis"):
        raise MarketplaceHtmlTwinWriteComposeError(
            "analysis_kind must be draft_analysis or full_analysis when set"
        )
    completed = [s for s in slots if s.get("status") == "completed"]
    all_completed = len(slots) >= 2 and len(completed) == len(slots)
    if analysis_kind is None and all_completed and operator_ack is True:
        kind = "full_analysis"
    if kind == "full_analysis" and not all_completed:
        kind = "draft_analysis"
        notes.append(
            "analysis_kind demoted to draft_analysis — full needs all slots completed"
        )
    if kind == "full_analysis" and operator_ack is not True:
        kind = "draft_analysis"
        notes.append(
            "analysis_kind demoted to draft_analysis — full_analysis requires operator_ack"
        )

    try:
        write_pack = compose_write_mode_twin_collective_analysis(
            session_id=session,
            draft_id=draft,
            parent_asset_id=asset,
            twin_slices=slices,
            chase_slots=slots,
            analysis_kind=kind,
            operator_ack=operator_ack,
            base_draft_html=base_draft_html,
            extra_findings=extra_write_findings,
            require_both=True,
        )
    except WriteModeTwinCollectiveAnalysisComposeError as e:
        raise MarketplaceHtmlTwinWriteComposeError(str(e)) from e
    notes.extend(f"[write_pack] {n}" for n in write_pack.notes)

    if require_write:
        pack_ready = (
            market_twin.session_ready is True
            and write_pack.pack_ready is True
            and operator_ack is True
        )
    else:
        pack_ready = operator_ack is True and (
            market_twin.session_ready is True or write_pack.pack_ready is True
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — marketplace HTML+twin + write pack ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — market session, write pack, or operator_ack gate open"
        )

    if (
        market_twin.purchase_executed is not False
        or market_twin.charge_executed is not False
        or market_twin.hosted is not False
        or market_twin.pdf_view_authorized is not False
        or market_twin.twin_written is not False
        or write_pack.draft_written is not False
        or write_pack.analysis_written is not False
        or write_pack.merge_executed is not False
        or write_pack.live_dispatched is not False
    ):
        raise MarketplaceHtmlTwinWriteComposeError(
            "invariant: honesty flags must remain false"
        )

    notes.extend(
        (
            "purchase_executed=false",
            "charge_executed=false",
            "hosted=false",
            "pdf_view_authorized=false",
            "twin_written=false",
            "draft_written=false",
            "analysis_written=false",
            "merge_executed=false",
            "store_mutated=false",
            "live_dispatched=false",
        )
    )

    return MarketplaceHtmlTwinWriteCompose(
        session_id=session,
        asset_id=asset,
        draft_id=draft,
        market_twin=market_twin,
        write_pack=write_pack,
        pack_ready=pack_ready,
        purchase_executed=False,
        charge_executed=False,
        hosted=False,
        pdf_view_authorized=False,
        twin_written=False,
        draft_written=False,
        analysis_written=False,
        merge_executed=False,
        store_mutated=False,
        live_dispatched=False,
        notes=tuple(notes),
        authority="marketplace_html_twin_write_compose_advisory",
    )


def format_marketplace_html_twin_write_summary(
    c: MarketplaceHtmlTwinWriteCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"market_session={c.market_twin.session_ready} · "
        f"write_ready={c.write_pack.pack_ready} · "
        f"purchase_executed=false · pdf_view_authorized=false · "
        f"draft_written=false · analysis_written=false · charge_executed=false"
    )


__all__ = [
    "MarketplaceHtmlTwinWriteCompose",
    "MarketplaceHtmlTwinWriteComposeError",
    "compose_marketplace_html_twin_write",
    "format_marketplace_html_twin_write_summary",
]
