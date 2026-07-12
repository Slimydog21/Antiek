"""NotDiamond shadow REJECT over source-attach weekly learn twin presentation (pure).

live_router_authorized always False.
remote_fetched / backlog_mutated / twin_written always False.
production_router_verdict always REJECT.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.notdiamond_shadow_advisory_compose import (
    NotDiamondShadowAdvisoryCompose,
    NotDiamondShadowAdvisoryComposeError,
    compose_notdiamond_shadow_advisory,
)
from substrate.source_attach_antiek_bench_weekly_learn_twin_presentation_compose import (
    SourceAttachAntiekBenchWeeklyLearnTwinPresentationCompose,
    SourceAttachAntiekBenchWeeklyLearnTwinPresentationComposeError,
    compose_source_attach_antiek_bench_weekly_learn_twin_presentation,
)


class NdShadowSourceAttachWeeklyLearnTwinPresentationComposeError(ValueError):
    """Fail-closed validation for ND shadow + source-attach weekly learn pack."""


@dataclass(frozen=True)
class NdShadowSourceAttachWeeklyLearnTwinPresentationCompose:
    session_id: str
    parent_asset_id: str
    week_id: str
    asset_id: str
    title: str
    account_id: str
    nd_shadow: NotDiamondShadowAdvisoryCompose
    source_pack: SourceAttachAntiekBenchWeeklyLearnTwinPresentationCompose
    pack_ready: bool
    live_router_authorized: bool
    remote_fetched: bool
    live_dispatch_authorized: bool
    backlog_mutated: bool
    store_mutated: bool
    suite_rewritten: bool
    twin_written: bool
    prompts_injected: bool
    merge_executed: bool
    draft_written: bool
    analysis_written: bool
    live_dispatched: bool
    pack_dispatched: bool
    live_execution_authorized: bool
    secrets_stored: bool
    live_meter_read: bool
    remote_index_queried: bool
    pdf_view_authorized: bool
    pdf_primary: bool
    inventory_mutated: bool
    charge_executed: bool
    record_persisted: bool
    purchase_executed: bool
    hosted: bool
    production_router_verdict: str
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "parent_asset_id": self.parent_asset_id,
            "week_id": self.week_id,
            "asset_id": self.asset_id,
            "title": self.title,
            "account_id": self.account_id,
            "nd_shadow": self.nd_shadow.to_dict(),
            "source_pack": self.source_pack.to_dict(),
            "pack_ready": self.pack_ready,
            "live_router_authorized": False,
            "remote_fetched": False,
            "live_dispatch_authorized": False,
            "backlog_mutated": False,
            "store_mutated": False,
            "suite_rewritten": False,
            "twin_written": False,
            "prompts_injected": False,
            "merge_executed": False,
            "draft_written": False,
            "analysis_written": False,
            "live_dispatched": False,
            "pack_dispatched": False,
            "live_execution_authorized": False,
            "secrets_stored": False,
            "live_meter_read": False,
            "remote_index_queried": False,
            "pdf_view_authorized": False,
            "pdf_primary": False,
            "inventory_mutated": False,
            "charge_executed": False,
            "record_persisted": False,
            "purchase_executed": False,
            "hosted": False,
            "production_router_verdict": "REJECT",
            "notes": list(self.notes),
            "authority": (
                "nd_shadow_source_attach_weekly_learn_twin_presentation_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise NdShadowSourceAttachWeeklyLearnTwinPresentationComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_nd_shadow_source_attach_weekly_learn_twin_presentation(
    *,
    nd_shadow: object,
    source_pack: object,
    operator_ack: object,
    require_both: object | None = None,
) -> NdShadowSourceAttachWeeklyLearnTwinPresentationCompose:
    """ND shadow REJECT + source-attach weekly learn twin presentation. Never routes."""
    if not isinstance(operator_ack, bool):
        raise NdShadowSourceAttachWeeklyLearnTwinPresentationComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(nd_shadow, dict):
        raise NdShadowSourceAttachWeeklyLearnTwinPresentationComposeError(
            "nd_shadow must be an object"
        )
    if not isinstance(source_pack, dict):
        raise NdShadowSourceAttachWeeklyLearnTwinPresentationComposeError(
            "source_pack must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise NdShadowSourceAttachWeeklyLearnTwinPresentationComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "production_router_verdict=REJECT — NotDiamond is not production router (§16)",
        "live_router_authorized=false · remote_fetched=false · twin_written=false",
        "backlog_mutated=false · suite_rewritten=false",
    ]

    try:
        nd = compose_notdiamond_shadow_advisory(
            selected_model_id=nd_shadow.get("selected_model_id"),
            nd_recommended_model_id=nd_shadow.get("nd_recommended_model_id"),
            kill_switch_on=nd_shadow.get("kill_switch_on"),
            confidence=nd_shadow.get("confidence"),
            task=nd_shadow.get("task"),
            inventory_model_ids=nd_shadow.get("inventory_model_ids"),
        )
    except NotDiamondShadowAdvisoryComposeError as e:
        raise NdShadowSourceAttachWeeklyLearnTwinPresentationComposeError(
            str(e)
        ) from e
    notes.extend(f"[nd_shadow] {n}" for n in nd.notes)

    if nd.production_router_verdict != "REJECT":
        raise NdShadowSourceAttachWeeklyLearnTwinPresentationComposeError(
            "invariant: production_router_verdict must be REJECT"
        )
    if nd.live_router_authorized is not False:
        raise NdShadowSourceAttachWeeklyLearnTwinPresentationComposeError(
            "invariant: live_router_authorized must be false"
        )

    try:
        sp = compose_source_attach_antiek_bench_weekly_learn_twin_presentation(
            sources=source_pack.get("sources"),
            weekly_pack=source_pack.get("weekly_pack"),
            operator_ack=operator_ack,
            require_both=source_pack.get("require_both"),
        )
    except SourceAttachAntiekBenchWeeklyLearnTwinPresentationComposeError as e:
        raise NdShadowSourceAttachWeeklyLearnTwinPresentationComposeError(
            str(e)
        ) from e
    notes.extend(f"[source_pack] {n}" for n in sp.notes)

    session = _require_nonempty(sp.session_id, field="session_id")
    parent = _require_nonempty(sp.parent_asset_id, field="parent_asset_id")
    week = _require_nonempty(sp.week_id, field="week_id")
    asset = _require_nonempty(sp.asset_id, field="asset_id")
    title = _require_nonempty(sp.title, field="title")
    account = _require_nonempty(sp.account_id, field="account_id")

    nd_gate = (
        nd.production_router_verdict == "REJECT"
        and nd.live_router_authorized is False
    )

    if require:
        pack_ready = (
            nd_gate
            and sp.pack_ready is True
            and sp.remote_fetched is False
            and sp.live_dispatch_authorized is False
            and sp.backlog_mutated is False
            and sp.store_mutated is False
            and sp.suite_rewritten is False
            and sp.twin_written is False
            and sp.merge_executed is False
            and sp.draft_written is False
            and sp.live_dispatched is False
            and sp.live_router_authorized is False
            and sp.secrets_stored is False
            and sp.remote_index_queried is False
            and sp.pdf_primary is False
            and sp.production_router_verdict == "REJECT"
            and operator_ack is True
        )
    else:
        pack_ready = (
            nd_gate
            and operator_ack is True
            and sp.remote_fetched is False
            and sp.production_router_verdict == "REJECT"
            and sp.pdf_primary is False
            and (sp.pack_ready is True or nd.shadow_visible is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — ND shadow REJECT re-affirmed on source-attach weekly "
            "learn pack; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — nd_shadow, source_pack, or operator_ack gate open"
        )

    if (
        nd.live_router_authorized is not False
        or nd.production_router_verdict != "REJECT"
        or sp.remote_fetched is not False
        or sp.live_dispatch_authorized is not False
        or sp.backlog_mutated is not False
        or sp.store_mutated is not False
        or sp.suite_rewritten is not False
        or sp.twin_written is not False
        or sp.merge_executed is not False
        or sp.draft_written is not False
        or sp.live_dispatched is not False
        or sp.live_router_authorized is not False
        or sp.secrets_stored is not False
        or sp.remote_index_queried is not False
        or sp.pdf_primary is not False
        or sp.production_router_verdict != "REJECT"
    ):
        raise NdShadowSourceAttachWeeklyLearnTwinPresentationComposeError(
            "invariant: honesty flags must remain false / REJECT"
        )

    notes.extend(
        (
            "live_router_authorized=false",
            "remote_fetched=false",
            "live_dispatch_authorized=false",
            "backlog_mutated=false",
            "store_mutated=false",
            "suite_rewritten=false",
            "twin_written=false",
            "prompts_injected=false",
            "merge_executed=false",
            "draft_written=false",
            "analysis_written=false",
            "live_dispatched=false",
            "pack_dispatched=false",
            "live_execution_authorized=false",
            "secrets_stored=false",
            "live_meter_read=false",
            "remote_index_queried=false",
            "pdf_view_authorized=false",
            "pdf_primary=false",
            "inventory_mutated=false",
            "charge_executed=false",
            "record_persisted=false",
            "purchase_executed=false",
            "hosted=false",
            "production_router_verdict=REJECT",
        )
    )

    return NdShadowSourceAttachWeeklyLearnTwinPresentationCompose(
        session_id=session,
        parent_asset_id=parent,
        week_id=week,
        asset_id=asset,
        title=title,
        account_id=account,
        nd_shadow=nd,
        source_pack=sp,
        pack_ready=pack_ready,
        live_router_authorized=False,
        remote_fetched=False,
        live_dispatch_authorized=False,
        backlog_mutated=False,
        store_mutated=False,
        suite_rewritten=False,
        twin_written=False,
        prompts_injected=False,
        merge_executed=False,
        draft_written=False,
        analysis_written=False,
        live_dispatched=False,
        pack_dispatched=False,
        live_execution_authorized=False,
        secrets_stored=False,
        live_meter_read=False,
        remote_index_queried=False,
        pdf_view_authorized=False,
        pdf_primary=False,
        inventory_mutated=False,
        charge_executed=False,
        record_persisted=False,
        purchase_executed=False,
        hosted=False,
        production_router_verdict="REJECT",
        notes=tuple(notes),
        authority=(
            "nd_shadow_source_attach_weekly_learn_twin_presentation_compose_advisory"
        ),
    )


def format_nd_shadow_source_attach_weekly_learn_twin_presentation_summary(
    c: NdShadowSourceAttachWeeklyLearnTwinPresentationCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"nd_verdict={c.nd_shadow.production_router_verdict} · "
        f"source_ready={c.source_pack.pack_ready} · "
        f"shadow_visible={c.nd_shadow.shadow_visible} · "
        f"verdict={c.production_router_verdict} · "
        "live_router_authorized=false · remote_fetched=false · twin_written=false"
    )


__all__ = [
    "NdShadowSourceAttachWeeklyLearnTwinPresentationCompose",
    "NdShadowSourceAttachWeeklyLearnTwinPresentationComposeError",
    "compose_nd_shadow_source_attach_weekly_learn_twin_presentation",
    "format_nd_shadow_source_attach_weekly_learn_twin_presentation_summary",
]
