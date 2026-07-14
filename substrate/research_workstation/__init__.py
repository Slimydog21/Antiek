"""Research workstation pure-logic substrate (vision residual).

Operator vision clusters advanced here (no I/O, no live spend):

1. **Note twin** — every information asset has a twin document of insights +
   open questions (LLMs as recursive note-takers); twins can be merged and
   referenced.
2. **Research merge** — deep-research instances spun from highlights may be
   merged into the source asset, draft-merged (combined document without
   mutating source), or collective-merged (multi-sub-agent as one unit).
3. **Midnight oil** — timed autonomous research swarm: work duration + goals
   → recommended price ceiling (operator approves before spend).
4. **Model budget projection** — usage-vs-budget bar + proposed-prompt cost
   projection so a prompt cannot silently overshoot the operator's limit.

These modules are pure functions / frozen dataclasses. API routes and UI
wire them later; unit tests exercise the real shipped functions from their
start state. NotDiamond remains advisory and is NOT imported here (see
``.caffenagent`` / ``docs/decisions`` NotDiamond go/no-go for this cycle).
"""

from __future__ import annotations

from .midnight_oil import (
    DEFAULT_RATE_CARD,
    MidnightOilPlan,
    ModelRateCard,
    PriceCeilingRecommendation,
    build_midnight_oil_plan,
    recommend_price_ceiling,
)
from .model_budget import (
    BudgetLimit,
    CostProjection,
    UsageBar,
    project_prompt_cost,
    usage_bar,
    would_exceed_budget,
)
from .note_twin import (
    NoteTwin,
    TwinItem,
    build_note_twin,
    merge_twins,
    twin_to_html,
    twin_to_markdown,
)
from .research_merge import (
    MergedDocument,
    MergeMode,
    MergePlan,
    ResearchInstance,
    apply_merge_plan,
    plan_merge,
)

__all__ = [
    "TwinItem",
    "NoteTwin",
    "build_note_twin",
    "merge_twins",
    "twin_to_markdown",
    "twin_to_html",
    "ResearchInstance",
    "MergeMode",
    "MergePlan",
    "MergedDocument",
    "plan_merge",
    "apply_merge_plan",
    "ModelRateCard",
    "DEFAULT_RATE_CARD",
    "PriceCeilingRecommendation",
    "MidnightOilPlan",
    "recommend_price_ceiling",
    "build_midnight_oil_plan",
    "BudgetLimit",
    "CostProjection",
    "UsageBar",
    "project_prompt_cost",
    "usage_bar",
    "would_exceed_budget",
]
