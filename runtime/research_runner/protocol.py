"""DRW SPR-02 — the ResearchRunner execution contract.

This module defines the *interface* a research runner satisfies and the
plain dataclasses that cross it. It imports neither concrete
implementation, so the host-local runner that ships now and the Daytona
runner that is gated behind CLAUDE.md §16 are interchangeable behind it:
**a call site that targets this protocol needs zero changes when the
operator ratifies §16 and the Daytona impl drops in.** That mirrors the
existing ``runtime/db_lock.WriteCoordinator`` abstraction built for the
autumn-2026 Quack swap.

The unit of work is an Antiek *investigation* (``investigation_id``). One
investigation = one focused deep research running a multi-step *browse
loop*. The runner owns the loop's lifecycle (start / stream / steer /
status / cost / cancel); the loop's actual step logic (Exa retrieval →
Browserbase escalation → claim/insight emission) is injected as a
``BrowseLoop`` and wired by SPR-06 — the runner is deliberately ignorant
of it so it stays testable against a fake loop.

Concurrency model (host-local impl): each investigation's browse loop is
an ``asyncio`` task under a bounded semaphore. Browse loops only ever
append to their own per-investigation event-log JSONL; **no browse loop
writes the graph**. Graph promotion is drained by a single serialized
funnel (``promotion_funnel.py``) through ``runtime/db_lock`` — that is how
N parallel researches coexist with the ``--workers 1`` single-writer
invariant.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import (
    Any,
    AsyncIterator,
    Awaitable,
    Callable,
    Dict,
    List,
    Optional,
    Protocol,
    runtime_checkable,
)


class RunState(str, enum.Enum):
    """Lifecycle states of a single research. ``stopped`` and
    ``budget_halted`` are both terminal-by-steering / terminal-by-policy;
    ``done`` is terminal-by-completion; ``failed`` is terminal-by-error."""

    PENDING = "pending"        # accepted, not yet scheduled (semaphore wait)
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"      # stop requested, sealing in progress
    DONE = "done"
    STOPPED = "stopped"
    FAILED = "failed"
    BUDGET_HALTED = "budget_halted"

    def is_terminal(self) -> bool:
        return self in {RunState.DONE, RunState.STOPPED, RunState.FAILED, RunState.BUDGET_HALTED}


class CommandKind(str, enum.Enum):
    PAUSE = "pause"
    RESUME = "resume"
    STOP = "stop"
    REDIRECT = "redirect"   # inject a revised sub-question
    DEEPEN = "deepen"       # extend budget + queue a follow-up


@dataclass(frozen=True)
class BudgetCap:
    """A research's spend ceiling. ``cost_usd`` is the hard cap; exceeding
    it halts the research. ``max_steps`` bounds runaway loops independently
    of cost (a loop that makes free calls still terminates)."""

    cost_usd: float = 0.50
    max_steps: int = 50


@dataclass(frozen=True)
class ResearchPlan:
    """The approved unit of work handed to the runner. Produced by the
    cascade planner (SPR-05); the runner does not decompose, it executes."""

    investigation_id: str
    sub_question: str
    parent_investigation_id: Optional[str] = None
    budget: BudgetCap = field(default_factory=BudgetCap)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CostState:
    """A live snapshot of a research's spend. ``spent_usd`` reconciles with
    the sum of ``DispatchCall`` cost events the loop's calls emit — the
    runner never invents cost, it accumulates what each step reports."""

    spent_usd: float
    cap_usd: float
    tokens: int
    steps: int

    @property
    def remaining_usd(self) -> float:
        return max(0.0, self.cap_usd - self.spent_usd)

    @property
    def over_budget(self) -> bool:
        return self.spent_usd > self.cap_usd


@dataclass(frozen=True)
class StepEvent:
    """One observable event in a research's stream. ``kind`` partitions the
    glass-box surface (SPR-09): plan/step/cost/note/question/status/error/done."""

    investigation_id: str
    seq: int
    kind: str            # "plan"|"step"|"cost"|"note"|"question"|"status"|"error"|"done"
    text: str = ""
    cost_usd: float = 0.0
    tokens: int = 0
    state: Optional[RunState] = None
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Command:
    """A steer command. ``payload`` carries kind-specific data: redirect →
    ``{"sub_question": str}``; deepen → ``{"extra_budget_usd": float,
    "follow_up": str|None}``."""

    kind: CommandKind
    payload: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Status:
    investigation_id: str
    state: RunState
    sub_question: str
    cost: CostState
    started: bool
    follow_ups: List[str] = field(default_factory=list)
    error: Optional[str] = None


@dataclass(frozen=True)
class Handle:
    """Opaque reference to a started research. Carries only the id; all
    mutable state lives inside the runner, so a handle is safe to pass to
    a UI layer."""

    investigation_id: str


# A browse loop drives one investigation. It receives a LoopContext (defined
# by the concrete runner) and yields StepEvents. Declared loosely here so the
# protocol module stays free of any impl dependency.
BrowseLoop = Callable[[Any], AsyncIterator[StepEvent]]


@runtime_checkable
class ResearchRunner(Protocol):
    """The execution abstraction. Host-local impl ships now; the Daytona
    impl is gated on §16 ratification and is a drop-in behind this
    protocol — no call-site changes.

    Contract:

    * ``start`` accepts a plan, registers the research, and schedules its
      browse loop (subject to the concurrency cap). Returns a Handle
      immediately; it does not block on completion.
    * ``stream`` yields the research's StepEvents in order until a terminal
      event (``kind == "done"``). Multiple consumers are not guaranteed;
      one consumer per handle.
    * ``steer`` applies a Command. A command targeting an already-terminal
      research is a safe no-op, never an error.
    * ``status`` / ``cost`` are synchronous snapshots.
    * ``cancel`` is graceful: it stops the loop, seals the investigation,
      and transitions to ``STOPPED``.
    """

    async def start(self, investigation_id: str, plan: ResearchPlan) -> Handle: ...

    def stream(self, handle: Handle) -> AsyncIterator[StepEvent]: ...

    async def steer(self, handle: Handle, command: Command) -> None: ...

    def status(self, handle: Handle) -> Status: ...

    def cost(self, handle: Handle) -> CostState: ...

    async def cancel(self, handle: Handle) -> None: ...


class StopResearch(Exception):
    """Raised inside a browse loop's checkpoint when a stop/cancel has been
    requested. The runner catches it, seals, and transitions to STOPPED."""


class BudgetExceeded(Exception):
    """Raised when a charge would push a research past its cap (per-research
    or aggregate). The runner catches it and transitions to BUDGET_HALTED."""

    def __init__(self, message: str, *, scope: str):
        super().__init__(message)
        self.scope = scope  # "per_research" | "aggregate"
