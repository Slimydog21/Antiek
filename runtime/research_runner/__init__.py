"""DRW SPR-02 — ResearchRunner: parallel deep-research execution.

Public surface for the Deep Research Workspace's fan-out runtime. The
protocol is the contract; ``HostLocalRunner`` is the implementation that
ships now; ``DaytonaRunner`` is gated on CLAUDE.md §16. ``PromotionFunnel``
is the single serialized path research output takes into the graph.

    from runtime.research_runner import (
        HostLocalRunner, ResearchPlan, BudgetCap, Command, CommandKind,
        PromotionFunnel,
    )
"""

from __future__ import annotations

from .budget import BudgetManager
from .cost_projection import project_cascade_cost

# Imported from ``daytona_gated`` (not ``daytona``) deliberately: the
# tier-0 integration checker keys on the top-level import name, and a module
# literally named ``daytona`` would read as importing the §16-REJECTed
# Daytona SDK. This stub imports no Daytona SDK — it refuses to run.
from .daytona_gated import DaytonaGatedError, DaytonaRunner, daytona_enabled
from .host_local import (
    DEFAULT_MAX_CONCURRENCY,
    HostLocalRunner,
    LoopContext,
    make_contract_gather_stub,
    make_demo_loop,
    make_exa_gather_loop,
)
from .promotion_funnel import PromotionFunnel
from .protocol import (
    BillingUnit,
    BoundedUsage,
    BudgetCap,
    BudgetExceeded,
    Command,
    CommandKind,
    CostProjection,
    CostProjectionRequest,
    CostState,
    Handle,
    ProjectionDisposition,
    ProjectionIneligibility,
    ProjectionRate,
    ResearchPlan,
    ResearchRunner,
    RunState,
    SpendControlMode,
    Status,
    StepEvent,
    StopResearch,
)

__all__ = [
    # protocol
    "ResearchRunner", "ResearchPlan", "BudgetCap", "Command", "CommandKind",
    "CostState", "Handle", "RunState", "Status", "StepEvent",
    "StopResearch", "BudgetExceeded", "SpendControlMode",
    "BillingUnit", "BoundedUsage", "CostProjectionRequest", "CostProjection",
    "ProjectionDisposition", "ProjectionIneligibility",
    "ProjectionRate",
    "project_cascade_cost",
    # impls + machinery
    "HostLocalRunner", "LoopContext", "make_demo_loop",
    "make_contract_gather_stub", "make_exa_gather_loop",
    "DEFAULT_MAX_CONCURRENCY",
    "BudgetManager", "PromotionFunnel",
    # gated
    "DaytonaRunner", "DaytonaGatedError", "daytona_enabled",
]
