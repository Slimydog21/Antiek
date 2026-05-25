"""The ``RemoteExecProvider`` interface — what a remote sandbox must offer.

A remote-exec provider is the thing that turns "run this browse loop" into
"run this browse loop in a sandbox that is not this host's process." The
``RemoteResearchRunner`` (``runner.py``) talks to *this* interface and nothing
provider-specific, so swapping Daytona for some future provider is a one-class
change behind a frozen seam — the same drop-in discipline the
``runtime/db_lock.WriteCoordinator`` abstraction has for the autumn-2026 Quack
swap, and the same discipline the ``ResearchRunner`` protocol itself has for
host-local vs remote.

The lifecycle a provider implements, per investigation:

  * ``provision`` — allocate a sandbox for one investigation. Returns a
    ``Sandbox`` handle. Idempotent per investigation_id is **not** required;
    the runner provisions exactly once per leaf.
  * ``run`` — start the browse loop inside the sandbox and return an async
    iterator of ``RemoteStepEvent``s. The iterator ends when the loop
    completes, fails, or is torn down. The provider streams; it does not
    buffer the whole run.
  * ``steer`` — inject a steering signal (redirect / deepen / pause / stop /
    resume) into the running loop. Cooperative, like the host-local
    checkpoint — never a thread-kill.
  * ``teardown`` — destroy the sandbox and reclaim its resources. Called on
    completion, on cancel, and on error. Must be safe to call more than once
    (the runner may call it on cancel and the provider may already have torn
    down on completion).

Cost reporting is carried *on the events* (``RemoteStepEvent.cost_usd`` /
``.tokens``) rather than via a separate poll, so a remote research's spend
flows through the same per-step charging the host-local runner uses — which
is what lets the cost path (``cost.py``) emit ``DispatchCall`` events
indistinguishable in shape from host-local dispatch.

The interface is a ``runtime_checkable`` ``Protocol`` so a fake provider in
the test suite satisfies it structurally without inheriting — exactly how the
tests exercise the runner with zero network and zero Daytona credentials.

Failure discipline mirrors ``acquisition/urls/client_browserbase.py``: a
common ``RemoteExecProviderError`` base with concrete subclasses, and a
``RemoteExecUnavailable`` raised loudly when the SDK or credentials are
missing and remote-exec was *enabled* — never a silent degradation that hides
a misconfiguration. (Falling back to host-local is the factory's explicit
decision, not a swallowed import error here.)
"""

from __future__ import annotations

import enum
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import (
    Any,
    Protocol,
    runtime_checkable,
)


class RemoteExecProviderError(RuntimeError):
    """Common base for every remote-exec failure the runner should surface
    loudly. Mirrors ``BrowserbaseProviderError`` in
    ``acquisition/urls/client_browserbase.py``: ``except
    RemoteExecProviderError`` catches all of them; the concrete subclasses
    distinguish the failure mode (config vs provision vs runtime) so callers
    can branch informatively. No remote-exec failure degrades silently."""


class RemoteExecUnavailable(RemoteExecProviderError):
    """Raised when the remote-exec SDK is not installed (or credentials are
    missing) and the caller asked to run remotely. Loud, not silent — the
    remote path is opt-in (``ANTIEK_REMOTE_EXEC_ENABLED=1``) and a missing
    SDK / credential is a config error, not a reason to quietly run on the
    host.

    The runner factory (``factory.py``) is the one place that *intentionally*
    catches this and falls back to host-local — and it logs that fallback
    once. The provider itself never swallows it."""


class RemoteExecProvisionError(RemoteExecProviderError):
    """Raised when a sandbox could not be allocated (quota, transient
    provider outage, image pull failure). Distinguished from
    ``RemoteExecUnavailable`` (which is a config error) so the runner can mark
    the *one* leaf failed without concluding the whole provider is down."""


