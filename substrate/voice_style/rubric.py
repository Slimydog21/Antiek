"""Heuristic voice-and-style scorer.

Implements seven slop-pattern detectors per master-spec §5.1:

1. Bullet abuse — > 30% of non-empty lines are bullets
2. Em-dash overuse — > 1 em-dash per 100 words
3. "Key takeaways" / "let me explain" / "in this article" boilerplate
4. Excessive hedging ("perhaps", "arguably", "it could be argued")
5. Generic transition phrases ("moreover", "furthermore", "in conclusion")
6. Numbered-list-as-prose ("First, ... Second, ... Third, ...")
7. Trailing summary line that restates the opening

The score in [0, 1] is `1.0 - violation_penalty`. Each violation
deducts a fixed weight; total weight caps at 1.0. A clean prose
passage scores 1.0; a heavily-slopped one scores 0.0.
"""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass


class ViolationKind(str, enum.Enum):
    BULLET_ABUSE = "bullet_abuse"
    EM_DASH_OVERUSE = "em_dash_overuse"
    SLOP_BOILERPLATE = "slop_boilerplate"
    EXCESSIVE_HEDGING = "excessive_hedging"
    GENERIC_TRANSITIONS = "generic_transitions"
    NUMBERED_LIST_AS_PROSE = "numbered_list_as_prose"
    TRAILING_SUMMARY = "trailing_summary"


@dataclass(frozen=True)
class Violation:
    kind: ViolationKind
    detail: str
    weight: float  # penalty deducted from base score


@dataclass(frozen=True)
class VoiceStyleScore:
    score: float
    violations: tuple[Violation, ...]


# Penalty weights — tuned so any TWO strong violations or THREE weak
# ones drop the score below the default quality-gate threshold (0.70).
_WEIGHT_HEAVY = 0.20
_WEIGHT_MEDIUM = 0.12
_WEIGHT_LIGHT = 0.08


_BOILERPLATE_PATTERNS = (
    r"\bkey takeaways?\b",
    r"\blet me explain\b",
    r"\bin this (?:article|piece|essay|post)\b",
    r"\bin conclusion\b",
    r"\bas an (?:ai|llm|assistant)\b",
    r"\bcertainly[!\.]",
    r"\bi('|')d be happy to\b",
)


_HEDGE_WORDS = {
    "perhaps", "arguably", "potentially", "possibly",
    "it could be argued", "one might say", "to some extent",
    "in some sense", "it's worth noting", "it is worth noting",
    "it could be said",
}


_GENERIC_TRANSITIONS = {
    "moreover", "furthermore", "additionally",
    "in addition,", "on the other hand,", "in summary",
    "to summarize", "all in all", "all that said",
}


def _bullet_abuse(text: str) -> tuple[bool, str]:
    lines = [l for l in text.splitlines() if l.strip()]
    if len(lines) < 6:
        # Too few lines to make a bullet judgement.
        return (False, "")
    bullets = sum(
        1 for l in lines
        if l.lstrip().startswith(("- ", "* ", "• ")) or re.match(r"^\d+\.\s", l.lstrip())
    )
    share = bullets / len(lines)
    if share > 0.30:
        return (True, f"{share:.0%} of lines are bullet/numbered ({bullets}/{len(lines)})")
    return (False, "")


def _em_dash_overuse(text: str) -> tuple[bool, str]:
    em_dashes = text.count("—") + text.count("—")
    words = max(1, len(text.split()))
    per_100 = em_dashes / words * 100
    if per_100 > 1.0:
        return (True, f"{em_dashes} em-dashes in {words} words ({per_100:.1f}/100 words)")
    return (False, "")


def _slop_boilerplate(text: str) -> tuple[bool, str]:
    lower = text.lower()
    found = [p for p in _BOILERPLATE_PATTERNS if re.search(p, lower)]
    if found:
        return (True, f"matched {len(found)} boilerplate pattern(s): {found[:3]}")
    return (False, "")


def _excessive_hedging(text: str) -> tuple[bool, str]:
    lower = text.lower()
    matches: list[str] = []
    for hedge in _HEDGE_WORDS:
        if hedge in lower:
            matches.append(hedge)
    if len(matches) >= 3:
        return (True, f"{len(matches)} hedging tokens: {matches[:5]}")
    return (False, "")


def _generic_transitions(text: str) -> tuple[bool, str]:
    lower = text.lower()
    matches: list[str] = []
    for transition in _GENERIC_TRANSITIONS:
        if transition in lower:
            matches.append(transition)
    if matches:
        return (True, f"{len(matches)} generic transition(s): {matches[:5]}")
    return (False, "")


def _numbered_list_as_prose(text: str) -> tuple[bool, str]:
    # Sequence like "First, ... Second, ... Third, ..." within one paragraph.
    if re.search(r"\bfirst,?\b.*?\bsecond,?\b.*?\bthird,?\b", text.lower(), re.DOTALL):
        return (True, "First/Second/Third sequence inside prose")
    return (False, "")


def _trailing_summary(text: str) -> tuple[bool, str]:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if len(lines) < 4:
        return (False, "")
    first = lines[0].lower()
    last = lines[-1].lower()
    # Detect trailing-summary if last line shares ≥ 3 content words with first
    # AND last line starts with a summary cue.
    summary_cues = ("in summary", "to summarize", "in conclusion", "overall,", "in short,")
    if not any(last.startswith(cue) for cue in summary_cues):
        return (False, "")
    first_words = set(re.findall(r"\b[a-z]{4,}\b", first))
    last_words = set(re.findall(r"\b[a-z]{4,}\b", last))
    overlap = first_words & last_words
    if len(overlap) >= 3:
        return (True, f"trailing summary restates {len(overlap)} content words")
    return (False, "")


_DETECTORS: tuple[tuple[ViolationKind, callable, float], ...] = (  # type: ignore[type-arg]
    (ViolationKind.BULLET_ABUSE, _bullet_abuse, _WEIGHT_HEAVY),
    (ViolationKind.EM_DASH_OVERUSE, _em_dash_overuse, _WEIGHT_LIGHT),
    (ViolationKind.SLOP_BOILERPLATE, _slop_boilerplate, _WEIGHT_HEAVY),
    (ViolationKind.EXCESSIVE_HEDGING, _excessive_hedging, _WEIGHT_MEDIUM),
    (ViolationKind.GENERIC_TRANSITIONS, _generic_transitions, _WEIGHT_MEDIUM),
    (ViolationKind.NUMBERED_LIST_AS_PROSE, _numbered_list_as_prose, _WEIGHT_MEDIUM),
    (ViolationKind.TRAILING_SUMMARY, _trailing_summary, _WEIGHT_LIGHT),
)


def score_voice_style(text: str) -> tuple[float, list[str]]:
    """Score the prose against the §5.5 rubric.

    Returns `(score, violations)` where:
    - score is in [0, 1]; higher is better; 1.0 means no violations
    - violations is a list of human-readable detail strings

    The wrapper returns the simple shape callers expect (the
    quality_gate's `check_voice_style` consumes this directly).
    For the full Violation objects use the dataclass version below.
    """
    full = score_voice_style_detailed(text)
    return (full.score, [v.detail for v in full.violations])


def score_voice_style_detailed(text: str) -> VoiceStyleScore:
    violations: list[Violation] = []
    penalty = 0.0
    for kind, detector, weight in _DETECTORS:
        fired, detail = detector(text)
        if fired:
            violations.append(Violation(kind=kind, detail=detail, weight=weight))
            penalty += weight
    score = max(0.0, 1.0 - min(1.0, penalty))
    return VoiceStyleScore(score=score, violations=tuple(violations))
