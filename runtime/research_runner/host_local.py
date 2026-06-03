"""DRW SPR-02 — the host-local ResearchRunner implementation.

Runs each investigation's browse loop as an ``asyncio`` task under a
bounded semaphore. **In-process asyncio, not a process pool** — this is a
deliberate choice to avoid the loky/multiprocessing external-kill
semaphore failure already recorded at ``parameter_extractor`` (a worker
killed out-of-band left a semaphore leaked and wedged the pool). Browse
loops are I/O-bound (Exa / Browserbase network calls), so asyncio
multiplexes them on one thread with no GIL contention and no external
process to be killed.

Concurrency ceiling — honest report (rigor #1)
----------------------------------------------
asyncio itself imposes no hard cap on the number of concurrent I/O-bound
tasks: the ``DEFAULT_MAX_CONCURRENCY`` semaphore below is a *policy* cap,
not a runtime limit, and the test starts 20 loops concurrently to prove
it. The real binding ceiling on live browse loops is downstream and is
**not** raised by switching to Daytona's per-box isolation:

  * Browserbase escalation is capped at 3 concurrent sessions per process
    (``acquisition/urls/client_browserbase`` ``MAX_CONCURRENT_SESSIONS``);
  * aggregate spend is bounded by ``TOTAL_ACQUISITION_BUDGET_USD``;
  * Exa has its own per-key rate limits.

So "launch 20 at once" is reachable for the *orchestration* (20 loops
multiplexed fine), but the *escalation-heavy* fraction serializes behind
the 3-session Browserbase cap regardless of runner. That is the measured,
defensible statement — not "20 parallel full-throughput browse loops".
The default cap mirrors the product target (20); raise it only with a
profiling note.

Single-writer safety
---------------------
A browse loop **never** opens a graph write connection. It appends only to
its own per-investigation JSONL (keyed by ``investigation_id`` — automatic
isolation) and yields ``StepEvent``s. Graph promotion is the
``promotion_funnel``'s job, serialized through ``db_lock``.
"""

from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

try:
    from ...event_log import log_event, seal_investigation
    from ...schemas.events import ActionType
    from .budget import BudgetManager
    from .protocol import (
        BudgetExceeded,
        Command,
        CommandKind,
        CostState,
        Handle,
        ResearchPlan,
        RunState,
        Status,
        StepEvent,
        StopResearch,
    )
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from runtime.research_runner.budget import BudgetManager  # type: ignore[no-redef]
    from runtime.research_runner.protocol import (  # type: ignore[no-redef]
        BudgetExceeded,
        Command,
        CommandKind,
        CostState,
        Handle,
        ResearchPlan,
        RunState,
        Status,
        StepEvent,
        StopResearch,
    )
    from substrate.event_log import log_event, seal_investigation  # type: ignore[no-redef]
    from substrate.schemas.events import ActionType  # type: ignore[no-redef]


# Policy cap, not a runtime limit — see module docstring. The product
# target is "launch 20 at once"; this is that target.
DEFAULT_MAX_CONCURRENCY = 20

# Sentinel pushed onto a research's stream queue to end iteration.
_STREAM_DONE = object()


