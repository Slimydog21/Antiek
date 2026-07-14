from __future__ import annotations

import math

import pytest

from substrate.multimedia.verified_audio_playback import (
    AudioChapterPlaybackMetadata,
    VerifiedPlaybackError,
    validate_audio_chapters,
)


def _chapter(
    chapter_id: str = "chapter-1",
    *,
    sequence: int = 0,
    start: float = 0.0,
    end: float = 10.0,
) -> AudioChapterPlaybackMetadata:
    return AudioChapterPlaybackMetadata(chapter_id, "Exact title", sequence, start, end)


def test_audio_chapter_timeline_accepts_exact_contiguous_projection() -> None:
    chapters = (_chapter(end=4.25), _chapter("chapter-2", sequence=1, start=4.25))
    assert validate_audio_chapters(
        chapters, chapter_ids=("chapter-1", "chapter-2"), duration_seconds=10.0
    ) == chapters


@pytest.mark.parametrize(
    ("chapters", "chapter_ids", "duration"),
    [
        ((_chapter(start=0.1),), ("chapter-1",), 10.0),
        ((_chapter(end=4.0), _chapter("chapter-2", sequence=1, start=4.1)),
         ("chapter-1", "chapter-2"), 10.0),
        ((_chapter(end=4.0), _chapter("chapter-2", sequence=1, start=3.9)),
         ("chapter-1", "chapter-2"), 10.0),
        ((_chapter(sequence=1),), ("chapter-1",), 10.0),
        ((_chapter(),), ("chapter-2",), 10.0),
        ((_chapter(), _chapter()), ("chapter-1", "chapter-1"), 20.0),
        ((_chapter(end=9.998),), ("chapter-1",), 10.0),
        ((_chapter(end=math.inf),), ("chapter-1",), 10.0),
    ],
)
def test_audio_chapter_timeline_rejects_malformed_timing_order_and_ids(
    chapters: tuple[AudioChapterPlaybackMetadata, ...],
    chapter_ids: tuple[str, ...],
    duration: float,
) -> None:
    with pytest.raises(VerifiedPlaybackError, match="chapter"):
        validate_audio_chapters(chapters, chapter_ids=chapter_ids, duration_seconds=duration)
