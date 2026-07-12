"""Collective deep-research -> LLM-synthesized written analysis (full mode).

The full-synthesis sibling of the draft writer (#1833 ``collective_analysis_writer``).
Where the draft writer mechanically groups per-instance content with attribution,
THIS module asks an LLM (via an **injectable caller**) to integrate insights across
N completed research instances into one cohesive written analysis -- the operator's
"merge various sub-agent deep researches ... to create a written analysis" (ask #3).

**Pure except for ONE injected seam: the ``SynthesisCaller``.** The module itself
does no networking, no credentials, no dispatch. The caller is injected by the
authorized routes layer (which owns the budget gate + operator consent). This
mirrors the bench runner's injectable-ModelCaller discipline: the boundary is the
only place a real model is reached, and tests inject a deterministic fake.

**Authority split** (matches #884 intent + #1000 Midnight Oil): the intent layer
PROPOSES; this synthesizer EXECUTES synthesis only when ``operator_ack=True``.
Without ack, synthesis is **withheld** and the caller is NEVER invoked -- this
module is the single synthesis authority. Withholding is honest (render_html
shows the guard), never silent.

**Provenance is real, never fabricated:** the merged body's ``source_event_ids``
is the union of every source instance's own ``source_event_ids``; merged insight/
question nodes are content-addressed (dedup by text) and re-attributed to their
source instance via ``source_document_id``. Nothing is invented.

**Output:** a merged ``ResearchArtifactBody`` rendered HTML-native via the
canonical ``render_html`` (on main, fully escaped -- ask #6).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from substrate.research_artifact.render import render_html
from substrate.research_artifact.schema import (
    ArtifactInsight,
    ArtifactQuestion,
    ResearchArtifactBody,
)


class CollectiveSynthesisError(ValueError):
    """Fail-closed: input that cannot be honestly synthesized."""


@dataclass(frozen=True)
class SynthesisInstanceContribution:
    """One source instance's resolved contribution to the collective synthesis."""

    investigation_id: str
    problem_question: str
    insights: tuple[str, ...]
    open_questions: tuple[str, ...]
    synthesis_excerpt: str | None
    source_event_ids: tuple[str, ...]
    complete: bool


@dataclass(frozen=True)
class SynthesisBrief:
    """Structured, model-agnostic material handed to the ``SynthesisCaller``.

    Deliberately NOT a prompt string: each caller formats its own prompt from
    this structure, so the module stays model-agnostic (any model/caller can
    synthesize from the same brief).
    """

    parent_asset_id: str
    instances: tuple[SynthesisInstanceContribution, ...]
    findings: tuple[str, ...]
    brief_hash: str


@dataclass(frozen=True)
class SynthesisResult:
    """What the injected caller returns."""

    synthesis_text: str
    model_id: str


class SynthesisCaller(Protocol):
    """The single dispatch seam. Implementations reach a real model; tests fake it."""

    def __call__(self, brief: SynthesisBrief, *, model_id: str) -> SynthesisResult: ...


@dataclass(frozen=True)
class CollectiveSynthesis:
    """The full-mode output: merged HTML analysis + honest provenance + accounting."""

    parent_asset_id: str
    analysis_id: str
    source_instance_ids: tuple[str, ...]
    combined_html: str
    synthesis_excerpt: str | None
    synthesis_withheld: bool
    model_id: str
    operator_ack: bool
    findings_hash: str
    instance_contributions: tuple[SynthesisInstanceContribution, ...]
    content_hash: str  # the merged body's content_hash (idempotency)


def _contribution_from_body(
    body: ResearchArtifactBody, *, complete: bool
) -> SynthesisInstanceContribution:
    excerpt = None if body.synthesis_withheld else body.synthesis_excerpt
    return SynthesisInstanceContribution(
        investigation_id=body.investigation_id,
        problem_question=body.problem_question,
        insights=tuple(ins.text for ins in body.insights),
        open_questions=tuple(q.text for q in body.open_questions),
        synthesis_excerpt=excerpt,
        source_event_ids=tuple(body.source_event_ids),
        complete=complete,
    )


