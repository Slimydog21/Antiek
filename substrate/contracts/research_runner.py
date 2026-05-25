"""Research-runner contract — re-export of the DRW SPR-02 execution protocol.

Owned by **DRW SPR-02**, which already ships the protocol at
``runtime/research_runner/protocol.py``. The unified spec's open question —
"does the §16 amendment land before DRW SPR-02 or with it?" — resolves cleanly
here: the protocol is *already defined*, so the contract package does not
redefine it; it **re-exports** it as the canonical, stable import surface that
unified SPR-02's ``RemoteResearchRunner`` builds against.

That keeps the rule "DRW owns the shared primitives; everyone else contracts"
literal: the host-local runner and the §16-gated Daytona runner are
interchangeable behind this one protocol, and SPR-02 imports it from
``substrate.contracts`` rather than reaching into ``runtime/``.

If a future restructuring moves the protocol, only this re-export changes; the
fifty call sites that ``from substrate.contracts import ResearchRunner`` do
not. COMMITTED — the implementation (host-local runner) exists.
"""

from __future__ import annotations

# Re-export the canonical protocol + the dataclasses that cross it. The
# fallback mirrors the codebase's direct-script import idiom.
try:
    from runtime.research_runner.protocol import (
        BudgetCap,
        BudgetExceeded,
        Command,
        CommandKind,
        CostState,
        Handle,
        ResearchPlan,
        ResearchRunner,
        RunState,
        Status,
        StepEvent,
        StopResearch,
    )
except ImportError:  # pragma: no cover — direct-script fallback
    import os
    import sys

    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from runtime.research_runner.protocol import (  # noqa: F811
        BudgetCap,
        BudgetExceeded,
        Command,
        CommandKind,
        CostState,
        Handle,
        ResearchPlan,
        ResearchRunner,
        RunState,
        Status,
        StepEvent,
        StopResearch,
    )

__all__ = [
    "ResearchRunner",
    "StepEvent",
    "RunState",
    "ResearchPlan",
    "BudgetCap",
    "CostState",
    "Command",
    "CommandKind",
    "Status",
    "Handle",
    "StopResearch",
    "BudgetExceeded",
]
