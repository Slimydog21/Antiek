"""Default check implementations for the §13.9 quality gate.

Each check is heuristic + cheap; production swaps in stronger
implementations behind the same Check protocol.

- check_verification — every claim has at least one evidence chunk
- check_voice_style — defers to substrate.voice_style; threshold-gated
- check_source_tier — every cited source is within accepted tier bounds
"""

from __future__ import annotations

from dataclasses import dataclass

from .gate import CandidateNote, CheckResult, CheckResultKind


def check_verification(note: CandidateNote) -> CheckResult:
    """Every declared claim must have ≥ 1 evidence chunk citation.

    Notes with zero claims are also REJECTed by this check — a note
    without any structured claim is not what the §13.9 public-notes
    pipeline aims to accumulate.
    """
    reasons: list[str] = []
    if not note.claims:
        return CheckResult(
            check_name="verification",
            kind=CheckResultKind.FAIL,
            score=0.0,
            reasons=("note has zero claims",),
        )
    missing = [c for c in note.claims if not note.claim_evidence.get(c)]
    if missing:
        reasons.append(
            f"{len(missing)} claim(s) without evidence: "
            f"{sorted(missing)[:5]}{'...' if len(missing) > 5 else ''}"
        )
        return CheckResult(
            check_name="verification",
            kind=CheckResultKind.FAIL,
            score=1.0 - (len(missing) / len(note.claims)),
            reasons=tuple(reasons),
        )
    return CheckResult(
        check_name="verification",
        kind=CheckResultKind.PASS,
        score=1.0,
        reasons=("every claim has evidence",),
    )


@dataclass(frozen=True)
class SourceTierBounds:
    """Accepted-tier bounds for the source-tier check."""

    min_acceptable: int = 1
    max_acceptable: int = 3  # Tier 4-5 reroutes to private


def check_source_tier(
    note: CandidateNote,
    *,
    bounds: SourceTierBounds = SourceTierBounds(),
) -> CheckResult:
    """Every cited source must be in [bounds.min_acceptable,
    bounds.max_acceptable]. Tier 4-5 sources are blog-tier and below;
    they're OK in the user's private graph but not the collective
    one.
    """
    if not note.cited_source_tiers:
        # No cited sources at all — degenerate case; treat as PASS
        # (verification check handles whether claims need sources).
        return CheckResult(
            check_name="source_tier",
            kind=CheckResultKind.PASS,
            score=1.0,
            reasons=("no cited sources",),
        )
    out_of_range = [
        t for t in note.cited_source_tiers
        if t < bounds.min_acceptable or t > bounds.max_acceptable
    ]
    if out_of_range:
        return CheckResult(
            check_name="source_tier",
            kind=CheckResultKind.FAIL,
            score=1.0 - (len(out_of_range) / len(note.cited_source_tiers)),
            reasons=(
                f"{len(out_of_range)} source(s) outside tier range "
                f"[{bounds.min_acceptable}, {bounds.max_acceptable}]: "
                f"{sorted(out_of_range)}",
            ),
        )
    return CheckResult(
        check_name="source_tier",
        kind=CheckResultKind.PASS,
        score=1.0,
        reasons=("all cited sources within accepted tier range",),
    )


def check_voice_style(
    note: CandidateNote,
    *,
    threshold: float = 0.70,
) -> CheckResult:
    """Score the note's prose against the §5.5 voice rubric.

    Defers to `substrate.voice_style.score_voice_style`. Threshold
    is operator-tunable; default 0.70 is calibrated against the
    rubric's heuristic baseline."""
    # Local import keeps voice_style optional (the quality_gate
    # composes optional checks; callers can omit voice_style_check).
    from substrate.voice_style import score_voice_style

    score, violations = score_voice_style(note.prose)
    if score >= threshold:
        return CheckResult(
            check_name="voice_style",
            kind=CheckResultKind.PASS,
            score=score,
            reasons=(f"voice-style score={score:.2f} ≥ threshold={threshold:.2f}",),
        )
    return CheckResult(
        check_name="voice_style",
        kind=CheckResultKind.FAIL,
        score=score,
        reasons=tuple([
            f"voice-style score={score:.2f} below threshold={threshold:.2f}",
            *(f"violation: {v}" for v in violations[:5]),
        ]),
    )
