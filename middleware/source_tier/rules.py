"""Source-tier ingestion classifier (Researchmaxx spec §C.1).

Deterministic mapping from document metadata to a tier 1–5 integer.
Pure functions — no LLM, no DB. The asymmetric design (rule-based
assignment; LLM may only adjust DOWNWARD via ``adjust_tier_after_extraction``)
is the architectural property called out in
``docs/architecture_notes.md`` §4 (preserved strengths).

Tier ranks (lower number = higher trust):

| Tier | Meaning |
|------|---------|
| 1    | primary, attributable, verifiable |
| 2    | peer-reviewed / patent / credentialed analyst |
| 3    | conference, white paper, vendor case study, trade press |
| 4    | general tech press, blog authored by named author, aggregator with attribution |
| 5    | anonymous / aggregator without attribution |

Migrated from ``~/.hermes/skills/research/graph-research-substrate/scripts/tier_rules.py``
(2026-05-16). The pure functions land here; the DB-touching
``update_all`` sweep is deferred to a separate turn once
``substrate/init_db.py`` migrates and the ``documents`` table is
available in Antiek.

The LLM-path of ``adjust_tier_after_extraction`` is preserved as a
TODO; the regex fallback path is fully migrated. When ``substrate/dispatch/``
integration with middleware is wired up, the LLM path will route
through ``dispatch(role="tier_assigner", ...)`` instead of calling
OpenRouter directly.
"""

from __future__ import annotations

import os
import re
import sys
from collections.abc import Mapping

# Package-relative imports with a direct-script fallback.
try:
    from ..._safe_typing import _no_op_marker  # type: ignore  # noqa
except Exception:  # pragma: no cover — placeholder while typing helpers don't exist
    pass

try:
    from ...event_log import emit_typed
    from ...schemas import TierAssignedPayload, TierOverriddenPayload, TierRewriteBulkPayload
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))  # project root
    from substrate.event_log import emit_typed  # type: ignore[no-redef]
    from substrate.schemas import (  # type: ignore[no-redef]
        TierAssignedPayload,
        TierOverriddenPayload,
        TierRewriteBulkPayload,
    )


# ---------------------------------------------------------------------------
# Deterministic catalogue — the spec §C.1 mapping, transcribed.
# ---------------------------------------------------------------------------

# Document type → tier. When the ingester sees a document_type that's not
# here it falls through to tier 5 — the conservative default. Better to
# misclassify high-quality content as low-trust than the reverse.
DOCUMENT_TYPE_TIER: dict[str, int] = {
    # ── Tier 1: primary, attributable, audited ──
    "expert_interview":                  1,
    "primary_expert_interview":          1,
    "sec_filing":                        1,
    "sec_filing_10k":                    1,
    "sec_filing_10q":                    1,
    "sec_filing_8k":                     1,
    "sec_filing_other":                  1,
    "audited_financial":                 1,
    "direct_correspondence":             1,
    "company_management_email":          1,
    "direct_management_correspondence":  1,

    # ── Tier 2: peer-reviewed / patent / credentialed analyst ──
    "peer_reviewed_paper":          2,
    "peer_reviewed_publication":    2,
    "preprint_with_doi":            2,
    "patent_uspto":                 2,
    "patent_filing":                2,
    "technical_datasheet":          2,
    "analyst_report_credentialed":  2,

    # ── Tier 3: conference, white paper, vendor case study, trade press ──
    "conference_presentation":  3,
    "white_paper":              3,
    "company_white_paper":      3,
    "vendor_case_study":        3,
    "trade_press":              3,
    "industry_report":          3,
    "research_synthesis":       3,

    # ── Tier 4: general tech press, blog with named author ──
    "general_tech_press":     4,
    "tech_press":             4,
    "blog_post":              4,
    "blog_authored":          4,
    "newsletter_authored":    4,
    "podcast_transcript":     4,
    "aggregator_attributed":  4,
    "youtube_transcript":     4,

    # ── Tier 5: anonymous / aggregator / unknown ──
    "anonymous":               5,
    "aggregator_unattributed": 5,
    "social_post":             5,
    "forum_post":              5,
    "unknown":                 5,
    "unknown_anonymous":       5,
}


# Backup keyword catalogues, used only when document_type is missing or
# unknown. These are the fallback heuristics that let ingestion still
# produce a defensible tier when the upstream pipeline did not classify
# the document explicitly.
_FALLBACK_KEYWORDS_PER_TIER: dict[int, list[str]] = {
    1: [
        "sec filing", "10-k", "10-q", "10k", "10q",
        "audited financial", "annual report (audited)",
        "expert interview", "primary interview",
        "direct management correspondence",
        "s-1", "s1 filing", "form 10",
    ],
    2: [
        "peer-reviewed", "peer reviewed", "doi:", "doi ",
        "journal article", "patent filing", "patent application",
        "technical datasheet", "datasheet",
        "credentialed analyst", "analyst report",
    ],
    3: [
        "conference presentation", "white paper", "whitepaper",
        "vendor case study", "case study", "trade press",
        "industry conference",
    ],
    4: [
        "tech press", "tech blog", "technical blog",
        "medium post", "substack", "general press",
    ],
    5: [
        "anonymous", "unknown author", "no provenance",
        "forum post", "reddit", "twitter", "social media",
    ],
}


