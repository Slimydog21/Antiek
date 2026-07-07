"""Multimedia planning and generation substrate.

SPR-02 starts with the plan-before-render layer. Provider adapters live in
later sprints; importing this package must not require paid media credentials.
"""

from .audio import (
    AudioExperienceAsset,
    AudioPlaybackModel,
    FakeTTSProvider,
    NarrationParagraph,
    assemble_audio_experience,
    normalize_script_for_audio,
)
from .planner import (
    ChapterPlan,
    CoverageSuggestion,
    EvidenceChunk,
    MultimediaPlan,
    MultimediaPlanRequest,
    StoryboardScene,
    build_multimedia_plan,
)
from .provider_router import (
    BudgetExceeded,
    KreaProviderAdapter,
    MediaGenerationRequest,
    ProviderExecutionRecord,
    ProviderRoute,
    ProviderUnavailable,
    route_media_request,
)

__all__ = [
    "ChapterPlan",
    "CoverageSuggestion",
    "EvidenceChunk",
    "AudioExperienceAsset",
    "AudioPlaybackModel",
    "FakeTTSProvider",
    "MultimediaPlan",
    "MultimediaPlanRequest",
    "NarrationParagraph",
    "StoryboardScene",
    "BudgetExceeded",
    "KreaProviderAdapter",
    "MediaGenerationRequest",
    "ProviderExecutionRecord",
    "ProviderRoute",
    "ProviderUnavailable",
    "assemble_audio_experience",
    "build_multimedia_plan",
    "normalize_script_for_audio",
    "route_media_request",
]
