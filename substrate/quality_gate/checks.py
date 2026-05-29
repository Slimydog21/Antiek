"""Default check implementations for the §13.9 quality gate.

Each check is heuristic + cheap; production swaps in stronger
implementations behind the same Check protocol.

- check_verification — every claim has at least one evidence chunk
- check_voice_style — defers to substrate.voice_style; threshold-gated
- check_source_tier — every cited source is within accepted tier bounds
- check_extraction_quality — extracted text is real prose, not OCR garbage
  / near-empty (SPR-03 M6); reuses the corpus extraction heuristics rather
  than re-deriving thresholds
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


# Below this many distinct characters the text is a single repeated glyph
# ("aaaaaa…", "█████") — a degenerate OCR/extraction artifact, not prose. A
# real sentence draws on dozens of distinct characters; 5 is a generous floor
# (the smallest English word set still spans well past it) that only ever trips
# on a pathological single-/few-glyph husk.
_MIN_DISTINCT_CHARS = 5


def check_extraction_quality(note: CandidateNote) -> CheckResult:
    """Reject extracted document text that is OCR garbage or near-empty before
    it is ingested (SPR-03 M6).

    This is a QUALITY decision only — it never touches ``content_class`` /
    servability (a passing extraction is still gated unless SPR-02's license
    logic establishes a held license; passing quality is not a license grant).

    The heuristics are REUSED, not re-derived: ``acquisition.corpus_quality``
    already owns the calibrated real-word-ratio and OCR-garbage checks with
    their cited thresholds (``MIN_REAL_WORD_RATIO`` 0.60, ``MIN_TOKEN_COUNT``
    20, ``MIN_ALPHA_CHAR_RATIO`` 0.50, …). We run those against the note's
    extracted ``prose`` and add the explicit near-empty / single-repeated-glyph
    guard the gate needs at this layer. Importing locally (like
    ``check_voice_style``) keeps the module load-cycle-free; the corpus module
    is pure stdlib.
    """
    from acquisition.corpus_quality import (
        CheckResultKind as _CqKind,
        check_ocr_garbage,
        check_real_word_ratio,
    )

    text = note.prose or ""
    stripped = text.strip()

    # Near-empty guard — the cheapest, most decisive signal. An empty or
    # whitespace-only extraction is a failed extract, not a short document.
    if not stripped:
        return CheckResult(
            check_name="extraction_quality",
            kind=CheckResultKind.FAIL,
            score=0.0,
            reasons=("extracted text is empty / whitespace-only",),
        )

    # Single-repeated-glyph guard — "aaaa…" / "████" is a degenerate artifact
    # that the token-ratio checks can paradoxically pass (one long token).
    distinct = len(set(stripped.replace(" ", "")))
    if distinct < _MIN_DISTINCT_CHARS:
        return CheckResult(
            check_name="extraction_quality",
            kind=CheckResultKind.FAIL,
            score=0.0,
            reasons=(
                f"only {distinct} distinct character(s); need ≥ "
                f"{_MIN_DISTINCT_CHARS} — single-repeated-glyph extraction "
                "artifact, not prose",
            ),
        )

    rwr = check_real_word_ratio(text)
    ocr = check_ocr_garbage(text)
    failed = [c for c in (rwr, ocr) if c.kind is _CqKind.FAIL]
    if failed:
        reasons = tuple(r for c in failed for r in c.reasons)
        # score = the lowest sub-check score, the most pessimistic signal.
        return CheckResult(
            check_name="extraction_quality",
            kind=CheckResultKind.FAIL,
            score=min(c.score for c in failed),
            reasons=reasons,
        )
    return CheckResult(
        check_name="extraction_quality",
        kind=CheckResultKind.PASS,
        score=min(rwr.score, ocr.score),
        reasons=(
            f"real-word ratio {rwr.score:.2f}, OCR alpha-ratio {ocr.score:.2f} "
            "— extracted text is real prose",
        ),
    )
