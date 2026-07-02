"""Deterministic, opt-in fault-injection core.

Importing this module installs nothing. A fault is active only inside
``with arm(injector):`` and is always torn down in ``finally``.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Protocol


class FaultArmed(RuntimeError):
    """Raised when a named fault injector is used incorrectly."""


class Injector(Protocol):
    name: str

    def install(self) -> None: ...
    def uninstall(self) -> None: ...


@dataclass(frozen=True)
class RegisteredInjector:
    name: str
    description: str


REGISTRY: dict[str, RegisteredInjector] = {
    "readonly_fs": RegisteredInjector(
        name="readonly_fs",
        description="Path-scoped EROFS/EACCES at filesystem write primitives.",
    ),
    "locked_db": RegisteredInjector(
        name="locked_db",
        description="Real flock contention on runtime.db_lock sidecar path.",
    ),
    "provider_fault": RegisteredInjector(
        name="provider_fault",
        description="Deterministic 503 or timeout at dispatch provider .call.",
    ),
}


@contextmanager
def arm(injector: Injector) -> Iterator[Injector]:
    """Install ``injector`` for the duration of the ``with`` body.

    The try/finally is the safety contract: even if the test body raises, the
    injector gets a chance to restore every primitive it changed.
    """
    injector.install()
    try:
        yield injector
    finally:
        injector.uninstall()
