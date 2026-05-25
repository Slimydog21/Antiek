"""DRW SPR-05 M5 — focus heuristics.

The operator's core insight: deep research benefits from *focus* — a narrow
sub-question yields a sharper, cheaper, more reliable result than a broad
one. So the planner must detect over-broad sub-questions and split them, and
an over-broad problem must produce a *deeper* tree, not three vague branches.

The focus check is a **real, measurable check, not a label the planner
self-applies** (rigor #1). It scores a question on conjunction-count,
multi-interrogative count, and length, and flags "three questions in a
trench coat". It is a heuristic, and it is honest about that: it catches
syntactic breadth well and is weak on *semantically* broad single questions
("what is the future of AI?") that are short and conjunction-free — those
are reported as a known blind spot rather than silently passed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Max sub-questions per node. Mirrors constants.SUB_QUESTIONS_MAX (8): beyond
# that a decomposition is performative breadth, not focus. Exceeding it
# SURFACES (the planner flags and caps) rather than silently truncating.
MAX_BRANCHES = 8

# A question with this many "and/or/plus/as well as" joins is doing the work
# of multiple questions.
_CONJUNCTIONS = re.compile(r"\b(and|or|plus|as well as|along with|versus|vs\.?)\b", re.I)
# Multiple interrogatives in one question ("what X and how Y") is a tell.
_INTERROGATIVES = re.compile(r"\b(what|how|why|when|where|who|which|whether)\b", re.I)

# Tunable thresholds (documented so the maintainer can reproduce a verdict).
_MAX_CONJUNCTIONS_FOCUSED = 1     # 2+ joins → over-broad
_MAX_INTERROGATIVES_FOCUSED = 2   # 3+ distinct interrogatives → over-broad
_MAX_WORDS_FOCUSED = 32           # very long questions tend to bundle asks


@dataclass(frozen=True)
class FocusVerdict:
    is_focused: bool
    reason: str
    conjunctions: int
    interrogatives: int
    words: int


def focus_check(question: str) -> FocusVerdict:
    conj = len(_CONJUNCTIONS.findall(question))
    interro = len(set(m.lower() for m in _INTERROGATIVES.findall(question)))
    words = len(question.split())
    reasons = []
    if conj > _MAX_CONJUNCTIONS_FOCUSED:
        reasons.append(f"{conj} conjunctions (>{_MAX_CONJUNCTIONS_FOCUSED})")
    if interro > _MAX_INTERROGATIVES_FOCUSED:
        reasons.append(f"{interro} distinct interrogatives (>{_MAX_INTERROGATIVES_FOCUSED})")
    if words > _MAX_WORDS_FOCUSED:
        reasons.append(f"{words} words (>{_MAX_WORDS_FOCUSED})")
    if reasons:
        return FocusVerdict(False, "over-broad: " + "; ".join(reasons), conj, interro, words)
    return FocusVerdict(True, "focused", conj, interro, words)


def is_over_broad(question: str) -> bool:
    return not focus_check(question).is_focused
