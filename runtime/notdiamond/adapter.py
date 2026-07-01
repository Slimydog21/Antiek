"""ANT-ND SPR-01 — the NotDiamond adapter.

One public function, :func:`select_model`, returns a structured
:class:`Recommendation`. The ND SDK is imported *lazily inside the call* so any
module can ``from runtime.notdiamond import select_model`` and dispatch can run
when the optional ``notdiamond`` extra is uninstalled.

Scope (SPR-01): importable, smoke-tested adapter behind an optional extra. There
is **no dispatch integration** here — that is SPR-03. ND is advisory: every
failure raises a :class:`NotDiamondError` subclass so the caller falls through
to dispatch's own routing (``cd602c9`` verify-tier fallback stays primary).
"""

from __future__ import annotations

import concurrent.futures
import os
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

# Default advisory-decision timeout. 500 ms mirrors the SPR-06 latency-budget
# circuit breaker and keeps ND's call well under the dispatch call it precedes;
# ND docs describe model_select as a single network round-trip. Exact p50 is
# measured by the smoke test (master-spec open question Q2).
_DEFAULT_TIMEOUT_MS: int = 500

# Env var holding the NotDiamond API key. Resolved lazily at first call — never
# at import, never logged. Matches the provider-key idiom in
# substrate/dispatch/providers/anthropic.py:_resolve_api_key (os.environ.get +
# fail-loud naming only the env var, not the value).
_API_KEY_ENV: str = "NOTDIAMOND_API_KEY"

# A selector callable: (api_key, messages, candidates, tradeoff) -> (session_id, best).
# The real one imports the SDK lazily; tests inject a fake so CI needs neither
# the SDK nor a key.
Selector = Callable[[str, Sequence[dict[str, str]], Sequence[str], str], "tuple[Any, Any]"]


def _resolve_api_key() -> str:
    """Return the NotDiamond API key or fail loud. Never logs the value."""
    value = os.environ.get(_API_KEY_ENV)
    if not value:
        raise NotDiamondAuthError(
            f"notdiamond: API key not configured. Set {_API_KEY_ENV} in the "
            "environment. ND is advisory — treat this as 'no recommendation' "
            "and fall through to dispatch's own routing."
        )
    return value


def _default_selector(
    api_key: str,
    messages: Sequence[dict[str, str]],
    candidates: Sequence[str],
    tradeoff: str,
) -> tuple[Any, Any]:
    """The real ND SDK call. Imported lazily so dispatch runs when the optional
    ``notdiamond`` extra is absent.

    ND docs: ``NotDiamond(api_key=, llm_configs=[...]).model_select(messages=,
    tradeoff=)`` returns ``(session_id, best_llm)`` where ``best_llm`` exposes
    ``.provider`` / ``.model`` (a ``"provider/model"`` string form is also
    handled by :func:`_parse_best`).
    """
    try:
        from notdiamond import NotDiamond  # type: ignore[import-not-found]
    except ImportError as exc:
        raise NotDiamondNotInstalled(
            "notdiamond SDK not installed. Install the optional extra "
            "(`pip install 'antiek[notdiamond]'`) to enable advisory routing; "
            "ND is optional and dispatch runs unchanged without it."
        ) from exc

    client = NotDiamond(api_key=api_key, llm_configs=list(candidates))
    # ND returns (session_id, best_llm); unpack + re-pack a tuple literal so the
    # untyped SDK's Any return doesn't leak past the declared signature.
    session_id, best = client.model_select(messages=list(messages), tradeoff=tradeoff)
    return session_id, best


