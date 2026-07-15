"""Chaptered audio assembly (multimedia SPR-04, milestone 3).

Stitch a planner :class:`~substrate.multimedia.planner.MultimediaPlan` into a
chaptered, replayable audio experience: normalize the cited script to speech,
synthesize each paragraph through the TTS seam, concatenate per chapter, and emit
a SPR-01 :class:`~substrate.contracts.multimedia.MultimediaManifest` whose
referential integrity (prompts -> files -> calls -> cost rows -> segments) is
satisfied by construction.

Craftsmanship invariants this module guarantees:

* GROUNDING SURVIVES SYNTHESIS. Every chapter segment carries the union of its
  paragraphs' ``source_chunk_ids`` (plus the planner's chapter-level chunks), and
  the manifest's ``claim_to_chunk`` maps each cited spoken line back to its
  chunks. A listener (or a player) can always surface the source behind a claim.
* HONEST UNSOURCED MARKING. A factual paragraph with no citations is collected in
  ``AudioExperience.unsourced_paragraph_ids`` rather than hidden — mirroring the
  planner's ``unsourced_line_ids`` discipline so the gap is a review surface.
* INTEGRITY BY CONSTRUCTION. Each chapter audio file's ``sha256`` is the digest of
  its concatenated synthesized bytes; with the deterministic fake TTS the same
  plan yields a byte-stable manifest, so CI can assert hashes without a real voice.
* CHAPTERS ARE INDEPENDENTLY REPLAYABLE. Each chapter is one audio file + one
  segment with its own offset/duration, so a player can seek/replay a chapter
  without re-synthesizing the whole asset.

No provider key is required: the default fake TTS makes this fully credential-free.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Literal

from ..contracts.multimedia import (
    ClaimToChunk,
    CostRow,
    GeneratedFile,
    MediaSegment,
    MultimediaManifest,
    PromptRecord,
    ProviderCall,
)
from .narration import NarrationParagraph, normalize_script
from .planner import MultimediaPlan
from .tts import TTSProvider, TTSRequest


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _chapter_of(line_id: str) -> str:
    """Inverse of the planner's line-id convention ``{chapter}-line-{n}``.

    Matches ``planner.to_manifest`` exactly (split on the first ``-line-``) so a
    paragraph always lands in the chapter the planner assigned it to."""
    return line_id.split("-line-", 1)[0]


def _dedupe(items: tuple[str, ...]) -> tuple[str, ...]:
    """Order-preserving de-duplication (chunk-id unions must stay stable)."""
    return tuple(dict.fromkeys(items))


@dataclass(frozen=True)
class AudioParagraphSpan:
    """One synthesized paragraph's exact window in the assembled experience."""

    paragraph_id: str
    line_id: str
    chapter_id: str
    spoken_text: str
    line_kind: str
    start_offset_seconds: float
    end_offset_seconds: float
    source_chunk_ids: tuple[str, ...]
    marker_kind: Literal["content", "signpost", "remember", "recap"] = "content"
    grounding_status: Literal["sourced", "unsourced", "not_required"] = "not_required"


@dataclass(frozen=True)
class ChapterAudio:
    """One replayable chapter: its audio file, timeline window, and provenance."""

    chapter_id: str
    title: str
    sequence: int
    audio_file_id: str
    duration_seconds: float
    start_offset_seconds: float
    script_line_ids: tuple[str, ...]
    source_chunk_ids: tuple[str, ...]
    paragraph_ids: tuple[str, ...]
    recap_prompt: str
    paragraph_spans: tuple[AudioParagraphSpan, ...] = field(default_factory=tuple)
    assembled_end_offset_seconds: float | None = None

    @property
    def end_offset_seconds(self) -> float:
        if self.assembled_end_offset_seconds is not None:
            return self.assembled_end_offset_seconds
        return round(self.start_offset_seconds + self.duration_seconds, 3)


@dataclass(frozen=True)
class AudioExperience:
    """A fully assembled, manifest-backed audio asset ready for playback.

    ``manifest`` is the SPR-01 replay artifact; ``chapters`` is the playback
    timeline; ``unsourced_paragraph_ids`` is the honest gap surface."""

    manifest: MultimediaManifest
    chapters: tuple[ChapterAudio, ...]
    total_duration_seconds: float
    transcript_file_id: str
    unsourced_paragraph_ids: tuple[str, ...] = field(default_factory=tuple)


