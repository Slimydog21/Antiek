"""Workstation insight records → marketplace highlight float twin MO (pure).

record_persisted / prompts_injected always False.
purchase_executed / hosted / pdf_view_authorized / live_execution always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.marketplace_highlight_float_recursive_twin_mo_compose import (
    MarketplaceHighlightFloatRecursiveTwinMoCompose,
    MarketplaceHighlightFloatRecursiveTwinMoComposeError,
    compose_marketplace_highlight_float_recursive_twin_mo,
)
from substrate.workstation_session_insight_record_compose import (
    WorkstationSessionInsightRecordCompose,
    WorkstationSessionInsightRecordComposeError,
    compose_workstation_session_insight_record,
)


class WorkstationInsightMarketplaceHighlightMoComposeError(ValueError):
    """Fail-closed validation for workstation insight → marketplace MO pack."""


@dataclass(frozen=True)
class WorkstationInsightMarketplaceHighlightMoCompose:
    session_id: str
    parent_asset_id: str
    records: WorkstationSessionInsightRecordCompose
    marketplace_research: MarketplaceHighlightFloatRecursiveTwinMoCompose
    pack_ready: bool
    record_persisted: bool
    prompts_injected: bool
    purchase_executed: bool
    charge_executed: bool
    hosted: bool
    pdf_view_authorized: bool
    live_dispatched: bool
    twin_written: bool
    live_execution_authorized: bool
    store_mutated: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "parent_asset_id": self.parent_asset_id,
            "records": self.records.to_dict(),
            "marketplace_research": self.marketplace_research.to_dict(),
            "pack_ready": self.pack_ready,
            "record_persisted": False,
            "prompts_injected": False,
            "purchase_executed": False,
            "charge_executed": False,
            "hosted": False,
            "pdf_view_authorized": False,
            "live_dispatched": False,
            "twin_written": False,
            "live_execution_authorized": False,
            "store_mutated": False,
            "notes": list(self.notes),
            "authority": (
                "workstation_insight_marketplace_highlight_mo_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorkstationInsightMarketplaceHighlightMoComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_workstation_insight_marketplace_highlight_mo(
    *,
    records: object,
    marketplace_research: object,
    operator_ack: object,
    require_both: object | None = None,
) -> WorkstationInsightMarketplaceHighlightMoCompose:
    """Workstation records + marketplace highlight MO. Never persists/launches."""
    if not isinstance(operator_ack, bool):
        raise WorkstationInsightMarketplaceHighlightMoComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(records, dict):
        raise WorkstationInsightMarketplaceHighlightMoComposeError(
            "records must be an object"
        )
    if not isinstance(marketplace_research, dict):
        raise WorkstationInsightMarketplaceHighlightMoComposeError(
            "marketplace_research must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise WorkstationInsightMarketplaceHighlightMoComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "record_persisted=false · prompts_injected=false — records inform pack advisory only",
        "purchase_executed=false · hosted=false · pdf_view_authorized=false",
        "live_dispatched=false · twin_written=false · live_execution_authorized=false",
        "store_mutated=false",
    ]

    try:
        record_pack = compose_workstation_session_insight_record(
            session_id=records.get("session_id"),
            parent_asset_id=records.get("parent_asset_id"),
            records=records.get("records"),
            operator_ack=operator_ack,
            mark_for_prompt_context=records.get("mark_for_prompt_context"),
        )
    except WorkstationSessionInsightRecordComposeError as e:
        raise WorkstationInsightMarketplaceHighlightMoComposeError(
            str(e)
        ) from e
    notes.extend(f"[records] {n}" for n in record_pack.notes)

    try:
        market_pack = compose_marketplace_highlight_float_recursive_twin_mo(
            market=marketplace_research.get("market"),
            research=marketplace_research.get("research"),
            operator_ack=operator_ack,
            seed_highlight_from_title=marketplace_research.get(
                "seed_highlight_from_title"
            ),
            require_both=marketplace_research.get("require_both"),
        )
    except MarketplaceHighlightFloatRecursiveTwinMoComposeError as e:
        raise WorkstationInsightMarketplaceHighlightMoComposeError(
            str(e)
        ) from e
    notes.extend(f"[marketplace_research] {n}" for n in market_pack.notes)

    if record_pack.mark_for_prompt_context and record_pack.record_ready:
        notes.append(
            f"prompt_context_candidates={record_pack.record_count} — still prompts_injected=false"
        )

    session = _require_nonempty(record_pack.session_id, field="session_id")
    parent = _require_nonempty(
        record_pack.parent_asset_id, field="parent_asset_id"
    )

    if require:
        pack_ready = (
            record_pack.record_ready is True
            and market_pack.pack_ready is True
            and operator_ack is True
        )
    else:
        pack_ready = operator_ack is True and (
            record_pack.record_ready is True or market_pack.pack_ready is True
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — workstation records + marketplace highlight MO ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — records, marketplace_research, or operator_ack gate open"
        )

    if (
        record_pack.record_persisted is not False
        or record_pack.prompts_injected is not False
        or record_pack.store_mutated is not False
        or market_pack.purchase_executed is not False
        or market_pack.hosted is not False
        or market_pack.pdf_view_authorized is not False
        or market_pack.live_execution_authorized is not False
        or market_pack.twin_written is not False
    ):
        raise WorkstationInsightMarketplaceHighlightMoComposeError(
            "invariant: honesty flags must remain false"
        )

    notes.extend(
        (
            "record_persisted=false",
            "prompts_injected=false",
            "purchase_executed=false",
            "charge_executed=false",
            "hosted=false",
            "pdf_view_authorized=false",
            "live_dispatched=false",
            "twin_written=false",
            "live_execution_authorized=false",
            "store_mutated=false",
        )
    )

    return WorkstationInsightMarketplaceHighlightMoCompose(
        session_id=session,
        parent_asset_id=parent,
        records=record_pack,
        marketplace_research=market_pack,
        pack_ready=pack_ready,
        record_persisted=False,
        prompts_injected=False,
        purchase_executed=False,
        charge_executed=False,
        hosted=False,
        pdf_view_authorized=False,
        live_dispatched=False,
        twin_written=False,
        live_execution_authorized=False,
        store_mutated=False,
        notes=tuple(notes),
        authority=(
            "workstation_insight_marketplace_highlight_mo_compose_advisory"
        ),
    )


def format_workstation_insight_marketplace_highlight_mo_summary(
    c: WorkstationInsightMarketplaceHighlightMoCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"records_ready={c.records.record_ready} · "
        f"market_research_ready={c.marketplace_research.pack_ready} · "
        f"record_count={c.records.record_count} · "
        f"record_persisted=false · prompts_injected=false · "
        f"purchase_executed=false · live_execution_authorized=false"
    )


__all__ = [
    "WorkstationInsightMarketplaceHighlightMoCompose",
    "WorkstationInsightMarketplaceHighlightMoComposeError",
    "compose_workstation_insight_marketplace_highlight_mo",
    "format_workstation_insight_marketplace_highlight_mo_summary",
]
