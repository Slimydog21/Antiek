"""Grounded movement-friendly audio lessons and reopenable review manifests."""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

from substrate.contracts.multimedia import ScriptLine, ScriptLineKind, SourceCitation

from .audio_assembly import AudioExperience, assemble_audio_experience
from .planner import MultimediaPlan
from .tts import TTSProvider


class _RunModel(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        allow_inf_nan=False,
        revalidate_instances="always",
    )


class RunTranscriptSpan(_RunModel):
    paragraph_id: str
    line_id: str
    chapter_id: str
    spoken_text: str = Field(min_length=1)
    line_kind: ScriptLineKind
    start_offset_seconds: float = Field(ge=0)
    end_offset_seconds: float = Field(gt=0)
    source_chunk_ids: tuple[str, ...] = ()
    marker_kind: Literal["content", "signpost", "remember", "recap"]
    grounding_status: Literal["sourced", "unsourced", "not_required"]

    @model_validator(mode="after")
    def has_positive_window(self) -> RunTranscriptSpan:
        if self.end_offset_seconds <= self.start_offset_seconds:
            raise ValueError("run transcript spans require a positive timing window")
        if self.marker_kind in {"remember", "recap"} and not self.source_chunk_ids:
            raise ValueError("retention markers require source authority")
        if bool(self.source_chunk_ids) != (self.grounding_status == "sourced"):
            raise ValueError("span grounding status conflicts with its source authority")
        return self


class RunChapter(_RunModel):
    chapter_id: str
    title: str
    sequence: int = Field(ge=0)
    start_offset_seconds: float = Field(ge=0)
    end_offset_seconds: float = Field(gt=0)
    source_chunk_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def has_positive_window(self) -> RunChapter:
        if self.end_offset_seconds <= self.start_offset_seconds:
            raise ValueError("run chapters require a positive timing window")
        return self


class RetentionMarker(_RunModel):
    line_id: str
    chapter_id: str
    kind: Literal["remember", "recap"]
    at_seconds: float = Field(ge=0)
    source_chunk_ids: tuple[str, ...] = Field(min_length=1)


class LearnedClaimCard(_RunModel):
    line_id: str
    chapter_id: str
    claim_text: str = Field(min_length=1)
    source_chunk_ids: tuple[str, ...] = Field(min_length=1)
    follow_up_prompt: str = Field(min_length=1)