class LoopContext:
    """Handed to a browse loop. Exposes the steerable checkpoint, cost
    charging, and StepEvent factories. The loop awaits ``checkpoint()`` at
    the top of each iteration; that is the single point at which pause /
    stop / redirect take effect (cooperative steering — no thread-kill)."""

    def __init__(self, plan: ResearchPlan, budget: BudgetManager):
        self.plan = plan
        self.investigation_id = plan.investigation_id
        self.sub_question = plan.sub_question
        self._budget = budget
        self._seq = 0
        self._resume = asyncio.Event()
        self._resume.set()                # starts un-paused
        self._stop = False
        self._pending_redirect: str | None = None
        self.paused = False
        # ACV SPR-06 — the assembled reuse pack from this investigation's
        # ``start`` (the units ``_maybe_reuse_prior_knowledge`` injected). A
        # reuse-CONSUMING browse loop reads this to short-circuit planned steps
        # already covered by a reused unit (so cost drops when primed). It is a
        # PLAIN READ-ONLY list of ``RetrievedUnit`` — the loop never writes the
        # graph through it (§16). ``None`` for the cold path / a loop that
        # ignores reuse (the demo loop), so reading it is purely additive and
        # the demo loop is byte-unchanged.
        self.pack: list[Any] | None = None

    # -- steering (mutated by the runner from steer()) -----------------

    def request_pause(self) -> None:
        self.paused = True
        self._resume.clear()

    def request_resume(self) -> None:
        self.paused = False
        self._resume.set()

    def request_stop(self) -> None:
        self._stop = True
        self._resume.set()                # unblock a paused loop so it can stop

    def request_redirect(self, sub_question: str) -> None:
        self._pending_redirect = sub_question
        self._resume.set()

    async def checkpoint(self) -> str:
        """Block while paused; raise ``StopResearch`` if stopped; apply a
        pending redirect. Returns the current (possibly redirected)
        sub-question so the loop can adapt mid-flight."""
        if self._stop:
            raise StopResearch(self.investigation_id)
        await self._resume.wait()
        if self._stop:
            raise StopResearch(self.investigation_id)
        if self._pending_redirect is not None:
            self.sub_question = self._pending_redirect
            self._pending_redirect = None
        return self.sub_question

    # -- StepEvent factories -------------------------------------------

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def step(self, text: str, *, cost_usd: float = 0.0, tokens: int = 0, **data) -> StepEvent:
        return StepEvent(self.investigation_id, self._next_seq(), "step",
                         text=text, cost_usd=cost_usd, tokens=tokens, data=data)

    def note(self, text: str, **data) -> StepEvent:
        return StepEvent(self.investigation_id, self._next_seq(), "note", text=text, data=data)

    def question(self, text: str, **data) -> StepEvent:
        return StepEvent(self.investigation_id, self._next_seq(), "question", text=text, data=data)

    def plan_event(self, text: str, **data) -> StepEvent:
        return StepEvent(self.investigation_id, self._next_seq(), "plan", text=text, data=data)


class _ResearchState:
    def __init__(self, plan: ResearchPlan):
        self.plan = plan
        self.state = RunState.PENDING
        self.ctx: LoopContext | None = None
        self.queue: asyncio.Queue = asyncio.Queue()
        self.task: asyncio.Task | None = None
        self.error: str | None = None
        self.follow_ups: list[str] = []
        self.started = False
        # ACV SPR-06 — the reuse pack assembled in ``start`` (before the loop's
        # LoopContext exists). Captured here so ``_run`` can attach it to the
        # context the reuse-consuming loop reads. Empty list (not None) once
        # reuse ran, even if it retrieved nothing — so the consuming loop sees
        # "reuse ran, covered nothing" distinctly from "no reuse path".
        self.reuse_pack: list[Any] | None = None


