"""Model decision tree + HTML-native competition pack (pure).

live_router_authorized / secrets_stored / live_meter_read always False.
pdf_view_authorized / pdf_primary always False.
live_dispatch_authorized / remote_fetched / remote_index_queried always False.
draft_written / analysis_written / merge_executed / twin_written always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.html_native_competition_write_twin_search_compose import (
    HtmlNativeCompetitionWriteTwinSearchCompose,
    HtmlNativeCompetitionWriteTwinSearchComposeError,
    compose_html_native_competition_write_twin_search,
)
from substrate.settings_decision_tree_usage_bar_compose import (
    SettingsDecisionTreeUsageBarCompose,
    SettingsDecisionTreeUsageBarComposeError,
    compose_settings_decision_tree_usage_bar,
)


class ModelDecisionHtmlNativeCompetitionComposeError(ValueError):
    """Fail-closed validation for model decision + HTML competition pack."""


@dataclass(frozen=True)
class ModelDecisionHtmlNativeCompetitionCompose:
    session_id: str
    asset_id: str
    decision: SettingsDecisionTreeUsageBarCompose
    competition_view: HtmlNativeCompetitionWriteTwinSearchCompose
    pack_ready: bool
    live_router_authorized: bool
    secrets_stored: bool
    live_meter_read: bool
    pdf_view_authorized: bool
    pdf_primary: bool
    live_dispatch_authorized: bool
    remote_fetched: bool
    backlog_mutated: bool
    draft_written: bool
    analysis_written: bool
    merge_executed: bool
    remote_index_queried: bool
    twin_written: bool
    store_mutated: bool
    live_dispatched: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "asset_id": self.asset_id,
            "decision": self.decision.to_dict(),
            "competition_view": self.competition_view.to_dict(),
            "pack_ready": self.pack_ready,
            "live_router_authorized": False,
            "secrets_stored": False,
            "live_meter_read": False,
            "pdf_view_authorized": False,
            "pdf_primary": False,
            "live_dispatch_authorized": False,
            "remote_fetched": False,
            "backlog_mutated": False,
            "draft_written": False,
            "analysis_written": False,
            "merge_executed": False,
            "remote_index_queried": False,
            "twin_written": False,
            "store_mutated": False,
            "live_dispatched": False,
            "notes": list(self.notes),
            "authority": (
                "model_decision_html_native_competition_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ModelDecisionHtmlNativeCompetitionComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_model_decision_html_native_competition(
    *,
    decision: object,
    competition_view: object,
    operator_ack: object,
    require_both: object | None = None,
    block_on_budget_exceed: object | None = None,
) -> ModelDecisionHtmlNativeCompetitionCompose:
    """Model decision + HTML-native competition pack. Never routes/writes."""
    if not isinstance(operator_ack, bool):
        raise ModelDecisionHtmlNativeCompetitionComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(decision, dict):
        raise ModelDecisionHtmlNativeCompetitionComposeError(
            "decision must be an object"
        )
    if not isinstance(competition_view, dict):
        raise ModelDecisionHtmlNativeCompetitionComposeError(
            "competition_view must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise ModelDecisionHtmlNativeCompetitionComposeError(
            "require_both must be boolean when set"
        )
    block_budget = (
        True if block_on_budget_exceed is None else block_on_budget_exceed
    )
    if not isinstance(block_budget, bool):
        raise ModelDecisionHtmlNativeCompetitionComposeError(
            "block_on_budget_exceed must be boolean when set"
        )

    session = _require_nonempty(
        competition_view.get("session_id"), field="competition_view.session_id"
    )
    asset = _require_nonempty(
        competition_view.get("asset_id"), field="competition_view.asset_id"
    )

    notes: list[str] = [
        "live_router_authorized=false · secrets_stored=false · live_meter_read=false",
        "pdf_view_authorized=false · pdf_primary=false",
        "live_dispatch_authorized=false · remote_fetched=false · remote_index_queried=false",
        "draft_written=false · analysis_written=false · merge_executed=false · twin_written=false",
        "store_mutated=false · live_dispatched=false · backlog_mutated=false",
    ]

    try:
        decision_pack = compose_settings_decision_tree_usage_bar(
            selected_model_id=decision.get("selected_model_id"),
            models=decision.get("models"),
            daily_cap_usd=decision.get("daily_cap_usd"),
            spent_usd=decision.get("spent_usd"),
            operator_ack=operator_ack,
            projected_cost_usd_high=decision.get("projected_cost_usd_high"),
            projected_cost_usd_low=decision.get("projected_cost_usd_low"),
            bench_bests=decision.get("bench_bests"),
            focus_task=decision.get("focus_task"),
            nd_shadow=decision.get("nd_shadow"),
            pending_add_model_ids=decision.get("pending_add_model_ids"),
        )
    except SettingsDecisionTreeUsageBarComposeError as e:
        raise ModelDecisionHtmlNativeCompetitionComposeError(str(e)) from e
    notes.extend(f"[decision] {n}" for n in decision_pack.notes)

    competition_body = competition_view.get("competition")
    if not isinstance(competition_body, dict):
        raise ModelDecisionHtmlNativeCompetitionComposeError(
            "competition_view.competition must be an object"
        )

    try:
        competition_pack = compose_html_native_competition_write_twin_search(
            session_id=session,
            asset_id=asset,
            html_projection_sha=competition_view.get("html_projection_sha"),
            view_requested=competition_view.get("view_requested"),
            twin_bound=competition_view.get("twin_bound"),
            operator_ack=operator_ack,
            competition=competition_body,
            twin_substrate_ready=competition_view.get("twin_substrate_ready"),
            claimed_format=competition_view.get("claimed_format"),
            reading=competition_view.get("reading"),
            research=competition_view.get("research"),
            require_both=competition_view.get("require_both"),
        )
    except HtmlNativeCompetitionWriteTwinSearchComposeError as e:
        raise ModelDecisionHtmlNativeCompetitionComposeError(str(e)) from e
    notes.extend(f"[competition_view] {n}" for n in competition_pack.notes)

    budget_ok = (not block_budget) or (decision_pack.would_exceed is not True)
    if not budget_ok:
        notes.append(
            "budget_block=true — decision.would_exceed=true blocks pack_ready"
        )

    if require:
        pack_ready = (
            decision_pack.decision_ready is True
            and competition_pack.pack_ready is True
            and budget_ok
            and operator_ack is True
        )
    else:
        pack_ready = (
            operator_ack is True
            and budget_ok
            and (
                decision_pack.decision_ready is True
                or competition_pack.pack_ready is True
            )
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — model decision + HTML-native competition pack ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — decision, competition_view, budget, or operator_ack gate open"
        )

    if (
        decision_pack.live_router_authorized is not False
        or decision_pack.secrets_stored is not False
        or decision_pack.live_meter_read is not False
        or competition_pack.pdf_view_authorized is not False
        or competition_pack.pdf_primary is not False
        or competition_pack.live_dispatch_authorized is not False
        or competition_pack.remote_fetched is not False
        or competition_pack.remote_index_queried is not False
        or competition_pack.draft_written is not False
        or competition_pack.twin_written is not False
        or competition_pack.store_mutated is not False
    ):
        raise ModelDecisionHtmlNativeCompetitionComposeError(
            "invariant: honesty flags must remain false"
        )

    notes.extend(
        (
            "live_router_authorized=false",
            "secrets_stored=false",
            "live_meter_read=false",
            "pdf_view_authorized=false",
            "pdf_primary=false",
            "live_dispatch_authorized=false",
            "remote_fetched=false",
            "backlog_mutated=false",
            "draft_written=false",
            "analysis_written=false",
            "merge_executed=false",
            "remote_index_queried=false",
            "twin_written=false",
            "store_mutated=false",
            "live_dispatched=false",
        )
    )

    return ModelDecisionHtmlNativeCompetitionCompose(
        session_id=session,
        asset_id=asset,
        decision=decision_pack,
        competition_view=competition_pack,
        pack_ready=pack_ready,
        live_router_authorized=False,
        secrets_stored=False,
        live_meter_read=False,
        pdf_view_authorized=False,
        pdf_primary=False,
        live_dispatch_authorized=False,
        remote_fetched=False,
        backlog_mutated=False,
        draft_written=False,
        analysis_written=False,
        merge_executed=False,
        remote_index_queried=False,
        twin_written=False,
        store_mutated=False,
        live_dispatched=False,
        notes=tuple(notes),
        authority="model_decision_html_native_competition_compose_advisory",
    )


def format_model_decision_html_native_competition_summary(
    c: ModelDecisionHtmlNativeCompetitionCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"decision_ready={c.decision.decision_ready} · "
        f"competition_ready={c.competition_view.pack_ready} · "
        f"would_exceed={c.decision.would_exceed} · "
        f"model={c.decision.driver.decision.selected_model_id} · "
        f"live_router_authorized=false · pdf_view_authorized=false · "
        f"remote_index_queried=false · twin_written=false"
    )


__all__ = [
    "ModelDecisionHtmlNativeCompetitionCompose",
    "ModelDecisionHtmlNativeCompetitionComposeError",
    "compose_model_decision_html_native_competition",
    "format_model_decision_html_native_competition_summary",
]