class AudibleRunManifest(_RunModel):
    schema_version: Literal["antiek.audible-run.v1"] = "antiek.audible-run.v1"
    asset_id: str
    revision_id: str
    total_duration_seconds: float = Field(gt=0)
    transcript_file_id: str
    chapters: tuple[RunChapter, ...] = Field(min_length=1)
    transcript_spans: tuple[RunTranscriptSpan, ...] = Field(min_length=1)
    retention_markers: tuple[RetentionMarker, ...] = Field(min_length=1)
    learned_claims: tuple[LearnedClaimCard, ...] = Field(min_length=1)
    unsourced_line_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def timeline_is_complete_and_unique(self) -> AudibleRunManifest:
        _unique((chapter.chapter_id for chapter in self.chapters), "chapter ids")
        _unique((span.paragraph_id for span in self.transcript_spans), "paragraph ids")
        _unique((span.line_id for span in self.transcript_spans), "transcript line ids")
        _unique((marker.line_id for marker in self.retention_markers), "marker line ids")
        _unique((card.line_id for card in self.learned_claims), "learned claim ids")
        ordered = sorted(self.transcript_spans, key=lambda span: span.start_offset_seconds)
        expected = 0.0
        for span in ordered:
            if abs(span.start_offset_seconds - expected) > 0.001:
                raise ValueError("run transcript timeline has a gap or overlap")
            expected = span.end_offset_seconds
        if abs(expected - self.total_duration_seconds) > 0.001:
            raise ValueError("run transcript timeline does not cover the complete audio")
        if tuple(chapter.sequence for chapter in self.chapters) != tuple(range(len(self.chapters))):
            raise ValueError("run chapters must have contiguous sequence numbers")
        chapter_by_id = {chapter.chapter_id: chapter for chapter in self.chapters}
        span_by_line = {span.line_id: span for span in self.transcript_spans}
        chapter_spans: dict[str, list[RunTranscriptSpan]] = {
            chapter_id: [] for chapter_id in chapter_by_id
        }
        for span in self.transcript_spans:
            chapter = chapter_by_id.get(span.chapter_id)
            if chapter is None:
                raise ValueError("run transcript span references an unknown chapter")
            if (
                span.start_offset_seconds < chapter.start_offset_seconds - 0.001
                or span.end_offset_seconds > chapter.end_offset_seconds + 0.001
            ):
                raise ValueError("run transcript span escapes its chapter window")
            if not set(span.source_chunk_ids).issubset(chapter.source_chunk_ids):
                raise ValueError("run transcript source escapes chapter authority")
            chapter_spans[span.chapter_id].append(span)
        chapter_expected = 0.0
        for chapter in self.chapters:
            spans = chapter_spans[chapter.chapter_id]
            if not spans:
                raise ValueError("run chapter has no transcript spans")
            if abs(chapter.start_offset_seconds - chapter_expected) > 0.001:
                raise ValueError("run chapter timeline has a gap or overlap")
            if abs(spans[0].start_offset_seconds - chapter.start_offset_seconds) > 0.001:
                raise ValueError("run chapter start does not match its transcript")
            if abs(spans[-1].end_offset_seconds - chapter.end_offset_seconds) > 0.001:
                raise ValueError("run chapter end does not match its transcript")
            chapter_expected = chapter.end_offset_seconds
        marker_lines: set[str] = set()
        for marker in self.retention_markers:
            marker_span = span_by_line.get(marker.line_id)
            if (
                marker_span is None
                or marker_span.chapter_id != marker.chapter_id
                or marker_span.marker_kind != marker.kind
                or marker_span.start_offset_seconds != marker.at_seconds
                or marker_span.source_chunk_ids != marker.source_chunk_ids
            ):
                raise ValueError("retention marker does not match its transcript span")
            marker_lines.add(marker.line_id)
        expected_markers = {
            span.line_id
            for span in self.transcript_spans
            if span.marker_kind in {"remember", "recap"}
        }
        if marker_lines != expected_markers:
            raise ValueError("retention marker index is incomplete")
        for chapter_id in chapter_by_id:
            signposts = [
                span for span in chapter_spans[chapter_id] if span.marker_kind == "signpost"
            ]
            if len(signposts) != 1 or chapter_spans[chapter_id][0] != signposts[0]:
                raise ValueError("every run chapter must begin with one signpost")
            remember_spans = [
                span for span in chapter_spans[chapter_id] if span.marker_kind == "remember"
            ]
            recap_spans = [
                span for span in chapter_spans[chapter_id] if span.marker_kind == "recap"
            ]
            if len(remember_spans) != 1 or len(recap_spans) != 1:
                raise ValueError("every run chapter requires remember and recap markers")
            grounded_content = [
                span
                for span in chapter_spans[chapter_id]
                if (
                    span.marker_kind == "content"
                    and span.line_kind == "factual"
                    and span.grounding_status == "sourced"
                )
            ]
            if not grounded_content:
                raise ValueError("every run chapter requires sourced factual content")
            if (
                remember_spans[0].line_id != f"{chapter_id}-line-run-remember"
                or (
                    remember_spans[0].spoken_text
                    != "Remember this. " + grounded_content[0].spoken_text
                )
                or remember_spans[0].source_chunk_ids != grounded_content[0].source_chunk_ids
            ):
                raise ValueError("remember marker text, identity, or authority is invalid")
            recap_authority = tuple(
                dict.fromkeys(
                    chunk_id for span in grounded_content for chunk_id in span.source_chunk_ids
                )
            )
            if (
                recap_spans[0].line_id != f"{chapter_id}-line-run-recap"
                or (
                    recap_spans[0].spoken_text
                    != "Chapter recap. " + " ".join(span.spoken_text for span in grounded_content)
                )
                or recap_spans[0].source_chunk_ids != recap_authority
            ):
                raise ValueError("recap marker text, identity, or authority is invalid")
        learned_lines: set[str] = set()
        for card in self.learned_claims:
            card_span = span_by_line.get(card.line_id)
            expected_prompt = _follow_up_prompt(card.source_chunk_ids)
            if (
                card_span is None
                or card_span.chapter_id != card.chapter_id
                or card_span.marker_kind != "content"
                or card_span.line_kind != "factual"
                or card_span.grounding_status != "sourced"
                or card_span.spoken_text != card.claim_text
                or card_span.source_chunk_ids != card.source_chunk_ids
                or card.follow_up_prompt != expected_prompt
            ):
                raise ValueError("learned claim does not match a grounded content span")
            learned_lines.add(card.line_id)
        expected_learned = {
            span.line_id
            for span in self.transcript_spans
            if span.marker_kind == "content"
            and span.grounding_status == "sourced"
            and span.line_kind == "factual"
        }
        if learned_lines != expected_learned:
            raise ValueError("learned claim index is incomplete")
        actual_unsourced = tuple(
            span.line_id for span in self.transcript_spans if span.grounding_status == "unsourced"
        )
        if actual_unsourced != self.unsourced_line_ids:
            raise ValueError("unsourced line disclosure is incomplete")
        return self


