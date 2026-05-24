"""Burn telemetry context -- propagates call identity via ContextVar."""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BurnContext:
    session_id: str
    project_root: Path
    project_id: str | None = None
    extension_ids_active: tuple[str, ...] = ()


_burn_context: ContextVar[BurnContext | None] = ContextVar(
    "antiek_burn_context", default=None
)


class BurnContextNotSet(RuntimeError):
    pass


def set_burn_context(ctx: BurnContext) -> Token[BurnContext | None]:
    return _burn_context.set(ctx)


def reset_burn_context(token: Token[BurnContext | None]) -> None:
    _burn_context.reset(token)


def current_burn_context() -> BurnContext:
    ctx = _burn_context.get()
    if ctx is None:
        raise BurnContextNotSet(
            "current_burn_context() called before set_burn_context(); "
            "wrap your session start with set_burn_context(BurnContext(...))"
        )
    return ctx
