"""Multimedia planning and generation substrate.

SPR-02 starts with the plan-before-render layer. Provider adapters live in
later sprints; importing this package must not require paid media credentials.
"""

from .planner import (
    ChapterPlan,
    CoverageSuggestion,
    EvidenceChunk,
    MultimediaPlan,
    MultimediaPlanRequest,
    StoryboardScene,
    build_multimedia_plan,
)

__all__ = [
    "ChapterPlan",
    "CoverageSuggestion",
    "EvidenceChunk",
    "MultimediaPlan",
    "MultimediaPlanRequest",
    "StoryboardScene",
    "build_multimedia_plan",
]
