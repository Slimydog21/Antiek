"""DRW SPR-02 — the gated Daytona runner stub.

The operator chose Daytona for research fan-out, but **CLAUDE.md §16
explicitly REJECTs Daytona/Modal/Pulumi**, and there is no
``runtime/remote_exec/`` in the tree. This module therefore does **not**
implement Daytona. It is a stub that conforms to the ``ResearchRunner``
protocol so the drop-in is provably shaped correctly, but every method
raises a guard that references §16, and a config flag gates it OFF.

Unlock path (the master-spec Open Question): the operator ratifies
lifting §16 for research fan-out specifically (amend ``CLAUDE.md`` §16 or
the existing ``docs/daytona_integration_spec.md`` draft). Until then the
gate stays closed. **Importing or constructing this class does not enable
it** — only the explicit flag does, and flipping the flag without the
implementation still raises ``NotImplementedError`` because no Daytona SDK
is wired (and none is added to the project's dependencies).
"""

from __future__ import annotations

import os
import sys
from collections.abc import AsyncIterator

try:
    from .protocol import (
        Command,
        CostState,
        Handle,
        ResearchPlan,
        Status,
        StepEvent,
    )
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from runtime.research_runner.protocol import (  # type: ignore[no-redef]
        Command,
        CostState,
        Handle,
        ResearchPlan,
        Status,
        StepEvent,
    )


# The §16 gate. Default OFF. Set ANTIEK_ENABLE_DAYTONA_RUNNER=1 only after
# the operator ratifies §16 — and even then this stub raises, because the
# implementation does not exist yet.
_GATE_ENV = "ANTIEK_ENABLE_DAYTONA_RUNNER"

SIXTEEN_REF = (
    "CLAUDE.md §16 REJECTs Daytona for research fan-out. This is the "
    "documented unlock: the operator must ratify lifting §16 for fan-out "
    "(see the master spec's Open Questions and docs/daytona_integration_spec.md). "
    "The host-local runner (runtime.research_runner.host_local.HostLocalRunner) "
    "is the sanctioned runtime until then."
)


class DaytonaGatedError(RuntimeError):
    """Raised by every DaytonaRunner method while §16 forbids Daytona."""


def daytona_enabled() -> bool:
    """Whether the §16 gate has been lifted via the env flag. Default OFF.
    Reading this never enables anything."""
    return os.environ.get(_GATE_ENV, "0").lower() in ("1", "true", "yes")


class DaytonaRunner:
    """ResearchRunner-shaped stub. Gated on §16; never functional in this
    build. Present so the eventual swap is a provable drop-in (same
    protocol) with zero call-site changes."""

    def __init__(self, *args, **kwargs):
        # Construction is allowed (so the type is importable / checkable),
        # but it records that the gate must be lifted before use.
        self._args, self._kwargs = args, kwargs

    def _guard(self) -> None:
        if not daytona_enabled():
            raise DaytonaGatedError(SIXTEEN_REF)
        # Gate lifted but no implementation exists — and no Daytona SDK is a
        # project dependency. This is the second, deliberate stop.
        raise NotImplementedError(
            "DaytonaRunner is a gated stub: §16 was lifted but the Daytona "
            "implementation has not been built and no Daytona SDK is wired. "
            "Implement against runtime.research_runner.protocol.ResearchRunner."
        )

    async def start(self, investigation_id: str, plan: ResearchPlan) -> Handle:
        self._guard()
        raise AssertionError("unreachable")  # pragma: no cover

    def stream(self, handle: Handle) -> AsyncIterator[StepEvent]:
        self._guard()
        raise AssertionError("unreachable")  # pragma: no cover

    async def steer(self, handle: Handle, command: Command) -> None:
        self._guard()

    def status(self, handle: Handle) -> Status:
        self._guard()
        raise AssertionError("unreachable")  # pragma: no cover

    def cost(self, handle: Handle) -> CostState:
        self._guard()
        raise AssertionError("unreachable")  # pragma: no cover

    async def cancel(self, handle: Handle) -> None:
        self._guard()
