"""Highlight → floating DR + source attach quality interrogation (pure).

live_dispatched / merge_executed / remote_fetched / pdf_view_authorized
always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.highlight_deep_research_launch_compose import (
    HighlightDeepResearchLaunchCompose,
    HighlightDeepResearchLaunchComposeError,
    compose_highlight_deep_research_launch,
)
from substrate.source_attach_quality_interrogation_compose import (
    SourceAttachQualityInterrogationCompose,
    SourceAttachQualityInterrogationComposeError,
    compose_source_attach_quality_interrogation,
)


class HighlightSourceAttachQualityInterrogationComposeError(ValueError):
    """Fail-closed validation for highlight source attach interrogation pack."""


@dataclass(frozen=True)
class HighlightSourceAttachQualityInterrogationCompose:
    parent_asset_id: str
    session_id: str
    highlight_launch: HighlightDeepResearchLaunchCompose
    source_interrogation: SourceAttachQualityInterrogationCompose
    pack_ready: bool
    live_dispatched: bool
    merge_executed: bool
    remote_fetched: bool
    pdf_view_authorized: bool
    record_persisted: bool
    prompts_injected: bool
    store_mutated: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "parent_asset_id": self.parent_asset_id,
            "session_id": self.session_id,
            "highlight_launch": self.highlight_launch.to_dict(),
            "source_interrogation": self.source_interrogation.to_dict(),
            "pack_ready": self.pack_ready,
            "live_dispatched": False,
            "merge_executed": False,
            "remote_fetched": False,
            "pdf_view_authorized": False,
            "record_persisted": False,
            "prompts_injected": False,
            "store_mutated": False,
            "notes": list(self.notes),
            "authority": (
                "highlight_source_attach_quality_interrogation_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HighlightSourceAttachQualityInterrogationComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_highlight_source_attach_quality_interrogation(
    *,
    parent_asset_id: object,
    highlight: object,
    gated: object,
    would_exceed: object,
    operator_ack: object,
    session_id: object,
    requested_families: object,
    sources: object,
    quality_overall: object,
    questions: object,
    chase_mode: object,
    models: object,
    daily_cap_usd: object,
    spent_usd: object,
    prompt: object | None = None,
    preferred_view_mode: object | None = None,
    operator_override: object | None = None,
    selected_model_id: object | None = None,
    source_families: object | None = None,
    citations: object | None = None,
    derive_citations_from_sources: object | None = None,
    quality_floor: object | None = None,
    prior_records: object | None = None,
    user_prompt: object | None = None,
    projected_cost_usd_high: object | None = None,
    projected_cost_usd_low: object | None = None,
    bench_bests: object | None = None,
    focus_task: object | None = None,
    nd_shadow: object | None = None,
    require_both: object | None = None,
) -> HighlightSourceAttachQualityInterrogationCompose:
    """Highlight DR launch + source attach interrogation. Never dispatches."""
    if not isinstance(operator_ack, bool):
        raise HighlightSourceAttachQualityInterrogationComposeError(
            "operator_ack must be an explicit boolean"
        )
    parent = _require_nonempty(parent_asset_id, field="parent_asset_id")
    session = _require_nonempty(session_id, field="session_id")
    hl = _require_nonempty(highlight, field="highlight")

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise HighlightSourceAttachQualityInterrogationComposeError(
            "require_both must be boolean when set"
        )

    notes: list[str] = [
        "live_dispatched=false — highlight launch + interrogation pure intent",
        "merge_executed=false — parent asset not mutated",
        "remote_fetched=false — no live arxiv/substack scrape",
        "pdf_view_authorized=false — HTML-native only",
    ]

    selected = selected_model_id
    if selected is None or (isinstance(selected, str) and not selected.strip()):
        if not isinstance(models, list) or len(models) == 0:
            raise HighlightSourceAttachQualityInterrogationComposeError(
                "selected_model_id or models[0] required"
            )
        first = models[0]
        if not isinstance(first, dict):
            raise HighlightSourceAttachQualityInterrogationComposeError(
                "models[0] must be an object"
            )
        selected = _require_nonempty(
            first.get("model_id"), field="models[0].model_id"
        )
    else:
        selected = _require_nonempty(selected, field="selected_model_id")

    if user_prompt is not None and str(user_prompt).strip():
        uprompt = _require_nonempty(user_prompt, field="user_prompt")
    else:
        uprompt = hl

    launch_families = source_families
    if launch_families is None:
        launch_families = requested_families

    try:
        highlight_launch = compose_highlight_deep_research_launch(
            parent_asset_id=parent,
            highlight=hl,
            gated=gated,
            would_exceed=would_exceed,
            operator_ack=operator_ack,
            prompt=prompt if prompt is not None else uprompt,
            preferred_view_mode=preferred_view_mode,
            operator_override=operator_override,
            selected_model_id=selected,
            source_families=launch_families,
        )
    except HighlightDeepResearchLaunchComposeError as e:
        raise HighlightSourceAttachQualityInterrogationComposeError(str(e)) from e
    notes.extend(f"[highlight_launch] {n}" for n in highlight_launch.notes)

    try:
        source_interrogation = compose_source_attach_quality_interrogation(
            session_id=session,
            parent_asset_id=parent,
            requested_families=requested_families,
            sources=sources,
            quality_overall=quality_overall,
            would_exceed=would_exceed,
            questions=questions,
            chase_mode=chase_mode,
            user_prompt=uprompt,
            selected_model_id=selected,
            models=models,
            daily_cap_usd=daily_cap_usd,
            spent_usd=spent_usd,
            operator_ack=operator_ack,
            citations=citations,
            derive_citations_from_sources=derive_citations_from_sources,
            quality_floor=quality_floor,
            operator_override=operator_override,
            prior_records=prior_records,
            projected_cost_usd_high=projected_cost_usd_high,
            projected_cost_usd_low=projected_cost_usd_low,
            bench_bests=bench_bests,
            focus_task=(
                "deep_research" if focus_task is None else focus_task
            ),
            nd_shadow=nd_shadow,
            require_both=True,
        )
    except SourceAttachQualityInterrogationComposeError as e:
        raise HighlightSourceAttachQualityInterrogationComposeError(str(e)) from e
    notes.extend(
        f"[source_interrogation] {n}" for n in source_interrogation.notes
    )

    if require:
        pack_ready = (
            highlight_launch.launch_ready is True
            and source_interrogation.pack_ready is True
            and operator_ack is True
        )
    else:
        pack_ready = operator_ack is True and (
            highlight_launch.launch_ready is True
            or source_interrogation.pack_ready is True
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — highlight launch + source interrogation ready; "
            "still pure"
        )
    else:
        notes.append(
            "pack_ready=false — launch, source interrogation, or operator_ack "
            "gate open"
        )

    if (
        highlight_launch.live_dispatched is not False
        or highlight_launch.merge_executed is not False
        or source_interrogation.remote_fetched is not False
        or source_interrogation.live_dispatched is not False
        or source_interrogation.record_persisted is not False
        or source_interrogation.prompts_injected is not False
    ):
        raise HighlightSourceAttachQualityInterrogationComposeError(
            "invariant: honesty flags must remain false"
        )

    notes.extend(
        (
            "live_dispatched=false",
            "merge_executed=false",
            "remote_fetched=false",
            "pdf_view_authorized=false",
            "record_persisted=false",
            "prompts_injected=false",
            "store_mutated=false",
        )
    )

    return HighlightSourceAttachQualityInterrogationCompose(
        parent_asset_id=parent,
        session_id=session,
        highlight_launch=highlight_launch,
        source_interrogation=source_interrogation,
        pack_ready=pack_ready,
        live_dispatched=False,
        merge_executed=False,
        remote_fetched=False,
        pdf_view_authorized=False,
        record_persisted=False,
        prompts_injected=False,
        store_mutated=False,
        notes=tuple(notes),
        authority=(
            "highlight_source_attach_quality_interrogation_compose_advisory"
        ),
    )


def format_highlight_source_attach_quality_interrogation_summary(
    c: HighlightSourceAttachQualityInterrogationCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"launch_ready={c.highlight_launch.launch_ready} · "
        f"source_ready={c.source_interrogation.pack_ready} · "
        f"live_dispatched=false · merge_executed=false · remote_fetched=false"
    )


__all__ = [
    "HighlightSourceAttachQualityInterrogationCompose",
    "HighlightSourceAttachQualityInterrogationComposeError",
    "compose_highlight_source_attach_quality_interrogation",
    "format_highlight_source_attach_quality_interrogation_summary",
]
