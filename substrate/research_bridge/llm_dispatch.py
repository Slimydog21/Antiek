"""Production LLM wiring for the research bridge extractor + gap-finder.

Decision-tree residual: when a process-local decision-tree registry is set
(via ``substrate.model_registration.set_decision_tree_registry``) or passed
explicitly, this call site applies **both** ``provider_override`` and
``model_override`` on the real ``dispatch`` path.
"""

from __future__ import annotations

import os
from typing import Any

try:
    from ..constants import SYSTEM_INVESTIGATION_ID
    from ..dispatch.router import DispatchConfig, DispatchResult, dispatch
    from ..model_registration import ModelRegistry, apply_decision_tree_overrides
    from .extractor import LlmCallResult
except ImportError:  # pragma: no cover
    import sys
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from substrate.constants import SYSTEM_INVESTIGATION_ID  # type: ignore[no-redef]
    from substrate.dispatch.router import (  # type: ignore[no-redef]
        DispatchConfig,
        DispatchResult,
        dispatch,
    )
    from substrate.model_registration import (  # type: ignore[no-redef]
        ModelRegistry,
        apply_decision_tree_overrides,
    )
    from substrate.research_bridge.extractor import LlmCallResult  # type: ignore[no-redef]


DISPATCH_ROLE: str = "note_taker"


def build_dispatch_llm_callable(
    *,
    investigation_id: str | None = None,
    role: str = DISPATCH_ROLE,
    config: DispatchConfig | None = None,
    registry: ModelRegistry | None = None,
    model_id: str | None = None,
):
    """Build an ``LlmCallable`` that routes through the real ``dispatch``.

    When ``registry`` / process-local decision-tree selection is present,
    applies provider+model overrides so the operator's decision-tree choice
    reaches the shipped Hermes-routed path (not a second dispatcher).
    """
    inv = investigation_id or SYSTEM_INVESTIGATION_ID

    def _call(prompt: str) -> LlmCallResult:
        kwargs: dict[str, Any] = {
            "prompt": prompt,
            "role": role,
            "investigation_id": inv,
        }
        if config is not None:
            kwargs["config"] = config
        kwargs = apply_decision_tree_overrides(
            kwargs, registry=registry, model_id=model_id, required=False
        )
        result: DispatchResult = dispatch(**kwargs)
        usage = result.usage
        return LlmCallResult(
            text=result.text or "",
            input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
            output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
            cost_usd=float(getattr(result, "cost_usd", 0.0) or 0.0),
            model_id=f"{result.provider}/{result.model}",
        )

    return _call