class AudibleRunArtifact(_RunModel):
    manifest: AudibleRunManifest
    manifest_sha256: str = Field(pattern="^[0-9a-f]{64}$")

    @classmethod
    def seal(cls, manifest: AudibleRunManifest) -> AudibleRunArtifact:
        validated = AudibleRunManifest.model_validate(dict(manifest.__dict__))
        return cls(manifest=validated, manifest_sha256=_manifest_digest(validated))

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))

    @classmethod
    def reopen(cls, payload: str | bytes) -> AudibleRunArtifact:
        artifact = cls.model_validate_json(payload)
        if not hmac.compare_digest(artifact.manifest_sha256, _manifest_digest(artifact.manifest)):
            raise ValueError("audible run manifest digest does not match its payload")
        return artifact


@dataclass(frozen=True)
class AudibleRunBundle:
    plan: MultimediaPlan
    experience: AudioExperience
    artifact: AudibleRunArtifact


def prepare_audible_run_plan(plan: MultimediaPlan) -> MultimediaPlan:
    """Insert spoken navigation and citation-preserving retention beats."""
    source_lines = tuple(
        line for line in plan.script_lines if line.kind == "factual" and line.citations
    )
    if not source_lines:
        raise ValueError("audible run mode requires at least one sourced factual claim")
    if any(line.kind == "factual" and not line.citations for line in plan.script_lines):
        raise ValueError("audible run mode refuses unsourced factual narration")
    if any(_marker_kind_from_id(line.line_id) != "content" for line in plan.script_lines):
        raise ValueError("input plan uses reserved audible-run marker identities")
    by_chapter: dict[str, list[ScriptLine]] = {chapter.chapter_id: [] for chapter in plan.chapters}
    for line in plan.script_lines:
        chapter_id = line.line_id.split("-line-", 1)[0]
        if "-line-" not in line.line_id or chapter_id not in by_chapter:
            raise ValueError(f"script line {line.line_id!r} does not belong to a plan chapter")
        by_chapter[chapter_id].append(line)

    transformed: list[ScriptLine] = []
    for chapter in plan.chapters:
        lines = by_chapter[chapter.chapter_id]
        grounded = [line for line in lines if line.kind == "factual" and line.citations]
        if not grounded:
            raise ValueError(
                f"audible run chapter {chapter.chapter_id!r} has no sourced factual claim"
            )
        transformed.append(
            ScriptLine(
                line_id=f"{chapter.chapter_id}-line-run-signpost",
                sequence=len(transformed),
                text=f"Next, {chapter.title}. {chapter.purpose}",
                kind="transition",
            )
        )
        for line in lines:
            transformed.append(_resequence(line, len(transformed)))
            if grounded and line.line_id == grounded[0].line_id:
                transformed.append(
                    _grounded_marker(
                        line,
                        line_id=f"{chapter.chapter_id}-line-run-remember",
                        sequence=len(transformed),
                        prefix="Remember this. ",
                    )
                )
        transformed.append(
            _chapter_recap(
                grounded,
                line_id=f"{chapter.chapter_id}-line-run-recap",
                sequence=len(transformed),
            )
        )
    if len({line.line_id for line in transformed}) != len(transformed):
        raise ValueError("audible run transform produced duplicate line ids")
    values = plan.model_dump(mode="python")
    values["script_lines"] = tuple(transformed)
    values["unsourced_line_ids"] = tuple(
        line.line_id for line in transformed if line.kind == "factual" and not line.citations
    )
    return MultimediaPlan.model_validate(values)


