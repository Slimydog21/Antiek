"""Prime Agent dispatch provider.

Optional, env-gated text provider that routes one prompt through
``prime-agent -p`` via the bounded RLM backend.

Registration is intentionally import-time and opt-in only:
``ANTIEK_PRIME_AGENT_RLM_ENABLED=1`` must be set, otherwise the
provider stays out of the registry and cannot appear in default tiers
or fallback chains.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Mapping
from pathlib import Path

from orchestration.rlm.prime_agent_backend import (
    PrimeAgentRequest,
    PrimeAgentRLMBackend,
    PrimeAgentTerminalState,
    prime_agent_backend_from_environment,
)

try:
    from ..base import NormalizedUsage, ProviderError, RawProviderResponse
    from ..router import register_provider
except ImportError:  # pragma: no cover
    import sys

    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from dispatch.base import (  # type: ignore[no-redef, import-not-found]
        NormalizedUsage,
        ProviderError,
        RawProviderResponse,
    )
    from dispatch.router import register_provider  # type: ignore[no-redef, import-not-found]


_ENABLED_ENV = "ANTIEK_PRIME_AGENT_RLM_ENABLED"


class PrimeAgentProvider:
    """Dispatch ``Provider`` adapter backed by ``PrimeAgentRLMBackend``."""

    name = "prime_agent"

    def __init__(
        self,
        *,
        backend: PrimeAgentRLMBackend | None = None,
        environ: Mapping[str, str] | None = None,
        cwd: Path | str | None = None,
    ) -> None:
        values = os.environ if environ is None else environ
        self._backend = (
            backend
            if backend is not None
            else prime_agent_backend_from_environment(
                values,
                cwd=Path.cwd() if cwd is None else cwd,
            )
        )

    def call(
        self,
        *,
        model: str,
        prompt: str,
        max_tokens: int,
        temperature: float,
    ) -> RawProviderResponse:
        del max_tokens, temperature  # Prime backend contract is prompt-only.

        request_id = _request_id(model=model, prompt=prompt)
        outcome = self._backend.run(PrimeAgentRequest(
            prompt=prompt,
            workflow=f"dispatch:{self.name}:{model}",
            request_id=request_id,
        ))

        evidence = outcome.evidence
        if (
            outcome.receipt.state is PrimeAgentTerminalState.SUCCESS
            and evidence is not None
            and evidence.text.strip()
        ):
            return RawProviderResponse(
                text=evidence.text,
                raw_usage={},
                finish_reason="stop",
                latency_ms=outcome.receipt.duration_ms,
                request_id=request_id,
                extra={"prime_terminal_state": outcome.receipt.state.value},
            )

        state = outcome.receipt.state
        detail = outcome.receipt.detail or state.value
        retryable = state in {
            PrimeAgentTerminalState.TIMEOUT,
            PrimeAgentTerminalState.UNAVAILABLE,
        }
        raise ProviderError(
            f"{self.name}: {detail}",
            provider=self.name,
            model=model,
            latency_ms=outcome.receipt.duration_ms,
            retryable=retryable,
            request_id=request_id,
        )

    def normalize_usage(self, raw_usage: dict[str, object]) -> NormalizedUsage:
        del raw_usage
        return NormalizedUsage(input_tokens=0, output_tokens=0)


def _request_id(*, model: str, prompt: str) -> str:
    digest = hashlib.sha256(f"prime-agent\0{model}\0{prompt}".encode()).hexdigest()
    return f"prime-{digest[:24]}"


def _is_enabled(values: Mapping[str, str]) -> bool:
    return values.get(_ENABLED_ENV, "").strip() == "1"


def maybe_register_provider(
    *,
    environ: Mapping[str, str] | None = None,
    cwd: Path | str | None = None,
) -> PrimeAgentProvider | None:
    """Register and return the provider when Prime-Agent RLM mode is enabled."""
    values = os.environ if environ is None else environ
    if not _is_enabled(values):
        return None

    provider = PrimeAgentProvider(environ=values, cwd=cwd)
    register_provider(provider)
    return provider


REGISTERED_PROVIDER = maybe_register_provider()


__all__ = [
    "PrimeAgentProvider",
    "REGISTERED_PROVIDER",
    "maybe_register_provider",
]
