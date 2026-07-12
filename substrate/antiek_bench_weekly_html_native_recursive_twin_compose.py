"""Antiek-bench weekly usage-learn over HTML-native recursive twin settings
fullscreen MO pack (pure).

backlog_mutated / store_mutated / suite_rewritten always False.
pdf_view_authorized / pdf_primary always False.
twin_written / secrets_stored / charge_executed always False.
production_router_verdict always REJECT.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.antiek_bench_weekly_usage_learn_compose import (
    AntiekBenchWeeklyUsageLearnCompose,
    AntiekBenchWeeklyUsageLearnComposeError,
    compose_antiek_bench_weekly_usage_learn,
)
from substrate.html_native_recursive_twin_settings_fullscreen_mo_compose import (
    HtmlNativeRecursiveTwinSettingsFullscreenMoCompose,
    HtmlNativeRecursiveTwinSettingsFullscreenMoComposeError,
    compose_html_native_recursive_twin_settings_fullscreen_mo,
)


class AntiekBenchWeeklyHtmlNativeRecursiveTwinComposeError(ValueError):
    """Fail-closed validation for weekly bench + HTML-native recursive twin pack."""


@dataclass(frozen=True)
class AntiekBenchWeeklyHtmlNativeRecursiveTwinCompose:
    week_id: str
    session_id: str
    parent_asset_id: str
    asset_id: str
    weekly_learn: AntiekBenchWeeklyUsageLearnCompose
    html_pack: HtmlNativeRecursiveTwinSettingsFullscreenMoCompose
    pack_ready: bool
    learn_ready: bool
    backlog_mutated: bool
    store_mutated: bool
    pdf_view_authorized: bool
    pdf_primary: bool
    twin_written: bool
    prompts_injected: bool
    live_dispatch_authorized: bool
    secrets_stored: bool
    inventory_mutated: bool
    live_router_authorized: bool
    live_dispatched: bool
    pack_dispatched: bool
    merge_executed: bool
    live_execution_authorized: bool
    charge_executed: bool
    draft_written: bool
    record_persisted: bool
    remote_index_queried: bool
    analysis_written: bool
    production_router_verdict: str
    purchase_executed: bool
    hosted: bool
    suite_rewritten: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "week_id": self.week_id,
            "session_id": self.session_id,
            "parent_asset_id": self.parent_asset_id,
            "asset_id": self.asset_id,
            "weekly_learn": self.weekly_learn.to_dict(),
            "html_pack": self.html_pack.to_dict(),
            "pack_ready": self.pack_ready,
            "learn_ready": self.learn_ready,
            "backlog_mutated": False,
            "store_mutated": False,
            "pdf_view_authorized": False,
            "pdf_primary": False,
            "twin_written": False,
            "prompts_injected": False,
            "live_dispatch_authorized": False,
            "secrets_stored": False,
            "inventory_mutated": False,
            "live_router_authorized": False,
            "live_dispatched": False,
            "pack_dispatched": False,
            "merge_executed": False,
            "live_execution_authorized": False,
            "charge_executed": False,
            "draft_written": False,
            "record_persisted": False,
            "remote_index_queried": False,
            "analysis_written": False,
            "production_router_verdict": "REJECT",
            "purchase_executed": False,
            "hosted": False,
            "suite_rewritten": False,
            "notes": list(self.notes),
            "authority": (
                "antiek_bench_weekly_html_native_recursive_twin_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AntiekBenchWeeklyHtmlNativeRecursiveTwinComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_antiek_bench_weekly_html_native_recursive_twin(
    *,
    weekly_learn: object,
    html_pack: object,
    operator_ack: object,
    require_both: object | None = None,
) -> AntiekBenchWeeklyHtmlNativeRecursiveTwinCompose:
    """Weekly Antiek-bench learn + HTML-native recursive twin MO. Never mutates."""
    if not isinstance(operator_ack, bool):
        raise AntiekBenchWeeklyHtmlNativeRecursiveTwinComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(weekly_learn, dict):
        raise AntiekBenchWeeklyHtmlNativeRecursiveTwinComposeError(
            "weekly_learn must be an object"
        )
    if not isinstance(html_pack, dict):
        raise AntiekBenchWeeklyHtmlNativeRecursiveTwinComposeError(
            "html_pack must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise AntiekBenchWeeklyHtmlNativeRecursiveTwinComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "backlog_mutated=false · store_mutated=false · suite_rewritten=false",
        "pdf_view_authorized=false · pdf_primary=false",
        "twin_written=false · secrets_stored=false · charge_executed=false",
        "production_router_verdict=REJECT",
    ]

    try:
        wl = compose_antiek_bench_weekly_usage_learn(
            week_id=weekly_learn.get("week_id"),
            events=weekly_learn.get("events"),
            operator_ack=operator_ack,
            min_events_per_task=weekly_learn.get("min_events_per_task"),
        )
    except AntiekBenchWeeklyUsageLearnComposeError as e:
        raise AntiekBenchWeeklyHtmlNativeRecursiveTwinComposeError(str(e)) from e
    notes.extend(f"[weekly_learn] {n}" for n in wl.notes)

    try:
        hp = compose_html_native_recursive_twin_settings_fullscreen_mo(
            html_view=html_pack.get("html_view"),
            twin_pack=html_pack.get("twin_pack"),
            operator_ack=operator_ack,
            require_both=html_pack.get("require_both"),
        )
    except HtmlNativeRecursiveTwinSettingsFullscreenMoComposeError as e:
        raise AntiekBenchWeeklyHtmlNativeRecursiveTwinComposeError(str(e)) from e
    notes.extend(f"[html_pack] {n}" for n in hp.notes)

    week = _require_nonempty(wl.week_id, field="week_id")
    session = _require_nonempty(hp.session_id, field="session_id")
    asset = _require_nonempty(hp.asset_id, field="asset_id")
    parent = _require_nonempty(hp.parent_asset_id, field="parent_asset_id")

    if require:
        pack_ready = (
            wl.learn_ready is True
            and hp.pack_ready is True
            and wl.backlog_mutated is False
            and wl.store_mutated is False
            and hp.production_router_verdict == "REJECT"
            and hp.pdf_view_authorized is False
            and hp.pdf_primary is False
            and hp.twin_written is False
            and hp.secrets_stored is False
            and hp.charge_executed is False
            and operator_ack is True
        )
    else:
        pack_ready = (
            operator_ack is True
            and wl.backlog_mutated is False
            and wl.store_mutated is False
            and hp.production_router_verdict == "REJECT"
            and hp.pdf_view_authorized is False
            and hp.pdf_primary is False
            and (wl.learn_ready is True or hp.pack_ready is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — weekly bench learn + HTML-native recursive twin "
            "settings MO ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — weekly_learn, html_pack, or operator_ack gate open"
        )

    if (
        wl.backlog_mutated is not False
        or wl.store_mutated is not False
        or hp.pdf_view_authorized is not False
        or hp.pdf_primary is not False
        or hp.store_mutated is not False
        or hp.twin_written is not False
        or hp.secrets_stored is not False
        or hp.charge_executed is not False
        or hp.production_router_verdict != "REJECT"
    ):
        raise AntiekBenchWeeklyHtmlNativeRecursiveTwinComposeError(
            "invariant: honesty flags must remain false"
        )

    notes.extend(
        (
            "backlog_mutated=false",
            "store_mutated=false",
            "suite_rewritten=false",
            "pdf_view_authorized=false",
            "pdf_primary=false",
            "twin_written=false",
            "prompts_injected=false",
            "live_dispatch_authorized=false",
            "secrets_stored=false",
            "inventory_mutated=false",
            "live_router_authorized=false",
            "live_dispatched=false",
            "pack_dispatched=false",
            "merge_executed=false",
            "live_execution_authorized=false",
            "charge_executed=false",
            "draft_written=false",
            "record_persisted=false",
            "remote_index_queried=false",
            "analysis_written=false",
            "production_router_verdict=REJECT",
            "purchase_executed=false",
            "hosted=false",
        )
    )

    return AntiekBenchWeeklyHtmlNativeRecursiveTwinCompose(
        week_id=week,
        session_id=session,
        parent_asset_id=parent,
        asset_id=asset,
        weekly_learn=wl,
        html_pack=hp,
        pack_ready=pack_ready,
        learn_ready=wl.learn_ready,
        backlog_mutated=False,
        store_mutated=False,
        pdf_view_authorized=False,
        pdf_primary=False,
        twin_written=False,
        prompts_injected=False,
        live_dispatch_authorized=False,
        secrets_stored=False,
        inventory_mutated=False,
        live_router_authorized=False,
        live_dispatched=False,
        pack_dispatched=False,
        merge_executed=False,
        live_execution_authorized=False,
        charge_executed=False,
        draft_written=False,
        record_persisted=False,
        remote_index_queried=False,
        analysis_written=False,
        production_router_verdict="REJECT",
        purchase_executed=False,
        hosted=False,
        suite_rewritten=False,
        notes=tuple(notes),
        authority=(
            "antiek_bench_weekly_html_native_recursive_twin_compose_advisory"
        ),
    )


def format_antiek_bench_weekly_html_native_recursive_twin_summary(
    c: AntiekBenchWeeklyHtmlNativeRecursiveTwinCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"learn_ready={c.learn_ready} · "
        f"html_ready={c.html_pack.pack_ready} · "
        f"week={c.week_id} · "
        f"proposals={c.weekly_learn.proposal_count} · "
        f"verdict={c.production_router_verdict} · "
        f"backlog_mutated=false · suite_rewritten=false · pdf_primary=false"
    )


__all__ = [
    "AntiekBenchWeeklyHtmlNativeRecursiveTwinCompose",
    "AntiekBenchWeeklyHtmlNativeRecursiveTwinComposeError",
    "compose_antiek_bench_weekly_html_native_recursive_twin",
    "format_antiek_bench_weekly_html_native_recursive_twin_summary",
]