def assemble_audible_run(
    plan: MultimediaPlan,
    tts: TTSProvider,
    *,
    asset_id: str,
    revision_id: str,
    voice: str = "narrator",
    speed: float = 1.0,
) -> AudibleRunBundle:
    run_plan = prepare_audible_run_plan(plan)
    experience = assemble_audio_experience(
        run_plan,
        tts,
        asset_id=asset_id,
        revision_id=revision_id,
        voice=voice,
        speed=speed,
    )
    manifest = _compile_manifest(run_plan, experience)
    return AudibleRunBundle(run_plan, experience, AudibleRunArtifact.seal(manifest))


def _compile_manifest(plan: MultimediaPlan, experience: AudioExperience) -> AudibleRunManifest:
    lines = {line.line_id: line for line in plan.script_lines}
    claims = {claim.script_line_id: claim.chunk_ids for claim in experience.manifest.claim_to_chunk}
    spans = tuple(
        RunTranscriptSpan(
            paragraph_id=span.paragraph_id,
            line_id=span.line_id,
            chapter_id=span.chapter_id,
            spoken_text=span.spoken_text,
            line_kind=cast(ScriptLineKind, span.line_kind),
            start_offset_seconds=span.start_offset_seconds,
            end_offset_seconds=span.end_offset_seconds,
            source_chunk_ids=span.source_chunk_ids,
            marker_kind=span.marker_kind,
            grounding_status=span.grounding_status,
        )
        for chapter in experience.chapters
        for span in chapter.paragraph_spans
    )
    for span in spans:
        line = lines.get(span.line_id)
        if line is None:
            raise ValueError("audio span refers to an unknown script line")
        expected = tuple(citation.chunk_id for citation in line.citations)
        if expected != span.source_chunk_ids or (expected and claims.get(span.line_id) != expected):
            raise ValueError("audio span source authority drifted from the script")
    return compile_audible_run_manifest(
        plan,
        asset_id=experience.manifest.asset_id,
        revision_id=experience.manifest.revision_id,
        transcript_file_id=experience.transcript_file_id,
        chapters=tuple(
            RunChapter(
                chapter_id=chapter.chapter_id,
                title=chapter.title,
                sequence=chapter.sequence,
                start_offset_seconds=chapter.start_offset_seconds,
                end_offset_seconds=chapter.end_offset_seconds,
                source_chunk_ids=chapter.source_chunk_ids,
            )
            for chapter in experience.chapters
        ),
        transcript_spans=spans,
    )