def _safe_lower(val) -> str:
    if val is None:
        return ""
    return str(val).lower()


# ---------------------------------------------------------------------------
# Pure classifiers
# ---------------------------------------------------------------------------


def classify(document_type: str | None) -> int:
    """Return tier 1–5 for the given document_type. Unknown types default
    to 5. This is the fast deterministic path — when the ingester has a
    known ``document_type`` value, this function is the answer."""
    if not document_type:
        return 5
    return DOCUMENT_TYPE_TIER.get(document_type.strip().lower(), 5)


def assign_tier_at_ingestion(
    document_metadata: Mapping[str, object],
) -> tuple[int, str, list[str]]:
    """Document-tier assignment at ingestion time (spec §C.1).

    Primary path: look up ``document_type`` in the deterministic catalogue.
    Fallback: keyword-score across (source_uri, title, document_type,
    author, raw_text[:2000]) and pick the highest-scoring tier; ties
    resolve toward the *lower-trust* tier on purpose (conservative posture).

    Returns ``(tier, classification_method, keyword_matches)``:
        - ``tier`` ∈ [1, 5]. Default when nothing matches: 4.
        - ``classification_method`` ∈ {"document_type_lookup",
          "keyword_fallback", "default"}.
        - ``keyword_matches`` lists the keywords that triggered the
          fallback (empty when the primary path produced the answer).
    """
    dtype = _safe_lower(document_metadata.get("document_type"))
    if dtype:
        primary = DOCUMENT_TYPE_TIER.get(dtype)
        if primary is not None:
            return primary, "document_type_lookup", []

    haystack = " ".join(
        _safe_lower(document_metadata.get(k))
        for k in ("source_uri", "title", "document_type", "author", "raw_text")
    )
    if not haystack.strip():
        return 4, "default", []  # "we know nothing" → tech-press tier

    scores: dict[int, int] = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    matched: list[str] = []
    for tier, kws in _FALLBACK_KEYWORDS_PER_TIER.items():
        for kw in kws:
            if kw in haystack:
                scores[tier] += 1
                matched.append(kw)

    best_score = max(scores.values())
    if best_score == 0:
        return 4, "default", []
    # Tie break: prefer the higher tier number (more conservative).
    return max(t for t, s in scores.items() if s == best_score), "keyword_fallback", matched


# ---------------------------------------------------------------------------
# Hedging detection (spec §C.2 + C.3)
# ---------------------------------------------------------------------------


# Pattern, signal_type, adjustment-strength.
# adjustment-strength: 0 = nudge (informational), 1 = likely downgrade,
# 2 = strong downgrade signal.
HEDGING_PATTERNS: list[tuple[str, str, int]] = [
    (r"\bwe\s+hypothesize\b", "explicit_hypothesis", 1),
    (r"\bwe\s+speculate\b", "speculation", 1),
    (r"\bpreliminary\s+results?\s+suggest\b", "preliminary_results", 1),
    (r"\bearly\s+(stage|findings|data|indications?)\b", "early_stage", 1),
    (r"\blimited\s+sample\s+size\b", "limited_sample", 2),
    (r"\bsmall\s+(sample|dataset|cohort|study)\b", "small_sample", 1),
    (r"\bresults?\s+may\s+not\s+generalize\b", "not_generalizable", 1),
    (r"\banecdotal\s+evidence\b", "anecdotal", 2),
    (r"\bunconfirmed\s+report\b", "unconfirmed", 1),
    (r"\bsubject\s+to\s+change\b", "subject_to_change", 0),
    (r"\bforward[- ]looking\b", "forward_looking", 0),
    (r"\bestimated?\b", "estimate", 0),
    (r"\bprojected?\b", "projection", 0),
    (r"\bapproximately?\b|\broughly\b|\babout\b", "approximate", 0),
    (r"\bmay\b|\bmight\b|\bcould\b|\bpotentially\b", "tentative_language", 0),
    (r"\baccording\s+to\s+(unnamed|anonymous|sources?)\b", "anonymous_source", 2),
    (r"\bunverified\b", "unverified", 2),
    (r"\brumored?\b|\ballegedly\b", "rumor", 2),
    (r"\bto\s+be\s+confirmed\b", "tbc", 1),
    (r"\binitial\s+(results?|findings?|data)\b", "initial_findings", 0),
]


def _detect_hedging_signals(chunk_text: str) -> list[dict]:
    """Detect hedging signals via regex pattern matching (fast path).
    Returns one dict per distinct signal_type matched. Order matches
    the pattern catalogue."""
    chunk_lower = chunk_text.lower()
    signals: list[dict] = []
    seen_types = set()
    for pattern, signal_type, adjustment in HEDGING_PATTERNS:
        if signal_type in seen_types:
            continue
        if re.search(pattern, chunk_lower):
            signals.append({
                "type": signal_type,
                "adjustment_down": adjustment,
            })
            seen_types.add(signal_type)
    return signals