class HostLocalRunner:
    """In-process asyncio runner. Conforms to the ResearchRunner protocol."""

    def __init__(
        self,
        loop_fn: Callable[[LoopContext], AsyncIterator[StepEvent]],
        *,
        max_concurrency: int = DEFAULT_MAX_CONCURRENCY,
        budget: BudgetManager | None = None,
        events_dir: str | None = None,
        seal_on_complete: bool = True,
        on_emit: Callable[[StepEvent], Awaitable[None]] | None = None,
        retrieval_substrate: object | None = None,
        reuse_role: str = "user_agent",
    ):
        self._loop_fn = loop_fn
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self.max_concurrency = max_concurrency
        self.budget = budget or BudgetManager()
        self._events_dir = events_dir
        self._seal_on_complete = seal_on_complete
        # Optional async hook the promotion funnel subscribes to so notes /
        # questions get drained as they are emitted.
        self._on_emit = on_emit
        # AFF SPR-06 — the flywheel's reuse half. When a RetrievalSubstrate is
        # injected, ``start`` retrieves prior knowledge units relevant to the
        # plan's question and injects the §9.0-servable, token-bounded top-k into
        # a reuse context layer + emits one knowledge.reused event, BEFORE the
        # browse loop emits its first step. When it is None (the default + the
        # automatic fallback when retrieval is unavailable), ``start`` behaves
        # exactly as before — reuse is purely additive. This is NOT a new
        # protocol method and NOT a forked runner (§16): it is an in-place
        # extension of the existing ``start`` lifecycle stage.
        self._retrieval_substrate = retrieval_substrate
        self._reuse_role = reuse_role
        self._states: dict[str, _ResearchState] = {}

    # -- protocol: start -----------------------------------------------

    async def start(self, investigation_id: str, plan: ResearchPlan) -> Handle:
        st = _ResearchState(plan)
        self._states[investigation_id] = st
        self.budget.register(investigation_id, plan.budget.cost_usd)

        if plan.parent_investigation_id:
            log_event(
                investigation_id, ActionType.INVESTIGATION_SPAWNED_FROM,
                payload={"parent_investigation_id": plan.parent_investigation_id,
                         "sub_question": plan.sub_question},
                role="user_agent", events_dir=self._events_dir,
            )

        # Aggregate-cap gate: refuse the launch with a surfaced reason rather
        # than starting a loop we will immediately have to halt.
        if not self.budget.can_launch(plan.budget.cost_usd):
            reason = self.budget.launch_block_reason()
            st.state = RunState.BUDGET_HALTED
            st.error = reason
            log_event(investigation_id, ActionType.INVESTIGATION_CHASE_HALTED,
                      payload={"reason": "aggregate_budget", "detail": reason},
                      role="user_agent", events_dir=self._events_dir)
            await st.queue.put(StepEvent(investigation_id, 0, "status",
                                         text=reason, state=RunState.BUDGET_HALTED))
            await st.queue.put(StepEvent(investigation_id, 0, "done",
                                         state=RunState.BUDGET_HALTED))
            await st.queue.put(_STREAM_DONE)
            return Handle(investigation_id)

        # AFF SPR-06 — retrieve + inject prior knowledge units ONCE, here, before
        # the browse loop is scheduled (so the reuse layer + knowledge.reused
        # event land before the first StepEvent the loop emits). No-op unless a
        # RetrievalSubstrate was injected; non-fatal on any failure (a retrieval
        # hiccup must degrade to "no reuse", never a dead investigation).
        # ACV SPR-06: the retrieved units are captured on the state so ``_run``
        # can thread them onto the LoopContext a reuse-CONSUMING loop reads.
        st.reuse_pack = self._maybe_reuse_prior_knowledge(investigation_id, plan)

        st.task = asyncio.create_task(self._run(st))
        return Handle(investigation_id)

    def _maybe_reuse_prior_knowledge(
        self, investigation_id: str, plan: ResearchPlan
    ) -> list[Any] | None:
        """AFF SPR-06 reuse hook (called exactly once from ``start``).

        Composes ``substrate.context_pack.knowledge_reuse`` — retrieve prior
        units relevant to ``plan.sub_question``, filter to §9.0-servable +
        token-bounded top-k, inject a single reuse layer into a context pack, and
        emit one ``knowledge.reused`` event on this investigation's JSONL. Lives
        on the existing ``start`` path; adds no ResearchRunner protocol method.

        ACV SPR-06: returns the INJECTED units (``assemble_context_pack_with_reuse``
        already filtered them through §9.0-servability + the SPR-08 trust gate +
        the relevance floor + the token budget, so this is exactly the pack the
        model would see) so ``start`` can thread them onto the LoopContext a
        reuse-CONSUMING loop reads. Returns ``None`` when no retrieval substrate
        was injected (the cold path) and ``[]`` when reuse ran but injected
        nothing (novel question) — the two are distinct so the loop can tell
        "no reuse path" from "reuse covered nothing"."""
        if self._retrieval_substrate is None:
            return None
        try:
            from substrate.context_pack.knowledge_reuse import (
                assemble_context_pack_with_reuse,
                retrieve_prior_units,
            )
        except ImportError:  # pragma: no cover — defensive
            return None
        try:
            units = retrieve_prior_units(
                self._retrieval_substrate,
                question_text=plan.sub_question,
            )
            pack = assemble_context_pack_with_reuse(
                role=self._reuse_role,
                investigation_id=investigation_id,
                layers=[],
                units=units,
                events_dir=self._events_dir,
            )
            # The INJECTED set only — the units that cleared every gate and
            # actually landed in the pack. A consuming loop must only ever skip
            # work a GENUINELY-injected unit covers, never a retrieved-but-
            # dropped one (rigor #1: never fabricate a saving).
            return list(pack.injected)
        except Exception:  # pragma: no cover — reuse never breaks a research
            return []

    # -- the per-research coroutine ------------------------------------

    async def _run(self, st: _ResearchState) -> None:
        iid = st.plan.investigation_id
        async with self._semaphore:        # bounded concurrency
            st.started = True
            ctx = LoopContext(st.plan, self.budget)
            # ACV SPR-06 — thread the reuse pack assembled in ``start`` onto the
            # context so a reuse-CONSUMING loop can read ``ctx.pack`` and skip
            # work already covered. None for the cold/no-substrate path; the demo
            # loop ignores it (byte-unchanged).
            ctx.pack = st.reuse_pack
            st.ctx = ctx
            st.state = RunState.RUNNING
            # Durable lifecycle marker on the per-investigation JSONL (the
            # fine-grained step stream stays in-memory for live monitoring;
            # SPR-06 decides what else to persist). Each investigation writes
            # only its own file — automatic isolation by investigation_id.
            log_event(iid, ActionType.INVESTIGATION_START_REQUESTED,
                      payload={"sub_question": ctx.sub_question},
                      role="user_agent", events_dir=self._events_dir)
            await self._push(st, StepEvent(iid, 0, "status", text="running",
                                           state=RunState.RUNNING))
            try:
                async for ev in self._loop_fn(ctx):
                    st.state = RunState.PAUSED if ctx.paused else RunState.RUNNING
                    # Charge budget from the cost the step reports — this is
                    # the same number the step's DispatchCall events carry, so
                    # the ledger reconciles with dispatch by construction.
                    if ev.cost_usd or ev.tokens:
                        self.budget.charge(iid, ev.cost_usd, ev.tokens)
                    if ev.kind == "step" and self.budget.steps(iid) > st.plan.budget.max_steps:
                        raise BudgetExceeded(
                            f"{iid} exceeded max_steps={st.plan.budget.max_steps}",
                            scope="per_research",
                        )
                    await self._push(st, ev)
            except StopResearch:
                st.state = RunState.STOPPED
                await self._finish(st, ActionType.INVESTIGATION_COMPLETED,
                                   {"outcome": "stopped"})
                return
            except BudgetExceeded as exc:
                st.state = RunState.BUDGET_HALTED
                st.error = str(exc)
                log_event(iid, ActionType.INVESTIGATION_CHASE_HALTED,
                          payload={"reason": exc.scope, "detail": str(exc),
                                   "spent_usd": self.budget.spent(iid)},
                          role="user_agent", events_dir=self._events_dir)
                await self._finish(st, None, None, halted=True)
                return
            except asyncio.CancelledError:
                st.state = RunState.STOPPED
                await self._finish(st, ActionType.INVESTIGATION_COMPLETED,
                                   {"outcome": "cancelled"})
                raise
            except Exception as exc:        # one loop failing must not kill siblings
                st.state = RunState.FAILED
                st.error = f"{type(exc).__name__}: {exc}"
                log_event(iid, ActionType.INVESTIGATION_FAILED,
                          payload={"error": st.error}, role="user_agent",
                          events_dir=self._events_dir)
                await self._push(st, StepEvent(iid, 0, "error", text=st.error,
                                               state=RunState.FAILED))
                await self._finish(st, None, None, already_logged=True)
                return
            st.state = RunState.DONE
            await self._finish(st, ActionType.INVESTIGATION_COMPLETED, {"outcome": "done"})

    async def _push(self, st: _ResearchState, ev: StepEvent) -> None:
        await st.queue.put(ev)
        if self._on_emit is not None and ev.kind in ("note", "question"):
            await self._on_emit(ev)

    async def _finish(self, st, action, payload, *, halted=False, already_logged=False) -> None:
        iid = st.plan.investigation_id
        if action is not None and not already_logged:
            log_event(iid, action, payload=payload or {}, role="user_agent",
                      events_dir=self._events_dir)
        if self._seal_on_complete:
            try:
                seal_investigation(iid, events_dir=self._events_dir)
            except Exception:  # pragma: no cover — seal is best-effort
                pass
        await st.queue.put(StepEvent(iid, 0, "done", state=st.state))
        await st.queue.put(_STREAM_DONE)

    # -- protocol: stream ----------------------------------------------

    async def stream(self, handle: Handle) -> AsyncIterator[StepEvent]:
        st = self._states[handle.investigation_id]
        while True:
            item = await st.queue.get()
            if item is _STREAM_DONE:
                return
            yield item

    # -- protocol: steer -----------------------------------------------

    async def steer(self, handle: Handle, command: Command) -> None:
        st = self._states.get(handle.investigation_id)
        if st is None or st.state.is_terminal() or st.ctx is None:
            return  # safe no-op: command after a research finished
        ctx = st.ctx
        if command.kind == CommandKind.PAUSE:
            ctx.request_pause()
            st.state = RunState.PAUSED
        elif command.kind == CommandKind.RESUME:
            ctx.request_resume()
            st.state = RunState.RUNNING
        elif command.kind == CommandKind.STOP:
            st.state = RunState.STOPPING
            ctx.request_stop()
        elif command.kind == CommandKind.REDIRECT:
            new_q = command.payload.get("sub_question")
            if isinstance(new_q, str) and new_q.strip():
                ctx.request_redirect(new_q.strip())
        elif command.kind == CommandKind.DEEPEN:
            extra = float(command.payload.get("extra_budget_usd", 0.0))
            self.budget.raise_cap(handle.investigation_id, extra)
            follow_up = command.payload.get("follow_up")
            if isinstance(follow_up, str) and follow_up.strip():
                st.follow_ups.append(follow_up.strip())

    # -- protocol: status / cost / cancel ------------------------------

    def status(self, handle: Handle) -> Status:
        st = self._states[handle.investigation_id]
        return Status(
            investigation_id=handle.investigation_id,
            state=st.state,
            sub_question=st.ctx.sub_question if st.ctx else st.plan.sub_question,
            cost=self.cost(handle),
            started=st.started,
            follow_ups=list(st.follow_ups),
            error=st.error,
        )

    def cost(self, handle: Handle) -> CostState:
        iid = handle.investigation_id
        return CostState(
            spent_usd=self.budget.spent(iid),
            cap_usd=self.budget.cap(iid),
            tokens=self.budget.tokens(iid),
            steps=self.budget.steps(iid),
        )

    async def cancel(self, handle: Handle) -> None:
        st = self._states.get(handle.investigation_id)
        if st is None or st.state.is_terminal():
            return
        if st.ctx is not None:
            st.state = RunState.STOPPING
            st.ctx.request_stop()
        # Let the loop reach its next checkpoint and seal gracefully.
        if st.task is not None:
            try:
                await asyncio.wait_for(asyncio.shield(st.task), timeout=5.0)
            except (TimeoutError, asyncio.CancelledError):
                st.task.cancel()

    async def join(self) -> None:
        """Await all in-flight researches (test/CLI convenience)."""
        tasks = [st.task for st in self._states.values() if st.task is not None]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


