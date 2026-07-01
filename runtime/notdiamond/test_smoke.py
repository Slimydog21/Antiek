"""ANT-ND SPR-01 — live smoke test against NotDiamond's pre-trained router.

Skips cleanly when ``NOTDIAMOND_API_KEY`` is unset (so CI never breaks — ND is
advisory and inert until keyed) and runs the real cross-provider round-trip when
present. Records cold / warm / warm latencies for the handoff (master-spec open
question Q2). Pure adapter test — writes nothing to the event log (that is
SPR-03).

Run: ``NOTDIAMOND_API_KEY=… pytest runtime/notdiamond/test_smoke.py -v -s``
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("NOTDIAMOND_API_KEY"),
    reason="NOTDIAMOND_API_KEY not set — ND smoke is inert until keyed (advisory).",
)

# At least one Anthropic and one OpenAI candidate so cross-provider routing is
# actually exercised (verification gate: 'Cross-provider routing works').
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
    providers_chosen: set[str] = set()

    for _ in range(3):  # cold, warm, warm
        rec = select_model(_MESSAGES, _CANDIDATES, tradeoff="cost")
        assert isinstance(rec, Recommendation)
        assert rec.provider in {"openai", "anthropic"}, rec.provider
        assert rec.model
        assert rec.session_id
        latencies.append(rec.decision_latency_ms)
        providers_chosen.add(rec.provider)

    # Logged (—s) so the handoff can report p50 and confirm cross-provider reach.
    print(
        f"[nd-smoke] decision latency ms: cold={latencies[0]} "
        f"warm1={latencies[1]} warm2={latencies[2]}"
    )
    print(f"[nd-smoke] providers chosen across 3 calls: {sorted(providers_chosen)}")
