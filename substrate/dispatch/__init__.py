"""Multi-model LLM dispatch.

Single entry point: ``dispatch(prompt, role, ...)``. Routes by role to a
tier from ``config.yaml``, calls the chosen provider, emits a typed
``DispatchCall`` event, falls back on failure.

The Provider adapters live in ``providers/`` (Anthropic, OpenAI-compat,
etc.). The router never inspects provider-native shapes — each adapter
normalizes its own usage into ``NormalizedUsage`` (see ``base.py``).
"""

from .base import (
    NormalizedUsage,
    Provider,
    ProviderError,
    RawProviderResponse,
)
from .providers import AnthropicProvider, OpenAICompatProvider
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
    "ProviderError",
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
]
