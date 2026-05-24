"""@track_burn -- decorator that wraps an LLM call site and records its cost."""

from __future__ import annotations

import functools
import uuid
from typing import Any, Callable

from substrate.observability.burn import BurnEvent, BurnRecorder
from substrate.observability.burn_context import current_burn_context


def _extract_usage(result: Any) -> dict[str, Any]:
    usage = None
    model: str | None = None
    if hasattr(result, "usage"):
        usage = result.usage
        model = getattr(result, "model", None)
    elif isinstance(result, dict):
        usage = result.get("usage")
        model = result.get("model")
    if usage is None:
        return {"input_tokens": 0, "output_tokens": 0, "cached_tokens": 0, "model": model or "unknown"}

    def _get(key1: str, key2: str | None = None, default: int = 0) -> int:
        if hasattr(usage, key1):
            v = getattr(usage, key1, default)
            return int(v) if v is not None else default
        if key2 is not None and hasattr(usage, key2):
            v = getattr(usage, key2, default)
            return int(v) if v is not None else default
        if isinstance(usage, dict):
            v = usage.get(key1)
            if v is None and key2 is not None:
                v = usage.get(key2)
            return int(v) if v is not None else default
        return default

    return {
        "input_tokens": _get("input_tokens", "prompt_tokens"),
        "output_tokens": _get("output_tokens", "completion_tokens"),
        "cached_tokens": _get("cache_read_input_tokens"),
        "model": model or "unknown",
    }


def track_burn(tool_id: str | None = None) -> Callable[[Callable], Callable]:
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            ctx = current_burn_context()
            recorder = BurnRecorder.for_project(ctx.project_root)
            call_id = uuid.uuid4().hex
            try:
                result = fn(*args, **kwargs)
            except Exception as exc:
                recorder.record(
                    BurnEvent(
                        session_id=ctx.session_id, call_id=call_id, model="unknown",
                        input_tokens=0, output_tokens=0,
                        project_id=ctx.project_id, tool_id=tool_id,
                        error=repr(exc), extension_ids_active=ctx.extension_ids_active,
                    )
                )
                raise
            usage = _extract_usage(result)
            recorder.record(
                BurnEvent(
                    session_id=ctx.session_id, call_id=call_id,
                    model=usage["model"],
                    input_tokens=usage["input_tokens"],
                    output_tokens=usage["output_tokens"],
                    cached_tokens=usage["cached_tokens"],
                    project_id=ctx.project_id, tool_id=tool_id,
                    extension_ids_active=ctx.extension_ids_active,
                )
            )
            return result
        return wrapper
    return decorator
