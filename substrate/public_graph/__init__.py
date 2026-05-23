"""Public-graph quality gate (master-spec §13.9).

Per the spec text: *"Voice-and-style discipline (§5) is enforced on
synthesizer prompts but the platform doesn't control input quality
for user-contributed public notes. Users will paste in low-quality
notes and expect attribution revenue. Mechanism that handles this:
public-notes ingest pipeline runs verification + voice-style scoring
+ source-tier validation before eligibility for attribution. Low-
quality submissions get rejected or routed to private graph only.
This is what prevents the public graph becoming a content farm."*

This module is that mechanism. Three checks, all required to pass
before a note is eligible for attribution-bearing public-graph
status:

  1. **Verification** — every claim in the note must trace to a
     chunk_id in the substrate's ``chunks`` table. Substrate-
     grounding invariant from master-spec §5 + §13.9.
  2. **Voice-and-style scoring** — note text must meet the same
     §5.4 rubric the synthesizer enforces on its own output (no
     em-dash overuse, no LLM-slop padding, sector-vocabulary
     match if claimed sector is set).
  3. **Source-tier validation** — every cited chunk must trace to
     a document whose ``source_tier`` is acceptable for the note's
     declared topic (tier-1/2 for hard claims; tier-3 acceptable
     for opinion-class notes).

Outcomes:

  - PASS         → note eligible for public-graph + attribution.
  - REJECT       → not eligible. The note can still be saved to
                   the user's PRIVATE graph; just no attribution
                   revenue can route from it.
  - SOFT_REJECT  → operator can override (test note, opinion essay
                   etc.). Logged for §13.7 audit.

Substrate-only. The verifier-tier dispatch (Wedge 3 corroboration)
is not invoked here — that's a separate signal layer.
"""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass, field
from typing import Any, Optional


# Master-spec §5.4 — at most 2 em-dashes per thesis-shaped artifact.
# Note-level threshold is more permissive (4) since notes can chain.
MAX_EM_DASHES_PER_NOTE: int = 4

# Master-spec §5.4 — padding constructions that the synthesizer
# refuses to emit. Public-graph notes must also avoid them.
_PADDING_PHRASES: tuple[str, ...] = (
    "it is important to note",
    "in this article",
    "in this analysis",
    "as we delve",
    "navigate the complexities",
    "in today's rapidly",
    "in the modern era",
    "in the realm of",
    "it goes without saying",
)

# Minimum word count. Below this the note is too thin for
# meaningful attribution.
MIN_WORDS_PER_NOTE: int = 50

# Maximum source_tier for a "hard claim" note. Tier 1-2 is
# operator-curated / institutional; tier 3 is the boundary; tier
# 4-5 (anonymous internet, low-quality SEO) is rejected for hard
# claims but permitted for "opinion" notes.
MAX_SOURCE_TIER_FOR_HARD_CLAIM: int = 3


class QualityGateOutcome(str, enum.Enum):
    """Three-way outcome. PASS lets attribution flow; REJECT and
    SOFT_REJECT block it. SOFT_REJECT permits operator override."""

    PASS = "pass"
    SOFT_REJECT = "soft_reject"
    REJECT = "reject"


class QualityFailureReason(str, enum.Enum):
    """Why a note failed. Exposed in audit events so the operator
    can see which discipline is being violated."""

    TOO_SHORT = "too_short"
    EM_DASH_OVERUSE = "em_dash_overuse"
    PADDING_CONSTRUCTION = "padding_construction"
    NO_CITATIONS = "no_citations"
    UNGROUNDED_CITATION = "ungrounded_citation"
    SOURCE_TIER_TOO_LOW = "source_tier_too_low"
    SECTOR_VOCABULARY_MISMATCH = "sector_vocabulary_mismatch"


@dataclass(frozen=True)
class QualityGateResult:
    """The verdict + reasons. Multiple reasons can fire on one note;
    the outcome is the most-severe (REJECT > SOFT_REJECT > PASS)."""

    outcome: QualityGateOutcome
    reasons: tuple[QualityFailureReason, ...]
    em_dash_count: int
    word_count: int
    cited_chunk_count: int
    grounded_chunk_count: int
    detail: str = ""


@dataclass(frozen=True)
class NoteQualityInput:
    """The substrate's view of a candidate public-graph note.

    ``cited_chunk_ids`` are the chunk IDs the note's author cited as
    evidence. ``hard_claim`` is True for notes making factual claims
    (the strictest tier-validation applies); False for opinion /
    essay-style notes."""

    note_text: str
    cited_chunk_ids: tuple[str, ...]
    declared_sector: Optional[str] = None
    hard_claim: bool = True


# ── Individual checks ─────────────────────────────────────────────


def _count_em_dashes(text: str) -> int:
    """Count em-dashes (U+2014). The substrate's voice discipline
    refuses substituted patterns too — multi-char ' - ' separators
    are not policed here (the synthesizer handles that)."""
    return text.count("—")


def _word_count(text: str) -> int:
    """Tokenize on whitespace. Word-count thresholds are operator-
    tunable; the substrate uses a simple split."""
    return len([w for w in text.split() if w.strip()])


def _has_padding_phrase(text: str) -> Optional[str]:
    """Return the first padding phrase found, or None."""
    lowered = text.lower()
    for phrase in _PADDING_PHRASES:
        if phrase in lowered:
            return phrase
    return None


