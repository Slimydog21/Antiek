"""Disabled-by-default NotDiamond advice for Deep Research dispatch calls.

This module only evaluates and classifies an advisory recommendation. It never
selects a provider, mutates a dispatch tier, emits an event, or authorizes cost.
"""

from __future__ import annotations

import os
import queue
import re
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Literal

from runtime.notdiamond import (
    NotDiamondAuthError,
    NotDiamondError,
    NotDiamondNotInstalled,
    NotDiamondTimeout,
    Recommendation,
    select_model,
)

Mode = Literal["disabled", "shadow"]
_MODE_ENV = "ANTIEK_NOTDIAMOND_MODE"
_DISCLOSURE_ENV = "ANTIEK_NOTDIAMOND_ALLOW_PROMPT_DISCLOSURE"
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
_MODEL_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,511}$")
_SELECTOR_SLOT = threading.BoundedSemaphore(1)
_DRW_ROLES = frozenset(
    {
        "decomposer",
        "evidence_retriever",
        "parameter_extractor",
        "connector",
        "synthesizer",
        "note_taker",
        "challenger",
        "grounder",
        "verifier",
    }
)

Selector = Callable[..., Recommendation]


@dataclass(frozen=True)
class ShadowAttribution:
    session_id: str | None
    recommended_provider: str | None
    recommended_model: str | None
    tradeoff: str | None
    decision_latency_ms: int | None
    bypass_reason: str


def evaluate_notdiamond_shadow(
    *,
    prompt: str,
    role: str,
    candidates: tuple[str, ...],
    environ: Mapping[str, str] | None = None,
    selector: Selector = select_model,
    timeout_ms: int = 500,
) -> ShadowAttribution | None:
    """Return attributable shadow evidence for a DRW call, never route advice."""
    if role not in _DRW_ROLES:
        return None
    values = os.environ if environ is None else environ
    mode = values.get(_MODE_ENV, "disabled").strip().lower()
    if mode != "shadow":
        reason = "disabled" if mode in {"", "disabled"} else "invalid_mode"
        return ShadowAttribution(None, None, None, None, None, reason)
    if values.get(_DISCLOSURE_ENV, "").strip().lower() not in {"1", "true", "yes"}:
        return ShadowAttribution(
            None, None, None, "quality", None, "prompt_disclosure_not_approved"
        )
    if not candidates:
        return ShadowAttribution(None, None, None, "quality", None, "no_candidates")

    try:
        recommendation = _select_with_deadline(
            selector=selector,
            prompt=prompt,
            candidates=candidates,
            timeout_ms=timeout_ms,
        )
    except NotDiamondTimeout:
        return ShadowAttribution(None, None, None, "quality", None, "timeout")
    except (NotDiamondAuthError, NotDiamondNotInstalled):
        return ShadowAttribution(None, None, None, "quality", None, "unavailable")
    except NotDiamondError:
        return ShadowAttribution(None, None, None, "quality", None, "error")
    except Exception:
        return ShadowAttribution(None, None, None, "quality", None, "unexpected_error")

    if not _valid_recommendation(recommendation):
        return ShadowAttribution(None, None, None, "quality", None, "malformed_response")
    candidate = f"{recommendation.provider}/{recommendation.model}"
    if candidate not in candidates:
        return ShadowAttribution(
            recommendation.session_id,
            recommendation.provider,
            recommendation.model,
            "quality",
            recommendation.decision_latency_ms,
            "off_candidate_set",
        )
    return ShadowAttribution(
        recommendation.session_id,
        recommendation.provider,
        recommendation.model,
        "quality",
        recommendation.decision_latency_ms,
        "shadow",
    )


def _select_with_deadline(
    *, selector: Selector, prompt: str, candidates: tuple[str, ...], timeout_ms: int
) -> Recommendation:
    if timeout_ms <= 0 or not _SELECTOR_SLOT.acquire(blocking=False):
        raise NotDiamondTimeout("notdiamond shadow selector is unavailable")
    result: queue.Queue[Recommendation | Exception] = queue.Queue(maxsize=1)

    def invoke() -> None:
        try:
            value = selector(
                messages=[{"role": "user", "content": prompt}],
                candidates=candidates,
                tradeoff="quality",
                timeout_ms=timeout_ms,
            )
            result.put_nowait(value)
        except Exception as exc:
            result.put_nowait(exc)
        finally:
            _SELECTOR_SLOT.release()

    worker = threading.Thread(target=invoke, name="antiek-nd-shadow", daemon=True)
    try:
        worker.start()
    except Exception:
        _SELECTOR_SLOT.release()
        raise
    try:
        value = result.get(timeout=timeout_ms / 1000)
    except queue.Empty as exc:
        raise NotDiamondTimeout("notdiamond shadow deadline exceeded") from exc
    if isinstance(value, Exception):
        raise value
    return value


def _valid_recommendation(value: Recommendation) -> bool:
    return (
        isinstance(value, Recommendation)
        and isinstance(value.provider, str)
        and isinstance(value.model, str)
        and isinstance(value.session_id, str)
        and bool(_IDENTIFIER.fullmatch(value.provider))
        and bool(_MODEL_IDENTIFIER.fullmatch(value.model))
        and bool(_IDENTIFIER.fullmatch(value.session_id))
        and type(value.decision_latency_ms) is int
        and 0 <= value.decision_latency_ms <= 60_000
    )


__all__ = ["ShadowAttribution", "evaluate_notdiamond_shadow"]
