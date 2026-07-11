"""Highlight source attach quality interrogation → twin feed (pure).

live_dispatched / merge_executed / twin_written / remote_fetched always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.highlight_source_attach_quality_interrogation_compose import (
    HighlightSourceAttachQualityInterrogationCompose,
    HighlightSourceAttachQualityInterrogationComposeError,
    compose_highlight_source_attach_quality_interrogation,
)
from substrate.twin_chase_analysis_feed_compose import (
    TwinChaseAnalysisFeedCompose,
    TwinChaseAnalysisFeedComposeError,
    compose_twin_chase_analysis_feed,
)


class HighlightSourceAttachQualityInterrogationTwinComposeError(ValueError):
    """Fail-closed validation for highlight source twin pack."""


@dataclass(frozen=True)
class HighlightSourceAttachQualityInterrogationTwinCompose:
    parent_asset_id: str
    session_id: str
    highlight_pack: HighlightSourceAttachQualityInterrogationCompose
    twin_feed: TwinChaseAnalysisFeedCompose
    pack_ready: bool
    live_dispatched: bool
    merge_executed: bool
    remote_fetched: bool
    twin_written: bool
    prompts_injected: bool
    store_mutated: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "parent_asset_id": self.parent_asset_id,
            "session_id": self.session_id,
            "highlight_pack": self.highlight_pack.to_dict(),
            "twin_feed": self.twin_feed.to_dict(),
            "pack_ready": self.pack_ready,
            "live_dispatched": False,
            "merge_executed": False,
            "remote_fetched": False,
            "twin_written": False,
            "prompts_injected": False,
            "store_mutated": False,
            "notes": list(self.notes),
            "authority": (
                "highlight_source_attach_quality_interrogation_twin_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HighlightSourceAttachQualityInterrogationTwinComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def _derive_findings(
    highlight: str,
    sources: object,
    questions: object,
) -> list[dict[str, Any]]:
    if not isinstance(sources, list):
        raise HighlightSourceAttachQualityInterrogationTwinComposeError(
            "sources must be an array"
        )
    if not isinstance(questions, list):
        raise HighlightSourceAttachQualityInterrogationTwinComposeError(
            "questions must be an array"
        )
    findings: list[dict[str, Any]] = [
        {"source_id": "hl-highlight", "body": highlight, "kind": "data"}
    ]
    for s in sources:
        if not isinstance(s, dict):
            raise HighlightSourceAttachQualityInterrogationTwinComposeError(
                "sources items must be objects"
            )
        sid = str(s.get("source_id", "")).strip()
        title = str(s.get("title", "")).strip()
        if not sid or not title:
            raise HighlightSourceAttachQualityInterrogationTwinComposeError(
                "sources items need source_id and title"
            )
        findings.append(
            {"source_id": f"src-{sid}", "body": title, "kind": "data"}
        )
    for q in questions:
        if not isinstance(q, dict):
            raise HighlightSourceAttachQualityInterrogationTwinComposeError(
                "questions items must be objects"
            )
        qid = str(q.get("question_id", "")).strip()
        body = str(q.get("body", "")).strip()
        if not qid or not body:
            raise HighlightSourceAttachQualityInterrogationTwinComposeError(
                "questions items need question_id and body"
            )
        findings.append(
            {"source_id": f"q-{qid}", "body": body, "kind": "question"}
        )
    return findings


def compose_highlight_source_attach_quality_interrogation_twin(
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
    existing_twin_asset_id: object | None = None,
    analysis_excerpt: object | None = None,
    mark_for_prompt_context: object | None = None,
    twin_findings: object | None = None,
    require_both_with_twin: object | None = None,
) -> HighlightSourceAttachQualityInterrogationTwinCompose:
    """Highlight pack + twin feed. Never dispatches/writes twin."""
    if not isinstance(operator_ack, bool):
        raise HighlightSourceAttachQualityInterrogationTwinComposeError(
            "operator_ack must be an explicit boolean"
        )
    parent = _require_nonempty(parent_asset_id, field="parent_asset_id")
    session = _require_nonempty(session_id, field="session_id")
    hl = _require_nonempty(highlight, field="highlight")

    require_twin = (
        True if require_both_with_twin is None else require_both_with_twin
    )
    if not isinstance(require_twin, bool):
        raise HighlightSourceAttachQualityInterrogationTwinComposeError(
            "require_both_with_twin must be boolean when set"
        )

    mark_prompt = (
        True if mark_for_prompt_context is None else mark_for_prompt_context
    )
    if not isinstance(mark_prompt, bool):
        raise HighlightSourceAttachQualityInterrogationTwinComposeError(
            "mark_for_prompt_context must be boolean when set"
        )

    notes: list[str] = [
        "live_dispatched=false · merge_executed=false",
        "remote_fetched=false · twin_written=false · prompts_injected=false",
    ]

    try:
        highlight_pack = compose_highlight_source_attach_quality_interrogation(
            parent_asset_id=parent,
            highlight=hl,
            gated=gated,
            would_exceed=would_exceed,
            operator_ack=operator_ack,
            session_id=session,
            requested_families=requested_families,
            sources=sources,
            quality_overall=quality_overall,
            questions=questions,
            chase_mode=chase_mode,
            models=models,
            daily_cap_usd=daily_cap_usd,
            spent_usd=spent_usd,
            prompt=prompt,
            preferred_view_mode=preferred_view_mode,
            operator_override=operator_override,
            selected_model_id=selected_model_id,
            source_families=source_families,
            citations=citations,
            derive_citations_from_sources=derive_citations_from_sources,
            quality_floor=quality_floor,
            prior_records=prior_records,
            user_prompt=user_prompt,
            projected_cost_usd_high=projected_cost_usd_high,
            projected_cost_usd_low=projected_cost_usd_low,
            bench_bests=bench_bests,
            focus_task=focus_task,
            nd_shadow=nd_shadow,
            require_both=require_both,
        )
    except HighlightSourceAttachQualityInterrogationComposeError as e:
        raise HighlightSourceAttachQualityInterrogationTwinComposeError(
            str(e)
        ) from e
    notes.extend(f"[highlight_pack] {n}" for n in highlight_pack.notes)

    if twin_findings is not None:
        if not isinstance(twin_findings, list):
            raise HighlightSourceAttachQualityInterrogationTwinComposeError(
                "twin_findings must be an array when set"
            )
        findings = twin_findings
        notes.append(f"twin_findings={len(findings)} caller-supplied")
    else:
        findings = _derive_findings(hl, sources, questions)
        notes.append(
            f"twin_findings={len(findings)} derived from "
            "highlight+sources+questions"
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
        raise HighlightSourceAttachQualityInterrogationTwinComposeError(
            str(e)
        ) from e
    notes.extend(f"[twin_feed] {n}" for n in twin_feed.notes)

    if require_twin:
        pack_ready = (
            highlight_pack.pack_ready is True
            and twin_feed.feed_ready is True
            and operator_ack is True
        )
    else:
        pack_ready = operator_ack is True and (
            highlight_pack.pack_ready is True or twin_feed.feed_ready is True
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — highlight pack + twin feed ready; still pure"
        )
    else:
        notes.append(
            "pack_ready=false — highlight pack, twin feed, or operator_ack "
            "gate open"
        )

    if (
        highlight_pack.live_dispatched is not False
        or highlight_pack.merge_executed is not False
        or twin_feed.twin_written is not False
        or twin_feed.prompts_injected is not False
    ):
        raise HighlightSourceAttachQualityInterrogationTwinComposeError(
            "invariant: honesty flags must remain false"
        )

    notes.extend(
        (
            "live_dispatched=false",
            "merge_executed=false",
            "remote_fetched=false",
            "twin_written=false",
            "prompts_injected=false",
            "store_mutated=false",
        )
    )

    return HighlightSourceAttachQualityInterrogationTwinCompose(
        parent_asset_id=parent,
        session_id=session,
        highlight_pack=highlight_pack,
        twin_feed=twin_feed,
        pack_ready=pack_ready,
        live_dispatched=False,
        merge_executed=False,
        remote_fetched=False,
        twin_written=False,
        prompts_injected=False,
        store_mutated=False,
        notes=tuple(notes),
        authority=(
            "highlight_source_attach_quality_interrogation_twin_compose_advisory"
        ),
    )


def format_highlight_source_attach_quality_interrogation_twin_summary(
    c: HighlightSourceAttachQualityInterrogationTwinCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"highlight_ready={c.highlight_pack.pack_ready} · "
        f"twin_feed_ready={c.twin_feed.feed_ready} · "
        f"findings={c.twin_feed.finding_count} · "
        f"live_dispatched=false · twin_written=false · merge_executed=false"
    )


__all__ = [
    "HighlightSourceAttachQualityInterrogationTwinCompose",
    "HighlightSourceAttachQualityInterrogationTwinComposeError",
    "compose_highlight_source_attach_quality_interrogation_twin",
    "format_highlight_source_attach_quality_interrogation_twin_summary",
]
