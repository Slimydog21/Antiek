"""
Agent-loved response envelope for the Antiek REST surface.

Yegge (December 2025 interview): "AIs are lazy — if you provide a
service that's going to make something convenient for them, they'll
absolutely use it." The convention captured here: every new route
returns the same wrapped shape so an agent caller can match on
``error.code`` instead of parsing strings, and can rely on the same
top-level discriminator (``ok: bool``) across the entire surface.

Shape::

    success: {"ok": true, "data": <T>}
    failure: {"ok": false, "error": {"code": "INVALID_INPUT",
                                     "message": "human-readable",
                                     "details": {...optional...}}}

Why a closed ``ERROR_CODES`` set? Open sets rot — every route invents
its own code, agents memorize per-route quirks, the discoverability
benefit evaporates. The closed set forces a route author to either
re-use an existing code (preserves agent shape-matching) or extend the
set deliberately (one source-control review touches the canon).

Convention: NEW routes added after SPR-09 use ``ResponseEnvelope`` for
their return type and either:

  - ``return ResponseEnvelope.success(data=...)``, or
  - raise ``EnvelopedHTTPException(code=..., message=..., status_code=...)``
    which the registered exception handler renders as the failure
    shape.

Existing routes are intentionally NOT wrapped in this sprint — the
operator has in-flight parallel changes to ``app.py`` and route
modules, and migrating legacy routes touches surfaces both streams
would conflict on. A future "batch 2" sprint owns the legacy
migration. Until then, agent callers hitting legacy routes get the
raw FastAPI shape; new routes immediately get the agent-loved shape.

Spec: ~/specs/antiek-yegge-execute/sprint-09-agent-loved-api.html
"""

from __future__ import annotations

from typing import Any, Dict, Final, Generic, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


# Closed canonical error-code set. Extending requires a code review of
# this constant, which is the point — the discoverability guarantee
# only works if codes don't multiply silently. Each entry carries the
# canonical use case in its inline comment so a route author picks the
# right one without inventing a new one.
ERROR_CODES: Final[frozenset[str]] = frozenset({
    "INVALID_INPUT",            # request body / query / path is malformed
    "NOT_FOUND",                # resource doesn't exist
    "RATE_LIMIT",               # caller hit a quota; retry-after may be in details
    "UNAUTHORIZED",             # no credentials / invalid credentials
    "FORBIDDEN",                # credentials valid but not allowed for this op
    "CONFLICT",                 # state-change would violate an invariant
    "INTERNAL_ERROR",           # unexpected; reserved for catch-all handler
    "BUDGET_EXCEEDED",          # token / cost / time budget exceeded
    "IDEMPOTENCY_KEY_REQUIRED", # POST/PUT without Idempotency-Key header
    "IDEMPOTENCY_REPLAY",       # replay of a prior key; details.previous_response
    "UPSTREAM_UNAVAILABLE",     # external dependency failed (e.g. Hermes 503)
})


class ErrorEnvelope(BaseModel):
    """The error payload inside a failure ResponseEnvelope.

    ``code`` is one of the strings in :data:`ERROR_CODES` (validated at
    construction time). ``message`` is for humans; ``details`` is
    structured context (validation errors, retry-after seconds,
    previous response on replays, etc.).
    """

    code: str = Field(..., description="One of ERROR_CODES.")
    message: str = Field(..., description="Human-readable explanation.")
    details: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional structured context for the error.",
    )

    def __init__(self, **data: Any) -> None:
        # Validate `code` against the closed set at construction time
        # so a route author can't ship a typo or invented code.
        super().__init__(**data)
        if self.code not in ERROR_CODES:
            raise ValueError(
                f"ErrorEnvelope.code={self.code!r} is not in ERROR_CODES. "
                "Extend interfaces/research/api/envelope.py:ERROR_CODES "
                "with a code-review-worthy justification, then retry."
            )


class ResponseEnvelope(BaseModel, Generic[T]):
    """Canonical wrapped response shape for new routes.

    Use :meth:`success` to construct a 2xx payload; use the
    :class:`EnvelopedHTTPException` raise-path for failures so the
    central handler emits the matching shape.
    """

    ok: bool
    data: Optional[T] = None
    error: Optional[ErrorEnvelope] = None

    @classmethod
    def success(cls, *, data: T) -> "ResponseEnvelope[T]":
        return cls(ok=True, data=data, error=None)

    @classmethod
    def failure(
        cls, *, code: str, message: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> "ResponseEnvelope[None]":
        return cls(
            ok=False,
            data=None,
            error=ErrorEnvelope(code=code, message=message, details=details),
        )


class EnvelopedHTTPException(Exception):
    """Raise this from any route to return a properly-shaped failure.

    Register :func:`install_exception_handler` once at app construction
    to wire the central renderer; thereafter routes can simply
    ``raise EnvelopedHTTPException(code="NOT_FOUND", message="...")``.

    Why an Exception instead of returning the envelope? Because raising
    composes with FastAPI's dependency / middleware stack (an upstream
    dependency's auth check can ``raise EnvelopedHTTPException(
    code="UNAUTHORIZED", ...)`` and the route never runs). Returning
    can't short-circuit dependency resolution.
    """

    def __init__(
        self, *, code: str, message: str,
        status_code: int = 400,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        if code not in ERROR_CODES:
            raise ValueError(
                f"EnvelopedHTTPException code={code!r} is not in ERROR_CODES."
            )
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details
        super().__init__(f"[{code}] {message}")


def install_exception_handler(app: Any) -> None:
    """Wire the central renderer onto a FastAPI app.

    Call once at app construction. Then routes can raise
    :class:`EnvelopedHTTPException` and get the canonical failure
    envelope shape back at the HTTP layer.

    This function is intentionally a one-liner per the spec's
    "do not modify app.py" constraint at SPR-09 time: when the
    operator wires it (one ``install_exception_handler(app)`` call),
    new + legacy routes alike start returning the canonical shape on
    raised exceptions. Routes can opt in to envelope-shaped *success*
    responses on their own schedule.
    """
    # Lazy import — FastAPI is a runtime dep but we don't want the
    # envelope module to fail at import time if used in a test that
    # doesn't have FastAPI installed.
    from fastapi import Request
    from fastapi.responses import JSONResponse

    @app.exception_handler(EnvelopedHTTPException)
    async def _enveloped_handler(request: "Request", exc: EnvelopedHTTPException) -> "JSONResponse":
        env = ResponseEnvelope.failure(
            code=exc.code, message=exc.message, details=exc.details,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=env.model_dump(exclude_none=True),
        )


__all__ = [
    "ERROR_CODES",
    "ErrorEnvelope",
    "ResponseEnvelope",
    "EnvelopedHTTPException",
    "install_exception_handler",
]
