"""Source attach (arxiv/substack) + quality gate + interrogation loop (pure).

remote_fetched / pdf_view_authorized / live_dispatch* / record_persisted /
prompts_injected / store_mutated always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.research_workstation_interrogation_loop_compose import (
    ResearchWorkstationInterrogationLoopCompose,
    ResearchWorkstationInterrogationLoopComposeError,
    compose_research_workstation_interrogation_loop,
)
from substrate.source_publication_dr_attach_quality_compose import (
    SourcePublicationDrAttachQualityCompose,
    SourcePublicationDrAttachQualityComposeError,
    compose_source_publication_dr_attach_quality,
)


class SourceAttachQualityInterrogationComposeError(ValueError):
    """Fail-closed validation for source attach quality interrogation pack."""


@dataclass(frozen=True)
class SourceAttachQualityInterrogationCompose:
    session_id: str
    parent_asset_id: str
    source_quality: SourcePublicationDrAttachQualityCompose
    interrogation: ResearchWorkstationInterrogationLoopCompose
    pack_ready: bool
    remote_fetched: bool
    pdf_view_authorized: bool
    live_dispatch_authorized: bool
    live_dispatched: bool
    record_persisted: bool
    prompts_injected: bool
    store_mutated: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "parent_asset_id": self.parent_asset_id,
            "source_quality": self.source_quality.to_dict(),
            "interrogation": self.interrogation.to_dict(),
            "pack_ready": self.pack_ready,
            "remote_fetched": False,
            "pdf_view_authorized": False,
            "live_dispatch_authorized": False,
            "live_dispatched": False,
            "record_persisted": False,
            "prompts_injected": False,
            "store_mutated": False,
            "notes": list(self.notes),
            "authority": (
                "source_attach_quality_interrogation_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SourceAttachQualityInterrogationComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def _seed_source_prior_records(
    sources: object,
    prior: object | None,
) -> list[dict[str, Any]]:
    """Seed prior records from attached source titles (caller-supplied only)."""
    records: list[dict[str, Any]] = []
    if prior is not None:
        if not isinstance(prior, list):
            raise SourceAttachQualityInterrogationComposeError(
                "prior_records must be an array when set"
            )
        for r in prior:
            if not isinstance(r, dict):
                raise SourceAttachQualityInterrogationComposeError(
                    "prior_records items must be objects"
                )
            records.append(r)
    if not isinstance(sources, list):
        raise SourceAttachQualityInterrogationComposeError(
            "sources must be an array"
        )
    for s in sources:
        if not isinstance(s, dict):
            raise SourceAttachQualityInterrogationComposeError(
                "sources items must be objects"
            )
        sid = str(s.get("source_id", "")).strip()
        title = str(s.get("title", "")).strip()
        if not sid or not title:
            raise SourceAttachQualityInterrogationComposeError(
                "sources items need source_id and title"
            )
        records.append(
            {
                "record_id": f"src-{sid}",
                "kind": "data",
                "body": title,
                "source_ref": sid,
            }
        )
    return records


def compose_source_attach_quality_interrogation(
    *,
    session_id: object,
    parent_asset_id: object,
    requested_families: object,
    sources: object,
    quality_overall: object,
    would_exceed: object,
    questions: object,
    chase_mode: object,
    user_prompt: object,
    selected_model_id: object,
    models: object,
    daily_cap_usd: object,
    spent_usd: object,
    operator_ack: object,
    citations: object | None = None,
    derive_citations_from_sources: object | None = None,
    quality_floor: object | None = None,
    operator_override: object | None = None,
    prior_records: object | None = None,
    projected_cost_usd_high: object | None = None,
    projected_cost_usd_low: object | None = None,
    bench_bests: object | None = None,
    focus_task: object | None = None,
    nd_shadow: object | None = None,
    require_both: object | None = None,
) -> SourceAttachQualityInterrogationCompose:
    """HTML source attach + quality + interrogation chase. Never scrapes/dispatches."""
    if not isinstance(operator_ack, bool):
        raise SourceAttachQualityInterrogationComposeError(
            "operator_ack must be an explicit boolean"
        )
    session = _require_nonempty(session_id, field="session_id")
    parent = _require_nonempty(parent_asset_id, field="parent_asset_id")

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise SourceAttachQualityInterrogationComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "remote_fetched=false — no live arxiv/substack scrape",
        "pdf_view_authorized=false — HTML-native sources only",
        "live_dispatch_authorized=false · live_dispatched=false",
        "record_persisted=false · prompts_injected=false · store_mutated=false",
    ]

    try:
        source_quality = compose_source_publication_dr_attach_quality(
            session_id=session,
            parent_asset_id=parent,
            requested_families=requested_families,
            sources=sources,
            quality_overall=quality_overall,
            would_exceed=would_exceed,
            operator_ack=operator_ack,
            citations=citations,
            derive_citations_from_sources=derive_citations_from_sources,
            quality_floor=quality_floor,
            operator_override=operator_override,
        )
    except SourcePublicationDrAttachQualityComposeError as e:
        raise SourceAttachQualityInterrogationComposeError(str(e)) from e
    notes.extend(f"[source_quality] {n}" for n in source_quality.notes)

    prior = _seed_source_prior_records(sources, prior_records)
    notes.append(
        f"prior_records_seeded={len(prior)} (source titles + caller priors)"
    )

    try:
        interrogation = compose_research_workstation_interrogation_loop(
            session_id=session,
            parent_asset_id=parent,
            questions=questions,
            chase_mode=chase_mode,
            prior_records=prior,
            user_prompt=user_prompt,
            selected_model_id=selected_model_id,
            models=models,
            daily_cap_usd=daily_cap_usd,
            spent_usd=spent_usd,
            projected_cost_usd_high=projected_cost_usd_high,
            projected_cost_usd_low=projected_cost_usd_low,
            would_exceed=would_exceed,
            operator_override=operator_override,
            source_families=requested_families,
            bench_bests=bench_bests,
            focus_task=(
                "deep_research" if focus_task is None else focus_task
            ),
            nd_shadow=nd_shadow,
            operator_ack=operator_ack,
            mark_for_twin_record=True,
        )
    except ResearchWorkstationInterrogationLoopComposeError as e:
        raise SourceAttachQualityInterrogationComposeError(str(e)) from e
    notes.extend(f"[interrogation] {n}" for n in interrogation.notes)

    if require:
        pack_ready = (
            source_quality.pack_ready is True
            and interrogation.loop_ready is True
            and operator_ack is True
        )
    else:
        pack_ready = operator_ack is True and (
            source_quality.pack_ready is True
            or interrogation.loop_ready is True
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — source attach/quality + interrogation ready; "
            "still pure"
        )
    else:
        notes.append(
            "pack_ready=false — source quality, interrogation, or "
            "operator_ack gate open"
        )

    if (
        source_quality.remote_fetched is not False
        or source_quality.pdf_view_authorized is not False
        or source_quality.live_dispatch_authorized is not False
        or source_quality.store_mutated is not False
        or interrogation.live_dispatched is not False
        or interrogation.record_persisted is not False
        or interrogation.prompts_injected is not False
    ):
        raise SourceAttachQualityInterrogationComposeError(
            "invariant: honesty flags must remain false"
        )

    notes.extend(
        (
            "remote_fetched=false",
            "pdf_view_authorized=false",
            "live_dispatch_authorized=false",
            "live_dispatched=false",
            "record_persisted=false",
            "prompts_injected=false",
            "store_mutated=false",
        )
    )

    return SourceAttachQualityInterrogationCompose(
        session_id=session,
        parent_asset_id=parent,
        source_quality=source_quality,
        interrogation=interrogation,
        pack_ready=pack_ready,
        remote_fetched=False,
        pdf_view_authorized=False,
        live_dispatch_authorized=False,
        live_dispatched=False,
        record_persisted=False,
        prompts_injected=False,
        store_mutated=False,
        notes=tuple(notes),
        authority="source_attach_quality_interrogation_compose_advisory",
    )


def format_source_attach_quality_interrogation_summary(
    c: SourceAttachQualityInterrogationCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"source_ready={c.source_quality.pack_ready} · "
        f"loop_ready={c.interrogation.loop_ready} · "
        f"sources={c.source_quality.attach.source_count} · "
        f"chase_slots={c.interrogation.chase.slot_count} · "
        f"remote_fetched=false · live_dispatched=false · "
        f"pdf_view_authorized=false"
    )


__all__ = [
    "SourceAttachQualityInterrogationCompose",
    "SourceAttachQualityInterrogationComposeError",
    "compose_source_attach_quality_interrogation",
    "format_source_attach_quality_interrogation_summary",
]
