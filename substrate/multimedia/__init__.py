"""Multimedia planning and generation substrate.

SPR-02 starts with the plan-before-render layer; SPR-03 adds the provider router;
SPR-04 adds chaptered audio assembly + a playback read-model. Provider adapters
that spend money stay operator-gated; importing this package must not require paid
media credentials (CI runs against the deterministic fake TTS).
"""

from .audio import (
    AudioExperienceAsset,
    AudioPlaybackModel,
    normalize_script_for_audio,
)
from .audio_assembly import (
    AudioExperience,
    ChapterAudio,
    assemble_audio_experience,
)
from .hardening import (
    GateFinding,
    GateResult,
    MultimediaHardeningReport,
    evaluate_multimedia_asset,
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
    ExecutionMode,
    LiveProviderExecutionRequest,
    MultimediaAssetList,
    MultimediaAssetRecord,
    MultimediaAssetStore,
    MultimediaAssetSummary,
    MultimediaJobList,
    MultimediaJobRecord,
    ProviderArtifactAttachmentRequest,
    ProviderExecutionWorkerRequest,
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
    VideoDocumentaryAsset,
    VideoScene,
    assemble_video_documentary,
    build_video_scenes,
    compile_ken_burns_timeline,
)

__all__ = [
    # SPR-02 planner
    "ChapterPlan",
    "CoverageSuggestion",
    "EvidenceChunk",
    "AudioExperienceAsset",
    "AudioPlaybackModel",
    "CreateMultimediaDraftRequest",
    "ExecutionMode",
    "FakeTTSProvider",
    "GateFinding",
    "GateResult",
    "LiveProviderExecutionRequest",
    "MultimediaPlan",
    "MultimediaHardeningReport",
    "MultimediaAssetList",
    "MultimediaAssetRecord",
    "MultimediaAssetStore",
    "MultimediaAssetSummary",
    "MultimediaJobList",
    "MultimediaJobRecord",
    "ProviderArtifactAttachmentRequest",
    "ProviderExecutionWorkerRequest",
    "MultimediaPlanRequest",
    "NarrationParagraph",
    "StoryboardScene",
    "build_multimedia_plan",
    # SPR-03 provider router
    "BudgetExceeded",
    "KreaProviderAdapter",
    "MediaGenerationRequest",
    "ProviderExecutionRecord",
    "ProviderRoute",
    "ProviderUnavailable",
    "RevisionPlan",
    "SegmentReuse",
    "SteeringIntent",
    "SteeringOperation",
    "SteeringRequest",
    "SteeringTranscript",
    "VideoDocumentaryAsset",
    "VideoScene",
    "assemble_video_documentary",
    "build_video_scenes",
    "build_revision_asset",
    "compile_ken_burns_timeline",
    "evaluate_multimedia_asset",
    "parse_steering_prompt",
    "plan_revision",
    "route_media_request",
    # SPR-04 narration + TTS + assembly + playback
    "NarrationParagraph",
    "normalize_line",
    "normalize_script",
    "normalize_script_for_audio",
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
]
