"""example_token_counter — pre-hook on token_count that replaces the substrate
heuristic with a deterministic word-count.

Demonstrates the ``HookShortCircuit`` pattern: a pre-hook that returns the
seam's result directly, bypassing the substrate's fallback primitive.
"""

from __future__ import annotations

from typing import Any

from substrate.hooks import HookContext, HookRegistry, HookShortCircuit


class _WordCountTokenizer:
    """Token count ≈ word count. Cheap, deterministic, wrong by a constant
    factor for most models. Replace with tiktoken/anthropic.count_tokens in production."""

    def __call__(self, ctx: HookContext, **kw: Any) -> None:
        text: str = kw.get("text", "")
        n = max(1, len(text.split()))
        raise HookShortCircuit(result=n)


def register(registry: HookRegistry) -> None:
    registry.register_hook(
        seam_id="token_count",
        hook=_WordCountTokenizer(),
        stage="pre",
        extension_id="example_token_counter:v1",
        priority=0,
    )
