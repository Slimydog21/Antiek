"""Multimedia planning and generation substrate.

SPR-02 starts with the plan-before-render layer; SPR-03 adds the provider router;
SPR-04 adds chaptered audio assembly + a playback read-model;
SPR-05 adds the Ken Burns video documentary assembly (audio is timing truth). Provider adapters
that spend money stay operator-gated; importing this package must not require paid
media credentials (CI runs against the deterministic fake TTS).
"""

from .audio_assembly import (
    AudioExperience,
    ChapterAudio,
    assemble_audio_experience,
)
from .hardening import (
    GateFinding,
    GateResult,
    GateStatus,
    MultimediaHardeningReport,
    ShipStatus,
    evaluate_multimedia_asset,
)
from .live_worker import (
    preview_next_live_execution,
)
from .narration import (
    NarrationParagraph,
    normalize_line,
    normalize_script,
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
from .playback import (
    PlaybackChapter,
    PlaybackReadModel,
    RegenerationTarget,
    SourceCard,
    build_playback_read_model,
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
from .read_model import (
    CreateMultimediaDraftRequest,
    LiveProviderExecutionRequest,
    LiveProviderRoutePreview,
    MultimediaAssetList,
    MultimediaAssetRecord,
    MultimediaAssetStore,
    MultimediaAssetSummary,
    SteeringRequest,
)
from .steering import (
    RevisionPlan,
    SegmentReuse,
    SteeringIntent,
    SteeringOperation,
    SteeringTranscript,
    build_revision_asset,
    parse_steering_prompt,
    plan_revision,
)
from .tts import (
    FakeTTSProvider,
    TTSProvider,
    TTSRequest,
    TTSResult,
    make_tts_provider,
)
from .video import (
    CaptionCue,
    MotionPreset,
    TimelineEntry,
    VideoDocumentaryAsset,
    VideoRenderManifest,
    VideoScene,
    VisualGenerationPlan,
    VisualLabel,
    assemble_video_documentary,
    build_video_scenes,
    captions_from_timeline,
    compile_ken_burns_timeline,
    plan_visual_generation,
    simulate_documentary_render,
)

__all__ = [
    # SPR-02 planner
    "ChapterPlan",
    "CoverageSuggestion",
    "EvidenceChunk",
    "MultimediaPlan",
    "MultimediaPlanRequest",
    "StoryboardScene",
    "build_multimedia_plan",
    # SPR-03 provider router
    "BudgetExceeded",
    "KreaProviderAdapter",
    "MediaGenerationRequest",
    "ProviderExecutionRecord",
    "ProviderRoute",
    "ProviderUnavailable",
    "route_media_request",
    # SPR-04 narration + TTS + assembly + playback
    "NarrationParagraph",
    "normalize_line",
    "normalize_script",
    "FakeTTSProvider",
    "TTSProvider",
    "TTSRequest",
    "TTSResult",
    "make_tts_provider",
    "AudioExperience",
    "ChapterAudio",
    "assemble_audio_experience",
    "PlaybackChapter",
    "PlaybackReadModel",
    "RegenerationTarget",
    "SourceCard",
    "build_playback_read_model",
    # SPR-05 video documentary
    "CaptionCue",
    "MotionPreset",
    "TimelineEntry",
    "VideoDocumentaryAsset",
    "VideoRenderManifest",
    "VideoScene",
    "VisualGenerationPlan",
    "VisualLabel",
    "assemble_video_documentary",
    "build_video_scenes",
    "captions_from_timeline",
    "compile_ken_burns_timeline",
    "plan_visual_generation",
    "simulate_documentary_render",
    # SPR-07 steering + revisions
    "RevisionPlan",
    "SegmentReuse",
    "SteeringIntent",
    "SteeringOperation",
    "SteeringTranscript",
    "build_revision_asset",
    "parse_steering_prompt",
    "plan_revision",
    # SPR-08 evaluation + hardening
    "GateFinding",
    "GateResult",
    "LiveProviderExecutionRequest",
    "LiveProviderRoutePreview",
    "GateStatus",
    "MultimediaHardeningReport",
    "ShipStatus",
    "evaluate_multimedia_asset",
    # SPR-09 API persistence/read-model
    "CreateMultimediaDraftRequest",
    "MultimediaAssetList",
    "MultimediaAssetRecord",
    "MultimediaAssetStore",
    "MultimediaAssetSummary",
    "SteeringRequest",
    "preview_next_live_execution",
]
