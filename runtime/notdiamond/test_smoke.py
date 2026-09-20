from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("NOTDIAMOND_API_KEY"),
    reason="NOTDIAMOND_API_KEY not set; live ND smoke is advisory and skipped.",
)

_CANDIDATES = [
    "openai/gpt-4o-mini",
    "anthropic/claude-3-5-haiku-20241022",
]
_MESSAGES = [
    {"role": "user", "content": "Summarize general relativity in one sentence."}
]


def test_cross_provider_round_trip() -> None:
    from runtime.notdiamond import Recommendation, select_model

    latencies: list[int] = []
    providers: set[str] = set()
    for _ in range(3):
        rec = select_model(_MESSAGES, _CANDIDATES, tradeoff="cost")
        assert isinstance(rec, Recommendation)
        assert rec.provider in {"openai", "anthropic"}
        assert rec.model
        assert rec.session_id
        latencies.append(rec.decision_latency_ms)
        providers.add(rec.provider)

    print(
        f"[nd-smoke] decision latency ms: cold={latencies[0]} "
        f"warm1={latencies[1]} warm2={latencies[2]}"
    )
    print(f"[nd-smoke] providers chosen across 3 calls: {sorted(providers)}")
