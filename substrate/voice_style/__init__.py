"""§5.5 voice and style rubric — substrate-side scoring.

Per master-spec §5 (voice and style discipline) and §5.1 (slop
pattern to suppress):

- No LLM-slop patterns (bullet abuse, em-dash overuse, "key
  takeaways" enumeration where prose belongs, excessive hedging,
  generic transition phrases)
- Prose flows; insights stand alone; no forced bullets inside
  synthesis prose
- Voice and style discipline is synthesizer-level + extends to UI
  choices (§5.5)

Two surfaces:
- `score_voice_style(text) -> (score, violations)` — heuristic
  scorer for tests + a substrate baseline; production wires an LLM
  judge
- `AdSlot.shouldSuppress` predicate that the §5.5-discipline gate
  in the AdSlot React component consumes (see also
  `evaluate_inline_suppression`)

Substrate-side discipline: the scorer is pure-functional + offline.
It does NOT call an LLM. Production has an `LLMJudgeVoiceStyle`
variant that's a Protocol; tests stay with the heuristic.
"""

from .rubric import (
    Violation,
    ViolationKind,
    VoiceStyleScore,
    score_voice_style,
)
from .suppression import (
    SuppressionContext,
    SuppressionVerdict,
    evaluate_inline_suppression,
)

__all__ = [
    "SuppressionContext",
    "SuppressionVerdict",
    "Violation",
    "ViolationKind",
    "VoiceStyleScore",
    "evaluate_inline_suppression",
    "score_voice_style",
]
