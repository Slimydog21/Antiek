"""The only executable adapter is local. Reserved providers always refuse."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from types import MappingProxyType
from typing import Protocol

from .models import BackendKind, JobContext


class CredentialFailure(RuntimeError):
    """Block this tenant/route, without retry or fallback."""


class BillingFailure(RuntimeError):
    """Block this tenant/route, without retry or fallback."""


class AdapterUnavailable(RuntimeError):
    pass


class ExecutionBackend(Protocol):
    @property
    def available(self) -> bool: ...

    def execute(self, task: Callable[[JobContext], object], context: JobContext) -> object: ...


class InProcessBackend:
    available = True

    def execute(self, task: Callable[[JobContext], object], context: JobContext) -> object:
        return task(context)


class StubBackend:
    available = False

    def __init__(self, kind: BackendKind) -> None:
        self.kind = kind

    def execute(self, task: Callable[[JobContext], object], context: JobContext) -> object:
        raise AdapterUnavailable(f"{self.kind.value} is an unimplemented adapter")


def adapter_registry() -> Mapping[BackendKind, ExecutionBackend]:
    return MappingProxyType(
        {
            BackendKind.IN_PROCESS: InProcessBackend(),
            **{
                kind: StubBackend(kind)
                for kind in (
                    BackendKind.MODAL,
                    BackendKind.PRIME_SANDBOXES,
                    BackendKind.MINI_NODE,
                )
            },
        }
    )