def adjust_tier_after_extraction(
    chunk_text: str,
    current_tier: int,
    *,
    llm_fallback: bool = False,  # DEFAULT CHANGED: regex-only until dispatch integration lands
) -> dict:
    """Adjust tier downward based on hedging language. The asymmetry is
    enforced here: ``adjusted_tier >= current_tier`` always.

    Returns:
        dict with keys ``original_tier``, ``adjusted_tier``, ``tier_changed``,
        ``reason``, ``hedging_signals``, ``adjustment_method``.

    LLM-fallback path: the Researchmaxx implementation called OpenRouter
    directly. In Antiek the LLM path will route through
    ``substrate.dispatch`` once the middleware ↔ dispatch wiring lands.
    Until then, ``llm_fallback=True`` raises NotImplementedError so callers
    fail loudly rather than silently degrading to regex.
    """
    if not isinstance(current_tier, int) or current_tier < 1 or current_tier > 5:
        raise ValueError(f"current_tier must be 1-5, got {current_tier!r}")

    signals = _detect_hedging_signals(chunk_text)

    if not signals:
        return {
            "original_tier": current_tier,
            "adjusted_tier": current_tier,
            "tier_changed": False,
            "reason": "No hedging signals detected.",
            "hedging_signals": [],
            "adjustment_method": "none",
        }

    if llm_fallback:
        raise NotImplementedError(
            "LLM-mediated tier adjustment will route through substrate.dispatch "
            "once middleware/source_tier ↔ dispatch wiring lands. Use "
            "llm_fallback=False for the regex path until then."
        )

    # Rule-based adjustment from regex signals.
    strong_count = sum(1 for s in signals if s["adjustment_down"] >= 2)
    moderate_count = sum(1 for s in signals if s["adjustment_down"] == 1)

    tier_reduction = strong_count + (moderate_count // 2)
    adjusted = min(5, current_tier + min(tier_reduction, 3))

    return {
        "original_tier": current_tier,
        "adjusted_tier": adjusted,
        "tier_changed": adjusted != current_tier,
        "reason": (
            f"Regex detected {len(signals)} hedging signals "
            f"({strong_count} strong, {moderate_count} moderate)"
        ),
        "hedging_signals": [s["type"] for s in signals],
        "adjustment_method": "regex",
    }


# ---------------------------------------------------------------------------
# Event emit helpers
# ---------------------------------------------------------------------------


def emit_tier_assigned(
    *,
    investigation_id: str,
    document_id: str,
    document_type: str | None,
    assigned_tier: int,
    classification_method: str,
    keyword_matches: list[str] | None = None,
    parent_event_id: str | None = None,
) -> str | None:
    """Emit a GRAPH_TIER_ASSIGNED event for one document. Returns event_id."""
    return emit_typed(
        investigation_id,
        TierAssignedPayload(
            document_id=document_id,
            document_type=document_type,
            assigned_tier=assigned_tier,
            classification_method=classification_method,  # type: ignore[arg-type]
            keyword_matches=keyword_matches or [],
        ),
        parent_event_id=parent_event_id,
        role="tier_assigner",
        document_id=document_id,
    )


def emit_tier_overridden(
    *,
    investigation_id: str,
    chunk_id: str,
    original_tier: int,
    adjusted_tier: int,
    adjustment_method: str,
    hedging_signals: list[str],
    reason: str,
    parent_event_id: str | None = None,
) -> str | None:
    """Emit a GRAPH_TIER_OVERRIDDEN event. The asymmetry invariant
    (adjusted_tier >= original_tier) is asserted here as a defense — the
    middleware's own check should already enforce it, but this is the
    last gate before the event hits the trajectory store."""
    if adjusted_tier < original_tier:
        raise ValueError(
            f"tier override violates asymmetry: adjusted ({adjusted_tier}) < "
            f"original ({original_tier}). LLM may only argue DOWN (higher number)."
        )
    return emit_typed(
        investigation_id,
        TierOverriddenPayload(
            chunk_id=chunk_id,
            original_tier=original_tier,
            adjusted_tier=adjusted_tier,
            adjustment_method=adjustment_method,  # type: ignore[arg-type]
            hedging_signals=hedging_signals,
            reason=reason,
        ),
        parent_event_id=parent_event_id,
        role="tier_assigner",
    )


def emit_tier_rewrite_bulk(
    *,
    investigation_id: str,  # by convention: substrate.constants.SYSTEM_INVESTIGATION_ID
    total: int,
    updated: int,
    unchanged: int,
    by_tier: dict[int, int],
    parent_event_id: str | None = None,
) -> str | None:
    """Emit a TIER_REWRITE_BULK event for a global reclassification sweep."""
    return emit_typed(
        investigation_id,
        TierRewriteBulkPayload(
            total=total,
            updated=updated,
            unchanged=unchanged,
            by_tier=by_tier,
        ),
        parent_event_id=parent_event_id,
        role="tier_assigner",
    )
