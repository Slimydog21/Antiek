"""HTML-native source attach residual over Antiek-bench recommend + MO unattended (pure).

remote_fetched always False.
suite_rewritten / live_router_authorized always False.
live_execution_authorized / charge_executed always False.
pdf_primary always False.
production_router_verdict always REJECT.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.antiek_bench_recommend_mo_unattended_fullscreen_draft_compose import (
    AntiekBenchRecommendMoUnattendedFullscreenDraftCompose,
    AntiekBenchRecommendMoUnattendedFullscreenDraftComposeError,
    compose_antiek_bench_recommend_mo_unattended_fullscreen_draft,
)
from substrate.html_native_source_attach_compose import (
    HtmlNativeSourceAttachCompose,
    HtmlNativeSourceAttachComposeError,
    compose_html_native_source_attach,
)


class SourceAttachAntiekBenchRecommendMoUnattendedComposeError(ValueError):
    """Fail-closed validation for source-attach + bench recommend MO unattended pack."""


@dataclass(frozen=True)
class SourceAttachAntiekBenchRecommendMoUnattendedCompose:
    session_id: str
    parent_asset_id: str
    asset_id: str
    week_id: str
    focus_task: str
    title: str
    account_id: str
    operator_id: str
    sources: HtmlNativeSourceAttachCompose
    recommend_pack: AntiekBenchRecommendMoUnattendedFullscreenDraftCompose
    session_aligned: bool
    parent_aligned: bool
    pack_ready: bool
    attach_ready: bool
    remote_fetched: bool
    store_mutated: bool
    pdf_view_authorized: bool
    pdf_primary: bool
    suite_rewritten: bool
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
            "focus_task": self.focus_task,
            "title": self.title,
            "account_id": self.account_id,
            "operator_id": self.operator_id,
            "sources": self.sources.to_dict(),
            "recommend_pack": self.recommend_pack.to_dict(),
            "session_aligned": self.session_aligned,
            "parent_aligned": self.parent_aligned,
            "pack_ready": self.pack_ready,
            "attach_ready": self.attach_ready,
            "remote_fetched": False,
            "store_mutated": False,
            "pdf_view_authorized": False,
            "pdf_primary": False,
            "suite_rewritten": False,
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
                "source_attach_antiek_bench_recommend_mo_unattended_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SourceAttachAntiekBenchRecommendMoUnattendedComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_source_attach_antiek_bench_recommend_mo_unattended(
    *,
    sources: object,
    recommend_pack: object,
    operator_ack: object,
    require_both: object | None = None,
) -> SourceAttachAntiekBenchRecommendMoUnattendedCompose:
    """Source attach residual over bench recommend + MO unattended. Never remote-fetches."""
    if not isinstance(operator_ack, bool):
        raise SourceAttachAntiekBenchRecommendMoUnattendedComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(sources, dict):
        raise SourceAttachAntiekBenchRecommendMoUnattendedComposeError(
            "sources must be an object"
        )
    if not isinstance(recommend_pack, dict):
        raise SourceAttachAntiekBenchRecommendMoUnattendedComposeError(
            "recommend_pack must be an object"
        )

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise SourceAttachAntiekBenchRecommendMoUnattendedComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "remote_fetched=false — pure attach only (no live arxiv/substack)",
        "pdf_view_authorized=false · pdf_primary=false",
        "suite_rewritten=false · live_router_authorized=false",
        "live_execution_authorized=false · charge_executed=false",
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
        raise SourceAttachAntiekBenchRecommendMoUnattendedComposeError(
            str(e)
        ) from e
    notes.extend(f"[sources] {n}" for n in src.notes)

    try:
        rp = compose_antiek_bench_recommend_mo_unattended_fullscreen_draft(
            bench=recommend_pack.get("bench"),
            mo_pack=recommend_pack.get("mo_pack"),
            operator_ack=operator_ack,
            require_both=recommend_pack.get("require_both"),
        )
    except AntiekBenchRecommendMoUnattendedFullscreenDraftComposeError as e:
        raise SourceAttachAntiekBenchRecommendMoUnattendedComposeError(
            str(e)
        ) from e
    notes.extend(f"[recommend_pack] {n}" for n in rp.notes)

    session = _require_nonempty(src.session_id, field="session_id")
    parent = _require_nonempty(src.parent_asset_id, field="parent_asset_id")
    asset = _require_nonempty(rp.asset_id, field="asset_id")
    week_id = _require_nonempty(rp.week_id, field="week_id")
    focus = _require_nonempty(rp.focus_task, field="focus_task")
    title = _require_nonempty(rp.title, field="title")
    account = _require_nonempty(rp.account_id, field="account_id")
    op = _require_nonempty(rp.operator_id, field="operator_id")

    session_aligned = rp.session_id == session
    parent_aligned = (
        rp.parent_asset_id == parent or rp.asset_id == parent
    )
    if not session_aligned:
        notes.append(
            "session_id mismatch between sources and recommend_pack — pack_ready blocked"
        )
    if not parent_aligned:
        notes.append(
            "parent_asset_id mismatch between sources and recommend_pack — "
            "pack_ready blocked"
        )

    if require:
        pack_ready = (
            session_aligned
            and parent_aligned
            and src.attach_ready is True
            and rp.pack_ready is True
            and src.remote_fetched is False
            and src.pdf_view_authorized is False
            and src.store_mutated is False
            and rp.suite_rewritten is False
            and rp.live_router_authorized is False
            and rp.secrets_stored is False
            and rp.live_execution_authorized is False
            and rp.charge_executed is False
            and rp.production_router_verdict == "REJECT"
            and rp.pdf_primary is False
            and rp.remote_index_queried is False
            and rp.purchase_executed is False
            and rp.hosted is False
            and rp.inventory_mutated is False
            and operator_ack is True
        )
    else:
        pack_ready = (
            session_aligned
            and parent_aligned
            and operator_ack is True
            and src.remote_fetched is False
            and src.pdf_view_authorized is False
            and rp.production_router_verdict == "REJECT"
            and rp.pdf_primary is False
            and rp.suite_rewritten is False
            and (src.attach_ready is True or rp.pack_ready is True)
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — source attach + Antiek-bench recommend MO unattended "
            "ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — sources, recommend_pack, alignment, or operator_ack "
            "gate open"
        )

    if (
        src.remote_fetched is not False
        or src.pdf_view_authorized is not False
        or src.store_mutated is not False
        or rp.suite_rewritten is not False
        or rp.pdf_primary is not False
        or rp.live_router_authorized is not False
        or rp.secrets_stored is not False
        or rp.live_execution_authorized is not False
        or rp.charge_executed is not False
        or rp.remote_index_queried is not False
        or rp.purchase_executed is not False
        or rp.hosted is not False
        or rp.inventory_mutated is not False
        or rp.production_router_verdict != "REJECT"
    ):
        raise SourceAttachAntiekBenchRecommendMoUnattendedComposeError(
            "invariant: honesty flags must remain false / REJECT"
        )

    notes.extend(
        (
            "remote_fetched=false",
            "store_mutated=false",
            "pdf_view_authorized=false",
            "pdf_primary=false",
            "suite_rewritten=false",
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

    return SourceAttachAntiekBenchRecommendMoUnattendedCompose(
        session_id=session,
        parent_asset_id=parent,
        asset_id=asset,
        week_id=week_id,
        focus_task=focus,
        title=title,
        account_id=account,
        operator_id=op,
        sources=src,
        recommend_pack=rp,
        session_aligned=session_aligned,
        parent_aligned=parent_aligned,
        pack_ready=pack_ready,
        attach_ready=src.attach_ready,
        remote_fetched=False,
        store_mutated=False,
        pdf_view_authorized=False,
        pdf_primary=False,
        suite_rewritten=False,
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
            "source_attach_antiek_bench_recommend_mo_unattended_compose_advisory"
        ),
    )


def format_source_attach_antiek_bench_recommend_mo_unattended_summary(
    c: SourceAttachAntiekBenchRecommendMoUnattendedCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"attach_ready={c.attach_ready} · "
        f"recommend_ready={c.recommend_pack.pack_ready} · "
        f"sources={c.sources.source_count} · "
        f"html_ready={c.sources.html_ready_count} · "
        f"focus={c.focus_task} · "
        f"week={c.week_id} · "
        f"verdict={c.production_router_verdict} · "
        "remote_fetched=false · suite_rewritten=false · "
        "live_execution_authorized=false"
    )


__all__ = [
    "SourceAttachAntiekBenchRecommendMoUnattendedCompose",
    "SourceAttachAntiekBenchRecommendMoUnattendedComposeError",
    "compose_source_attach_antiek_bench_recommend_mo_unattended",
    "format_source_attach_antiek_bench_recommend_mo_unattended_summary",
]
