"""``RemoteResearchRunner`` — the remote sibling of ``HostLocalRunner``.

Satisfies the **same** ``ResearchRunner`` protocol (start / stream / steer /
status / cost / cancel) that the host-local runner satisfies, by delegating
each leaf's browse loop to a ``RemoteExecProvider`` sandbox instead of an
in-process asyncio task. The two runners are interchangeable behind the
protocol: DRW SPR-06's orchestration and SPR-09's UI consume both identically
because ``stream`` yields the *same* ``StepEvent`` dataclass either way.

Where the host-local runner runs the loop in-process under a semaphore, this
runner:

  1. ``provision``s a sandbox per leaf (one box per investigation),
  2. ``run``s the loop remotely and maps each ``RemoteStepEvent`` 1:1 onto a
     ``StepEvent``,
  3. charges the budget + emits a ``DispatchCall`` from each step's realized
     cost (via ``cost.record_remote_dispatch``),
  4. ``teardown``s the sandbox on completion, cancel, or error.

Single-writer safety is preserved exactly as DRW SPR-02 specifies it for the
host-local case: **this runner never opens a graph write connection.** Each
leaf's lifecycle markers go to its own per-investigation JSONL (keyed by
``investigation_id`` — automatic isolation); the note/question events the loop
emits are forwarded to the host's serialized ``PromotionFunnel`` via the
``on_emit`` hook (``runtime/remote_exec/funnel.py``), which is the *only*
caller of ``connect_write``. Twenty concurrent remote leaves produce twenty
independent logs and one serialized promotion path — the same invariant, now
across off-host execution.

Cancel teardown (rigor — the negative test): ``cancel`` requests a cooperative
stop, cancels the streaming task, and **always** tears the sandbox down so a
cancelled leaf never leaks a sandbox. The test asserts the fake provider
recorded the teardown.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from collections.abc import Awaitable, Callable

try:
    from ...event_log import log_event, seal_investigation
    from ...schemas.events import ActionType
    from ..research_runner.budget import BudgetManager
    from ..research_runner.protocol import (
        BudgetExceeded,
        Command,
        CommandKind,
        CostState,
        Handle,
        ResearchPlan,
        RunState,
        Status,
        StepEvent,
    )
    from .cost import record_remote_dispatch
    from .provider import (
        RemoteCommand,
        RemoteExecProvider,
        RemoteExecProviderError,
        RemoteSignal,
        Sandbox,
    )
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from runtime.remote_exec.cost import record_remote_dispatch  # type: ignore[no-redef]
    from runtime.remote_exec.provider import (  # type: ignore[no-redef]
        RemoteCommand,
        RemoteExecProvider,
        RemoteExecProviderError,
        RemoteSignal,
        Sandbox,
    )
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
    )
    from substrate.event_log import log_event, seal_investigation  # type: ignore[no-redef]
    from substrate.schemas.events import ActionType  # type: ignore[no-redef]


logger = logging.getLogger("antiek.remote_exec")

# Mirrors HostLocalRunner.DEFAULT_MAX_CONCURRENCY — the product target. Unlike
# the host-local semaphore (which multiplexes in-process tasks on one event
# loop), this caps how many sandboxes are provisioned at once; the real
# concurrency ceiling is the provider's quota + the aggregate budget, not this
# number. Set to the same 20 so "launch 20 at once" is the default either way.
DEFAULT_MAX_CONCURRENCY = 20

# Sentinel pushed onto a research's stream queue to end iteration. Same idiom
# as the host-local runner.
_STREAM_DONE = object()

# Signal map: protocol CommandKind → provider RemoteSignal. One place so the
# mapping is auditable.
_SIGNAL_MAP = {
    CommandKind.PAUSE: RemoteSignal.PAUSE,
    CommandKind.RESUME: RemoteSignal.RESUME,
    CommandKind.STOP: RemoteSignal.STOP,
    CommandKind.REDIRECT: RemoteSignal.REDIRECT,
    CommandKind.DEEPEN: RemoteSignal.DEEPEN,
}


class _RemoteState:
    def __init__(self, plan: ResearchPlan):
        self.plan = plan
        self.state = RunState.PENDING
        self.sandbox: Sandbox | None = None
        self.queue: asyncio.Queue = asyncio.Queue()
        self.task: asyncio.Task | None = None
        self.error: str | None = None
        self.follow_ups: list[str] = []
        self.started = False
        self.torn_down = False
        self.sub_question = plan.sub_question


class RemoteResearchRunner:
    """ResearchRunner over a ``RemoteExecProvider``. Conforms to the protocol;
    drop-in for ``HostLocalRunner`` behind the factory."""

    def __init__(
        self,
        provider: RemoteExecProvider,
        *,
        max_concurrency: int = DEFAULT_MAX_CONCURRENCY,
        budget: BudgetManager | None = None,
        events_dir: str | None = None,
        outbox_db_path: str | None = None,
        seal_on_complete: bool = True,
        on_emit: Callable[[StepEvent], Awaitable[None]] | None = None,
    ):
        self._provider = provider
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self.max_concurrency = max_concurrency
        self.budget = budget or BudgetManager()
        self._events_dir = events_dir
        if outbox_db_path is None:
            from substrate.graph import default_db_path

            outbox_db_path = default_db_path()
        self._outbox_db_path = outbox_db_path
        self._seal_on_complete = seal_on_complete
        self._on_emit = on_emit
        self._states: dict[str, _RemoteState] = {}

    # -- protocol: start -----------------------------------------------

    async def start(self, investigation_id: str, plan: ResearchPlan) -> Handle:
        st = _RemoteState(plan)
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
        # than provisioning a sandbox we will immediately have to tear down.
        # Same semantics as HostLocalRunner.start.
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

        st.task = asyncio.create_task(self._run(st))
        return Handle(investigation_id)

    # -- the per-leaf coroutine ----------------------------------------

    async def _run(self, st: _RemoteState) -> None:
        iid = st.plan.investigation_id
        async with self._semaphore:        # cap on concurrent sandboxes
            st.started = True
            st.state = RunState.RUNNING
            log_event(iid, ActionType.INVESTIGATION_START_REQUESTED,
                      payload={"sub_question": st.sub_question, "runner": "remote_exec"},
                      role="user_agent", events_dir=self._events_dir)
            await self._push(st, StepEvent(iid, 0, "status", text="running",
                                           state=RunState.RUNNING))
            try:
                st.sandbox = await self._provider.provision(st.plan)
                async for rev in self._provider.run(st.sandbox, st.plan):
                    # Charge budget + emit DispatchCall from the realized cost
                    # the sandbox reported. BudgetExceeded propagates to the
                    # halt arm below.
                    if rev.cost_usd or rev.tokens:
                        record_remote_dispatch(
                            investigation_id=iid, event=rev, budget=self.budget,
                            events_dir=self._events_dir,
                        )
                    if rev.kind == "step" and self.budget.steps(iid) > st.plan.budget.max_steps:
                        raise BudgetExceeded(
                            f"{iid} exceeded max_steps={st.plan.budget.max_steps}",
                            scope="per_research",
                        )
                    # Map RemoteStepEvent → StepEvent 1:1. Identical shape;
                    # SPR-06/09 cannot tell which runner produced it.
                    await self._push(st, StepEvent(
                        investigation_id=iid, seq=rev.seq, kind=rev.kind,
                        text=rev.text, cost_usd=rev.cost_usd, tokens=rev.tokens,
                        state=RunState.RUNNING, data=dict(rev.data),
                    ))
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
            except (RemoteExecProviderError, Exception) as exc:
                # One leaf failing — including a provider/provision/runtime
                # error — must not kill its siblings.
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

    async def _push(self, st: _RemoteState, ev: StepEvent) -> None:
        await st.queue.put(ev)
        if self._on_emit is not None and ev.kind in ("note", "question"):
            await self._on_emit(ev)

    async def _finish(self, st, action, payload, *, halted=False, already_logged=False) -> None:
        iid = st.plan.investigation_id
        # ALWAYS tear the sandbox down — completion, halt, failure, cancel.
        # A leaf that finishes any way must not leak a sandbox.
        await self._teardown(st)
        if action is not None and not already_logged:
            log_event(iid, action, payload=payload or {}, role="user_agent",
                      events_dir=self._events_dir)
        if self._seal_on_complete:
            try:
                seal_investigation(
                    iid,
                    events_dir=self._events_dir,
                    outbox_db_path=self._outbox_db_path,
                )
            except Exception as e:  # seal is best-effort
                try:
                    logger.warning(
                        "investigation seal failed (best-effort): iid=%s "
                        "events_dir=%s: %r", iid, self._events_dir, e)
                except Exception:
                    pass  # a broken log channel must not break the finish path
        await st.queue.put(StepEvent(iid, 0, "done", state=st.state))
        await st.queue.put(_STREAM_DONE)

    async def _teardown(self, st: _RemoteState) -> None:
        """Idempotent sandbox teardown. Safe to call from both the finish path
        and an explicit cancel — the ``torn_down`` flag + the provider's own
        idempotent teardown guarantee no double-destroy error."""
        if st.torn_down or st.sandbox is None:
            return
        st.torn_down = True
        try:
            await self._provider.teardown(st.sandbox)
        except Exception as e:  # teardown is best-effort
            try:
                logger.warning(
                    "sandbox teardown failed (best-effort, NOT retried — "
                    "st.torn_down already set): sandbox_id=%s "
                    "investigation_id=%s: %r",
                    st.sandbox.sandbox_id, st.plan.investigation_id, e)
            except Exception:
                pass  # a broken log channel must not break teardown isolation

    # -- protocol: stream ----------------------------------------------

    async def stream(self, handle: Handle):
        st = self._states[handle.investigation_id]
        while True:
            item = await st.queue.get()
            if item is _STREAM_DONE:
                return
            yield item

    # -- protocol: steer -----------------------------------------------

    async def steer(self, handle: Handle, command: Command) -> None:
        st = self._states.get(handle.investigation_id)
        if st is None or st.state.is_terminal():
            return  # safe no-op: command after a research finished
        # DEEPEN extends the cap host-side (the budget lives on the host's
        # BudgetManager regardless of where the loop runs); REDIRECT updates
        # the surfaced sub-question. All signals are relayed to the sandbox.
        if command.kind == CommandKind.PAUSE:
            st.state = RunState.PAUSED
        elif command.kind == CommandKind.RESUME:
            st.state = RunState.RUNNING
        elif command.kind == CommandKind.STOP:
            st.state = RunState.STOPPING
        elif command.kind == CommandKind.REDIRECT:
            new_q = command.payload.get("sub_question")
            if isinstance(new_q, str) and new_q.strip():
                st.sub_question = new_q.strip()
        elif command.kind == CommandKind.DEEPEN:
            extra = float(command.payload.get("extra_budget_usd", 0.0))
            self.budget.raise_cap(handle.investigation_id, extra)
            follow_up = command.payload.get("follow_up")
            if isinstance(follow_up, str) and follow_up.strip():
                st.follow_ups.append(follow_up.strip())
        if st.sandbox is not None:
            signal = _SIGNAL_MAP.get(command.kind)
            if signal is not None:
                try:
                    await self._provider.steer(
                        st.sandbox, RemoteCommand(signal=signal, payload=dict(command.payload))
                    )
                except Exception:  # pragma: no cover — steer is best-effort
                    pass

    # -- protocol: status / cost / cancel ------------------------------

    def status(self, handle: Handle) -> Status:
        st = self._states[handle.investigation_id]
        return Status(
            investigation_id=handle.investigation_id,
            state=st.state,
            sub_question=st.sub_question,
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
            # Even on a terminal leaf, guarantee no sandbox leaked.
            if st is not None:
                await self._teardown(st)
            return
        st.state = RunState.STOPPING
        # Relay a cooperative stop into the sandbox, then cancel the streaming
        # task and tear the sandbox down. Teardown is unconditional — a
        # cancelled leaf never leaks a sandbox (rigor: the negative test).
        if st.sandbox is not None:
            try:
                await self._provider.steer(
                    st.sandbox, RemoteCommand(signal=RemoteSignal.STOP)
                )
            except Exception:  # pragma: no cover
                pass
        if st.task is not None:
            try:
                await asyncio.wait_for(asyncio.shield(st.task), timeout=5.0)
            except (TimeoutError, asyncio.CancelledError):
                st.task.cancel()
        await self._teardown(st)
        st.state = RunState.STOPPED

    async def join(self) -> None:
        """Await all in-flight leaves (test/CLI convenience)."""
        tasks = [st.task for st in self._states.values() if st.task is not None]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


__all__ = ["RemoteResearchRunner", "DEFAULT_MAX_CONCURRENCY"]
