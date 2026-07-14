"""Curriculum and storyboard planner for Antiek multimedia assets.

This is the plan-before-render layer from multimedia SPR-02. It takes a topic,
duration, mode, route tier, user constraints, and graph evidence, then returns:

* coverage suggestions ("what could I learn?"),
* a duration-budgeted chapter plan,
* cited script lines using the SPR-01 ``ScriptLine`` contract,
* storyboard scenes with information purpose, and
* explicit omissions/cuts before any Krea/TTS/video spend occurs.

The planner is deterministic and credential-free. It is intentionally useful as
a dry-run approval artifact before later sprints call paid providers.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from substrate.contracts.multimedia import (
    ClaimToChunk,
    MediaSegment,
    MultimediaManifest,
    RoutePolicy,
    ScriptLine,
    SourceCitation,
)

PlanMode = Literal["video", "audio", "hybrid"]
Depth = Literal["overview", "intermediate", "deep"]

MIN_MULTIMEDIA_MINUTES = 15
MAX_MULTIMEDIA_MINUTES = 45
_DEFAULT_ARCS = (
    ("history", "Historical arc", "how the topic changed over time"),
    ("mechanism", "Mechanism arc", "the technical or causal mechanism that makes it work"),
    ("comparison", "Comparison arc", "what differs across designs, eras, or schools"),
    ("consequences", "Consequences arc", "why the topic mattered after adoption"),
)
_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9-]{2,}")
_STOPWORDS = frozenset({
    "about",
    "across",
    "after",
    "also",
    "because",
    "before",
    "between",
    "could",
    "from",
    "have",
    "into",
    "learn",
    "make",
    "more",
    "over",
    "that",
    "their",
    "there",
    "these",
    "this",
    "through",
    "what",
    "when",
    "where",
    "which",
    "while",
    "with",
    "would",
})


def validate_selected_arc_ids(values: tuple[str, ...]) -> tuple[str, ...]:
    """Validate ordered operator coverage choices at every input boundary."""

    if any(not arc.strip() for arc in values):
        raise ValueError("selected_arc_ids cannot contain empty values")
    if len(set(values)) != len(values):
        raise ValueError("selected_arc_ids cannot contain duplicates")
    supported = {arc_id for arc_id, _, _ in _DEFAULT_ARCS}
    unknown = sorted(set(values) - supported)
    if unknown:
        raise ValueError(f"unsupported selected_arc_ids: {', '.join(unknown)}")
    return values


class _PlannerBase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class EvidenceChunk(_PlannerBase):
    """One graph chunk available to ground the plan."""

    chunk_id: str
    document_id: str
    text: str = Field(min_length=1)
    title: str | None = None
    section_path: str | None = None

    def citation(self) -> SourceCitation:
        return SourceCitation(
            chunk_id=self.chunk_id,
            document_id=self.document_id,
            locator=self.section_path,
            quote_sha256=hashlib.sha256(self.text.encode("utf-8")).hexdigest(),
        )


class MultimediaPlanRequest(_PlannerBase):
    """User and routing inputs for a multimedia dry-run plan."""

    topic: str = Field(min_length=1)
    target_minutes: int = Field(ge=MIN_MULTIMEDIA_MINUTES, le=MAX_MULTIMEDIA_MINUTES)
    mode: PlanMode = "hybrid"
    depth: Depth = "intermediate"
    sources: tuple[str, ...] = Field(default_factory=tuple)
    must_cover: tuple[str, ...] = Field(default_factory=tuple)
    avoid: tuple[str, ...] = Field(default_factory=tuple)
    audience: str = "curious generalist"
    route_policy: RoutePolicy = "balanced"
    disclosure_preferences: tuple[str, ...] = Field(default_factory=tuple)
    selected_arc_ids: tuple[str, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def selected_arcs_are_non_empty(self) -> MultimediaPlanRequest:
        validate_selected_arc_ids(self.selected_arc_ids)
        return self


class CoverageSuggestion(_PlannerBase):
    """A learnable coverage arc the user can accept, combine, or reject."""

    arc_id: str
    title: str
    teaches: str
    evidence: tuple[SourceCitation, ...] = Field(default_factory=tuple)
    tradeoff: str


class ChapterPlan(_PlannerBase):
    chapter_id: str
    title: str
    minutes: float = Field(ge=0)
    purpose: str
    arc_id: str
    source_chunk_ids: tuple[str, ...] = Field(default_factory=tuple)
    cuts: tuple[str, ...] = Field(default_factory=tuple)


class StoryboardScene(_PlannerBase):
    scene_id: str
    chapter_id: str
    visual_intent: str
    information_purpose: str
    narration_line_ids: tuple[str, ...] = Field(default_factory=tuple)
    source_chunk_ids: tuple[str, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def purpose_is_substantive(self) -> StoryboardScene:
        if self.information_purpose.strip().lower() in {"decorative", "filler", "atmosphere"}:
            raise ValueError("storyboard scenes require an information purpose")
        return self


class MultimediaPlan(_PlannerBase):
    request: MultimediaPlanRequest
    suggestions: tuple[CoverageSuggestion, ...]
    chosen_arc_ids: tuple[str, ...]
    chapters: tuple[ChapterPlan, ...]
    script_lines: tuple[ScriptLine, ...]
    scenes: tuple[StoryboardScene, ...]
    omissions: tuple[str, ...] = Field(default_factory=tuple)
    unsourced_line_ids: tuple[str, ...] = Field(default_factory=tuple)
    duration_tolerance_minutes: float = 0.25

    @property
    def total_minutes(self) -> float:
        return round(sum(chapter.minutes for chapter in self.chapters), 2)

    @model_validator(mode="after")
    def duration_and_grounding_are_visible(self) -> MultimediaPlan:
        delta = abs(self.total_minutes - self.request.target_minutes)
        if delta > self.duration_tolerance_minutes:
            raise ValueError(
                f"chapter minutes sum to {self.total_minutes}, expected "
                f"{self.request.target_minutes} +/- {self.duration_tolerance_minutes}"
            )
        actual_unsourced = tuple(
            line.line_id
            for line in self.script_lines
            if line.kind == "factual" and not line.citations
        )
        if actual_unsourced != self.unsourced_line_ids:
            raise ValueError("unsourced_line_ids must list every unsourced factual line")
        return self

    def to_manifest(self, *, asset_id: str, revision_id: str) -> MultimediaManifest:
        """Compile the dry-run plan into the SPR-01 manifest shape."""

        line_ids_by_chapter: dict[str, list[str]] = {}
        for line in self.script_lines:
            chapter_id = line.line_id.split("-line-", 1)[0]
            line_ids_by_chapter.setdefault(chapter_id, []).append(line.line_id)

        segments = tuple(
            MediaSegment(
                segment_id=f"seg-{chapter.chapter_id}",
                sequence=index,
                title=chapter.title,
                media_kind="chapter",
                script_line_ids=tuple(line_ids_by_chapter.get(chapter.chapter_id, ())),
                source_chunk_ids=chapter.source_chunk_ids,
                duration_seconds=round(chapter.minutes * 60, 2),
            )
            for index, chapter in enumerate(self.chapters)
        )
        claim_rows: list[ClaimToChunk] = []
        for line in self.script_lines:
            chunk_ids = tuple(c.chunk_id for c in line.citations)
            if chunk_ids:
                claim_rows.append(
                    ClaimToChunk(
                        claim_id=f"claim-{line.line_id}",
                        script_line_id=line.line_id,
                        chunk_ids=chunk_ids,
                    )
                )
        return MultimediaManifest(
            asset_id=asset_id,
            revision_id=revision_id,
            route_policy=self.request.route_policy,
            script_lines=self.script_lines,
            segments=segments,
            claim_to_chunk=tuple(claim_rows),
        )


def build_multimedia_plan(
    request: MultimediaPlanRequest,
    evidence: tuple[EvidenceChunk, ...] = (),
) -> MultimediaPlan:
    """Build a deterministic, source-aware multimedia plan.

    No provider call is made. Sparse evidence produces narrower suggestions,
    explicit omissions, and unsourced markers so render gates can block or ask
    for research before paid generation.
    """

    suggestions = _coverage_suggestions(request, evidence)
    chosen = _choose_arcs(request, suggestions)
    chapters, omissions = _chapters(request, evidence, suggestions, chosen)
    script_lines = _script_lines(request, evidence, chapters)
    scenes = _storyboard_scenes(request, chapters, script_lines)
    unsourced = tuple(
        line.line_id
        for line in script_lines
        if line.kind == "factual" and not line.citations
    )
    return MultimediaPlan(
        request=request,
        suggestions=suggestions,
        chosen_arc_ids=chosen,
        chapters=chapters,
        script_lines=script_lines,
        scenes=scenes,
        omissions=omissions,
        unsourced_line_ids=unsourced,
    )


def _coverage_suggestions(
    request: MultimediaPlanRequest,
    evidence: tuple[EvidenceChunk, ...],
) -> tuple[CoverageSuggestion, ...]:
    top_terms = _top_terms(request.topic, evidence)
    evidence_by_arc = _assign_evidence_to_arcs(evidence)
    suggestions: list[CoverageSuggestion] = []
    for arc_id, title, teaches in _DEFAULT_ARCS:
        terms = ", ".join(top_terms[:3]) if top_terms else request.topic
        suggestions.append(
            CoverageSuggestion(
                arc_id=arc_id,
                title=f"{title}: {request.topic}",
                teaches=f"Learn {teaches}, using {terms} as the through-line.",
                evidence=tuple(chunk.citation() for chunk in evidence_by_arc.get(arc_id, ())[:3]),
                tradeoff=_tradeoff_for(arc_id),
            )
        )
    return tuple(suggestions)


def _choose_arcs(
    request: MultimediaPlanRequest,
    suggestions: tuple[CoverageSuggestion, ...],
) -> tuple[str, ...]:
    available = {s.arc_id for s in suggestions}
    selected = tuple(arc for arc in request.selected_arc_ids if arc in available)
    if selected:
        return selected
    if request.depth == "overview":
        return ("history", "mechanism")
    if request.depth == "deep":
        return ("history", "mechanism", "comparison", "consequences")
    return ("history", "mechanism", "consequences")


def _chapters(
    request: MultimediaPlanRequest,
    evidence: tuple[EvidenceChunk, ...],
    suggestions: tuple[CoverageSuggestion, ...],
    chosen_arc_ids: tuple[str, ...],
) -> tuple[tuple[ChapterPlan, ...], tuple[str, ...]]:
    omissions: list[str] = []
    suggestion_by_id = {s.arc_id: s for s in suggestions}
    middle_minutes = round(request.target_minutes * 0.82, 2)
    intro_minutes = round(request.target_minutes * 0.10, 2)
    recap_minutes = round(request.target_minutes - middle_minutes - intro_minutes, 2)
    per_arc = round(middle_minutes / max(1, len(chosen_arc_ids)), 2)
    chapters: list[ChapterPlan] = [
        ChapterPlan(
            chapter_id="intro",
            title=f"Why {request.topic} is worth learning",
            minutes=intro_minutes,
            purpose="Frame the learning objective and disclose plan scope.",
            arc_id="intro",
            source_chunk_ids=tuple(chunk.chunk_id for chunk in evidence[:2]),
        )
    ]

    evidence_by_arc = _assign_evidence_to_arcs(evidence)
    must_cover_remaining = list(request.must_cover)
    for arc_id in chosen_arc_ids:
        suggestion = suggestion_by_id[arc_id]
        chunks = tuple(chunk.chunk_id for chunk in evidence_by_arc.get(arc_id, ())[:4])
        cuts: list[str] = []
        if request.target_minutes <= 18 and len(chosen_arc_ids) > 2:
            cuts.append("Compress examples to keep the requested runtime.")
        if not chunks:
            cuts.append("Needs more source evidence before rendering.")
            omissions.append(f"{suggestion.title}: weak source coverage")
        if must_cover_remaining:
            must = must_cover_remaining.pop(0)
            purpose = f"Teach {suggestion.teaches}; include must-cover angle: {must}."
        else:
            purpose = f"Teach {suggestion.teaches}."
        chapters.append(
            ChapterPlan(
                chapter_id=f"ch-{arc_id}",
                title=suggestion.title,
                minutes=per_arc,
                purpose=purpose,
                arc_id=arc_id,
                source_chunk_ids=chunks,
                cuts=tuple(cuts),
            )
        )
    for must in must_cover_remaining:
        omissions.append(f"Must-cover item omitted for runtime: {must}")
    for avoided in request.avoid:
        omissions.append(f"User excluded: {avoided}")

    allocated = round(sum(chapter.minutes for chapter in chapters) + recap_minutes, 2)
    final_recap = round(request.target_minutes - (allocated - recap_minutes), 2)
    chapters.append(
        ChapterPlan(
            chapter_id="recap",
            title="Recap and next questions",
            minutes=final_recap,
            purpose="Summarize what was learned and name follow-up questions.",
            arc_id="recap",
            source_chunk_ids=tuple(chunk.chunk_id for chunk in evidence[-2:]),
        )
    )
    return tuple(chapters), tuple(omissions)


def _script_lines(
    request: MultimediaPlanRequest,
    evidence: tuple[EvidenceChunk, ...],
    chapters: tuple[ChapterPlan, ...],
) -> tuple[ScriptLine, ...]:
    evidence_by_id = {chunk.chunk_id: chunk for chunk in evidence}
    lines: list[ScriptLine] = []
    for index, chapter in enumerate(chapters):
        citations = tuple(
            evidence_by_id[chunk_id].citation()
            for chunk_id in chapter.source_chunk_ids[:2]
            if chunk_id in evidence_by_id
        )
        line_id = f"{chapter.chapter_id}-line-0"
        if citations:
            text = f"{chapter.title}: {chapter.purpose}"
            lines.append(
                ScriptLine(
                    line_id=line_id,
                    sequence=index,
                    text=text,
                    citations=citations,
                )
            )
        else:
            lines.append(
                ScriptLine(
                    line_id=line_id,
                    sequence=index,
                    text=f"{chapter.title}: {chapter.purpose}",
                    unsourced_reason="planner needs more graph evidence before render",
                )
            )
    if request.disclosure_preferences:
        lines.append(
            ScriptLine(
                line_id="disclosure-line-0",
                sequence=len(lines),
                text="Disclose generation and source limits requested by the operator.",
                kind="instruction",
            )
        )
    return tuple(lines)


def _storyboard_scenes(
    request: MultimediaPlanRequest,
    chapters: tuple[ChapterPlan, ...],
    script_lines: tuple[ScriptLine, ...],
) -> tuple[StoryboardScene, ...]:
    line_ids_by_chapter: dict[str, list[str]] = {}
    for line in script_lines:
        chapter_id = line.line_id.split("-line-", 1)[0]
        line_ids_by_chapter.setdefault(chapter_id, []).append(line.line_id)
    scenes: list[StoryboardScene] = []
    for index, chapter in enumerate(chapters):
        if request.mode == "audio":
            visual = "No primary visual; structure as a spoken chapter with optional chapter card."
        elif request.mode == "video":
            visual = f"Ken Burns pan over source cards and relevant archival/diagram imagery for {chapter.title}."
        else:
            visual = f"Hybrid: narrated chapter plus Ken Burns-style visual cards for {chapter.title}."
        scenes.append(
            StoryboardScene(
                scene_id=f"scene-{index:02d}",
                chapter_id=chapter.chapter_id,
                visual_intent=visual,
                information_purpose=chapter.purpose,
                narration_line_ids=tuple(line_ids_by_chapter.get(chapter.chapter_id, ())),
                source_chunk_ids=chapter.source_chunk_ids,
            )
        )
    return tuple(scenes)


def _assign_evidence_to_arcs(
    evidence: tuple[EvidenceChunk, ...],
) -> dict[str, tuple[EvidenceChunk, ...]]:
    buckets: dict[str, list[EvidenceChunk]] = {arc_id: [] for arc_id, _, _ in _DEFAULT_ARCS}
    keywords = {
        "history": ("history", "first", "early", "origin", "began", "war", "century"),
        "mechanism": ("engine", "design", "system", "mechanism", "aerodynamic", "manufacturing"),
        "comparison": ("versus", "compare", "different", "variant", "competitor", "unlike"),
        "consequences": ("therefore", "impact", "safety", "cost", "market", "changed", "result"),
    }
    for chunk in evidence:
        lower = chunk.text.lower()
        scored = {
            arc: sum(1 for word in words if word in lower)
            for arc, words in keywords.items()
        }
        best = max(scored, key=lambda arc: (scored[arc], -len(buckets[arc])))
        if scored[best] == 0:
            best = min(buckets, key=lambda arc: len(buckets[arc]))
        buckets[best].append(chunk)
    return {arc: tuple(items) for arc, items in buckets.items()}


def _top_terms(topic: str, evidence: tuple[EvidenceChunk, ...]) -> tuple[str, ...]:
    counter: Counter[str] = Counter()
    for text in (topic, *(chunk.text for chunk in evidence)):
        for token in _TOKEN_RE.findall(text.lower()):
            if token not in _STOPWORDS:
                counter[token] += 1
    return tuple(term for term, _ in counter.most_common(6))


def _tradeoff_for(arc_id: str) -> str:
    return {
        "history": "Sacrifices some technical depth for chronology.",
        "mechanism": "Sacrifices some biography and politics for causal clarity.",
        "comparison": "Sacrifices narrative momentum for side-by-side contrast.",
        "consequences": "Sacrifices build detail for downstream effects.",
    }[arc_id]
