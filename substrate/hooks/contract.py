"""Hook contract — Protocol classes for the three lifecycle stages."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class HookContext:
    seam_id: str
    extension_id: str
    call_id: str
    project_id: str | None = None


class HookShortCircuit(Exception):
    def __init__(self, result: Any) -> None:
        super().__init__("HookShortCircuit")
        self.result = result


@runtime_checkable
class PreCallHook(Protocol):
    def __call__(self, ctx: HookContext, **kwargs: Any) -> dict[str, Any] | None: ...


@runtime_checkable
class PostCallHook(Protocol):
    def __call__(self, ctx: HookContext, result: Any, **kwargs: Any) -> Any: ...


@runtime_checkable
class OnErrorHook(Protocol):
    def __call__(self, ctx: HookContext, exc: BaseException, **kwargs: Any) -> Any | None: ...
