"""Source attach quality + interrogation → twin chase feed (pure).

remote_fetched / pdf_view_authorized / live_* / twin_written /
record_persisted / prompts_injected / store_mutated always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.source_attach_quality_interrogation_compose import (
    SourceAttachQualityInterrogationCompose,
    SourceAttachQualityInterrogationComposeError,
    compose_source_attach_quality_interrogation,
)
from substrate.twin_chase_analysis_feed_compose import (
    TwinChaseAnalysisFeedCompose,
    TwinChaseAnalysisFeedComposeError,
    compose_twin_chase_analysis_feed,
)


class SourceAttachQualityInterrogationTwinComposeError(ValueError):
    """Fail-closed validation for source attach interrogation twin pack."""


@dataclass(frozen=True)
class SourceAttachQualityInterrogationTwinCompose:
    session_id: str
    parent_asset_id: str
    source_interrogation: SourceAttachQualityInterrogationCompose
    twin_feed: TwinChaseAnalysisFeedCompose
    pack_ready: bool
    remote_fetched: bool
    pdf_view_authorized: bool
    live_dispatch_authorized: bool
    live_dispatched: bool
    twin_written: bool
    record_persisted: bool
    prompts_injected: bool
    store_mutated: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "parent_asset_id": self.parent_asset_id,
            "source_interrogation": self.source_interrogation.to_dict(),
            "twin_feed": self.twin_feed.to_dict(),
            "pack_ready": self.pack_ready,
            "remote_fetched": False,
            "pdf_view_authorized": False,
            "live_dispatch_authorized": False,
            "live_dispatched": False,
            "twin_written": False,
            "record_persisted": False,
            "prompts_injected": False,
            "store_mutated": False,
            "notes": list(self.notes),
            "authority": (
                "source_attach_quality_interrogation_twin_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SourceAttachQualityInterrogationTwinComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def _derive_findings(
    sources: object,
    questions: object,
) -> list[dict[str, Any]]:
    """Derive twin findings from source titles + question bodies."""
    if not isinstance(sources, list):
        raise SourceAttachQualityInterrogationTwinComposeError(
            "sources must be an array"
        )
    if not isinstance(questions, list):
        raise SourceAttachQualityInterrogationTwinComposeError(
            "questions must be an array"
        )
    findings: list[dict[str, Any]] = []
    for s in sources:
        if not isinstance(s, dict):
            raise SourceAttachQualityInterrogationTwinComposeError(
                "sources items must be objects"
            )
        sid = str(s.get("source_id", "")).strip()
        title = str(s.get("title", "")).strip()
        if not sid or not title:
            raise SourceAttachQualityInterrogationTwinComposeError(
                "sources items need source_id and title"
            )
        findings.append(
            {
                "source_id": f"src-{sid}",
                "body": title,
                "kind": "data",
            }
        )
    for q in questions:
        if not isinstance(q, dict):
            raise SourceAttachQualityInterrogationTwinComposeError(
                "questions items must be objects"
            )
        qid = str(q.get("question_id", "")).strip()
        body = str(q.get("body", "")).strip()
        if not qid or not body:
            raise SourceAttachQualityInterrogationTwinComposeError(
                "questions items need question_id and body"
            )
        findings.append(
            {
                "source_id": f"q-{qid}",
                "body": body,
                "kind": "question",
            }
        )
    return findings


def compose_source_attach_quality_interrogation_twin(
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
    existing_twin_asset_id: object | None = None,
    analysis_excerpt: object | None = None,
    mark_for_prompt_context: object | None = None,
    twin_findings: object | None = None,
) -> SourceAttachQualityInterrogationTwinCompose:
    """Source attach/quality/interrogation + twin feed. Never scrapes/writes."""
    if not isinstance(operator_ack, bool):
        raise SourceAttachQualityInterrogationTwinComposeError(
            "operator_ack must be an explicit boolean"
        )
    session = _require_nonempty(session_id, field="session_id")
    parent = _require_nonempty(parent_asset_id, field="parent_asset_id")

    require = True if require_both is None else require_both
    if not isinstance(require, bool):
        raise SourceAttachQualityInterrogationTwinComposeError(
            "require_both must be boolean when set"
        )

    mark_prompt = (
        True if mark_for_prompt_context is None else mark_for_prompt_context
    )
    if not isinstance(mark_prompt, bool):
        raise SourceAttachQualityInterrogationTwinComposeError(
            "mark_for_prompt_context must be boolean when set"
        )

    notes: list[str] = [
        "remote_fetched=false — no live arxiv/substack scrape",
        "pdf_view_authorized=false — HTML-native sources only",
        "twin_written=false · record_persisted=false · prompts_injected=false",
        "live_dispatch_authorized=false · live_dispatched=false · store_mutated=false",
    ]

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
            user_prompt=user_prompt,
            selected_model_id=selected_model_id,
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
            focus_task=focus_task,
            nd_shadow=nd_shadow,
            require_both=require,
        )
    except SourceAttachQualityInterrogationComposeError as e:
        raise SourceAttachQualityInterrogationTwinComposeError(str(e)) from e
    notes.extend(
        f"[source_interrogation] {n}" for n in source_interrogation.notes
    )

    if twin_findings is not None:
        if not isinstance(twin_findings, list):
            raise SourceAttachQualityInterrogationTwinComposeError(
                "twin_findings must be an array when set"
            )
        findings = twin_findings
        notes.append(f"twin_findings={len(findings)} caller-supplied")
    else:
        findings = _derive_findings(sources, questions)
        notes.append(
            f"twin_findings={len(findings)} derived from sources+questions"
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
        raise SourceAttachQualityInterrogationTwinComposeError(str(e)) from e
    notes.extend(f"[twin_feed] {n}" for n in twin_feed.notes)

    if require:
        pack_ready = (
            source_interrogation.pack_ready is True
            and twin_feed.feed_ready is True
            and operator_ack is True
        )
    else:
        pack_ready = operator_ack is True and (
            source_interrogation.pack_ready is True
            or twin_feed.feed_ready is True
        )

    if pack_ready:
        notes.append(
            "pack_ready=true — source attach/interrogation + twin feed ready; "
            "still pure"
        )
    else:
        notes.append(
            "pack_ready=false — source interrogation, twin feed, or "
            "operator_ack gate open"
        )

    if (
        source_interrogation.remote_fetched is not False
        or source_interrogation.pdf_view_authorized is not False
        or source_interrogation.live_dispatched is not False
        or source_interrogation.record_persisted is not False
        or source_interrogation.prompts_injected is not False
        or twin_feed.twin_written is not False
        or twin_feed.record_persisted is not False
        or twin_feed.prompts_injected is not False
    ):
        raise SourceAttachQualityInterrogationTwinComposeError(
            "invariant: honesty flags must remain false"
        )

    notes.extend(
        (
            "remote_fetched=false",
            "pdf_view_authorized=false",
            "live_dispatch_authorized=false",
            "live_dispatched=false",
            "twin_written=false",
            "record_persisted=false",
            "prompts_injected=false",
            "store_mutated=false",
        )
    )

    return SourceAttachQualityInterrogationTwinCompose(
        session_id=session,
        parent_asset_id=parent,
        source_interrogation=source_interrogation,
        twin_feed=twin_feed,
        pack_ready=pack_ready,
        remote_fetched=False,
        pdf_view_authorized=False,
        live_dispatch_authorized=False,
        live_dispatched=False,
        twin_written=False,
        record_persisted=False,
        prompts_injected=False,
        store_mutated=False,
        notes=tuple(notes),
        authority="source_attach_quality_interrogation_twin_compose_advisory",
    )


def format_source_attach_quality_interrogation_twin_summary(
    c: SourceAttachQualityInterrogationTwinCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · "
        f"source_ready={c.source_interrogation.pack_ready} · "
        f"twin_feed_ready={c.twin_feed.feed_ready} · "
        f"findings={c.twin_feed.finding_count} · "
        f"remote_fetched=false · twin_written=false · live_dispatched=false"
    )


__all__ = [
    "SourceAttachQualityInterrogationTwinCompose",
    "SourceAttachQualityInterrogationTwinComposeError",
    "compose_source_attach_quality_interrogation_twin",
    "format_source_attach_quality_interrogation_twin_summary",
]
