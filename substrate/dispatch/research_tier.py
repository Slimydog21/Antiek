"""Research-entry fast/deep tier → provider map (SPR-01 M3).

THE ONE PLACE the curated research-entry tier resolves to a concrete
(provider, model). Nothing else in the codebase may hardcode this
mapping — a surface that wants to know "what does 'deep' route to"
imports ``resolve_research_tier`` from here.

Scope discipline (§16 + master-spec §16.1 REJECT list):

  - This is a CLOSED three-value set ({fast, deep, wrestle}) offered at
    research entry / launch budget projection. It is NOT a raw model
    dropdown, NOT open-ended BYO-model / temperature optionality.
    Residual (gp): ``wrestle`` records long-horizon depth (competitive
    OpenAI Deep Research posture) while reusing the thinking-enabled
    GLM lane — optionality with a measurable product meaning.
  - It does NOT introduce a second runtime. Both lanes below are
    OpenAI-compatible APIs the dispatch router already calls through the
    one ``OpenAICompatProvider`` adapter (z.ai, same endpoint, two
    thinking policies). The selector chooses WHICH already-registered
    provider the deep work prefers; it never spins up a parallel
    dispatcher.
  - The chosen tier is recorded on the investigation's start event
    (``InvestigationStartRequestedPayload.research_tier``) so it is
    queryable after the fact (M3 acceptance).

Why a two-value tier at all (and not one always-deep default)?
  Steelman of the rejected single-default: one provider for every
  investigation is simpler — no map to rot, no UI control, no
  "which-tier-was-this" query. We keep the two-value selector because
  BOTH lanes now run the platform's AI driver — GLM-5.2 (operator
  decision 2026-07-06: claude-less, GLM-5.2 for ALL parts) — and the
  real, operator-felt gap at the research entry is THINKING POLICY, not
  model family: ``fast`` runs GLM-5.2 with thinking DISABLED (the
  ``zai`` provider) for crystallized, cheap, low-latency extraction;
  ``deep`` runs GLM-5.2 with thinking ENABLED (the ``zai_reasoning``
  provider) for reasoning-heavy questions worth the latency. Collapsing
  them would either burn reasoning tokens on every shallow ask or
  starve every deep one. The cross-family backups (DeepSeek V4 Pro →
  MiMo V2.5 Pro) live in the config tier's fallback chain, NOT here —
  so this map names the GLM primary only and a single z.ai outage still
  falls through to a different family. The selector is the minimum
  optionality that buys a measurable difference — and it is a CLOSED
  set, so the map cannot sprawl. (See substrate/dispatch/config.yaml
  CLAUDE-LESS POSTURE for the GLM-primary directive.)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# The closed set. Expanding requires a deliberate edit here, gated by the
# same scope discipline above — never an open-ended dropdown.
ResearchTier = Literal["fast", "deep", "wrestle"]

RESEARCH_TIERS: tuple[ResearchTier, ...] = ("fast", "deep", "wrestle")

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
# providers/bootstrap.py: ``zai`` = GLM-5.2 thinking-DISABLED,
# ``zai_reasoning`` = GLM-5.2 thinking-ENABLED (both z.ai DIRECT API).
# The model id (``glm-5.2``) is the per-call argument the
# OpenAICompatProvider sends; it is NOT pinned in bootstrap (one endpoint
# serves the whole GLM family). DeepSeek V4 Pro + MiMo V2.5 Pro are the
# CROSS-FAMILY BACKUPS — they live in the config tier fallback chain, not
# here, so this map names the GLM primary only (operator directive: GLM-5.2
# is the driver for ALL parts; DeepSeek/MiMo are secondary).
_RESEARCH_TIER_MAP: dict[ResearchTier, ResearchTierTarget] = {
    "fast": ResearchTierTarget(
        tier="fast",
        provider="zai",  # GLM-5.2 thinking-DISABLED (z.ai DIRECT API)
        model="glm-5.2",
        # WHY: GLM-5.2 with thinking DISABLED is the cheap, low-latency
        # lane for shallow or exploratory research questions. Page-level
        # extraction / crystallized answers are the volume-thesis use case
        # the `zai` provider was built for (thinking off → direct content,
        # no reasoning overhead). The cross-family backups (DeepSeek V4 Pro
        # → MiMo V2.5 Pro) live in the config tier's fallback chain, NOT
        # here, so a single z.ai outage still falls through to a different
        # family. (Operator directive 2026-07-06: GLM-5.2 is the driver for
        # ALL parts; DeepSeek/MiMo are secondary.)
        why="GLM-5.2 (thinking disabled) — cheap/low-latency lane for "
        "shallow or exploratory research questions.",
    ),
    "deep": ResearchTierTarget(
        tier="deep",
        provider="zai_reasoning",  # GLM-5.2 thinking-ENABLED (z.ai DIRECT API)
        model="glm-5.2",
        # WHY: GLM-5.2 with thinking ENABLED is the reasoning-heavy lane for
        # questions worth the latency. It is the DEFAULT
        # (DEFAULT_RESEARCH_TIER) because a cold research question is the
        # high-value case where GLM's native chain-of-thought earns its
        # tokens. The only dispatch consumer of this map is the
        # research-runner lane (e.g. substrate/books/meta_reading.py); the
        # synthesizer keeps its own zai_reasoning config pin regardless
        # (interfaces/research/api/synthesizer.py:_research_tier_override
        # returns (None, None) for every tier — the §14.4 guard now enforcing
        # the PERMANENT claude-less synthesis pin). Choosing "deep" swaps
        # the thinking policy on the SAME model, not the runtime (§16).
        why="GLM-5.2 (thinking enabled) — reasoning-heavy lane for "
        "questions worth the deeper reasoning; the default for a cold "
        "research question.",
    ),
    # Residual (gp): long-horizon / multi-minute wrestle depth. Same thinking-
    # enabled GLM primary as deep (no second runtime); distinct tier value so
    # investigation start events + Antiek-bench task classes can differentiate
    # competitive "Deep Research" posture from ordinary deep asks.
    "wrestle": ResearchTierTarget(
        tier="wrestle",
        provider="zai_reasoning",  # GLM-5.2 thinking-ENABLED (z.ai DIRECT API)
        model="glm-5.2",
        why="GLM-5.2 (thinking enabled) — long-horizon wrestle lane for "
        "multi-minute synthesis (competitive Deep Research depth); "
        "same provider as deep, recorded as wrestle for queryability.",
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
