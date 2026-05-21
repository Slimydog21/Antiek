"""Quality gate for public-graph entry (master-spec §13.9, Sprint 19).

Per master-spec §13.9 verbatim:
'Voice-and-style discipline (§5) is enforced on synthesizer prompts
but the platform doesn't control input quality for user-contributed
public notes. Users will paste in low-quality notes and expect
attribution revenue. The mechanism that handles this: public-notes
ingest pipeline runs verification + voice-style scoring + source-
tier validation before eligibility for attribution. Low-quality
submissions get rejected or routed to private graph only.'

This module is the substrate-side quality gate. Three checks:
1. **Verification**: rubric scorer signs off (LLM-judged or human)
2. **Voice-style scoring**: deterministic checks from §5.4 (em-dash
   density, padding patterns, sector vocab overlap)
3. **Source-tier validation**: contributions citing only Tier-4/5
   sources are routed to private (not public-graph)

The gate composes a single accept/reject verdict + reasoning. The
Notebook.promote_to_public endpoint runs this before flipping
content_class to 'user_public_contribution'.
"""

from .gate import (
    PublicGraphAcceptanceVerdict,
    QualityGate,
    QualityGateError,
    QualityGateReason,
    SourceTierResult,
    VerificationResult,
    VoiceStyleResult,
    evaluate_notebook_for_public,
)

__all__ = [
    "PublicGraphAcceptanceVerdict",
    "QualityGate",
    "QualityGateError",
    "QualityGateReason",
    "SourceTierResult",
    "VerificationResult",
    "VoiceStyleResult",
    "evaluate_notebook_for_public",
]
