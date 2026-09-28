"""The Prime Agent adapter DECLARES that it reports no usage.

Decision record: ``docs/decisions/prime-agent-usage-ceiling.md``. The binary
reports no token counts, so every Prime Agent dispatch is billed at the call
ceiling (one input token per prompt byte plus the output budget), never at a
definite zero. Before this change the ceiling was an accident of the adapter's
empty ``raw_usage``: ``normalize_usage`` returned ``NormalizedUsage(0, 0)`` with
the default ``reported=True``, so any later adapter change that put anything
into ``raw_usage`` would have flipped the router back to trusting zeros. The
adapter now returns ``reported=False`` itself; the second test is the one that
goes red if that declaration is removed.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from orchestration.rlm.prime_agent_backend import (
    PrimeAgentEvidence,
    PrimeAgentOutcome,
    PrimeAgentReceipt,
    PrimeAgentRequest,
    PrimeAgentRLMBackend,
    PrimeAgentTerminalState,
)
from substrate.dispatch import register_provider, reset_provider_registry
from substrate.dispatch.base import RawProviderResponse
from substrate.dispatch.providers.prime_agent import PrimeAgentProvider
from substrate.dispatch.router import (
    DispatchConfig,
    DispatchResult,
    TierConfig,
    TierPricing,
    dispatch,
)

_PROMPT = "x " * 4000  # 8000 UTF-8 bytes
_MAX_TOKENS = 1000
_PRICING = TierPricing(input_per_mtok=1.0, output_per_mtok=4.0, cached_input_per_mtok=0.1)
_CEILING_USD = (8000 / 1_000_000) * 1.0 + (_MAX_TOKENS / 1_000_000) * 4.0


@pytest.fixture(autouse=True)
def _registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    reset_provider_registry()
    yield
    reset_provider_registry()


class _SucceedingBackend(PrimeAgentRLMBackend):
    """A backend whose receipt is a real success with text and no usage —
    exactly what the binary produces today. No subprocess is spawned."""

    def __init__(self, cwd: Path) -> None:
        super().__init__(cwd=cwd)

    def run(self, request: PrimeAgentRequest) -> PrimeAgentOutcome:
        return PrimeAgentOutcome(
            request=request,
            evidence=PrimeAgentEvidence(text="a long paid answer"),
            receipt=PrimeAgentReceipt(
                state=PrimeAgentTerminalState.SUCCESS,
                argv=("prime-agent", "--prompt-only"),
                exit_code=0,
                duration_ms=1234,
                output_bytes=18,
            ),
        )


class _AdapterThatPopulatesRawUsage(PrimeAgentProvider):
    """The hazard the decision record names: a future adapter shape that puts
    something other than real counts into ``raw_usage``. The router's
    empty-``raw_usage`` fallback no longer applies; only the adapter's own
    ``reported=False`` keeps the call at the ceiling."""

    def call(
        self, *, model: str, prompt: str, max_tokens: int, temperature: float,
    ) -> RawProviderResponse:
        base = super().call(
            model=model, prompt=prompt, max_tokens=max_tokens, temperature=temperature,
        )
        return RawProviderResponse(
            text=base.text,
            raw_usage={"prime_terminal_state": "success", "duration_ms": 1234},
            finish_reason=base.finish_reason,
            latency_ms=base.latency_ms,
            request_id=base.request_id,
            extra=base.extra,
        )


def _config() -> DispatchConfig:
    tier = TierConfig(
        name="pro", provider="prime_agent", model="prime-agent", max_tokens=_MAX_TOKENS,
        temperature=0.1, context_budget_tokens=32000, pricing=_PRICING,
    )
    return DispatchConfig(role_tiers={"thought_partner": "pro"}, tiers={"pro": tier})


def _dispatch() -> DispatchResult:
    return dispatch(
        _PROMPT, "thought_partner", investigation_id="inv-prime-usage", config=_config(),
    )


@pytest.mark.parametrize(
    "raw_usage",
    [
        pytest.param({}, id="empty-as-today"),
        pytest.param({"prompt_tokens": 12, "completion_tokens": 7}, id="counts-shaped"),
        pytest.param({"prime_terminal_state": "success"}, id="receipt-shaped"),
    ],
)
def test_normalize_usage_declares_unreported_whatever_raw_usage_holds(
    raw_usage: dict[str, object], tmp_path: Path,
) -> None:
    usage = PrimeAgentProvider(backend=_SucceedingBackend(tmp_path)).normalize_usage(raw_usage)
    assert usage.reported is False
    assert (usage.input_tokens, usage.output_tokens) == (0, 0)
    assert usage.cache_unknown is False


def test_a_populated_raw_usage_still_bills_the_ceiling(tmp_path: Path) -> None:
    """Red without the adapter's own ``reported=False``: the router would see a
    non-empty ``raw_usage`` and a ``reported=True`` zero usage, and price a paid
    call at $0."""
    register_provider(_AdapterThatPopulatesRawUsage(backend=_SucceedingBackend(tmp_path)))
    result = _dispatch()
    assert result.text == "a long paid answer"
    assert result.usage.reported is False
    assert result.usage.input_tokens == len(_PROMPT.encode("utf-8"))
    assert result.usage.output_tokens == _MAX_TOKENS
    assert result.cost_usd == pytest.approx(_CEILING_USD)
    assert result.cost_usd > 0


def test_the_wired_adapter_bills_the_ceiling_today(tmp_path: Path) -> None:
    """Positive control on the real ``call`` path: an honest success receipt
    with no usage reaches the router as an unreported call at the ceiling."""
    register_provider(PrimeAgentProvider(backend=_SucceedingBackend(tmp_path)))
    result = _dispatch()
    assert result.text == "a long paid answer"
    assert result.usage.reported is False
    assert result.cost_usd == pytest.approx(_CEILING_USD)
