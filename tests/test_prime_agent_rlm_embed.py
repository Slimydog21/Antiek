from __future__ import annotations

import importlib
from dataclasses import dataclass

import pytest

from orchestration.rlm.prime_agent_backend import (
    PrimeAgentEvidence,
    PrimeAgentOutcome,
    PrimeAgentReceipt,
    PrimeAgentRequest,
    PrimeAgentTerminalState,
)
from substrate.dispatch.base import ProviderError
from substrate.dispatch.router import _PROVIDER_REGISTRY, get_provider, reset_provider_registry


@dataclass
class _BackendStub:
    state: PrimeAgentTerminalState
    text: str | None = None

    def __post_init__(self) -> None:
        self.requests: list[PrimeAgentRequest] = []

    def run(self, request: PrimeAgentRequest) -> PrimeAgentOutcome:
        self.requests.append(request)
        evidence = PrimeAgentEvidence(self.text) if self.text is not None else None
        return PrimeAgentOutcome(
            request=request,
            evidence=evidence,
            receipt=PrimeAgentReceipt(
                state=self.state,
                argv=("prime-agent", "-p"),
                exit_code=0,
                duration_ms=7,
                output_bytes=len((self.text or "").encode()),
                detail="stub",
            ),
        )


@pytest.fixture(autouse=True)
def _clean_registry() -> None:
    reset_provider_registry()
    yield
    reset_provider_registry()


def test_prime_provider_import_registration_is_gated_off_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ANTIEK_PRIME_AGENT_RLM_ENABLED", raising=False)
    module = importlib.import_module("substrate.dispatch.providers.prime_agent")
    module = importlib.reload(module)

    assert module.REGISTERED_PROVIDER is None
    assert "prime_agent" not in _PROVIDER_REGISTRY


def test_prime_provider_import_registration_is_enabled_with_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTIEK_PRIME_AGENT_RLM_ENABLED", "1")
    module = importlib.import_module("substrate.dispatch.providers.prime_agent")
    module = importlib.reload(module)

    assert module.REGISTERED_PROVIDER is not None
    assert "prime_agent" in _PROVIDER_REGISTRY
    provider = get_provider("prime_agent")
    assert provider is module.REGISTERED_PROVIDER
    assert provider.name == "prime_agent"


def test_prime_provider_call_uses_backend_success_path() -> None:
    module = importlib.import_module("substrate.dispatch.providers.prime_agent")
    backend = _BackendStub(PrimeAgentTerminalState.SUCCESS, "prime answer")
    provider = module.PrimeAgentProvider(backend=backend)

    raw = provider.call(
        model="ignored-model",
        prompt="What changed?",
        max_tokens=64,
        temperature=0.2,
    )

    assert raw.text == "prime answer"
    assert raw.finish_reason == "stop"
    assert raw.latency_ms == 7
    assert backend.requests[0].prompt == "What changed?"


def test_prime_provider_call_maps_failure_to_provider_error() -> None:
    module = importlib.import_module("substrate.dispatch.providers.prime_agent")
    backend = _BackendStub(PrimeAgentTerminalState.FAILED)
    provider = module.PrimeAgentProvider(backend=backend)

    with pytest.raises(ProviderError) as excinfo:
        provider.call(
            model="any",
            prompt="Q",
            max_tokens=32,
            temperature=0.0,
        )
    assert "prime_agent" in str(excinfo.value)
    assert excinfo.value.retryable is False
