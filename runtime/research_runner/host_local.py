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
import contextlib
import os
import sys
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, cast

try:
    from ...event_log import log_event, seal_investigation  # type: ignore[import-not-found]
    from ...schemas.events import ActionType  # type: ignore[import-not-found]
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
    from runtime.research_runner.budget import BudgetManager
    from runtime.research_runner.protocol import (
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
    from substrate.event_log import log_event, seal_investigation
    from substrate.schemas.events import ActionType


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

    def step(
        self,
        text: str,
        *,
        cost_usd: float = 0.0,
        tokens: int = 0,
        **data: Any,
    ) -> StepEvent:
        return StepEvent(self.investigation_id, self._next_seq(), "step",
                         text=text, cost_usd=cost_usd, tokens=tokens, data=data)

    def note(self, text: str, **data: Any) -> StepEvent:
        return StepEvent(self.investigation_id, self._next_seq(), "note", text=text, data=data)

    def question(self, text: str, **data: Any) -> StepEvent:
        return StepEvent(self.investigation_id, self._next_seq(), "question", text=text, data=data)

    def plan_event(self, text: str, **data: Any) -> StepEvent:
        return StepEvent(self.investigation_id, self._next_seq(), "plan", text=text, data=data)


class _ResearchState:
    def __init__(self, plan: ResearchPlan):
        self.plan = plan
        self.state = RunState.PENDING
        self.ctx: LoopContext | None = None
        self.queue: asyncio.Queue[StepEvent | object] = asyncio.Queue()
        self.task: asyncio.Task[None] | None = None
        self.error: str | None = None
        self.follow_ups: list[str] = []
        self.started = False


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
                payload=self._lifecycle_payload(
                    plan,
                    {"parent_investigation_id": plan.parent_investigation_id,
                     "sub_question": plan.sub_question},
                ),
                role="user_agent", events_dir=self._events_dir,
            )

        # Aggregate-cap gate: refuse the launch with a surfaced reason rather
        # than starting a loop we will immediately have to halt.
        if not self.budget.can_launch(plan.budget.cost_usd):
            reason = self.budget.launch_block_reason()
            st.state = RunState.BUDGET_HALTED
            st.error = reason
            log_event(investigation_id, ActionType.INVESTIGATION_CHASE_HALTED,
                      payload=self._lifecycle_payload(
                          plan, {"reason": "aggregate_budget", "detail": reason}
                      ),
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
        self._maybe_reuse_prior_knowledge(investigation_id, plan)

        st.task = asyncio.create_task(self._run(st))
        return Handle(investigation_id)

    def _maybe_reuse_prior_knowledge(self, investigation_id: str, plan: ResearchPlan) -> None:
        """AFF SPR-06 reuse hook (called exactly once from ``start``).

        Composes ``substrate.context_pack.knowledge_reuse`` — retrieve prior
        units relevant to ``plan.sub_question``, filter to audience-readable +
        token-bounded top-k, inject a single reuse layer into a context pack, and
        emit one ``knowledge.reused`` event on this investigation's JSONL. Lives
        on the existing ``start`` path; adds no ResearchRunner protocol method.

        Audience: this is the single-operator local runner, so every investigation
        here is the owner's own private research — ``owner=True`` admits the
        owner-readable track (servable ∪ personal_reading, not taken_down) on the
        reuse gate. The owner already reads personal_reading in full on the
        privileged serve path (books/serve.py), so reusing an insight derived from
        it here widens nothing publicly (the public path stays byte-identical).
        The multi-operator audience signal arrives with the hosted runner (D19)."""
        if self._retrieval_substrate is None:
            return
        try:
            from substrate.context_pack.knowledge_reuse import (
                assemble_context_pack_with_reuse,
                retrieve_prior_units,
            )
        except ImportError:  # pragma: no cover — defensive
            return
        try:
            units = retrieve_prior_units(
                self._retrieval_substrate,
                question_text=plan.sub_question,
            )
            assemble_context_pack_with_reuse(
                role=self._reuse_role,
                investigation_id=investigation_id,
                layers=[],
                units=units,
                events_dir=self._events_dir,
                owner=True,
            )
        except Exception:  # pragma: no cover — reuse never breaks a research
            return

    # -- the per-research coroutine ------------------------------------

    async def _run(self, st: _ResearchState) -> None:
        iid = st.plan.investigation_id
        async with self._semaphore:        # bounded concurrency
            # A leaf may have waited behind the semaphore while siblings spent
            # the aggregate budget. Recheck at the actual dispatch boundary so
            # queued work cannot incur a provider call after the stop limit.
            if not self.budget.can_launch(st.plan.budget.cost_usd):
                reason = self.budget.launch_block_reason()
                st.state = RunState.BUDGET_HALTED
                st.error = reason
                log_event(iid, ActionType.INVESTIGATION_CHASE_HALTED,
                          payload=self._lifecycle_payload(
                              st.plan, {"reason": "aggregate_budget", "detail": reason}
                          ),
                          role="user_agent", events_dir=self._events_dir)
                await self._push(st, StepEvent(iid, 0, "status", text=reason,
                                               state=RunState.BUDGET_HALTED))
                await self._finish(st, None, None, halted=True)
                return
            st.started = True
            ctx = LoopContext(st.plan, self.budget)
            st.ctx = ctx
            st.state = RunState.RUNNING
            # Durable lifecycle marker on the per-investigation JSONL (the
            # fine-grained step stream stays in-memory for live monitoring;
            # SPR-06 decides what else to persist). Each investigation writes
            # only its own file — automatic isolation by investigation_id.
            log_event(iid, ActionType.INVESTIGATION_START_REQUESTED,
                      payload=self._lifecycle_payload(
                          st.plan, {"sub_question": ctx.sub_question}
                      ),
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
                          payload=self._lifecycle_payload(
                              st.plan,
                              {"reason": exc.scope, "detail": str(exc),
                               "spent_usd": self.budget.spent(iid)},
                          ),
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
                          payload=self._lifecycle_payload(st.plan, {"error": st.error}),
                          role="user_agent",
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

    @staticmethod
    def _lifecycle_payload(
        plan: ResearchPlan, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Carry an optional cascade generation through durable lifecycle events.

        The metadata field is ignored for ordinary researches. Cascade recovery
        uses it as a monotonic generation boundary, avoiding wall-clock ordering.
        """
        generation = plan.metadata.get("cascade_launch_generation")
        if isinstance(generation, int) and not isinstance(generation, bool) and generation > 0:
            return {**payload, "cascade_launch_generation": generation}
        return payload

    async def _finish(
        self,
        st: _ResearchState,
        action: ActionType | None,
        payload: dict[str, Any] | None,
        *,
        halted: bool = False,
        already_logged: bool = False,
    ) -> None:
        iid = st.plan.investigation_id
        if action is not None and not already_logged:
            log_event(iid, action,
                      payload=self._lifecycle_payload(st.plan, payload or {}),
                      role="user_agent",
                      events_dir=self._events_dir)
        if self._seal_on_complete:
            # seal is best-effort (also clears the SIM105 my contextlib import
            # line-shifted out of the declared-bar baseline — shrink real debt,
            # do not re-mint a phantom)
            with contextlib.suppress(Exception):
                seal_investigation(iid, events_dir=self._events_dir)
        await st.queue.put(StepEvent(iid, 0, "done", state=st.state))
        await st.queue.put(_STREAM_DONE)

    # -- protocol: stream ----------------------------------------------

    async def stream(self, handle: Handle) -> AsyncIterator[StepEvent]:
        st = self._states[handle.investigation_id]
        while True:
            item = await st.queue.get()
            if item is _STREAM_DONE:
                return
            yield cast(StepEvent, item)

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
        """Await all in-flight researches (test/CLI convenience), then release
        the reuse substrate's read-only DB connection.

        The SPR-02 wire hands the runner a read-only ``retrieval_substrate``
        that holds a DuckDB connection; DuckDB enforces in-process exclusion
        between a read-only and a read-write handle to the same file, so leaving
        it open past the runner's life both leaks the connection and can block a
        later writer on the same DB. ``join`` is the terminal point, so close it
        here (best-effort — a substrate without ``close`` or a double-close must
        never turn a completed research into a failure)."""
        tasks = [st.task for st in self._states.values() if st.task is not None]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        sub = self._retrieval_substrate
        if sub is not None and hasattr(sub, "close"):
            # teardown is best-effort — a double-close or a substrate without a
            # live connection must never turn a completed research into a failure
            with contextlib.suppress(Exception):
                sub.close()


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
) -> Callable[[LoopContext], AsyncIterator[StepEvent]]:
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


# ---------------------------------------------------------------------------
# Contract gather stub — prod factory default until Exa adapter (ANT-DRL-04).
# ---------------------------------------------------------------------------


def make_contract_gather_stub(
    *,
    steps: int = 2,
    cost_per_step: float = 0.01,
    delay_s: float = 0.0,
) -> Callable[[LoopContext], AsyncIterator[StepEvent]]:
    """Honest production gather placeholder — not real research.

    Unlike ``make_demo_loop`` (benchmark/test MOCK, reuse-blind), this stub
    is the default in ``cascade_routes._research_loop_factory``. It emits
    real ``StepEvent``s and promotes notes through ``PromotionFunnel``,
    but performs no retrieval or synthesis. It does **not** satisfy
    ``DeepResearchComplete`` — gather-only by design until Exa lands.
    """

    async def _loop(ctx: LoopContext) -> AsyncIterator[StepEvent]:
        yield ctx.plan_event(f"[gather-stub] plan: {ctx.sub_question}")
        for i in range(steps):
            sub_q = await ctx.checkpoint()
            if delay_s:
                await asyncio.sleep(delay_s)
            yield ctx.step(
                f"[gather-stub] pass {i} on '{sub_q}'",
                cost_usd=cost_per_step,
                tokens=0,
                gather_mode="contract_stub",
            )
        yield ctx.note(
            f"[gather-stub] provisional note from {ctx.investigation_id}: "
            f"{ctx.sub_question}",
            gather_mode="contract_stub",
        )

    return _loop


# ---------------------------------------------------------------------------
# Exa gather loop — real retrieval, env-gated (ANTIEK_DRW_GATHER=exa).
# ---------------------------------------------------------------------------


def make_exa_gather_loop(
    *,
    top_k: int = 3,
    client: object | None = None,
    legal_gate: object | None = None,
    events_dir: str | None = None,
    daily_budget_usd: float | None = None,
    db_path: str | None = None,
    embedder: object | None = None,
) -> Callable[[LoopContext], AsyncIterator[StepEvent]]:
    """Real DRW gather, wired to the Exa Wedge-1 discovery layer.

    Unlike ``make_contract_gather_stub`` (which retrieves nothing), this
    loop runs an Exa ``discover`` against the (possibly redirected)
    sub-question, then ``promote_discovery`` for the top-``top_k``
    proposals. Promotion routes through the single substrate-write seam
    (``ingest_url``) and consults the legal gate — this loop adds **no**
    new graph-write path. Each ingested proposal yields a provenance
    ``note`` carrying the real ``doc-url-*`` ``document_id``; the
    ``PromotionFunnel`` threads that onto the insight node as
    ``source_document_id`` so ``session_evidence_pack`` emits ``doc-url-*``
    chunks (not the ``doc-gather-*`` placeholder).

    Env-gated: prod stays on the stub by default. This loop fires only
    when ``cascade_routes._research_loop_factory`` reads
    ``ANTIEK_DRW_GATHER=exa``. In CI the ``client`` is an injected
    ``ExaClient(client=httpx.MockTransport(...))`` — there is never a live
    ``EXA_API_KEY`` in the gate.

    Two distinct ledgers are charged, deliberately not conflated:
    ``discover`` reserves against the Exa **daily** spend cap inside
    ``check_and_reserve`` (the provider-side sidecar), while each promoted
    proposal's ``p.cost_usd_estimate`` is charged to the runner's
    **per-research step budget** via ``ctx.step(cost_usd=...)``. The Exa
    daily cap and the per-research step budget are separate accounting
    paths by design; the loop touches both, each exactly once per event.
    """
    # Lazy import: keep the Exa stack off the import path for the stub-only
    # prod default (and for tests that never touch this factory).
    # ``ExaClient`` / ``LegalGate`` are pulled in only to type-narrow the
    # ``object``-typed factory params at the two call sites below (cast is
    # a runtime no-op; both modules are already loaded by the adapter import).
    from typing import cast

    from acquisition.search.exa import ExaClient, discover, promote_discovery
    from substrate.legal_gate import LegalGate

    async def _loop(ctx: LoopContext) -> AsyncIterator[StepEvent]:
        yield ctx.plan_event(f"[exa] plan: {ctx.sub_question}", gather_mode="exa")
        sub_q = await ctx.checkpoint()

        proposals = discover(
            query=sub_q,
            investigation_id=ctx.investigation_id,
            client=cast(ExaClient | None, client),
            events_dir=events_dir,
            daily_budget_usd=daily_budget_usd,
            db_path=db_path,
        )

        ingested_any = False
        for p in proposals[:top_k]:
            await ctx.checkpoint()
            result = promote_discovery(
                p,
                investigation_id=ctx.investigation_id,
                legal_gate=cast(LegalGate | None, legal_gate),
                events_dir=events_dir,
                db_path=db_path,
                embedder=embedder,
            )
            yield ctx.step(
                f"[exa] {result.decision}: {p.url}",
                cost_usd=(p.cost_usd_estimate or 0.0),
                gather_mode="exa",
                discovery_id=p.discovery_id,
                document_id=result.document_id,
                promotion_decision=result.decision,
            )
            if result.decision == "ingested":
                ingested_any = True
                # This note becomes a promoted insight node. The
                # ``document_id`` rides ``StepEvent.data`` → the funnel
                # threads it onto the node as ``source_document_id`` →
                # the pack emits a ``doc-url-*`` chunk. This is the
                # provenance the pack reads.
                yield ctx.note(
                    f"[exa] source for '{sub_q}': "
                    f"{p.title or p.url}",
                    gather_mode="exa",
                    document_id=result.document_id,
                )

        if not ingested_any:
            # Honest: no servable source was promoted. Do NOT fabricate a
            # document_id — this note carries none, so the pack records no
            # doc-url-* chunk for it.
            yield ctx.note(
                f"[exa] gather found no servable source for "
                f"'{sub_q}'",
                gather_mode="exa",
            )

    return _loop
