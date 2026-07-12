"""Midnight Oil unattended package over source attach + model decision (pure).

live_execution_authorized always False.
charge_executed always False.
remote_fetched / pdf_primary always False.
production_router_verdict always REJECT.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.midnight_oil_price_ceiling_approval_compose import (
    MidnightOilPriceCeilingApprovalCompose,
    MidnightOilPriceCeilingApprovalComposeError,
    compose_midnight_oil_price_ceiling_approval,
)
from substrate.source_attach_antiek_bench_rewrite_model_decision_compose import (
    SourceAttachAntiekBenchRewriteModelDecisionCompose,
    SourceAttachAntiekBenchRewriteModelDecisionComposeError,
    compose_source_attach_antiek_bench_rewrite_model_decision,
)


class MoUnattendedSourceAttachAntiekBenchRewriteComposeError(ValueError):
    """Fail-closed validation for MO unattended + source attach model decision."""


@dataclass(frozen=True)
class MoUnattendedSourceAttachAntiekBenchRewriteCompose:
    session_id: str
    parent_asset_id: str
    asset_id: str
    week_id: str
    operator_id: str
    mo: MidnightOilPriceCeilingApprovalCompose
    research_pack: SourceAttachAntiekBenchRewriteModelDecisionCompose
    pack_ready: bool
    live_execution_authorized: bool
    charge_executed: bool
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
            "operator_id": self.operator_id,
            "mo": self.mo.to_dict(),
            "research_pack": self.research_pack.to_dict(),
            "pack_ready": self.pack_ready,
            "live_execution_authorized": False,
            "charge_executed": False,
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
            "draft_written": False,
            "record_persisted": False,
            "analysis_written": False,
            "production_router_verdict": "REJECT",
            "purchase_executed": False,
            "hosted": False,
            "notes": list(self.notes),
            "authority": (
                "mo_unattended_source_attach_antiek_bench_rewrite_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MoUnattendedSourceAttachAntiekBenchRewriteComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_mo_unattended_source_attach_antiek_bench_rewrite(
    *,
    mo: object,
    research_pack: object,
    operator_ack: object,
    require_both: object | None = None,
) -> MoUnattendedSourceAttachAntiekBenchRewriteCompose:
    """MO unattended price-ceiling + source attach model decision. Never launches."""
    if not isinstance(operator_ack, bool):
        raise MoUnattendedSourceAttachAntiekBenchRewriteComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(mo, dict):
        raise MoUnattendedSourceAttachAntiekBenchRewriteComposeError(
            "mo must be an object"
        )
    if not isinstance(research_pack, dict):
        raise MoUnattendedSourceAttachAntiekBenchRewriteComposeError(
            "research_pack must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise MoUnattendedSourceAttachAntiekBenchRewriteComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "live_execution_authorized=false · charge_executed=false",
        "remote_fetched=false · pdf_primary=false",
        "production_router_verdict=REJECT",
    ]

    try:
        mo_c = compose_midnight_oil_price_ceiling_approval(
            operator_id=mo.get("operator_id"),
            work_minutes=mo.get("work_minutes"),
            goals=mo.get("goals"),
            price_ceiling_ack=mo.get("price_ceiling_ack"),
            operator_ack=operator_ack,
            stage=mo.get("stage"),
            usd_per_hour=mo.get("usd_per_hour"),
            goal_intensity=mo.get("goal_intensity"),
            approved_ceiling_usd=mo.get("approved_ceiling_usd"),
            below_recommend_override=mo.get("below_recommend_override"),
            unattended_ack=mo.get("unattended_ack"),
            spend_consent=mo.get("spend_consent"),
        )
    except MidnightOilPriceCeilingApprovalComposeError as e:
        raise MoUnattendedSourceAttachAntiekBenchRewriteComposeError(str(e)) from e
    notes.extend(f"[mo] {n}" for n in mo_c.notes)

    try:
        rp = compose_source_attach_antiek_bench_rewrite_model_decision(
            sources=research_pack.get("sources"),
            rewrite_pack=research_pack.get("rewrite_pack"),
            operator_ack=operator_ack,
            require_both=research_pack.get("require_both"),
        )
    except SourceAttachAntiekBenchRewriteModelDecisionComposeError as e:
        raise MoUnattendedSourceAttachAntiekBenchRewriteComposeError(str(e)) from e
    notes.extend(f"[research_pack] {n}" for n in rp.notes)

    session = _require_nonempty(rp.session_id, field="session_id")
    parent = _require_nonempty(rp.parent_asset_id, field="parent_asset_id")
    asset = _require_nonempty(rp.asset_id, field="asset_id")
    week = _require_nonempty(rp.week_id, field="week_id")
    op = _require_nonempty(mo_c.operator_id, field="operator_id")

    if require:
        pack_ready = (
            mo_c.pack_ready is True
            and rp.pack_ready is True
            and mo_c.live_execution_authorized is False
            and mo_c.charge_executed is False
            and rp.remote_fetched is False
            and rp.pdf_primary is False
            and rp.live_router_authorized is False
            and rp.secrets_stored is False
            and rp.charge_executed is False
            and rp.suite_rewritten is False
            and rp.production_router_verdict == "REJECT"
            and operator_ack is True
        )
    else:
        pack_ready = (
            operator_ack is True
            and mo_c.live_execution_authorized is False
            and mo_c.charge_executed is False
            and rp.production_router_verdict == "REJECT"
            and rp.pdf_primary is False
            and (mo_c.pack_ready is True or rp.pack_ready is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — MO unattended + source attach model decision ready; "
            "still pure"
        )
    else:
        notes.append(
            "pack_ready=false — mo, research_pack, or operator_ack gate open"
        )

    if (
        mo_c.live_execution_authorized is not False
        or mo_c.charge_executed is not False
        or rp.remote_fetched is not False
        or rp.pdf_primary is not False
        or rp.live_router_authorized is not False
        or rp.secrets_stored is not False
        or rp.charge_executed is not False
        or rp.suite_rewritten is not False
        or rp.production_router_verdict != "REJECT"
    ):
        raise MoUnattendedSourceAttachAntiekBenchRewriteComposeError(
            "invariant: honesty flags must remain false"
        )

    notes.extend(
        (
            "live_execution_authorized=false",
            "charge_executed=false",
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
            "draft_written=false",
            "record_persisted=false",
            "analysis_written=false",
            "production_router_verdict=REJECT",
            "purchase_executed=false",
            "hosted=false",
        )
    )

    return MoUnattendedSourceAttachAntiekBenchRewriteCompose(
        session_id=session,
        parent_asset_id=parent,
        asset_id=asset,
        week_id=week,
        operator_id=op,
        mo=mo_c,
        research_pack=rp,
        pack_ready=pack_ready,
        live_execution_authorized=False,
        charge_executed=False,
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
        draft_written=False,
        record_persisted=False,
        analysis_written=False,
        production_router_verdict="REJECT",
        purchase_executed=False,
        hosted=False,
        notes=tuple(notes),
        authority=(
            "mo_unattended_source_attach_antiek_bench_rewrite_compose_advisory"
        ),
    )


def format_mo_unattended_source_attach_antiek_bench_rewrite_summary(
    c: MoUnattendedSourceAttachAntiekBenchRewriteCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"mo_ready={c.mo.pack_ready} · "
        f"research_ready={c.research_pack.pack_ready} · "
        f"stage={c.mo.stage} · "
        f"ceiling_approved={c.mo.ceiling_approved} · "
        f"week={c.week_id} · "
        f"verdict={c.production_router_verdict} · "
        f"live_execution_authorized=false · charge_executed=false · "
        f"remote_fetched=false"
    )


__all__ = [
    "MoUnattendedSourceAttachAntiekBenchRewriteCompose",
    "MoUnattendedSourceAttachAntiekBenchRewriteComposeError",
    "compose_mo_unattended_source_attach_antiek_bench_rewrite",
    "format_mo_unattended_source_attach_antiek_bench_rewrite_summary",
]
