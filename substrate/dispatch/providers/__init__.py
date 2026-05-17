"""Concrete Provider adapters.

Each module here implements the ``Provider`` protocol from
``substrate/dispatch/base.py``. The router never imports these directly;
adapters self-register via ``register_provider`` when instantiated.

Currently shipped:

- ``anthropic`` — Claude family via api.anthropic.com.
- ``openai_compat`` — generic OpenAI-shaped chat-completions API.
  Configurable base URL covers DeepSeek, MiMo, Prime, OpenRouter,
  and OpenAI itself.

The mock providers in ``tests/test_dispatch.py`` are the shape contract
these adapters MUST satisfy on real responses. If a real provider's
response shape drifts from what the mocks encode, the unit tests against
the real adapter — using ``httpx.MockTransport`` — will catch it without
needing live API calls.
"""

from .anthropic import AnthropicProvider
from .bootstrap import register_default_providers
from .openai_compat import OpenAICompatProvider

__all__ = [
    "AnthropicProvider",
    "OpenAICompatProvider",
    "register_default_providers",
]
