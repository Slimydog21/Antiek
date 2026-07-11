"""Midnight Oil + source attach quality → twin chase feed (pure).

live_execution_authorized / remote_fetched / twin_written /
live_dispatched / prompts_injected / store_mutated always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.midnight_oil_source_attach_quality_compose import (
    MidnightOilSourceAttachQualityCompose,
    MidnightOilSourceAttachQualityComposeError,
    compose_midnight_oil_source_attach_quality,
)
from substrate.twin_chase_analysis_feed_compose import (
    TwinChaseAnalysisFeedCompose,
    TwinChaseAnalysisFeedComposeError,
    compose_twin_chase_analysis_feed,
)


class MidnightOilSourceAttachQualityTwinComposeError(ValueError):
    """Fail-closed validation for MO source twin pack."""


@dataclass(frozen=True)
class MidnightOilSourceAttachQualityTwinCompose:
    operator_id: str
    session_id: str
    parent_asset_id: str
    mo_source: MidnightOilSourceAttachQualityCompose
    twin_feed: TwinChaseAnalysisFeedCompose
    pack_ready: bool
    live_execution_authorized: bool
    remote_fetched: bool
    pdf_view_authorized: bool
    twin_written: bool
    live_dispatched: bool
    prompts_injected: bool
    store_mutated: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "operator_id": self.operator_id,
            "session_id": self.session_id,
            "parent_asset_id": self.parent_asset_id,
            "mo_source": self.mo_source.to_dict(),
            "twin_feed": self.twin_feed.to_dict(),
            "pack_ready": self.pack_ready,
            "live_execution_authorized": False,
            "remote_fetched": False,
            "pdf_view_authorized": False,
            "twin_written": False,
            "live_dispatched": False,
            "prompts_injected": False,
            "store_mutated": False,
            "notes": list(self.notes),
            "authority": (
                "midnight_oil_source_attach_quality_twin_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MidnightOilSourceAttachQualityTwinComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def _derive_findings(sources: object, goals: object) -> list[dict[str, Any]]:
    if not isinstance(sources, list):
        raise MidnightOilSourceAttachQualityTwinComposeError(
            "sources must be an array"
        )
    if not isinstance(goals, list):
        raise MidnightOilSourceAttachQualityTwinComposeError(
            "goals must be an array"
        )
    findings: list[dict[str, Any]] = []
    for s in sources:
        if not isinstance(s, dict):
            raise MidnightOilSourceAttachQualityTwinComposeError(
                "sources items must be objects"
            )
        sid = str(s.get("source_id", "")).strip()
        title = str(s.get("title", "")).strip()
        if not sid or not title:
            raise MidnightOilSourceAttachQualityTwinComposeError(
                "sources items need source_id and title"
            )
        findings.append(
            {"source_id": f"src-{sid}", "body": title, "kind": "data"}
        )
    for g in goals:
        if not isinstance(g, dict):
            raise MidnightOilSourceAttachQualityTwinComposeError(
                "goals items must be objects"
            )
        gid = str(g.get("goal_id", "")).strip()
        title = str(g.get("title", "")).strip()
        if not gid or not title:
            raise MidnightOilSourceAttachQualityTwinComposeError(
                "goals items need goal_id and title"
            )
        findings.append(
            {"source_id": f"goal-{gid}", "body": title, "kind": "question"}
        )
    return findings


def compose_midnight_oil_source_attach_quality_twin(
    *,
    operator_id: object,
    work_minutes: object,
    goals: object,
    operator_ack: object,
    unattended_ack: object,
    spend_consent: object,
    session_id: object,
    parent_asset_id: object,
    requested_families: object,
    sources: object,
    quality_overall: object,
    would_exceed: object,
    usd_per_hour: object | None = None,
    approved_ceiling_usd: object | None = None,
    brief_dispatch_ready: object | None = None,
    citations: object | None = None,
    derive_citations_from_sources: object | None = None,
    quality_floor: object | None = None,
    operator_override: object | None = None,
    require_both: object | None = None,
    existing_twin_asset_id: object | None = None,
    analysis_excerpt: object | None = None,
    mark_for_prompt_context: object | None = None,
    twin_findings: object | None = None,
    require_both_with_twin: object | None = None,
) -> MidnightOilSourceAttachQualityTwinCompose:
    """MO+source quality + twin feed. Never launches/scrapes/writes twin."""
    if not isinstance(operator_ack, bool):
        raise MidnightOilSourceAttachQualityTwinComposeError(
            "operator_ack must be an explicit boolean"
        )
    op = _require_nonempty(operator_id, field="operator_id")
    session = _require_nonempty(session_id, field="session_id")
    parent = _require_nonempty(parent_asset_id, field="parent_asset_id")

    require_twin = (
        True if require_both_with_twin is None else require_both_with_twin
    )
    if not isinstance(require_twin, bool):
        raise MidnightOilSourceAttachQualityTwinComposeError(
            "require_both_with_twin must be boolean when set"
        )

    mark_prompt = (
        True if mark_for_prompt_context is None else mark_for_prompt_context
    )
    if not isinstance(mark_prompt, bool):
        raise MidnightOilSourceAttachQualityTwinComposeError(
            "mark_for_prompt_context must be boolean when set"
        )

    notes: list[str] = [
        "live_execution_authorized=false — midnight oil never launches workers",
        "remote_fetched=false · pdf_view_authorized=false",
        "twin_written=false · prompts_injected=false · live_dispatched=false",
    ]

    try:
        mo_source = compose_midnight_oil_source_attach_quality(
            operator_id=op,
            work_minutes=work_minutes,
            goals=goals,
            operator_ack=operator_ack,
            unattended_ack=unattended_ack,
            spend_consent=spend_consent,
            session_id=session,
            parent_asset_id=parent,
            requested_families=requested_families,
            sources=sources,
            quality_overall=quality_overall,
            would_exceed=would_exceed,
            usd_per_hour=usd_per_hour,
            approved_ceiling_usd=approved_ceiling_usd,
            brief_dispatch_ready=brief_dispatch_ready,
            citations=citations,
            derive_citations_from_sources=derive_citations_from_sources,
            quality_floor=quality_floor,
            operator_override=operator_override,
            require_both=require_both,
        )
    except MidnightOilSourceAttachQualityComposeError as e:
        raise MidnightOilSourceAttachQualityTwinComposeError(str(e)) from e
    notes.extend(f"[mo_source] {n}" for n in mo_source.notes)

    if twin_findings is not None:
        if not isinstance(twin_findings, list):
            raise MidnightOilSourceAttachQualityTwinComposeError(
                "twin_findings must be an array when set"
            )
        findings = twin_findings
        notes.append(f"twin_findings={len(findings)} caller-supplied")
    else:
        findings = _derive_findings(sources, goals)
        notes.append(
            f"twin_findings={len(findings)} derived from sources+goals"
        )

    try:
        twin_feed = compose_twin_chase_analysis_feed(
            session_id=session,
            parent_asset_id=parent,
            findings=findings,
            operator_ack=operator_ack,
            analysis_excerpt=analysis_excerpt,
            existing_twin_asset_id=existing_twin_asset_id,
            mark_for_prompt_context=mark_prompt,
        )
    except TwinChaseAnalysisFeedComposeError as e:
        raise MidnightOilSourceAttachQualityTwinComposeError(str(e)) from e
    notes.extend(f"[twin_feed] {n}" for n in twin_feed.notes)

    if require_twin:
        pack_ready = (
            mo_source.pack_ready is True
            and twin_feed.feed_ready is True
            and operator_ack is True
        )
    else:
        pack_ready = operator_ack is True and (
            mo_source.pack_ready is True or twin_feed.feed_ready is True
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — MO+sources + twin feed ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — MO+source, twin feed, or operator_ack gate open"
        )

    if (
        mo_source.live_execution_authorized is not False
        or mo_source.remote_fetched is not False
        or twin_feed.twin_written is not False
        or twin_feed.prompts_injected is not False
    ):
        raise MidnightOilSourceAttachQualityTwinComposeError(
            "invariant: honesty flags must remain false"
        )

    notes.extend(
        (
            "live_execution_authorized=false",
            "remote_fetched=false",
            "pdf_view_authorized=false",
            "twin_written=false",
            "live_dispatched=false",
            "prompts_injected=false",
            "store_mutated=false",
        )
    )

    return MidnightOilSourceAttachQualityTwinCompose(
        operator_id=op,
        session_id=session,
        parent_asset_id=parent,
        mo_source=mo_source,
        twin_feed=twin_feed,
        pack_ready=pack_ready,
        live_execution_authorized=False,
        remote_fetched=False,
        pdf_view_authorized=False,
        twin_written=False,
        live_dispatched=False,
        prompts_injected=False,
        store_mutated=False,
        notes=tuple(notes),
        authority="midnight_oil_source_attach_quality_twin_compose_advisory",
    )


def format_midnight_oil_source_attach_quality_twin_summary(
    c: MidnightOilSourceAttachQualityTwinCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"mo_source_ready={c.mo_source.pack_ready} · "
        f"twin_feed_ready={c.twin_feed.feed_ready} · "
        f"findings={c.twin_feed.finding_count} · "
        f"live_execution_authorized=false · twin_written=false · "
        f"remote_fetched=false"
    )


__all__ = [
    "MidnightOilSourceAttachQualityTwinCompose",
    "MidnightOilSourceAttachQualityTwinComposeError",
    "compose_midnight_oil_source_attach_quality_twin",
    "format_midnight_oil_source_attach_quality_twin_summary",
]
