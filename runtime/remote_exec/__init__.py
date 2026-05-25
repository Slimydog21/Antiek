"""``runtime.remote_exec`` — off-host research fan-out (unified SPR-02).

The §16 research-fan-out exemption (operator-ratified 2026-05-25; see
``docs/decisions/s16-research-fanout-exemption.md``) is what this package
implements: a real external-execution provider behind DRW's ``ResearchRunner``
protocol, so a Deep Research Workspace cascade can run N sub-question
researches genuinely concurrently *off-host* rather than capped at the single
host VM. Everything else in §16 stays put — dispatch is Hermes-primary, the
DuckDB single-writer invariant is untouched.

The pieces, one owner per layer:

  * ``provider`` — ``RemoteExecProvider`` interface (provision / run / steer /
    teardown) + the loud-failure exception hierarchy
    (``RemoteExecUnavailable`` mirrors Browserbase's ``BrowserbaseUnavailable``).
  * ``daytona`` — the one provider implementation, with the Daytona SDK behind
    a lazy import + the ``[remote_exec]`` optional dep group. Imports cleanly
    without the SDK; raises ``RemoteExecUnavailable`` loudly if you try to run
    remotely without it.
  * ``runner`` — ``RemoteResearchRunner``, the remote sibling of
    ``HostLocalRunner``. Same ``ResearchRunner`` protocol; identical
    ``StepEvent`` shape; tears the sandbox down on completion / cancel / error.
  * ``funnel`` — ``RemotePromotionFunnel``, the **single** host-side graph
    writer (the only ``connect_write`` caller in this package). Reuses DRW's
    serialized ``PromotionFunnel`` so there is one promotion path, shared.
  * ``cost`` — emits ``DispatchCall`` events for remote spend in the same shape
    host-local dispatch emits; enforces the per-research + aggregate budget.
  * ``factory`` — selects remote vs host-local from config/env; host-local is
    the automatic fallback when remote-exec is disabled or unavailable.

Importing this package does **not** import the Daytona SDK and does **not**
touch the network — the lazy import inside ``daytona`` keeps the package
loadable on a machine that never installed the optional dependency.
"""

from __future__ import annotations

from .cost import record_remote_dispatch
from .factory import ENABLE_ENV, build_research_runner, remote_exec_enabled
from .funnel import RemotePromotionFunnel
from .provider import (
    RemoteCommand,
    RemoteExecProvider,
    RemoteExecProviderError,
    RemoteExecProvisionError,
    RemoteExecRuntimeError,
    RemoteExecUnavailable,
    RemoteSignal,
    RemoteStepEvent,
    Sandbox,
)
from .runner import DEFAULT_MAX_CONCURRENCY, RemoteResearchRunner

__all__ = [
    # provider interface + exceptions
    "RemoteExecProvider",
    "RemoteExecProviderError",
    "RemoteExecUnavailable",
    "RemoteExecProvisionError",
    "RemoteExecRuntimeError",
    "RemoteSignal",
    "RemoteCommand",
    "Sandbox",
    "RemoteStepEvent",
    # runner + machinery
    "RemoteResearchRunner",
    "DEFAULT_MAX_CONCURRENCY",
    "RemotePromotionFunnel",
    "record_remote_dispatch",
    # factory
    "build_research_runner",
    "remote_exec_enabled",
    "ENABLE_ENV",
]
