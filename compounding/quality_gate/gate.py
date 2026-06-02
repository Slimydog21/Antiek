"""Quality gate evaluator."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import UTC, datetime


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class QualityGateError(Exception):
    pass


class QualityGateReason(str, enum.Enum):
    """Why the gate rejected (or accepted). Each component contributes
    its own reason; the composite verdict lists all that fired."""

    VERIFICATION_PASSED = "verification_passed"
    VERIFICATION_FAILED = "verification_failed"
    VOICE_STYLE_PASSED = "voice_style_passed"
    VOICE_STYLE_FAILED = "voice_style_failed"
    SOURCE_TIER_OK = "source_tier_ok"
    SOURCE_TIER_TOO_LOW = "source_tier_too_low"


@dataclass(frozen=True)
class VerificationResult:
    """Rubric verifier's verdict on the content. Score in [0, 1];
    threshold per master-spec §13.9 is configurable but defaults to
    0.6 (medium quality)."""

    score: float
    threshold: float
    passed: bool
    notes: str = ""


@dataclass(frozen=True)
class VoiceStyleResult:
    """Deterministic voice-style metrics per master-spec §5.4."""

    em_dash_density_per_1k_chars: float
    padding_phrase_count: int
    sector_vocab_overlap: float
    passed: bool
    notes: str = ""


@dataclass(frozen=True)
class SourceTierResult:
    """Source-tier mix of the cited content. A submission citing
    only Tier-4/5 sources is routed to private graph (not eligible
    for the public-tier attribution flow)."""

    min_tier_cited: int  # 1=highest trust, 5=lowest
    pct_tier_1_or_2: float
    passed: bool
    notes: str = ""


@dataclass(frozen=True)
class PublicGraphAcceptanceVerdict:
    """Composite accept/reject verdict."""

    accepted: bool
    verification: VerificationResult
    voice_style: VoiceStyleResult
    source_tier: SourceTierResult
    reasons: tuple[QualityGateReason, ...]
    decided_at: str = field(default_factory=_now_iso)


@dataclass
class QualityGate:
    """Composable quality gate. Operator wires concrete check
    functions via the three injection points (rubric_verifier_fn,
    voice_style_checker_fn, source_tier_checker_fn) or accepts the
    defaults that come from substrate (compounding/verification/ +
    voice-style discipline + middleware/source_tier/)."""

    verification_threshold: float = 0.6
    voice_style_em_dash_max_per_1k: float = 4.0
    voice_style_padding_max: int = 0
    voice_style_sector_vocab_min: float = 0.30
    source_tier_min_tier1_pct: float = 0.20  # 20% must be Tier 1 or 2

    def evaluate(
        self,
        *,
        verification: VerificationResult,
        voice_style: VoiceStyleResult,
        source_tier: SourceTierResult,
    ) -> PublicGraphAcceptanceVerdict:
        """Combine the three component verdicts into a composite.
        Accept only if ALL THREE pass (AND-discipline) — per master-
        spec §13.9 the public graph quality must be high enough to
        sustain creator rev-share without becoming a content farm."""
        reasons: list[QualityGateReason] = []

        if verification.passed:
            reasons.append(QualityGateReason.VERIFICATION_PASSED)
        else:
            reasons.append(QualityGateReason.VERIFICATION_FAILED)

        if voice_style.passed:
            reasons.append(QualityGateReason.VOICE_STYLE_PASSED)
        else:
            reasons.append(QualityGateReason.VOICE_STYLE_FAILED)

        if source_tier.passed:
            reasons.append(QualityGateReason.SOURCE_TIER_OK)
        else:
            reasons.append(QualityGateReason.SOURCE_TIER_TOO_LOW)

        accepted = (
            verification.passed
            and voice_style.passed
            and source_tier.passed
        )

        return PublicGraphAcceptanceVerdict(
            accepted=accepted,
            verification=verification,
            voice_style=voice_style,
            source_tier=source_tier,
            reasons=tuple(reasons),
        )


def evaluate_notebook_for_public(
    *,
    text_content: str,
    cited_chunk_tiers: list[int],
    corpus_sector_terms: list[str],
    rubric_score: float,
    gate: QualityGate | None = None,
) -> PublicGraphAcceptanceVerdict:
    """End-to-end evaluation of a notebook for public-graph promotion.

    Args:
        text_content: aggregated text from the notebook's prose blocks
            and synthesizer outputs
        cited_chunk_tiers: list of source_tier values from cited chunks
        corpus_sector_terms: sector terms from the cited chunks (for
            voice-style overlap check)
        rubric_score: rubric verifier's score in [0, 1]
        gate: optional QualityGate (defaults to standard thresholds)
    """
    gate = gate or QualityGate()

    # Verification component
    verification = VerificationResult(
        score=rubric_score,
        threshold=gate.verification_threshold,
        passed=rubric_score >= gate.verification_threshold,
        notes=(
            f"rubric_score={rubric_score:.2f} vs "
            f"threshold={gate.verification_threshold:.2f}"
        ),
    )

    # Voice-style component (deterministic checks)
    em_dash_count = text_content.count("—")
    chars = max(1, len(text_content))
    em_dash_density = (em_dash_count / chars) * 1000
    padding_patterns = [
        "It is important to note",
        "It should be observed",
        "It can be argued",
        "It is worth noting",
        "Furthermore,",
        "Additionally,",
        "In conclusion,",
    ]
    padding_count = sum(
        text_content.count(p) for p in padding_patterns
    )
    if not corpus_sector_terms:
        sector_overlap = 1.0  # no terms to compare; pass
    else:
        text_lower = text_content.lower()
        sector_overlap = (
            sum(1 for t in corpus_sector_terms if t.lower() in text_lower)
            / len(corpus_sector_terms)
        )
    vs_passed = (
        em_dash_density <= gate.voice_style_em_dash_max_per_1k
        and padding_count <= gate.voice_style_padding_max
        and sector_overlap >= gate.voice_style_sector_vocab_min
    )
    voice_style = VoiceStyleResult(
        em_dash_density_per_1k_chars=em_dash_density,
        padding_phrase_count=padding_count,
        sector_vocab_overlap=sector_overlap,
        passed=vs_passed,
        notes=(
            f"em_dash/1k={em_dash_density:.2f} (cap {gate.voice_style_em_dash_max_per_1k}); "
            f"padding={padding_count} (cap {gate.voice_style_padding_max}); "
            f"sector_vocab={sector_overlap:.2f} (min {gate.voice_style_sector_vocab_min})"
        ),
    )

    # Source-tier component
    if not cited_chunk_tiers:
        # No citations at all → can't pass source-tier check.
        source_tier = SourceTierResult(
            min_tier_cited=5,
            pct_tier_1_or_2=0.0,
            passed=False,
            notes="no citations — public-graph contributions must cite sources",
        )
    else:
        min_tier = min(cited_chunk_tiers)
        pct_t1_or_2 = sum(1 for t in cited_chunk_tiers if t <= 2) / len(cited_chunk_tiers)
        st_passed = pct_t1_or_2 >= gate.source_tier_min_tier1_pct
        source_tier = SourceTierResult(
            min_tier_cited=min_tier,
            pct_tier_1_or_2=pct_t1_or_2,
            passed=st_passed,
            notes=(
                f"min_tier_cited={min_tier}; "
                f"pct_tier_1_or_2={pct_t1_or_2:.2f} (min {gate.source_tier_min_tier1_pct})"
            ),
        )

    return gate.evaluate(
        verification=verification,
        voice_style=voice_style,
        source_tier=source_tier,
    )