# ---------------------------------------------------------------------------
# Demo browse loop — placeholder until SPR-06 wires the real Exa→Browserbase
# loop. Used by tests and as the reference shape a real loop must satisfy.
# ---------------------------------------------------------------------------


def make_demo_loop(
    *,
    steps: int = 3,
    cost_per_step: float = 0.01,
    delay_s: float = 0.0,
    emit_note: bool = True,
    fail_on_step: int | None = None,
):
    """Build a deterministic browse loop for tests. A real loop calls Exa /
    Browserbase between checkpoints; this one just sleeps + charges."""

    async def _loop(ctx: LoopContext) -> AsyncIterator[StepEvent]:
        yield ctx.plan_event(f"plan for: {ctx.sub_question}")
        for i in range(steps):
            sub_q = await ctx.checkpoint()    # pause/stop/redirect point
            if fail_on_step is not None and i == fail_on_step:
                raise RuntimeError(f"injected failure at step {i}")
            if delay_s:
                await asyncio.sleep(delay_s)
            yield ctx.step(f"step {i} on '{sub_q}'", cost_usd=cost_per_step, tokens=10)
        if emit_note:
            yield ctx.note(f"insight from {ctx.investigation_id}: {ctx.sub_question}")
            yield ctx.question(f"open question from {ctx.investigation_id}?")

    return _loop
