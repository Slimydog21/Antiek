"""NotDiamond advisory model-router adapter.

SPR-01 scope: importable, smoke-tested adapter behind an optional dependency.
There is no dispatch integration here; SPR-03 owns any pre-dispatch hook.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Sequence
from typing import Any, cast

from .types import (
    NotDiamondAPIError,
    NotDiamondAuthError,
    NotDiamondError,
    NotDiamondNotInstalled,
    NotDiamondTimeout,
    Recommendation,
)

# Default advisory-decision budget from the Wave 1 spec. The smoke test reports
# real latency numbers so later waves can tune this with evidence.
_DEFAULT_TIMEOUT_MS: int = 500
_API_KEY_ENV: str = "NOTDIAMOND_API_KEY"

Selector = Callable[
    [str, Sequence[dict[str, str]], Sequence[str], str, float],
    tuple[Any, Any],
]


def _resolve_api_key() -> str:
    value = os.environ.get(_API_KEY_ENV)
    if not value:
        raise NotDiamondAuthError(
            f"notdiamond: API key not configured. Set {_API_KEY_ENV} in the "
            "environment. ND is advisory; callers should fall through to dispatch."
        )
    return value


def _default_selector(
    api_key: str,
    messages: Sequence[dict[str, str]],
    candidates: Sequence[str],
    tradeoff: str,
    timeout_s: float,
) -> tuple[Any, Any]:
    try:
        from notdiamond import NotDiamond  # type: ignore[import-not-found, unused-ignore]
    except ImportError as exc:
        raise NotDiamondNotInstalled(
            "notdiamond SDK not installed. Install the optional extra "
            "(`pip install 'antiek[notdiamond]'`) to enable advisory routing."
        ) from exc

    llm_providers = [_candidate_to_provider(candidate) for candidate in candidates]
    client = NotDiamond(api_key=api_key, timeout=timeout_s, max_retries=0)
    response = client.model_router.select_model(
        llm_providers=cast(Any, llm_providers),
        messages=cast(Any, list(messages)),
        tradeoff=tradeoff,
        timeout=timeout_s,
    )
    return response.session_id, response.providers[0]


def _candidate_to_provider(candidate: str) -> dict[str, str]:
    provider, sep, model = candidate.partition("/")
    if not sep or not provider or not model:
        raise NotDiamondAPIError(
            "notdiamond: candidates must use provider/model form; "
            f"got {candidate!r}."
        )
    return {"provider": provider, "model": model}


def _parse_best(best: Any) -> tuple[str, str]:
    provider = getattr(best, "provider", None)
    model = getattr(best, "model", None)
    if provider and model:
        return str(provider), str(model)

    text = str(best)
    if "/" in text:
        provider_text, _, model_text = text.partition("/")
        if provider_text and model_text:
            return provider_text, model_text

    raise NotDiamondAPIError(
        f"notdiamond: could not parse a (provider, model) recommendation from {best!r}"
    )


def select_model(
    messages: Sequence[dict[str, str]],
    candidates: Sequence[str],
    tradeoff: str = "quality",
    timeout_ms: int = _DEFAULT_TIMEOUT_MS,
    *,
    _selector: Selector | None = None,
) -> Recommendation:
    """Ask NotDiamond which candidate to try first.

    Raises only ``NotDiamondError`` subclasses for NotDiamond failures so callers
    can keep ND advisory and fail closed to the existing dispatch path.
    """
    if not candidates:
        raise NotDiamondAPIError("notdiamond: select_model requires >= 1 candidate.")

    api_key = _resolve_api_key()
    selector = _selector or _default_selector

    started = time.monotonic()
    try:
        session_id, best = selector(
            api_key,
            messages,
            candidates,
            tradeoff,
            max(timeout_ms, 0) / 1000.0,
        )
    except TimeoutError as exc:
        raise NotDiamondTimeout(
            f"notdiamond: select_model exceeded {timeout_ms}ms budget."
        ) from exc
    except NotDiamondError:
        raise
    except Exception as exc:
        if exc.__class__.__name__ in {"APITimeoutError", "TimeoutException"}:
            raise NotDiamondTimeout(
                f"notdiamond: select_model exceeded {timeout_ms}ms budget."
            ) from exc
        raise NotDiamondAPIError(f"notdiamond: select_model failed: {exc}") from exc

    latency_ms = int((time.monotonic() - started) * 1000)
    try:
        provider, model = _parse_best(best)
        return Recommendation(
            provider=provider,
            model=model,
            session_id=str(session_id),
            decision_latency_ms=latency_ms,
            raw={"best": repr(best), "session_id": str(session_id)},
        )
    except NotDiamondError:
        raise
    except Exception as exc:
        raise NotDiamondAPIError(
            f"notdiamond: failed to parse recommendation: {exc}"
        ) from exc