def assemble_audio_experience(
    plan: MultimediaPlan,
    tts: TTSProvider,
    *,
    asset_id: str,
    revision_id: str,
    voice: str = "narrator",
    speed: float = 1.0,
    pronunciation_notes: dict[str, str] | None = None,
) -> AudioExperience:
    """Assemble a chaptered audio experience from a grounded plan.

    Each chapter's narration is synthesized paragraph-by-paragraph and
    concatenated into one audio file; a transcript file covers the full asset.
    The returned manifest satisfies SPR-01 referential integrity by construction.
    Raises ``ValueError`` if no chapter carries any narration."""
    chapter_ids = {chapter.chapter_id for chapter in plan.chapters}
    # Only narrate lines that belong to a real plan chapter. The planner can emit
    # non-chapter script lines (e.g. ``disclosure-line-0``, an instruction for the
    # render gate, not narration); speaking those would put text in the transcript
    # + manifest.script_lines that no chapter's audio ever covers (transcript/audio
    # divergence). Filter at the source so transcript == audio == segment lines.
    spoken_lines = tuple(
        line for line in plan.script_lines if _chapter_of(line.line_id) in chapter_ids
    )
    paragraphs = normalize_script(spoken_lines, pronunciation_notes=pronunciation_notes)
    by_chapter: dict[str, list[NarrationParagraph]] = {}
    for para in paragraphs:
        by_chapter.setdefault(_chapter_of(para.line_id), []).append(para)

    prompts: list[PromptRecord] = []
    files: list[GeneratedFile] = []
    calls: list[ProviderCall] = []
    costs: list[CostRow] = []
    segments: list[MediaSegment] = []
    claim_rows: list[ClaimToChunk] = []
    chapter_audios: list[ChapterAudio] = []
    offset = 0.0

    assembled_sequence = 0
    for chapter in plan.chapters:
        paras = by_chapter.get(chapter.chapter_id, ())
        if not paras:
            # A chapter the planner emitted with no narration has nothing to
            # speak; skip it rather than emit an empty audio file (which would
            # collapse the manifest's integrity hashes to a constant).
            continue
        chapter_text = " ".join(p.text for p in paras)
        prompt_id = f"prompt-{asset_id}-{chapter.chapter_id}"
        prompts.append(
            PromptRecord(
                prompt_id=prompt_id,
                purpose="audio",
                prompt_sha256=_sha(chapter_text),
                provider_hint=tts.name,
            )
        )

        audio_chunks: list[bytes] = []
        chapter_duration_raw = 0.0
        chapter_cost = 0.0
        total_chars = 0
        paragraph_spans: list[AudioParagraphSpan] = []
        paragraph_offset = offset
        for para in paras:
            result = tts.synthesize(TTSRequest(text=para.text, voice=voice, speed=speed))
            audio_chunks.append(result.audio_bytes)
            chapter_duration_raw += result.duration_seconds
            chapter_cost += result.cost_usd
            total_chars += len(para.text)
            paragraph_start = round(paragraph_offset, 3)
            paragraph_offset += result.duration_seconds
            paragraph_end = round(paragraph_offset, 3)
            paragraph_spans.append(
                AudioParagraphSpan(
                    paragraph_id=para.para_id,
                    line_id=para.line_id,
                    chapter_id=chapter.chapter_id,
                    spoken_text=para.text,
                    line_kind=para.kind,
                    start_offset_seconds=paragraph_start,
                    end_offset_seconds=paragraph_end,
                    source_chunk_ids=para.source_chunk_ids,
                    marker_kind=_marker_kind(para.line_id),
                    grounding_status=(
                        "sourced"
                        if para.source_chunk_ids
                        else "unsourced"
                        if para.unsourced
                        else "not_required"
                    ),
                )
            )
        chapter_bytes = b"".join(audio_chunks)
        chapter_duration = round(chapter_duration_raw, 3)
        chapter_cost = round(chapter_cost, 6)

        audio_file_id = f"audio-{asset_id}-{chapter.chapter_id}"
        files.append(
            GeneratedFile(
                file_id=audio_file_id,
                kind="audio",
                storage_uri=(f"antiek-mm://{asset_id}/{revision_id}/{audio_file_id}.bin"),
                sha256=hashlib.sha256(chapter_bytes).hexdigest(),
                mime=getattr(tts, "mime", "audio/fake-pcm"),
                provider=tts.name,
                prompt_id=prompt_id,
                duration_seconds=chapter_duration,
            )
        )

        call_id = f"call-{asset_id}-{chapter.chapter_id}"
        calls.append(
            ProviderCall(
                call_id=call_id,
                provider=tts.name,
                prompt_id=prompt_id,
                route_policy=plan.request.route_policy,
                status="succeeded",
                input_units=float(total_chars),
                output_units=float(len(chapter_bytes)),
                unit_type="characters/bytes",
                cost_usd=chapter_cost,
            )
        )
        costs.append(
            CostRow(
                cost_id=f"cost-{call_id}",
                call_id=call_id,
                provider=tts.name,
                route_policy=plan.request.route_policy,
                cost_usd=chapter_cost,
                billable_units=float(total_chars),
                unit_type="characters",
            )
        )

        line_ids = tuple(p.line_id for p in paras)
        source_chunks = _dedupe(
            tuple(c for p in paras for c in p.source_chunk_ids) + tuple(chapter.source_chunk_ids)
        )
        segments.append(
            MediaSegment(
                segment_id=f"seg-{chapter.chapter_id}",
                sequence=assembled_sequence,
                title=chapter.title,
                media_kind="chapter",
                script_line_ids=line_ids,
                file_ids=(audio_file_id,),
                source_chunk_ids=source_chunks,
                duration_seconds=chapter_duration,
            )
        )
        chapter_audios.append(
            ChapterAudio(
                chapter_id=chapter.chapter_id,
                title=chapter.title,
                sequence=assembled_sequence,
                audio_file_id=audio_file_id,
                duration_seconds=chapter_duration,
                start_offset_seconds=round(offset, 3),
                script_line_ids=line_ids,
                source_chunk_ids=source_chunks,
                paragraph_ids=tuple(p.para_id for p in paras),
                recap_prompt=(
                    f"In one breath, recap the takeaway of “{chapter.title}”, "
                    "then pose one question that invites going deeper."
                ),
                paragraph_spans=tuple(paragraph_spans),
                assembled_end_offset_seconds=round(offset + chapter_duration_raw, 3),
            )
        )
        offset += chapter_duration_raw
        assembled_sequence += 1

    if not chapter_audios:
        raise ValueError(
            "audio assembly produced no chapters; the plan must carry narration "
            "for at least one chapter before assembly"
        )

    # Full-asset transcript: the text track for the whole experience. It carries
    # the total duration because it documents audio of exactly that length (the
    # contract requires every generated file to have a media shape).
    transcript_text = "\n\n".join(f"[{p.line_id}] {p.text}" for p in paragraphs)
    transcript_prompt_id = f"prompt-{asset_id}-transcript"
    prompts.append(
        PromptRecord(
            prompt_id=transcript_prompt_id,
            purpose="script",
            prompt_sha256=_sha(transcript_text),
            provider_hint=tts.name,
        )
    )
    transcript_file_id = f"transcript-{asset_id}"
    files.append(
        GeneratedFile(
            file_id=transcript_file_id,
            kind="transcript",
            storage_uri=(f"antiek-mm://{asset_id}/{revision_id}/{transcript_file_id}.txt"),
            sha256=_sha(transcript_text),
            mime="text/plain",
            provider=tts.name,
            prompt_id=transcript_prompt_id,
            duration_seconds=round(offset, 3),
        )
    )

    for para in paragraphs:
        if para.source_chunk_ids:
            claim_rows.append(
                ClaimToChunk(
                    claim_id=f"claim-{para.line_id}",
                    script_line_id=para.line_id,
                    chunk_ids=para.source_chunk_ids,
                )
            )

    manifest = MultimediaManifest(
        asset_id=asset_id,
        revision_id=revision_id,
        route_policy=plan.request.route_policy,
        prompts=tuple(prompts),
        script_lines=spoken_lines,
        segments=tuple(segments),
        files=tuple(files),
        provider_calls=tuple(calls),
        cost_rows=tuple(costs),
        claim_to_chunk=tuple(claim_rows),
        transcript_file_id=transcript_file_id,
    )

    unsourced = tuple(p.para_id for p in paragraphs if p.unsourced)
    return AudioExperience(
        manifest=manifest,
        chapters=tuple(chapter_audios),
        total_duration_seconds=round(offset, 3),
        transcript_file_id=transcript_file_id,
        unsourced_paragraph_ids=unsourced,
    )


def _marker_kind(
    line_id: str,
) -> Literal["content", "signpost", "remember", "recap"]:
    for marker in ("signpost", "remember", "recap"):
        if line_id.endswith(f"-run-{marker}"):
            return marker
    return "content"
