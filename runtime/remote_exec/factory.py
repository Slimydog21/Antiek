"""Runner factory — remote vs host-local, with host-local as the safe fallback.

This is M6: the one place that decides whether a fan-out runs remotely or on
the host, so **call sites stay runner-agnostic** — DRW SPR-06's orchestration
asks the factory for a ``ResearchRunner`` and drives it through the protocol,
never branching on which runner it got.

The decision, in order:

  1. If remote-exec is **disabled** (``ANTIEK_REMOTE_EXEC_ENABLED`` is unset or
     falsy, and no explicit ``enabled=True``) → ``HostLocalRunner``. Silent in
     the sense that this is the documented default; no warning, because
     host-local *is* the sanctioned baseline.
  2. If remote-exec is **enabled** but the provider is **unavailable at launch**
     (SDK missing / credentials missing — surfaced as ``RemoteExecUnavailable``
     when we probe the provider) → ``HostLocalRunner`` **plus one logged
     line**. This is an operational state worth seeing: the operator asked for
     remote and got host-local, so it is logged once at WARNING — not a crash,
     not a silent swallow.
  3. If remote-exec is enabled and the provider is available → ``RemoteResearchRunner``.

Honoring the steelman (rigor #2): host-local is the *automatic* fallback for
both the disabled case and the unavailable case. A cascade launched under
fallback runs at the host-local ceiling and the returned runner *is* the
host-local one, so a status surface that reports the runner kind says so.

The factory takes both a ``loop_fn`` (for host-local) and a ``provider_factory``
(for remote) so it can construct whichever it selects without the caller
pre-building both. ``provider_factory`` is a zero-arg callable that returns a
``RemoteExecProvider`` (or raises ``RemoteExecUnavailable``); the default
builds a ``DaytonaProvider`` and probes it.
"""

from __future__ import annotations

import logging
import os
import sys
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

try:
    from ..research_runner.budget import BudgetManager
    from ..research_runner.host_local import HostLocalRunner, LoopContext
    from ..research_runner.protocol import ResearchRunner, StepEvent
    from .provider import RemoteExecProvider, RemoteExecUnavailable
    from .runner import RemoteResearchRunner
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from runtime.remote_exec.provider import (  # type: ignore[no-redef]
        RemoteExecProvider,
        RemoteExecUnavailable,
    )
    from runtime.remote_exec.runner import RemoteResearchRunner  # type: ignore[no-redef]
    from runtime.research_runner.budget import BudgetManager  # type: ignore[no-redef]
    from runtime.research_runner.host_local import (  # type: ignore[no-redef]
        HostLocalRunner,
        LoopContext,
    )
    from runtime.research_runner.protocol import (  # type: ignore[no-redef]
        ResearchRunner,
        StepEvent,
    )


logger = logging.getLogger("antiek.remote_exec")

ENABLE_ENV = "ANTIEK_REMOTE_EXEC_ENABLED"


def remote_exec_enabled(*, explicit: bool | None = None) -> bool:
    """Whether remote-exec is enabled. ``explicit`` (from config) wins over the
    env flag; absent both, the default is OFF — host-local is the baseline.
    Reading this never enables anything and never touches the network."""
    if explicit is not None:
        return explicit
    return os.environ.get(ENABLE_ENV, "0").lower() in ("1", "true", "yes")


def _default_provider_factory() -> RemoteExecProvider:
    """Build the production provider (Daytona) and return it. Construction is
    cheap and does not import the SDK (the SDK loads lazily on first use); the
    availability probe below is what surfaces a missing SDK / credential as
    ``RemoteExecUnavailable``."""
    from .daytona import DaytonaProvider  # local import: keeps factory import light

    return DaytonaProvider()


def _probe_available(provider: RemoteExecProvider) -> None:
    """Raise ``RemoteExecUnavailable`` if the provider cannot run — without
    provisioning a real sandbox. For Daytona this resolves credentials + loads
    the SDK lazily (both raise ``RemoteExecUnavailable`` loudly if missing).
    A provider with no probe hook is assumed available (the fake provider in
    tests is always available)."""
    probe = getattr(provider, "probe", None)
    if callable(probe):
        probe()


def build_research_runner(
    *,
    loop_fn: Callable[[LoopContext], AsyncIterator[StepEvent]],
    enabled: bool | None = None,
    provider: RemoteExecProvider | None = None,
    provider_factory: Callable[[], RemoteExecProvider] | None = None,
    budget: BudgetManager | None = None,
    max_concurrency: int | None = None,
    events_dir: str | None = None,
    outbox_db_path: str | None = None,
    on_emit: Callable[[StepEvent], Awaitable[None]] | None = None,
) -> ResearchRunner:
    """Return the ``ResearchRunner`` the fan-out should use. Call-site-agnostic:
    the caller drives the result through the protocol and never branches on
    type.

    * ``loop_fn`` — the host-local browse loop (used when host-local is
      selected; the remote runner's loop runs in-sandbox so it does not need
      this).
    * ``enabled`` — config override; ``None`` defers to the ``ANTIEK_REMOTE_EXEC_ENABLED``
      env flag.
    * ``provider`` / ``provider_factory`` — inject a provider directly (tests
      pass a fake) or a zero-arg factory (production defaults to Daytona).
      ``provider`` wins if both given.

    Selection + fallback semantics are documented at module level. The
    unavailable-fallback logs exactly one WARNING line."""
    shared_budget = budget or BudgetManager()

    def _shared_kwargs() -> dict[str, Any]:
        kw: dict[str, Any] = {
            "budget": shared_budget,
            "events_dir": events_dir,
            "outbox_db_path": outbox_db_path,
            "on_emit": on_emit,
        }
        if max_concurrency is not None:
            kw["max_concurrency"] = max_concurrency
        return kw

    def _host_local(reason: str | None = None) -> HostLocalRunner:
        if reason:
            logger.warning(
                "remote-exec requested but unavailable (%s); falling back to "
                "HostLocalRunner — the cascade runs at the host-local "
                "concurrency ceiling. Set %s=0 to make this the explicit "
                "default and silence this line.",
                reason, ENABLE_ENV,
            )
        return HostLocalRunner(loop_fn, **_shared_kwargs())

    if not remote_exec_enabled(explicit=enabled):
        # Disabled — host-local is the documented default. No warning.
        return _host_local()

    # Enabled — resolve a provider and probe its availability at launch time.
    try:
        prov = provider if provider is not None else (
            provider_factory() if provider_factory is not None
            else _default_provider_factory()
        )
        _probe_available(prov)
    except RemoteExecUnavailable as exc:
        # The exactly-one-fallback site that intentionally catches
        # RemoteExecUnavailable (the provider never swallows it). One WARNING.
        return _host_local(reason=str(exc))

    logger.info("remote-exec enabled and available (provider=%s); using "
                "RemoteResearchRunner.", getattr(prov, "name", "remote"))
    return RemoteResearchRunner(prov, **_shared_kwargs())


__all__ = ["build_research_runner", "remote_exec_enabled", "ENABLE_ENV"]