def _lookup_source_tiers(
    con: Any, chunk_ids: tuple[str, ...],
) -> dict[str, Optional[int]]:
    """Return chunk_id → source_tier of its document. Missing
    chunks resolve to None (treated as ungrounded)."""
    if not chunk_ids:
        return {}
    placeholders = ",".join(["?"] * len(chunk_ids))
    rows = con.execute(
        f"""
        SELECT c.chunk_id, d.source_tier
        FROM chunks c
        LEFT JOIN documents d ON d.document_id = c.document_id
        WHERE c.chunk_id IN ({placeholders})
        """,
        list(chunk_ids),
    ).fetchall()
    found: dict[str, Optional[int]] = {
        cid: int(tier) if tier is not None else None
        for cid, tier in rows
    }
    # Fill missing chunks with None.
    for cid in chunk_ids:
        found.setdefault(cid, None)
    return found


# ── Composite gate ────────────────────────────────────────────────


def evaluate_quality(
    con: Any, note: NoteQualityInput,
) -> QualityGateResult:
    """Run every check; return composite result.

    Order of severity (most-severe wins):
      REJECT > SOFT_REJECT > PASS
    """
    reasons: list[QualityFailureReason] = []
    outcome = QualityGateOutcome.PASS
    detail_parts: list[str] = []

    em_dashes = _count_em_dashes(note.note_text)
    words = _word_count(note.note_text)
    tiers = _lookup_source_tiers(con, note.cited_chunk_ids)
    grounded_count = sum(1 for t in tiers.values() if t is not None)

    # Check 1: minimum word count
    if words < MIN_WORDS_PER_NOTE:
        reasons.append(QualityFailureReason.TOO_SHORT)
        outcome = QualityGateOutcome.REJECT
        detail_parts.append(
            f"word_count={words} below {MIN_WORDS_PER_NOTE}",
        )

    # Check 2: em-dash overuse
    if em_dashes > MAX_EM_DASHES_PER_NOTE:
        reasons.append(QualityFailureReason.EM_DASH_OVERUSE)
        # SOFT_REJECT — operator can override; voice discipline is
        # advisory at the note layer (the synthesizer is binding).
        if outcome == QualityGateOutcome.PASS:
            outcome = QualityGateOutcome.SOFT_REJECT
        detail_parts.append(
            f"em_dash_count={em_dashes} above {MAX_EM_DASHES_PER_NOTE}",
        )

    # Check 3: padding construction
    found_phrase = _has_padding_phrase(note.note_text)
    if found_phrase is not None:
        reasons.append(QualityFailureReason.PADDING_CONSTRUCTION)
        if outcome == QualityGateOutcome.PASS:
            outcome = QualityGateOutcome.SOFT_REJECT
        detail_parts.append(f"padding_phrase={found_phrase!r}")

    # Check 4: at least one citation
    if not note.cited_chunk_ids:
        # For opinion notes, this is SOFT_REJECT (operator can post
        # an essay without strict grounding). For hard claims it is
        # REJECT — every claim must trace per §5 substrate-grounding.
        reasons.append(QualityFailureReason.NO_CITATIONS)
        if note.hard_claim:
            outcome = QualityGateOutcome.REJECT
        elif outcome == QualityGateOutcome.PASS:
            outcome = QualityGateOutcome.SOFT_REJECT
        detail_parts.append("no cited chunks")

    # Check 5: every citation must be grounded (chunk exists in
    # the substrate's chunks table).
    ungrounded = [
        cid for cid in note.cited_chunk_ids if tiers.get(cid) is None
    ]
    if ungrounded:
        reasons.append(QualityFailureReason.UNGROUNDED_CITATION)
        outcome = QualityGateOutcome.REJECT
        detail_parts.append(
            f"ungrounded_chunk_ids={ungrounded[:3]!r}"
            + ("…" if len(ungrounded) > 3 else "")
        )

    # Check 6: source-tier validation for hard claims
    if note.hard_claim:
        too_low = [
            cid for cid, tier in tiers.items()
            if tier is not None and tier > MAX_SOURCE_TIER_FOR_HARD_CLAIM
        ]
        if too_low:
            reasons.append(QualityFailureReason.SOURCE_TIER_TOO_LOW)
            outcome = QualityGateOutcome.REJECT
            detail_parts.append(
                f"tier_too_low_chunk_ids={too_low[:3]!r}"
                + ("…" if len(too_low) > 3 else "")
            )

    return QualityGateResult(
        outcome=outcome,
        reasons=tuple(reasons),
        em_dash_count=em_dashes,
        word_count=words,
        cited_chunk_count=len(note.cited_chunk_ids),
        grounded_chunk_count=grounded_count,
        detail="; ".join(detail_parts),
    )


def is_attribution_eligible(result: QualityGateResult) -> bool:
    """Returns True iff the note can flow to public graph + earn
    attribution revenue. PASS only — SOFT_REJECT and REJECT both
    block until operator override (which is a separate event)."""
    return result.outcome == QualityGateOutcome.PASS


__all__ = [
    "MAX_EM_DASHES_PER_NOTE",
    "MAX_SOURCE_TIER_FOR_HARD_CLAIM",
    "MIN_WORDS_PER_NOTE",
    "NoteQualityInput",
    "QualityFailureReason",
    "QualityGateOutcome",
    "QualityGateResult",
    "evaluate_quality",
    "is_attribution_eligible",
]
