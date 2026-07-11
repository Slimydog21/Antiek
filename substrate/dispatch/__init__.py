"""Multi-model LLM dispatch.

Single entry point: ``dispatch(prompt, role, ...)``. Routes by role to a
tier from ``config.yaml``, calls the chosen provider, emits a typed
``DispatchCall`` event, falls back on failure.

The Provider adapters live in ``providers/`` (Anthropic, OpenAI-compat,
etc.). The router never inspects provider-native shapes — each adapter
normalizes its own usage into ``NormalizedUsage`` (see ``base.py``).
"""

from .base import (
    IdempotentProvider,
    NormalizedUsage,
    Provider,
    ProviderCallNotAttempted,
    ProviderError,
    RawProviderResponse,
)
from .providers import AnthropicProvider, OpenAICompatProvider
from .research_tier import (
    DEFAULT_RESEARCH_TIER,
    RESEARCH_TIERS,
    ResearchTier,
    ResearchTierTarget,
    normalize_research_tier,
    resolve_research_tier,
)
from .router import (
    DispatchConfig,
    DispatchResult,
    TierConfig,
    TierPricing,
    dispatch,
    get_provider,
    normalize_finish_reason,
    register_provider,
    reset_provider_registry,
)

__all__ = [
    "Provider",
    "IdempotentProvider",
    "ProviderError",
    "ProviderCallNotAttempted",
    "RawProviderResponse",
    "NormalizedUsage",
    "DispatchConfig",
    "DispatchResult",
    "TierConfig",
    "TierPricing",
    "dispatch",
    "get_provider",
    "register_provider",
    "reset_provider_registry",
    "normalize_finish_reason",
    "AnthropicProvider",
    "OpenAICompatProvider",
    # SPR-01 M3 — the curated fast/deep research-tier map.
    "DEFAULT_RESEARCH_TIER",
    "RESEARCH_TIERS",
    "ResearchTier",
    "ResearchTierTarget",
    "normalize_research_tier",
    "resolve_research_tier",
]