def _canonical_hash(
    parent_asset_id: str,
    contributions: Sequence[SynthesisInstanceContribution],
    findings: Sequence[str],
) -> str:
    payload = {
        "parent_asset_id": parent_asset_id,
        "instances": [
            {
                "investigation_id": c.investigation_id,
                "insights": list(c.insights),
                "open_questions": list(c.open_questions),
                "synthesis_excerpt": c.synthesis_excerpt,
                "source_event_ids": list(c.source_event_ids),
                "complete": c.complete,
            }
            for c in contributions
        ],
        "findings": list(findings),
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _content_addressed(*, kind: str, text: str) -> str:
    digest = hashlib.sha256(text.strip().lower().encode("utf-8")).hexdigest()[:12]
    return f"collective-{kind}-{digest}"


def build_synthesis_brief(
    *,
    parent_asset_id: str,
    instances: Sequence[ResearchArtifactBody],
    findings: Sequence[str] | None = None,
    instance_complete_flags: Mapping[str, bool] | None = None,
) -> SynthesisBrief:
    """Resolve N completed instances into a deterministic, model-agnostic brief.

    Full-mode contract: **every instance must be complete** (the draft writer
    tolerates partial; full synthesis requires complete content to exist). An
    incomplete instance is a write-boundary contract violation -> fail-closed.
    """
    if not parent_asset_id.strip():
        raise CollectiveSynthesisError("parent_asset_id must be non-empty")
    if not instances:
        raise CollectiveSynthesisError("at least one source instance is required")

    flags = instance_complete_flags or {}
    contributions = [
        _contribution_from_body(body, complete=flags.get(body.investigation_id, True))
        for body in instances
    ]
    incomplete = [c.investigation_id for c in contributions if not c.complete]
    if incomplete:
        raise CollectiveSynthesisError(
            "full synthesis requires all instances complete; incomplete: "
            + ", ".join(incomplete)
        )

    caller_findings = tuple(findings or [])
    brief_hash = _canonical_hash(parent_asset_id, contributions, caller_findings)
    return SynthesisBrief(
        parent_asset_id=parent_asset_id,
        instances=tuple(contributions),
        findings=caller_findings,
        brief_hash=brief_hash,
    )


def _merge_body(
    brief: SynthesisBrief,
    *,
    synthesis_excerpt: str | None,
    synthesis_withheld: bool,
) -> ResearchArtifactBody:
    """Build the merged ResearchArtifactBody (provenance = union of real events).

    Insight/question nodes are content-addressed (dedup by text) and
    re-attributed to their source instance via ``source_document_id`` -- so the
    merged graph never loses where each finding came from.
    """
    merged_insights: list[ArtifactInsight] = []
    seen_insight_nodes: set[str] = set()
    merged_questions: list[ArtifactQuestion] = []
    seen_question_nodes: set[str] = set()
    source_event_ids: list[str] = []

    for contrib in brief.instances:
        source_event_ids.extend(contrib.source_event_ids)
        for text in contrib.insights:
            if not text.strip():
                continue
            node_id = _content_addressed(kind="insight", text=text)
            if node_id in seen_insight_nodes:
                continue
            seen_insight_nodes.add(node_id)
            merged_insights.append(
                ArtifactInsight(
                    node_id=node_id,
                    text=text,
                    source_document_id=contrib.investigation_id,
                )
            )
        for text in contrib.open_questions:
            if not text.strip():
                continue
            node_id = _content_addressed(kind="question", text=text)
            if node_id in seen_question_nodes:
                continue
            seen_question_nodes.add(node_id)
            merged_questions.append(
                ArtifactQuestion(
                    node_id=node_id,
                    text=text,
                )
            )

    # Dedup source_event_ids preserving first-seen order (stable provenance).
    seen_events: set[str] = set()
    deduped_events: list[str] = []
    for eid in source_event_ids:
        if eid and eid not in seen_events:
            seen_events.add(eid)
            deduped_events.append(eid)

    return ResearchArtifactBody(
        investigation_id=f"collective-synthesis-{brief.brief_hash[:16]}",
        problem_question=(
            f"Collective analysis \u00b7 {len(brief.instances)} instances \u00b7 "
            f"parent {brief.parent_asset_id}"
        ),
        insights=merged_insights,
        open_questions=merged_questions,
        synthesis_excerpt=synthesis_excerpt,
        synthesis_withheld=synthesis_withheld,
        source_event_ids=deduped_events,
        agent_notes=list(brief.findings),
    )


def synthesize_collective_analysis(
    *,
    brief: SynthesisBrief,
    caller: SynthesisCaller,
    model_id: str,
    operator_ack: bool = False,
) -> CollectiveSynthesis:
    """Execute the full LLM synthesis (authority-gated on ``operator_ack``).

    Without ack: synthesis is **withheld**, the caller is NEVER invoked, and the
    rendered HTML shows the honest guard. With ack: the injected caller produces
    the synthesis; an empty/whitespace result is withheld honestly (never
    invented prose).
    """
    if not model_id.strip():
        raise CollectiveSynthesisError("model_id must be non-empty")

    synthesis_text: str | None = None
    withheld = True
    used_model = model_id

    if operator_ack:
        result = caller(brief, model_id=model_id)
        used_model = result.model_id or model_id
        if result.synthesis_text.strip():
            synthesis_text = result.synthesis_text
            withheld = False

    body = _merge_body(
        brief,
        synthesis_excerpt=synthesis_text,
        synthesis_withheld=withheld,
    )

    return CollectiveSynthesis(
        parent_asset_id=brief.parent_asset_id,
        analysis_id=body.investigation_id,
        source_instance_ids=tuple(c.investigation_id for c in brief.instances),
        combined_html=render_html(body),
        synthesis_excerpt=synthesis_text,
        synthesis_withheld=withheld,
        model_id=used_model,
        operator_ack=operator_ack,
        findings_hash=brief.brief_hash,
        instance_contributions=brief.instances,
        content_hash=body.content_hash(),
    )


__all__ = [
    "CollectiveSynthesis",
    "CollectiveSynthesisError",
    "SynthesisBrief",
    "SynthesisCaller",
    "SynthesisInstanceContribution",
    "SynthesisResult",
    "build_synthesis_brief",
    "synthesize_collective_analysis",
]
