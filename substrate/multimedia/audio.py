"""Audio experience assembly for multimedia assets.

SPR-04 turns a planned, cited multimedia script into a chaptered audio asset.
It does not choose a live TTS vendor or burn credits. The seam is a mockable
``TTSProvider``; the default fake provider returns deterministic bytes and
durations so CI can verify hashes, timestamps, transcript alignment, and source
maps without a key.
"""

from __future__ import annotations

import hashlib
import re
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from substrate.contracts.multimedia import (
    CostRow,
    GeneratedFile,
    MediaSegment,
    MultimediaManifest,
    ProviderCall,
    RoutePolicy,
)
from substrate.multimedia.planner import MultimediaPlan

NARRATION_WPM = 150
DEFAULT_AUDIO_VOICE = "alloy"
DEFAULT_AUDIO_SPEED = 1.0
SourceStatus = Literal["sourced", "unsourced", "instruction"]

_ABBREVIATIONS = {
    "AI": "A I",
    "ASR": "A S R",
    "TTS": "T T S",
    "U.S.": "U S",
    "e.g.": "for example",
    "i.e.": "that is",
}


class _AudioBase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class NarrationParagraph(_AudioBase):
    paragraph_id: str
    chapter_id: str
    text: str = Field(min_length=1)
    script_line_ids: tuple[str, ...]
    source_chunk_ids: tuple[str, ...] = Field(default_factory=tuple)
    source_status: SourceStatus
    pronunciation_notes: tuple[str, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def factual_source_status_is_explicit(self) -> NarrationParagraph:
        if self.source_status == "sourced" and not self.source_chunk_ids:
            raise ValueError("sourced paragraphs require source_chunk_ids")
        return self


class TTSRequest(_AudioBase):
    chapter_id: str
    text: str = Field(min_length=1)
    voice: str = DEFAULT_AUDIO_VOICE
    speed: float = Field(default=DEFAULT_AUDIO_SPEED, ge=0.5, le=2.0)
    route_policy: RoutePolicy = "balanced"


class TTSResult(_AudioBase):
    audio_bytes: bytes
    mime: str = "audio/mpeg"
    duration_seconds: float = Field(ge=0)
    transcript: str
    provider: str
    model: str
    cost_usd: float = Field(default=0, ge=0)


class TTSProvider(Protocol):
    name: str
    model: str

    def synthesize(self, request: TTSRequest) -> TTSResult:
        """Synthesize a chapter. Implementations must be injectable."""


class FakeTTSProvider:
    """Deterministic CI provider: no network, no key, stable bytes."""

    name = "fake_tts"
    model = "deterministic-fake-audio"

    def synthesize(self, request: TTSRequest) -> TTSResult:
        words = _word_count(request.text)
        duration = round(max(1.0, (words / (NARRATION_WPM * request.speed)) * 60), 2)
        digest = hashlib.sha256(
            f"{request.chapter_id}\x1f{request.voice}\x1f{request.speed}\x1f{request.text}".encode()
        ).hexdigest()
        return TTSResult(
            audio_bytes=f"FAKEAUDIO\n{digest}\n{request.text}".encode(),
            duration_seconds=duration,
            transcript=request.text,
            provider=self.name,
            model=self.model,
            cost_usd=0.0,
        )


class AudioChapter(_AudioBase):
    chapter_id: str
    title: str
    start_seconds: float = Field(ge=0)
    duration_seconds: float = Field(ge=0)
    audio_file_id: str
    transcript: str
    source_chunk_ids: tuple[str, ...] = Field(default_factory=tuple)
    paragraph_ids: tuple[str, ...]
    recap_prompt: str
    transcript_matches_audio: bool = True
    transcript_delta: str | None = None


class PlaybackChapter(_AudioBase):
    chapter_id: str
    title: str
    start_seconds: float
    duration_seconds: float
    source_cards: tuple[str, ...] = Field(default_factory=tuple)
    steering_target: str


class AudioPlaybackModel(_AudioBase):
    asset_id: str
    revision_id: str
    chapters: tuple[PlaybackChapter, ...]
    total_duration_seconds: float

    def chapter_at(self, seconds: float) -> PlaybackChapter | None:
        for chapter in self.chapters:
            if chapter.start_seconds <= seconds < chapter.start_seconds + chapter.duration_seconds:
                return chapter
        return self.chapters[-1] if self.chapters and seconds == self.total_duration_seconds else None


class AudioExperienceAsset(_AudioBase):
    asset_id: str
    revision_id: str
    voice: str
    speed: float
    paragraphs: tuple[NarrationParagraph, ...]
    chapters: tuple[AudioChapter, ...]
    manifest: MultimediaManifest
    playback: AudioPlaybackModel


def normalize_script_for_audio(plan: MultimediaPlan) -> tuple[NarrationParagraph, ...]:
    """Convert plan script lines into speech-ready paragraphs without losing
    source alignment."""

    chapter_for_line = _chapter_for_line(plan)
    paragraphs: list[NarrationParagraph] = []
    for index, line in enumerate(plan.script_lines):
        chapter_id = chapter_for_line.get(line.line_id, "intro")
        text, notes = _speech_text(line.text)
        if line.kind == "instruction":
            status: SourceStatus = "instruction"
        elif line.citations:
            status = "sourced"
        else:
            status = "unsourced"
        paragraphs.append(
            NarrationParagraph(
                paragraph_id=f"para-{index:03d}",
                chapter_id=chapter_id,
                text=text,
                script_line_ids=(line.line_id,),
                source_chunk_ids=tuple(c.chunk_id for c in line.citations),
                source_status=status,
                pronunciation_notes=tuple(notes),
            )
        )
    return tuple(paragraphs)


def assemble_audio_experience(
    plan: MultimediaPlan,
    *,
    asset_id: str,
    revision_id: str,
    voice: str = DEFAULT_AUDIO_VOICE,
    speed: float = DEFAULT_AUDIO_SPEED,
    provider: TTSProvider | None = None,
) -> AudioExperienceAsset:
    """Build a chaptered audio asset from a multimedia plan."""

    tts = provider or FakeTTSProvider()
    paragraphs = normalize_script_for_audio(plan)
    paragraphs_by_chapter: dict[str, list[NarrationParagraph]] = {}
    for paragraph in paragraphs:
        paragraphs_by_chapter.setdefault(paragraph.chapter_id, []).append(paragraph)

    generated_files: list[GeneratedFile] = []
    provider_calls: list[ProviderCall] = []
    costs: list[CostRow] = []
    segments: list[MediaSegment] = []
    chapters: list[AudioChapter] = []
    cursor = 0.0
    for index, chapter in enumerate(plan.chapters):
        chapter_paragraphs = tuple(paragraphs_by_chapter.get(chapter.chapter_id, ()))
        text = "\n\n".join(p.text for p in chapter_paragraphs) or chapter.purpose
        req = TTSRequest(
            chapter_id=chapter.chapter_id,
            text=text,
            voice=voice,
            speed=speed,
            route_policy=plan.request.route_policy,
        )
        result = tts.synthesize(req)
        audio_hash = hashlib.sha256(result.audio_bytes).hexdigest()
        transcript_hash = hashlib.sha256(result.transcript.encode("utf-8")).hexdigest()
        audio_file_id = f"aud-{chapter.chapter_id}"
        transcript_file_id = f"txt-{chapter.chapter_id}"
        call_id = f"tts-{chapter.chapter_id}"
        generated_files.extend([
            GeneratedFile(
                file_id=audio_file_id,
                kind="audio",
                storage_uri=f"memory://multimedia/{asset_id}/{revision_id}/{audio_file_id}.mp3",
                sha256=audio_hash,
                mime=result.mime,
                provider=result.provider,
                prompt_id=None,
                duration_seconds=result.duration_seconds,
            ),
            GeneratedFile(
                file_id=transcript_file_id,
                kind="transcript",
                storage_uri=f"memory://multimedia/{asset_id}/{revision_id}/{transcript_file_id}.txt",
                sha256=transcript_hash,
                mime="text/plain",
                provider=result.provider,
                prompt_id=None,
                duration_seconds=result.duration_seconds,
            ),
        ])
        provider_calls.append(
            ProviderCall(
                call_id=call_id,
                provider=result.provider,
                model=result.model,
                route_policy=plan.request.route_policy,
                status="succeeded",
                input_units=len(text),
                output_units=len(result.audio_bytes),
                unit_type="tts_chars_to_audio_bytes",
                cost_usd=result.cost_usd,
            )
        )
        costs.append(
            CostRow(
                cost_id=f"cost-{call_id}",
                call_id=call_id,
                provider=result.provider,
                route_policy=plan.request.route_policy,
                cost_usd=result.cost_usd,
                billable_units=len(text),
                unit_type="tts_characters",
            )
        )
        source_chunk_ids = tuple(
            dict.fromkeys(chunk for p in chapter_paragraphs for chunk in p.source_chunk_ids)
        )
        paragraph_ids = tuple(p.paragraph_id for p in chapter_paragraphs)
        transcript_matches = result.transcript == text
        chapters.append(
            AudioChapter(
                chapter_id=chapter.chapter_id,
                title=chapter.title,
                start_seconds=cursor,
                duration_seconds=result.duration_seconds,
                audio_file_id=audio_file_id,
                transcript=result.transcript,
                source_chunk_ids=source_chunk_ids,
                paragraph_ids=paragraph_ids,
                recap_prompt=f"What should you remember from {chapter.title}?",
                transcript_matches_audio=transcript_matches,
                transcript_delta=None if transcript_matches else "provider transcript differed from normalized text",
            )
        )
        segments.append(
            MediaSegment(
                segment_id=f"audio-seg-{chapter.chapter_id}",
                sequence=index,
                title=chapter.title,
                media_kind="voiceover",
                script_line_ids=tuple(line_id for p in chapter_paragraphs for line_id in p.script_line_ids),
                file_ids=(audio_file_id, transcript_file_id),
                source_chunk_ids=source_chunk_ids,
                duration_seconds=result.duration_seconds,
            )
        )
        cursor = round(cursor + result.duration_seconds, 2)

    manifest = plan.to_manifest(asset_id=asset_id, revision_id=revision_id).model_copy(
        update={
            "files": tuple(generated_files),
            "provider_calls": tuple(provider_calls),
            "cost_rows": tuple(costs),
            "segments": tuple(segments),
            "transcript_file_id": generated_files[1].file_id if len(generated_files) > 1 else None,
        }
    )
    playback = AudioPlaybackModel(
        asset_id=asset_id,
        revision_id=revision_id,
        chapters=tuple(
            PlaybackChapter(
                chapter_id=chapter.chapter_id,
                title=chapter.title,
                start_seconds=chapter.start_seconds,
                duration_seconds=chapter.duration_seconds,
                source_cards=chapter.source_chunk_ids,
                steering_target=chapter.chapter_id,
            )
            for chapter in chapters
        ),
        total_duration_seconds=round(sum(chapter.duration_seconds for chapter in chapters), 2),
    )
    return AudioExperienceAsset(
        asset_id=asset_id,
        revision_id=revision_id,
        voice=voice,
        speed=speed,
        paragraphs=paragraphs,
        chapters=tuple(chapters),
        manifest=manifest,
        playback=playback,
    )


def _chapter_for_line(plan: MultimediaPlan) -> dict[str, str]:
    chapter_ids = {chapter.chapter_id for chapter in plan.chapters}
    mapping: dict[str, str] = {}
    for line in plan.script_lines:
        prefix = line.line_id.split("-line-", 1)[0]
        mapping[line.line_id] = prefix if prefix in chapter_ids else "intro"
    return mapping


def _speech_text(text: str) -> tuple[str, list[str]]:
    notes: list[str] = []
    spoken = text
    for source, replacement in _ABBREVIATIONS.items():
        if source in spoken:
            spoken = spoken.replace(source, replacement)
            notes.append(f"{source} -> {replacement}")
    spoken = re.sub(r"\s+", " ", spoken).strip()
    return spoken, notes


def _word_count(text: str) -> int:
    return len([w for w in re.split(r"\s+", text.strip()) if w])


__all__ = [
    "AudioChapter",
    "AudioExperienceAsset",
    "AudioPlaybackModel",
    "DEFAULT_AUDIO_SPEED",
    "DEFAULT_AUDIO_VOICE",
    "FakeTTSProvider",
    "NarrationParagraph",
    "NARRATION_WPM",
    "PlaybackChapter",
    "TTSProvider",
    "TTSRequest",
    "TTSResult",
    "assemble_audio_experience",
    "normalize_script_for_audio",
]
