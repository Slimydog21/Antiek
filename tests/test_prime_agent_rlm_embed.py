from __future__ import annotations

import importlib
import json
from dataclasses import dataclass
from decimal import Decimal

import pytest

from interfaces.research.rlm_repl import RLMAgent, make_llm_query
from orchestration.rlm.prime_agent_backend import (
    PrimeAgentEvidence,
    PrimeAgentOutcome,
    PrimeAgentReceipt,
    PrimeAgentRequest,
    PrimeAgentSessionRequest,
    PrimeAgentTerminalState,
)
from orchestration.rlm.rlm_investigation import (
    RLMInvestigationConfig,
    RLMIterationOutcome,
    run_rlm_investigation,
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


class _SessionBackendStub:
    def __init__(
        self,
        *,
        session_payloads: list[str],
        final_state: PrimeAgentTerminalState = PrimeAgentTerminalState.FAILED,
        final_text: str | None = None,
    ) -> None:
        self._session_payloads = list(session_payloads)
        self._final_state = final_state
        self._final_text = final_text
        self.session_requests: list[PrimeAgentSessionRequest] = []
        self.run_requests: list[PrimeAgentRequest] = []

    def run_session(self, request: PrimeAgentSessionRequest) -> PrimeAgentOutcome:
        self.session_requests.append(request)
        index = len(self.session_requests) - 1
        payload = self._session_payloads[min(index, len(self._session_payloads) - 1)]
        canonical = PrimeAgentRequest(
            prompt=request.iteration_prompt,
            workflow=request.workflow,
            request_id=request.request_id,
        )
        return PrimeAgentOutcome(
            request=canonical,
            evidence=PrimeAgentEvidence(payload, source="prime-agent-session"),
            receipt=PrimeAgentReceipt(
                state=PrimeAgentTerminalState.SUCCESS,
                argv=("prime-agent", "-p"),
                exit_code=0,
                duration_ms=5,
                output_bytes=len(payload.encode()),
                detail="stub",
            ),
        )

    def run(self, request: PrimeAgentRequest) -> PrimeAgentOutcome:
        self.run_requests.append(request)
        evidence = (
            PrimeAgentEvidence(self._final_text)
            if self._final_state is PrimeAgentTerminalState.SUCCESS and self._final_text
            else None
        )
        return PrimeAgentOutcome(
            request=request,
            evidence=evidence,
            receipt=PrimeAgentReceipt(
                state=self._final_state,
                argv=("prime-agent", "-p"),
                exit_code=0,
                duration_ms=5,
                output_bytes=0,
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


def test_repl_agent_default_path_is_unchanged_without_prime_backend() -> None:
    seen_prompts: list[str] = []

    def llm_caller(prompt: str) -> str:
        seen_prompts.append(prompt)
        return f"canonical:{prompt}"

    agent = RLMAgent(llm_caller, max_parallel=1)

    assert agent.llm_query("single") == "canonical:single"
    assert agent.llm_batch(["a", "b"]) == ["canonical:a", "canonical:b"]
    assert seen_prompts == ["single", "a", "b"]


def test_repl_agent_routes_subcalls_through_prime_backend_when_enabled() -> None:
    seen_prompts: list[str] = []

    def llm_caller(prompt: str) -> str:
        seen_prompts.append(prompt)
        return "canonical"

    backend = _BackendStub(PrimeAgentTerminalState.SUCCESS, "supplement")
    agent = RLMAgent(
        llm_caller,
        max_parallel=1,
        prime_agent_backend=backend,
    )

    assert agent.llm_query("single") == "canonical"
    assert agent.llm_batch(["batch"]) == ["canonical"]
    assert len(backend.requests) == 2
    assert all(
        "Supplemental Prime Agent evidence (non-canonical)" in prompt
        for prompt in seen_prompts
    )


def test_make_llm_query_accepts_prime_agent_backend_alias() -> None:
    backend = _BackendStub(PrimeAgentTerminalState.SUCCESS, "evidence")
    seen_prompts: list[str] = []
    query = make_llm_query(
        lambda prompt: seen_prompts.append(prompt) or "ok",
        prime_agent_backend=backend,
    )

    assert query("question") == "ok"
    assert len(backend.requests) == 1
    assert "Supplemental Prime Agent evidence" in seen_prompts[0]


def test_rlm_investigation_prime_driver_uses_session_backend_flow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTIEK_RLM_RATIFIED", "1")
    monkeypatch.setenv("ANTIEK_PRIME_AGENT_RLM_ENABLED", "1")

    payloads = [
        json.dumps({
            "iteration": 1,
            "iteration_summary": "iter one",
            "new_sub_questions": ["q1"],
            "cost_usd": "0.10",
            "should_continue": True,
        }),
        json.dumps({
            "iteration": 2,
            "iteration_summary": "iter two",
            "new_sub_questions": [],
            "cost_usd": "0.15",
            "should_continue": False,
        }),
    ]
    backend = _SessionBackendStub(session_payloads=payloads)
    sink: list[PrimeAgentOutcome] = []
    fallback_calls = {"count": 0}

    def fallback_plan(_state: str, _questions: list[str]) -> RLMIterationOutcome:
        fallback_calls["count"] += 1
        return RLMIterationOutcome(
            iteration=99,
            iteration_summary="fallback",
            new_sub_questions=(),
            cost_usd=Decimal("0"),
            should_continue=False,
        )

    captured_inputs: list[str] = []

    def final_synthesis(inputs: list[str]) -> tuple[str, Decimal]:
        captured_inputs.extend(inputs)
        return ("final", Decimal("0.20"))

    final, session = run_rlm_investigation(
        RLMInvestigationConfig(
            investigation_id="inv-prime",
            initial_question="root question",
            max_iterations=4,
            driver="prime_agent",
        ),
        plan_iteration_fn=fallback_plan,
        final_synthesis_fn=final_synthesis,
        prime_agent_backend=backend,
        prime_outcome_sink=sink.append,
    )

    assert final == "final"
    assert session.state.status == "completed"
    assert session.state.root_executor == "prime_agent"
    assert session.state.prime_goal_brief is not None
    assert fallback_calls["count"] == 0
    assert len(backend.session_requests) == 2
    assert len(backend.run_requests) == 1  # final supplemental lane
    assert captured_inputs == ["root question", "q1"]
    assert len(sink) == 3  # two iteration session outcomes + final outcome


def test_rlm_investigation_prime_driver_requires_env_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTIEK_RLM_RATIFIED", "1")
    monkeypatch.delenv("ANTIEK_PRIME_AGENT_RLM_ENABLED", raising=False)
    backend = _SessionBackendStub(session_payloads=["{}"])

    with pytest.raises(ValueError, match="ANTIEK_PRIME_AGENT_RLM_ENABLED"):
        run_rlm_investigation(
            RLMInvestigationConfig(
                investigation_id="inv-gate",
                initial_question="root",
                driver="prime_agent",
            ),
            plan_iteration_fn=lambda state, qs: RLMIterationOutcome(
                iteration=1,
                iteration_summary="fallback",
                new_sub_questions=(),
                cost_usd=Decimal("0"),
                should_continue=False,
            ),
            final_synthesis_fn=lambda inputs: ("final", Decimal("0")),
            prime_agent_backend=backend,
        )
