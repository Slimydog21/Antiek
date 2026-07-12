"""Recursive twin note-taker over twin search model decision HTML-native pack (pure).

twin_written / prompts_injected / live_dispatch_authorized always False.
remote_index_queried / live_router_authorized / secrets_stored always False.
pdf_primary / purchase_executed / hosted always False.
production_router_verdict always REJECT.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.recursive_twin_note_taker_compose import (
    RecursiveTwinNoteTakerCompose,
    RecursiveTwinNoteTakerComposeError,
    compose_recursive_twin_note_taker,
)
from substrate.twin_search_model_decision_html_native_settings_marketplace_compose import (
    TwinSearchModelDecisionHtmlNativeSettingsMarketplaceCompose,
    TwinSearchModelDecisionHtmlNativeSettingsMarketplaceComposeError,
    compose_twin_search_model_decision_html_native_settings_marketplace,
)


class RecursiveTwinNoteTakerTwinSearchModelDecisionComposeError(ValueError):
    """Fail-closed validation for recursive twin + twin search model decision pack."""


@dataclass(frozen=True)
class RecursiveTwinNoteTakerTwinSearchModelDecisionCompose:
    session_id: str
    parent_asset_id: str
    title: str
    account_id: str
    week_id: str
    asset_id: str
    twin: RecursiveTwinNoteTakerCompose
    twin_search_pack: TwinSearchModelDecisionHtmlNativeSettingsMarketplaceCompose
    parent_aligned: bool
    pack_ready: bool
    twin_written: bool
    prompts_injected: bool
    live_dispatch_authorized: bool
    purchase_executed: bool
    hosted: bool
    pdf_view_authorized: bool
    pdf_primary: bool
    remote_fetched: bool
    backlog_mutated: bool
    secrets_stored: bool
    inventory_mutated: bool
    live_router_authorized: bool
    live_meter_read: bool
    suite_rewritten: bool
    store_mutated: bool
    live_execution_authorized: bool
    charge_executed: bool
    remote_index_queried: bool
    live_dispatched: bool
    pack_dispatched: bool
    merge_executed: bool
    draft_written: bool
    record_persisted: bool
    analysis_written: bool
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
            "twin": self.twin.to_dict(),
            "twin_search_pack": self.twin_search_pack.to_dict(),
            "parent_aligned": self.parent_aligned,
            "pack_ready": self.pack_ready,
            "twin_written": False,
            "prompts_injected": False,
            "live_dispatch_authorized": False,
            "purchase_executed": False,
            "hosted": False,
            "pdf_view_authorized": False,
            "pdf_primary": False,
            "remote_fetched": False,
            "backlog_mutated": False,
            "secrets_stored": False,
            "inventory_mutated": False,
            "live_router_authorized": False,
            "live_meter_read": False,
            "suite_rewritten": False,
            "store_mutated": False,
            "live_execution_authorized": False,
            "charge_executed": False,
            "remote_index_queried": False,
            "live_dispatched": False,
            "pack_dispatched": False,
            "merge_executed": False,
            "draft_written": False,
            "record_persisted": False,
            "analysis_written": False,
            "production_router_verdict": "REJECT",
            "notes": list(self.notes),
            "authority": (
                "recursive_twin_note_taker_twin_search_model_decision_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RecursiveTwinNoteTakerTwinSearchModelDecisionComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_recursive_twin_note_taker_twin_search_model_decision(
    *,
    twin: object,
    twin_search_pack: object,
    operator_ack: object,
    require_both: object | None = None,
) -> RecursiveTwinNoteTakerTwinSearchModelDecisionCompose:
    """Recursive twin on twin search model decision pack. Never writes/dispatches."""
    if not isinstance(operator_ack, bool):
        raise RecursiveTwinNoteTakerTwinSearchModelDecisionComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(twin, dict):
        raise RecursiveTwinNoteTakerTwinSearchModelDecisionComposeError(
            "twin must be an object"
        )
    if not isinstance(twin_search_pack, dict):
        raise RecursiveTwinNoteTakerTwinSearchModelDecisionComposeError(
            "twin_search_pack must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise RecursiveTwinNoteTakerTwinSearchModelDecisionComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "twin_written=false — twin document not created/updated",
        "prompts_injected=false — no live LLM note-taker prompt injection",
        "live_dispatch_authorized=false — no automatic twin agent dispatch",
        "remote_index_queried=false · production_router_verdict=REJECT",
    ]

    try:
        t = compose_recursive_twin_note_taker(
            parent_asset_id=twin.get("parent_asset_id"),
            source_excerpt=twin.get("source_excerpt"),
            operator_ack=operator_ack,
            existing_twin_asset_id=twin.get("existing_twin_asset_id"),
            focus_questions=twin.get("focus_questions"),
        )
    except RecursiveTwinNoteTakerComposeError as e:
        raise RecursiveTwinNoteTakerTwinSearchModelDecisionComposeError(
            str(e)
        ) from e
    notes.extend(f"[twin] {n}" for n in t.notes)

    try:
        tsp = compose_twin_search_model_decision_html_native_settings_marketplace(
            search_query=twin_search_pack.get("search_query"),
            twin_records=twin_search_pack.get("twin_records"),
            model_decision_pack=twin_search_pack.get("model_decision_pack"),
            operator_ack=operator_ack,
            search_limit=twin_search_pack.get("search_limit"),
            require_both=twin_search_pack.get("require_both"),
        )
    except TwinSearchModelDecisionHtmlNativeSettingsMarketplaceComposeError as e:
        raise RecursiveTwinNoteTakerTwinSearchModelDecisionComposeError(
            str(e)
        ) from e
    notes.extend(f"[twin_search_pack] {n}" for n in tsp.notes)

    parent = _require_nonempty(t.parent_asset_id, field="parent_asset_id")
    session = _require_nonempty(tsp.session_id, field="session_id")
    title = _require_nonempty(tsp.title, field="title")
    account = _require_nonempty(tsp.account_id, field="account_id")
    week = _require_nonempty(tsp.week_id, field="week_id")
    asset = _require_nonempty(tsp.asset_id, field="asset_id")
    search_parent = _require_nonempty(
        tsp.parent_asset_id, field="twin_search_pack.parent_asset_id"
    )

    parent_aligned = parent == search_parent
    if not parent_aligned:
        notes.append(
            f"parent_aligned=false — twin.parent={parent} "
            f"twin_search_pack.parent={search_parent}"
        )
    else:
        notes.append("parent_aligned=true")

    if require:
        pack_ready = (
            t.twin_propose_ready is True
            and tsp.pack_ready is True
            and parent_aligned is True
            and t.twin_written is False
            and t.prompts_injected is False
            and t.live_dispatch_authorized is False
            and tsp.remote_index_queried is False
            and tsp.twin_written is False
            and tsp.purchase_executed is False
            and tsp.hosted is False
            and tsp.pdf_primary is False
            and tsp.pdf_view_authorized is False
            and tsp.secrets_stored is False
            and tsp.live_router_authorized is False
            and tsp.live_meter_read is False
            and tsp.inventory_mutated is False
            and tsp.suite_rewritten is False
            and tsp.charge_executed is False
            and tsp.production_router_verdict == "REJECT"
            and operator_ack is True
        )
    else:
        pack_ready = (
            operator_ack is True
            and t.twin_written is False
            and t.prompts_injected is False
            and t.live_dispatch_authorized is False
            and tsp.remote_index_queried is False
            and tsp.pdf_primary is False
            and tsp.production_router_verdict == "REJECT"
            and (t.twin_propose_ready is True or tsp.pack_ready is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — recursive twin note-taker + twin search model "
            "decision ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — twin, twin_search_pack, parent align, or "
            "operator_ack gate open"
        )

    if (
        t.twin_written is not False
        or t.prompts_injected is not False
        or t.live_dispatch_authorized is not False
        or tsp.remote_index_queried is not False
        or tsp.twin_written is not False
        or tsp.purchase_executed is not False
        or tsp.hosted is not False
        or tsp.pdf_primary is not False
        or tsp.pdf_view_authorized is not False
        or tsp.secrets_stored is not False
        or tsp.live_router_authorized is not False
        or tsp.live_meter_read is not False
        or tsp.inventory_mutated is not False
        or tsp.suite_rewritten is not False
        or tsp.charge_executed is not False
        or tsp.production_router_verdict != "REJECT"
    ):
        raise RecursiveTwinNoteTakerTwinSearchModelDecisionComposeError(
            "invariant: honesty flags must remain false / REJECT"
        )

    notes.extend(
        (
            "twin_written=false",
            "prompts_injected=false",
            "live_dispatch_authorized=false",
            "purchase_executed=false",
            "hosted=false",
            "pdf_view_authorized=false",
            "pdf_primary=false",
            "remote_fetched=false",
            "backlog_mutated=false",
            "secrets_stored=false",
            "inventory_mutated=false",
            "live_router_authorized=false",
            "live_meter_read=false",
            "suite_rewritten=false",
            "store_mutated=false",
            "live_execution_authorized=false",
            "charge_executed=false",
            "remote_index_queried=false",
            "live_dispatched=false",
            "pack_dispatched=false",
            "merge_executed=false",
            "draft_written=false",
            "record_persisted=false",
            "analysis_written=false",
            "production_router_verdict=REJECT",
        )
    )

    return RecursiveTwinNoteTakerTwinSearchModelDecisionCompose(
        session_id=session,
        parent_asset_id=parent,
        title=title,
        account_id=account,
        week_id=week,
        asset_id=asset,
        twin=t,
        twin_search_pack=tsp,
        parent_aligned=parent_aligned,
        pack_ready=pack_ready,
        twin_written=False,
        prompts_injected=False,
        live_dispatch_authorized=False,
        purchase_executed=False,
        hosted=False,
        pdf_view_authorized=False,
        pdf_primary=False,
        remote_fetched=False,
        backlog_mutated=False,
        secrets_stored=False,
        inventory_mutated=False,
        live_router_authorized=False,
        live_meter_read=False,
        suite_rewritten=False,
        store_mutated=False,
        live_execution_authorized=False,
        charge_executed=False,
        remote_index_queried=False,
        live_dispatched=False,
        pack_dispatched=False,
        merge_executed=False,
        draft_written=False,
        record_persisted=False,
        analysis_written=False,
        production_router_verdict="REJECT",
        notes=tuple(notes),
        authority=(
            "recursive_twin_note_taker_twin_search_model_decision_compose_advisory"
        ),
    )


def format_recursive_twin_note_taker_twin_search_model_decision_summary(
    c: RecursiveTwinNoteTakerTwinSearchModelDecisionCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"twin_propose_ready={c.twin.twin_propose_ready} · "
        f"hits={c.twin_search_pack.hit_count} · "
        f"parent_aligned={c.parent_aligned} · "
        f"verdict={c.production_router_verdict} · "
        "twin_written=false · remote_index_queried=false · pdf_primary=false"
    )


__all__ = [
    "RecursiveTwinNoteTakerTwinSearchModelDecisionCompose",
    "RecursiveTwinNoteTakerTwinSearchModelDecisionComposeError",
    "compose_recursive_twin_note_taker_twin_search_model_decision",
    "format_recursive_twin_note_taker_twin_search_model_decision_summary",
]
