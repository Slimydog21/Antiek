"""Dispatch tier-differentiation verdict analyzer (Sprint 17–20, §14.4).

Closes Gate G5. The substrate has been pinning the synthesizer tier
to Opus 4.7 via OpenRouter primary since Sprint 17. After ≥14 days
of live traffic this analyzer consumes the trajectory JSONL, computes
verifier pass rates per provider on synthesis outputs, and writes
a verdict markdown.

The verdict criterion per §14.4:

- If Grok-4.3-on-synthesis passes verifier within 5 percentage
  points of Opus-on-synthesis: flip back to Hermes primary on
  cost grounds.
- If the gap is larger: keep Opus on synthesis as primary.

Usage:
    python -m tools.dispatch_tier_verdict \\
        --events ~/.antiek/events/ \\
        --since 2026-05-08 \\
        --output docs/decisions/dispatch-tier-verdict.md
"""

from tools.dispatch_tier_verdict.analyzer import (
    ProviderScore,
    Verdict,
    analyse_events,
    render_verdict_markdown,
)

__all__ = [
    "ProviderScore",
    "Verdict",
    "analyse_events",
    "render_verdict_markdown",
]
