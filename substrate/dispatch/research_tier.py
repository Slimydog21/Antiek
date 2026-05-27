"""Research-entry fast/deep tier → provider map (SPR-01 M3).

THE ONE PLACE the curated research-entry tier resolves to a concrete
(provider, model). Nothing else in the codebase may hardcode this
mapping — a surface that wants to know "what does 'deep' route to"
imports ``resolve_research_tier`` from here.

Scope discipline (§16 + master-spec §16.1 REJECT list):

  - This is a CLOSED two-value set ({fast, deep}) offered ONLY at the
    research entry (StartResearch). It is NOT a raw model dropdown, NOT
    a per-invocation picker on every surface, and NOT user-facing BYO-
    model / temperature optionality. Those are explicit OOS rejects.
  - It does NOT introduce a second runtime. Both providers below are
    OpenAI-compatible APIs the dispatch router already calls through the
    one ``OpenAICompatProvider`` adapter (mirror of the xAI/Hermes
    bridge). The selector chooses WHICH already-registered provider the
    deep work prefers; it never spins up a parallel dispatcher.
  - The chosen tier is recorded on the investigation's start event
    (``InvestigationStartRequestedPayload.research_tier``) so it is
    queryable after the fact (M3 acceptance).

Why a two-value tier at all (and not one always-deep default)?
  Steelman of the rejected single-default: one provider for every
  investigation is simpler — no map to rot, no UI control, no
  "which-tier-was-this" query. We reject it because the two providers
  have a real, operator-felt cost/latency gap at the research entry:
  MiMo V2.5 Pro (fast) is the cheap/low-latency lane for shallow or
  exploratory questions; DeepSeek V4 Pro (deep) is the
  reasoning-heavier lane for questions worth the spend. Collapsing them
  would either overpay on every shallow ask or underpower every deep
  one. The selector is the minimum optionality that buys a measurable
  difference — and it is a CLOSED set, so the map cannot sprawl. If, in
  practice, "fast" is never chosen / never matters, the right move is to
  DELETE the selector and default to deep — not to widen it. (See
  docs/decisions/dispatch-deepseek-mimo-wiring.md.)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Literal, Tuple


# The closed set. Adding a third value is a deliberate edit here, gated
# by the same scope discipline above — never an open-ended dropdown.
ResearchTier = Literal["fast", "deep"]

RESEARCH_TIERS: Tuple[ResearchTier, ...] = ("fast", "deep")

# Sensible default when the caller doesn't pick. "deep" is the default
# because a cold research question is the high-value case; the operator
# opts DOWN to fast for cheap/exploratory asks. (This matches the
# single-default steelman's instinct — deep is the safe baseline — while
# still letting fast be chosen when it demonstrably matters.)
DEFAULT_RESEARCH_TIER: ResearchTier = "deep"


@dataclass(frozen=True)
class ResearchTierTarget:
    """What a research tier resolves to. ``provider`` is a registered
    provider name (the router looks it up in its registry); ``model`` is
    the per-call model id passed to that provider's adapter. ``why`` is
    the one-line rationale carried here so the map and its justification
    can never drift apart."""

    tier: ResearchTier
    provider: str
    model: str
    why: str


# ── THE MAP ────────────────────────────────────────────────────────────
# tier → (provider, model). Each entry is commented WHY it maps where.
# These provider names MUST match the ones registered in
# providers/bootstrap.py (``xiaomi`` = MiMo, ``deepseek`` = DeepSeek).
# The model ids are the per-call argument the OpenAICompatProvider sends;
# they are NOT pinned in bootstrap (one endpoint serves several models).
_RESEARCH_TIER_MAP: Dict[ResearchTier, ResearchTierTarget] = {
    "fast": ResearchTierTarget(
        tier="fast",
        provider="xiaomi",  # MiMo endpoint registered in bootstrap.py
        model="mimo-v2.5-pro",
        # WHY: MiMo V2.5 Pro is the cheap, low-latency lane. Shallow or
        # exploratory research questions don't need V4-Pro reasoning; the
        # operator pays less and waits less. The substrate's quality moat
        # comes from VOLUME of dispatches over a compounding graph
        # (config.yaml architectural posture), so a faster cheaper model
        # on exploratory asks is strictly aligned with that thesis.
        why="MiMo V2.5 Pro — cheap/low-latency lane for shallow or "
        "exploratory research questions.",
    ),
    "deep": ResearchTierTarget(
        tier="deep",
        provider="deepseek",  # DeepSeek endpoint registered in bootstrap.py
        model="deepseek-v4-pro",
        # WHY: DeepSeek V4 Pro is the reasoning-heavier lane for questions
        # worth the spend. It is the DEFAULT (DEFAULT_RESEARCH_TIER) because
        # a cold research question is the high-value case. Both providers
        # speak the OpenAI shape behind the one Hermes-routed dispatch
        # path — choosing "deep" swaps the provider, not the runtime (§16).
        why="DeepSeek V4 Pro — reasoning-heavier lane for questions worth "
        "the deeper spend; the default for a cold research question.",
    ),
}


def normalize_research_tier(value: object) -> ResearchTier:
    """Coerce an arbitrary inbound value to a member of the closed set,
    falling back to the default for anything unrecognized.

    Honest-failure posture: an unknown / malformed tier does NOT raise
    and does NOT silently route to an arbitrary provider — it falls back
    to ``DEFAULT_RESEARCH_TIER`` (deep), which is always a registered,
    high-value target. The caller can detect the coercion by comparing
    the input to the result if it cares."""
    if isinstance(value, str) and value in _RESEARCH_TIER_MAP:
        return value  # type: ignore[return-value]
    return DEFAULT_RESEARCH_TIER


def resolve_research_tier(tier: object) -> ResearchTierTarget:
    """Resolve a research tier to its (provider, model) target.

    Accepts the closed-set strings; anything else is normalized to the
    default (see ``normalize_research_tier``). Returns the full
    ``ResearchTierTarget`` including the ``why`` rationale."""
    return _RESEARCH_TIER_MAP[normalize_research_tier(tier)]


__all__ = [
    "DEFAULT_RESEARCH_TIER",
    "RESEARCH_TIERS",
    "ResearchTier",
    "ResearchTierTarget",
    "normalize_research_tier",
    "resolve_research_tier",
]