class RemoteExecRuntimeError(RemoteExecProviderError):
    """Raised when a sandbox was provisioned and ran but the run failed
    unrecoverably (the remote process crashed, the channel dropped). The
    runner catches it, transitions the leaf to ``FAILED``, and tears the
    sandbox down."""


class RemoteSignal(str, enum.Enum):
    """A steering signal injected into a running remote loop. The provider
    relays it to the in-sandbox loop's cooperative checkpoint — the remote
    analogue of ``LoopContext.checkpoint()`` in the host-local runner.
    ``REDIRECT`` / ``DEEPEN`` carry payload data on the ``RemoteCommand``."""

    PAUSE = "pause"
    RESUME = "resume"
    STOP = "stop"
    REDIRECT = "redirect"
    DEEPEN = "deepen"


@dataclass(frozen=True)
class RemoteCommand:
    """A steering command crossing the provider seam. ``payload`` carries the
    same kind-specific data the host-local ``Command`` does: redirect →
    ``{"sub_question": str}``; deepen → ``{"extra_budget_usd": float,
    "follow_up": str|None}``."""

    signal: RemoteSignal
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Sandbox:
    """An opaque handle to one provisioned remote sandbox. Carries the id the
    provider uses to address it plus a free-form ``meta`` the provider may
    stash connection details in. The runner treats it as opaque — it only
    ever hands it back to the provider."""

    sandbox_id: str
    investigation_id: str
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RemoteStepEvent:
    """One event streamed back from a remote browse loop. Carries exactly the
    fields the host-local ``StepEvent`` carries (``kind`` / ``text`` /
    ``cost_usd`` / ``tokens`` / ``data``) plus the ``seq`` the in-sandbox loop
    assigned. The runner maps this 1:1 onto ``StepEvent`` so DRW SPR-06's
    orchestration and SPR-09's UI cannot tell which runner produced an
    event — that identity is the whole point.

    ``cost_usd`` here is the *realized* cost the sandbox reports for the step
    (sandbox time slice + the inference the step ran), not an estimate. The
    runner charges the budget from it and the cost path emits a
    ``DispatchCall`` event with it."""

    seq: int
    kind: str  # "plan"|"step"|"cost"|"note"|"question"|"status"|"error"|"done"
    text: str = ""
    cost_usd: float = 0.0
    tokens: int = 0
    provider: str = ""
    model: str = ""
    data: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class RemoteExecProvider(Protocol):
    """The remote-execution seam. A fake in the test suite satisfies this
    structurally (no inheritance, no network); the Daytona implementation
    satisfies it for real.

    Contract:

    * ``name`` identifies the provider in cost events (``DispatchCall.provider``)
      and logs. A property, not a method.
    * ``provision`` allocates one sandbox for one investigation. May raise
      ``RemoteExecUnavailable`` (config) or ``RemoteExecProvisionError``
      (transient).
    * ``run`` starts the loop in the sandbox and yields ``RemoteStepEvent``s
      until terminal. Must end the iterator (not hang) on completion, failure,
      or teardown.
    * ``steer`` relays a ``RemoteCommand`` into the running loop. A command to
      an already-finished loop is a safe no-op.
    * ``teardown`` destroys the sandbox. Idempotent — safe to call twice.
    """

    @property
    def name(self) -> str: ...

    async def provision(self, plan: Any) -> Sandbox: ...

    def run(self, sandbox: Sandbox, plan: Any) -> AsyncIterator[RemoteStepEvent]: ...

    async def steer(self, sandbox: Sandbox, command: RemoteCommand) -> None: ...

    async def teardown(self, sandbox: Sandbox) -> None: ...


__all__ = [
    "RemoteExecProvider",
    "RemoteExecProviderError",
    "RemoteExecUnavailable",
    "RemoteExecProvisionError",
    "RemoteExecRuntimeError",
    "RemoteSignal",
    "RemoteCommand",
    "Sandbox",
    "RemoteStepEvent",
]
