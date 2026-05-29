"""§13.9 quality gate — public-notes ingest pipeline.

Per master-spec §13.9: *"public-notes ingest pipeline runs
verification + voice-style scoring + source-tier validation before
eligibility for attribution. Low-quality submissions get rejected
or routed to private graph only. This is the mechanism that
prevents the public graph becoming a content farm."*

The gate is the substrate-side mechanism that gates Sprint 22 Phase
3 ("collective graph aggregation"). A user's public-facing note
enters the collective graph ONLY when this gate returns PASS.

Three checks compose the gate:
1. Verification — every claim in the note has at least one
   evidence chunk citation
2. Voice-style — the prose passes the §5.5 voice rubric above a
   configurable threshold
3. Source-tier — every cited source is within the accepted tier
   range (Tier 1-3 acceptable; Tier 4-5 routed to private only)

Pluggable: each check is a `Callable[[CandidateNote], CheckResult]`
so callers can swap implementations (e.g., LLM judge for voice-style
in production vs heuristic in tests).
"""

from .gate import (
    CandidateNote,
    CheckResult,
    CheckResultKind,
    QualityGateResult,
    QualityGateVerdict,
    run_quality_gate,
)
from .checks import (
    SourceTierBounds,
    check_extraction_quality,
    check_verification,
    check_voice_style,
    check_source_tier,
)

__all__ = [
    "CandidateNote",
    "CheckResult",
    "CheckResultKind",
    "QualityGateResult",
    "QualityGateVerdict",
    "SourceTierBounds",
    "check_extraction_quality",
    "check_source_tier",
    "check_verification",
    "check_voice_style",
    "run_quality_gate",
]