def compile_audible_run_manifest(
    plan: MultimediaPlan,
    *,
    asset_id: str,
    revision_id: str,
    transcript_file_id: str,
    chapters: tuple[RunChapter, ...],
    transcript_spans: tuple[RunTranscriptSpan, ...],
) -> AudibleRunManifest:
    """Compile review metadata from an exact measured transcript timeline."""
    if not transcript_spans:
        raise ValueError("audible run requires a measured transcript timeline")
    lines = {line.line_id: line for line in plan.script_lines}
    if len(lines) != len(plan.script_lines):
        raise ValueError("audible run plan contains duplicate script line ids")
    for span in transcript_spans:
        line = lines.get(span.line_id)
        if line is None or line.text != span.spoken_text or line.kind != span.line_kind:
            raise ValueError("audio span content drifted from the script")
        expected = tuple(citation.chunk_id for citation in line.citations)
        if expected != span.source_chunk_ids:
            raise ValueError("audio span source authority drifted from the script")
    markers: list[RetentionMarker] = []
    for span in transcript_spans:
        if span.marker_kind in {"remember", "recap"}:
            kind = cast(Literal["remember", "recap"], span.marker_kind)
            markers.append(
                RetentionMarker(
                    line_id=span.line_id,
                    chapter_id=span.chapter_id,
                    kind=kind,
                    at_seconds=span.start_offset_seconds,
                    source_chunk_ids=span.source_chunk_ids,
                )
            )
    learned = tuple(
        LearnedClaimCard(
            line_id=span.line_id,
            chapter_id=span.chapter_id,
            claim_text=span.spoken_text,
            source_chunk_ids=span.source_chunk_ids,
            follow_up_prompt=_follow_up_prompt(span.source_chunk_ids),
        )
        for span in transcript_spans
        if span.marker_kind == "content"
        and lines[span.line_id].kind == "factual"
        and span.source_chunk_ids
    )
    return AudibleRunManifest(
        asset_id=asset_id,
        revision_id=revision_id,
        total_duration_seconds=transcript_spans[-1].end_offset_seconds,
        transcript_file_id=transcript_file_id,
        chapters=chapters,
        transcript_spans=transcript_spans,
        retention_markers=tuple(markers),
        learned_claims=learned,
        unsourced_line_ids=tuple(
            span.line_id for span in transcript_spans if span.grounding_status == "unsourced"
        ),
    )


def _resequence(line: ScriptLine, sequence: int) -> ScriptLine:
    values = line.model_dump(mode="python")
    values["sequence"] = sequence
    return ScriptLine.model_validate(values)


def _grounded_marker(line: ScriptLine, *, line_id: str, sequence: int, prefix: str) -> ScriptLine:
    if line.kind != "factual" or not line.citations:
        raise ValueError("retention markers require a sourced factual line")
    return ScriptLine(
        line_id=line_id,
        sequence=sequence,
        text=prefix + line.text,
        kind="factual",
        citations=line.citations,
    )


def _chapter_recap(lines: list[ScriptLine], *, line_id: str, sequence: int) -> ScriptLine:
    if not lines:
        raise ValueError("chapter recap requires sourced factual lines")
    citations_by_chunk: dict[str, SourceCitation] = {}
    for line in lines:
        for citation in line.citations:
            existing = citations_by_chunk.get(citation.chunk_id)
            if existing is not None and existing != citation:
                raise ValueError("chapter recap source authority conflicts")
            citations_by_chunk[citation.chunk_id] = citation
    return ScriptLine(
        line_id=line_id,
        sequence=sequence,
        text="Chapter recap. " + " ".join(line.text for line in lines),
        kind="factual",
        citations=tuple(citations_by_chunk.values()),
    )


def _follow_up_prompt(source_chunk_ids: tuple[str, ...]) -> str:
    return (
        "What additional context do source chunks "
        + ", ".join(source_chunk_ids)
        + " provide for this claim?"
    )


def _marker_kind_from_id(
    line_id: str,
) -> Literal["content", "signpost", "remember", "recap"]:
    for marker in ("signpost", "remember", "recap"):
        if line_id.endswith(f"-run-{marker}"):
            return marker
    return "content"


def _manifest_digest(manifest: AudibleRunManifest) -> str:
    payload = json.dumps(
        manifest.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _unique(values: Iterable[str], label: str) -> None:
    materialized: tuple[str, ...] = tuple(values)
    if len(set(materialized)) != len(materialized):
        raise ValueError(f"audible run {label} must be unique")


__all__ = [
    "AudibleRunArtifact",
    "AudibleRunBundle",
    "AudibleRunManifest",
    "LearnedClaimCard",
    "RetentionMarker",
    "RunChapter",
    "RunTranscriptSpan",
    "assemble_audible_run",
    "compile_audible_run_manifest",
    "prepare_audible_run_plan",
]
