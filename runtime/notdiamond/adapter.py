"""NotDiamond advisory model-router adapter.

SPR-01 scope: importable, smoke-tested adapter behind an optional dependency.
There is no dispatch integration here; SPR-03 owns any pre-dispatch hook.
"""

from __future__ import annotations

import concurrent.futures
import os
import time
from collections.abc import Callable, Sequence
from typing import Any

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

Selector = Callable[[str, Sequence[dict[str, str]], Sequence[str], str], tuple[Any, Any]]


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
) -> tuple[Any, Any]:
    try:
        from notdiamond import NotDiamond  # type: ignore[import-not-found]
    except ImportError as exc:
        raise NotDiamondNotInstalled(
            "notdiamond SDK not installed. Install the optional extra "
            "(`pip install 'antiek[notdiamond]'`) to enable advisory routing."
        ) from exc

    client = NotDiamond(api_key=api_key, llm_configs=list(candidates))
    session_id, best = client.model_select(messages=list(messages), tradeoff=tradeoff)
    return session_id, best


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

    executor = concurrent.futures.ThreadPoolExecutor(
        max_workers=1,
        thread_name_prefix="nd-select",
    )
    started = time.monotonic()
    try:
        future = executor.submit(selector, api_key, messages, candidates, tradeoff)
        try:
            session_id, best = future.result(timeout=max(timeout_ms, 0) / 1000.0)
        except concurrent.futures.TimeoutError as exc:
            raise NotDiamondTimeout(
                f"notdiamond: select_model exceeded {timeout_ms}ms budget."
            ) from exc
        except NotDiamondError:
            raise
        except Exception as exc:
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
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
