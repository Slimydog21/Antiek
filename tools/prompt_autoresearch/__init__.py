"""Prompt autoresearch — Karpathy's propose-execute-measure-gate loop
applied to Antiek role prompts (master-spec §14.1 Sprint 19 + Sprint
20 ratify-or-REJECT verdict; integration_autoresearch.md Wedge 1).

The mutation target is `roles/<role>/program.md` (operator-editable
instructions) and `roles/<role>/prompt.py` (role-internal prompt).
The runner replays existing golden traces from `tools/golden_traces/`
against the candidate prompt, scores the rubric, keeps or reverts.

**LOCAL-ONLY**: this scaffold raises if it detects production
environment markers. Per master-spec §14.2 parallel track discipline:
"prompt mutation experiments on operator's local machine, gated to
NEVER touch production VM until ratified."

The Sprint 20 verdict gate is the **Lutke gap test** (§15.6): does
the propose-execute-measure-gate mechanic survive the deterministic
→ LLM-judged metric transition? Lutke's Shopify result was on a
deterministic metric (render time). Antiek's metrics are LLM-judged.
No published evidence yet that the mechanic survives. Wedge 1
ratification IS the test.
"""

from .budget import BudgetCap, BudgetExceeded
from .runner import (
    PromptAutoresearchRunner,
    PromptMutation,
    PromptMutationOutcome,
)
from .score import (
    CompositeScore,
    composite_score,
    deterministic_voice_style_score,
    grounding_preserved_rate,
    sector_vocab_overlap,
)

__all__ = [
    "BudgetCap",
    "BudgetExceeded",
    "CompositeScore",
    "PromptAutoresearchRunner",
    "PromptMutation",
    "PromptMutationOutcome",
    "composite_score",
    "deterministic_voice_style_score",
    "grounding_preserved_rate",
    "sector_vocab_overlap",
]
