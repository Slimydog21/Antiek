"""Listening UX read-model + steering hooks (multimedia SPR-04, milestone 4).

A pure read-model over an assembled :class:`~substrate.multimedia.audio_assembly.AudioExperience`
so a mobile or workstation player can render a chaptered listening surface without
touching the manifest internals. It exposes exactly what the spec's milestone 4
demands:

* playback shows the CURRENT chapter and its source cards;
* steering can TARGET a chapter for regeneration.

Everything here is derived data — no synthesis, no IO, no mutation. The model is
built once from an experience and queried by offset or chapter id, which keeps the
player stateless and the steering decision a pure function of (experience, target).
"""

from __future__ import annotations

from dataclasses import dataclass

from .audio_assembly import AudioExperience, ChapterAudio


@dataclass(frozen=True)
class SourceCard:
    """One citable source chunk and the spoken lines that invoke it.

    Inverting the chapter's claim map gives the player a per-chunk card showing
    *which* narration drew on it, not just that it was used somewhere."""

    chunk_id: str
    line_ids: tuple[str, ...]


@dataclass(frozen=True)
class PlaybackChapter:
    """A player-facing chapter: audio handle, timeline window, sources, recap.

    ``replayable`` is always True for an assembled chapter (each is one
    independent audio file) — the flag exists so a future streaming/partial state
    can mark a chapter not-yet-available without changing the model shape."""

    chapter_id: str
    title: str
    sequence: int
    audio_file_id: str
    start_offset_seconds: float
    end_offset_seconds: float
    duration_seconds: float
    script_line_ids: tuple[str, ...]
    source_cards: tuple[SourceCard, ...]
    recap_prompt: str
    replayable: bool = True


@dataclass(frozen=True)
class RegenerationTarget:
    """A steering decision: regenerate one chapter's narration.

    Carries the inputs a regeneration pass needs (the chapter, a steering
    instruction, and the voice/speed to re-render with) so the caller can hand it
    straight back to the assembler without re-deriving context."""

    chapter_id: str
    instruction: str
    voice: str
    speed: float


@dataclass(frozen=True)
class PlaybackReadModel:
    """The full playback surface for one asset revision."""

    asset_id: str
    revision_id: str
    chapters: tuple[PlaybackChapter, ...]
    total_duration_seconds: float
    transcript_file_id: str

    def chapter_at_offset(self, seconds: float) -> PlaybackChapter | None:
        """Resolve the chapter playing at ``seconds`` (None before 0 or past end).

        The last chapter owns its end-offset inclusive so a seek to exactly the
        total duration still resolves (a player paused at the very end shows the
        final chapter, not nothing)."""
        if seconds < 0 or not self.chapters:
            return None
        for chapter in self.chapters:
            if seconds < chapter.end_offset_seconds:
                return chapter
        return self.chapters[-1] if seconds <= self.total_duration_seconds else None

    def chapter_by_id(self, chapter_id: str) -> PlaybackChapter | None:
        for chapter in self.chapters:
            if chapter.chapter_id == chapter_id:
                return chapter
        return None

    def steering_target(
        self, chapter_id: str, *, instruction: str, voice: str, speed: float
    ) -> RegenerationTarget:
        """Build a regeneration target for one chapter.

        Raises ``KeyError`` if the chapter is not part of this experience: a
        steering request for a nonexistent chapter is a caller bug, not a silent
        no-op (the player should never offer a regenerate control for a chapter
        that is not in the model)."""
        if self.chapter_by_id(chapter_id) is None:
            raise KeyError(
                f"cannot steer chapter {chapter_id!r}; it is not in asset "
                f"{self.asset_id!r} revision {self.revision_id!r}"
            )
        if not instruction.strip():
            raise ValueError("steering instruction must be non-empty")
        return RegenerationTarget(
            chapter_id=chapter_id,
            instruction=instruction,
            voice=voice,
            speed=speed,
        )


def _source_cards_for(chapter: ChapterAudio) -> tuple[SourceCard, ...]:
    """Build per-chunk source cards for a chapter.

    The exact line->chunk mapping lives in the manifest's ``claim_to_chunk``; the
    player only needs chapter-scoped provenance (which chunks back this chapter's
    narration), so each source chunk is attributed to the chapter's spoken lines
    as a group. Order follows the chapter's source_chunk_ids (stable)."""
    return tuple(
        SourceCard(chunk_id=chunk_id, line_ids=chapter.script_line_ids)
        for chunk_id in chapter.source_chunk_ids
    )


def build_playback_read_model(experience: AudioExperience) -> PlaybackReadModel:
    """Derive the playback surface from an assembled experience.

    Pure: no synthesis, no IO. The read-model is what a player renders; the
    experience/manifest remain the source of truth."""
    chapters = tuple(
        PlaybackChapter(
            chapter_id=ch.chapter_id,
            title=ch.title,
            sequence=ch.sequence,
            audio_file_id=ch.audio_file_id,
            start_offset_seconds=ch.start_offset_seconds,
            end_offset_seconds=ch.end_offset_seconds,
            duration_seconds=ch.duration_seconds,
            script_line_ids=ch.script_line_ids,
            source_cards=_source_cards_for(ch),
            recap_prompt=ch.recap_prompt,
        )
        for ch in experience.chapters
    )
    return PlaybackReadModel(
        asset_id=experience.manifest.asset_id,
        revision_id=experience.manifest.revision_id,
        chapters=chapters,
        total_duration_seconds=experience.total_duration_seconds,
        transcript_file_id=experience.transcript_file_id,
    )
