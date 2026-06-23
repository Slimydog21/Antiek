"""Production LLM wiring for the research bridge extractor + gap-finder."""

from __future__ import annotations

import os
from collections.abc import Callable

try:
    from ..constants import SYSTEM_INVESTIGATION_ID
    from ..dispatch.router import DispatchConfig, DispatchResult, dispatch
    from ..dispatch.session_routing import PresenceHint, dispatch_routing_kwargs
    from .extractor import LlmCallResult
except ImportError:  # pragma: no cover
    import sys
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from substrate.constants import SYSTEM_INVESTIGATION_ID
    from substrate.dispatch.router import (
        DispatchConfig,
        DispatchResult,
        dispatch,
    )
    from substrate.dispatch.session_routing import (
        PresenceHint,
        dispatch_routing_kwargs,
    )
    from substrate.research_bridge.extractor import LlmCallResult


DISPATCH_ROLE: str = "note_taker"


def build_dispatch_llm_callable(
    *,
    investigation_id: str | None = None,
    role: str = DISPATCH_ROLE,
    config: DispatchConfig | None = None,
    presence: PresenceHint = "background",
) -> Callable[[str], LlmCallResult]:
    """Build an ``LlmCallable`` that routes through dispatch."""
    inv = investigation_id or SYSTEM_INVESTIGATION_ID

    def _call(prompt: str) -> LlmCallResult:
        result: DispatchResult = dispatch(
            prompt,
            role=role,
            investigation_id=inv,
            config=config,
            **dispatch_routing_kwargs(inv, presence=presence),
        )
        usage = result.usage
        return LlmCallResult(
            text=result.text or "",
            input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
            output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
            cost_usd=float(getattr(result, "cost_usd", 0.0) or 0.0),
            model_id=f"{result.provider}/{result.model}",
        )

    return _call