def _parse_best(best: Any) -> tuple[str, str]:
    """Extract ``(provider, model)`` from ND's ``best_llm`` return value.

    Handles both the object form (``.provider`` / ``.model`` attributes, the ND
    ``LLMConfig``) and the ``"provider/model"`` string form. Anything else is a
    parse failure — surfaced, never guessed.
    """
    provider = getattr(best, "provider", None)
    model = getattr(best, "model", None)
    if provider and model:
        return str(provider), str(model)
    text = str(best)
    if "/" in text:
        prov, _, mdl = text.partition("/")
        if prov and mdl:
            return prov, mdl
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
    """Ask NotDiamond which candidate provider to use for ``messages``.

    Args:
        messages: OpenAI-style chat messages (``[{"role": ..., "content": ...}]``).
        candidates: ND ``llm_configs`` — ``"provider/model"`` strings, at least
            one. ND routes only among these.
        tradeoff: ND routing objective — ``"quality"`` | ``"cost"`` | ``"latency"``
            | ``"ct_N"`` (numeric cost-tolerance). Default ``"quality"``.
        timeout_ms: Hard wall-clock budget for the decision. On overrun a
            :class:`NotDiamondTimeout` is raised and the runaway SDK call is
            abandoned (not awaited) so ND never stalls the dispatch path.
        _selector: Test seam — inject a fake ``(api_key, messages, candidates,
            tradeoff) -> (session_id, best)`` so CI exercises the adapter
            without the SDK or a key. Not for production callers.

    Returns:
        A populated :class:`Recommendation`.

    Raises:
        NotDiamondAPIError: no candidates, SDK/service error, or unparseable
            recommendation.
        NotDiamondAuthError: ``NOTDIAMOND_API_KEY`` unset.
        NotDiamondNotInstalled: the ``notdiamond`` extra is not installed.
        NotDiamondTimeout: the decision exceeded ``timeout_ms``.

    ND is advisory: callers catch :class:`NotDiamondError` and fall through to
    dispatch's own routing. This function has zero dispatch coupling (SPR-01).
    """
    if not candidates:
        raise NotDiamondAPIError("notdiamond: select_model requires >= 1 candidate provider.")

    selector: Selector = _selector or _default_selector
    api_key = _resolve_api_key()

    # Run the (blocking) decision on a worker thread so a hung SDK/network call
    # is abandoned FOR THIS CALL at the timeout: shutdown(wait=False) means the
    # per-call path never blocks on a stuck provider (an advisory decision must
    # not stall dispatch). Caveat: ThreadPoolExecutor workers are non-daemon, so
    # concurrent.futures still joins a genuinely-hung worker at interpreter exit
    # (until its socket times out) — that delays process shutdown, never a live
    # request. SPR-06's kill switch + a shared/daemon executor can tighten this
    # if it ever matters. monotonic-derived latency is what SPR-06's budget uses.
    import time

    executor = concurrent.futures.ThreadPoolExecutor(
        max_workers=1, thread_name_prefix="nd-select"
    )
    t_start = time.monotonic()
    try:
        future = executor.submit(selector, api_key, messages, candidates, tradeoff)
        try:
            session_id, best = future.result(timeout=max(timeout_ms, 0) / 1000.0)
        except concurrent.futures.TimeoutError as exc:
            raise NotDiamondTimeout(
                f"notdiamond: select_model exceeded {timeout_ms}ms budget."
            ) from exc
        except NotDiamondError:
            raise  # adapter-owned errors (e.g. NotDiamondNotInstalled) pass through
        except Exception as exc:  # SDK / network — map into the hierarchy
            raise NotDiamondAPIError(f"notdiamond: select_model failed — {exc}") from exc

        # Parse + build the Recommendation INSIDE the mapping boundary. A
        # malformed SDK return — e.g. an object whose ``__str__``/``__repr__``
        # raises — must surface as NotDiamondAPIError, never a raw exception, so
        # callers can ALWAYS treat ND as advisory and fall through to dispatch.
        decision_latency_ms = int((time.monotonic() - t_start) * 1000)
        try:
            provider, model = _parse_best(best)
            recommendation = Recommendation(
                provider=provider,
                model=model,
                session_id=str(session_id),
                decision_latency_ms=decision_latency_ms,
                raw={"best": repr(best), "session_id": str(session_id)},
            )
        except NotDiamondError:
            raise  # _parse_best's own NotDiamondAPIError for unparseable input
        except Exception as exc:  # bad __str__/__repr__ or any parse crash
            raise NotDiamondAPIError(
                f"notdiamond: failed to parse recommendation — {exc}"
            ) from exc
        return recommendation
    finally:
        # Never block on a runaway worker; cancel anything still queued.
        executor.shutdown(wait=False, cancel_futures=True)
