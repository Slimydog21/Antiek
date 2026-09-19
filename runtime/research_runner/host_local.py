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
import hashlib
import os
import re
import sys
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from substrate.investigation_streams import (
    initialize_composite_stream,
    resolve_investigation_stream,
)
from substrate.investigation_tenancy import (
    InvestigationAuthority,
    default_tenancy_root,
)
from substrate.multi_user.auth import UserClaims

if TYPE_CHECKING:
    from substrate.context_pack import ContextPack, RecursiveNotesPack
    from substrate.context_pack.knowledge_reuse import PackWithReuse

try:
    from ...event_log import (  # type: ignore[import-not-found]
        investigation_authority_context,
        log_event_authorized,
        seal_investigation_authorized,
    )
    from ...schemas.events import ActionType  # type: ignore[import-not-found]
    from .budget import BudgetManager, BudgetReservation
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
    from runtime.research_runner.budget import BudgetManager, BudgetReservation
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
    from substrate.event_log import (
        investigation_authority_context,
        log_event_authorized,
        seal_investigation_authorized,
    )
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

    def __init__(
        self,
        plan: ResearchPlan,
        budget: BudgetManager,
        *,
        prompt_prefix: str = "",
        context_pack_event_id: str | None = None,
        inherited_unit_ids: tuple[str, ...] = (),
    ):
        if len(inherited_unit_ids) > 100:
            raise ValueError("inherited reuse allowlist exceeds policy limit")
        if len(set(inherited_unit_ids)) != len(inherited_unit_ids):
            raise ValueError("inherited reuse allowlist contains duplicate IDs")
        if any(
            not isinstance(unit_id, str)
            or not unit_id.strip()
            or unit_id != unit_id.strip()
            or len(unit_id) > 512
            for unit_id in inherited_unit_ids
        ):
            raise ValueError("inherited reuse allowlist contains an invalid ID")
        self.plan = plan
        self.investigation_id = plan.investigation_id
        self.sub_question = plan.sub_question
        self._budget = budget
        self._seq = 0
        self._resume = asyncio.Event()
        self._resume.set()  # starts un-paused
        self._stop = False
        self._pending_redirect: str | None = None
        self.paused = False
        self.prompt_prefix = prompt_prefix
        self.context_pack_event_id = context_pack_event_id
        self.inherited_unit_ids = inherited_unit_ids

    # -- steering (mutated by the runner from steer()) -----------------

    def request_pause(self) -> None:
        self.paused = True
        self._resume.clear()

    def request_resume(self) -> None:
        self.paused = False
        self._resume.set()

    def request_stop(self) -> None:
        self._stop = True
        self._resume.set()  # unblock a paused loop so it can stop

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
        return StepEvent(
            self.investigation_id,
            self._next_seq(),
            "step",
            text=text,
            cost_usd=cost_usd,
            tokens=tokens,
            data=data,
        )

    def note(self, text: str, **data: Any) -> StepEvent:
        return StepEvent(self.investigation_id, self._next_seq(), "note", text=text, data=data)

    def question(self, text: str, **data: Any) -> StepEvent:
        return StepEvent(self.investigation_id, self._next_seq(), "question", text=text, data=data)

    def plan_event(self, text: str, **data: Any) -> StepEvent:
        return StepEvent(self.investigation_id, self._next_seq(), "plan", text=text, data=data)

    def reserve_provider_call(self, projected_cost_usd: float) -> BudgetReservation:
        return self._budget.reserve_call(self.investigation_id, projected_cost_usd)

    def settle_provider_call(
        self,
        reservation: BudgetReservation,
        *,
        actual_cost_usd: float,
        tokens: int,
    ) -> None:
        self._budget.settle_call(
            reservation,
            actual_cost_usd=actual_cost_usd,
            tokens=tokens,
        )

    def release_provider_call(self, reservation: BudgetReservation) -> None:
        self._budget.release_call(reservation)


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
        self.startup_context: ContextPack | None = None
        self.startup_reuse_unit_ids: tuple[str, ...] = ()


class HostLocalRunner:
    """In-process asyncio runner. Conforms to the ResearchRunner protocol."""

    def __init__(
        self,
        loop_fn: Callable[[LoopContext], AsyncIterator[StepEvent]],
        *,
        claims: UserClaims,
        max_concurrency: int = DEFAULT_MAX_CONCURRENCY,
        budget: BudgetManager | None = None,
        events_dir: str | None = None,
        seal_on_complete: bool = True,
        on_emit: Callable[[StepEvent], Awaitable[None]] | None = None,
        retrieval_substrate: object | None = None,
        reuse_role: str = "user_agent",
        recursive_notes_provider: Callable[[str, ResearchPlan], RecursiveNotesPack] | None = None,
    ):
        if not isinstance(claims, UserClaims):
            raise TypeError("claims must be validated UserClaims")
        if (
            not isinstance(claims.user_id, str)
            or not claims.user_id.strip()
            or claims.user_id != claims.user_id.strip()
            or not isinstance(claims.scopes, frozenset)
            or not all(isinstance(scope, str) and scope for scope in claims.scopes)
            or not isinstance(claims.issued_at, str)
            or not claims.issued_at
        ):
            raise ValueError("claims must be validated UserClaims")
        self._loop_fn = loop_fn
        self._claims = claims
        self._event_role = "operator" if "operator" in claims.scopes else "user_agent"
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self.max_concurrency = max_concurrency
        self.budget = budget or BudgetManager()
        self._events_dir = events_dir
        self._tenancy_root = (
            Path(events_dir).expanduser().resolve(strict=False)
            if events_dir
            else default_tenancy_root()
        )
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
        self._recursive_notes_provider = recursive_notes_provider
        self._states: dict[str, _ResearchState] = {}

    # -- protocol: start -----------------------------------------------

    async def start(self, investigation_id: str, plan: ResearchPlan) -> Handle:
        if plan.investigation_id != investigation_id:
            raise ValueError("plan investigation_id does not match start authority")
        if plan.parent_investigation_id:
            resolve_investigation_stream(self._authority(plan.parent_investigation_id))
        initialize_composite_stream(self._authority(investigation_id))
        st = _ResearchState(plan)
        self._states[investigation_id] = st
        self.budget.register(investigation_id, plan.budget.cost_usd)

        if plan.parent_investigation_id:
            self._log_event(
                investigation_id,
                ActionType.INVESTIGATION_SPAWNED_FROM,
                payload={
                    "parent_investigation_id": plan.parent_investigation_id,
                    "sub_question": plan.sub_question,
                },
                role=self._event_role,
                events_dir=self._events_dir,
            )

        # Aggregate-cap gate: refuse the launch with a surfaced reason rather
        # than starting a loop we will immediately have to halt.
        if not self.budget.can_launch(plan.budget.cost_usd):
            reason = self.budget.launch_block_reason()
            st.state = RunState.BUDGET_HALTED
            st.error = reason
            self._log_event(
                investigation_id,
                ActionType.INVESTIGATION_CHASE_HALTED,
                payload={"reason": "aggregate_budget", "detail": reason},
                role=self._event_role,
                events_dir=self._events_dir,
            )
            await st.queue.put(
                StepEvent(investigation_id, 0, "status", text=reason, state=RunState.BUDGET_HALTED)
            )
            await st.queue.put(StepEvent(investigation_id, 0, "done", state=RunState.BUDGET_HALTED))
            await st.queue.put(_STREAM_DONE)
            return Handle(investigation_id)

        # AFF SPR-06 — retrieve + inject prior knowledge units ONCE, here, before
        # the browse loop is scheduled (so the reuse layer + knowledge.reused
        # event land before the first StepEvent the loop emits). No-op unless a
        # RetrievalSubstrate was injected; non-fatal on any failure (a retrieval
        # hiccup must degrade to "no reuse", never a dead investigation).
        startup = self._maybe_reuse_prior_knowledge(investigation_id, plan)
        if startup is not None:
            st.startup_context = startup.pack
            st.startup_reuse_unit_ids = tuple(unit.unit_id for unit in startup.injected)

        st.task = asyncio.create_task(self._run(st))
        return Handle(investigation_id)

    @property
    def tenancy_root(self) -> Path:
        return self._tenancy_root

    def _authority(self, investigation_id: str) -> InvestigationAuthority:
        return InvestigationAuthority(self._claims.user_id, investigation_id, self._tenancy_root)

    def _log_event(self, investigation_id: str, action: ActionType, **kwargs: Any) -> str | None:
        kwargs.pop("events_dir", None)
        return log_event_authorized(self._authority(investigation_id), action, **kwargs)

    def _maybe_reuse_prior_knowledge(
        self, investigation_id: str, plan: ResearchPlan
    ) -> PackWithReuse | None:
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
        if self._retrieval_substrate is None and self._recursive_notes_provider is None:
            return None
        try:
            from substrate.context_pack import LayerSource
            from substrate.context_pack.knowledge_reuse import (
                assemble_context_pack_with_reuse,
                retrieve_prior_units,
            )
        except ImportError:  # pragma: no cover — defensive
            return None
        units = []
        if self._retrieval_substrate is not None:
            try:
                units = retrieve_prior_units(
                    self._retrieval_substrate,
                    question_text=plan.sub_question,
                    authority=self._authority(investigation_id),
                )
            except Exception as exc:  # pragma: no cover — optional reuse boundary
                print(
                    f"prior knowledge reuse unavailable: {type(exc).__name__}",
                    file=sys.stderr,
                )
        recursive_pack = (
            self._recursive_notes_provider(investigation_id, plan)
            if self._recursive_notes_provider is not None
            else None
        )
        try:
            return assemble_context_pack_with_reuse(
                role=self._reuse_role,
                investigation_id=investigation_id,
                layers=[
                    LayerSource(
                        kind="session",
                        source="research_plan.sub_question",
                        content=plan.sub_question,
                    )
                ],
                units=units,
                events_dir=self._events_dir,
                owner=True,
                include_reuse=self._retrieval_substrate is not None,
                recursive_notes_pack=recursive_pack,
            )
        except Exception as exc:  # pragma: no cover — optional context boundary
            if self._recursive_notes_provider is not None:
                raise
            print(
                f"research context assembly unavailable: {type(exc).__name__}",
                file=sys.stderr,
            )
            return None

    # -- the per-research coroutine ------------------------------------

    async def _run(self, st: _ResearchState) -> None:
        iid = st.plan.investigation_id
        async with self._semaphore:  # bounded concurrency
            st.started = True
            ctx = LoopContext(
                st.plan,
                self.budget,
                prompt_prefix=st.startup_context.text if st.startup_context else "",
                context_pack_event_id=(st.startup_context.event_id if st.startup_context else None),
                inherited_unit_ids=st.startup_reuse_unit_ids,
            )
            st.ctx = ctx
            st.state = RunState.RUNNING
            # Durable lifecycle marker on the per-investigation JSONL (the
            # fine-grained step stream stays in-memory for live monitoring;
            # SPR-06 decides what else to persist). Each investigation writes
            # only its own file — automatic isolation by investigation_id.
            self._log_event(
                iid,
                ActionType.INVESTIGATION_START_REQUESTED,
                payload={"sub_question": ctx.sub_question},
                role=self._event_role,
                events_dir=self._events_dir,
            )
            await self._push(
                st, StepEvent(iid, 0, "status", text="running", state=RunState.RUNNING)
            )
            try:
                async for ev in self._loop_fn(ctx):
                    st.state = RunState.PAUSED if ctx.paused else RunState.RUNNING
                    # Charge budget from the cost the step reports — this is
                    # the same number the step's DispatchCall events carry, so
                    # the ledger reconciles with dispatch by construction.
                    if (ev.cost_usd or ev.tokens) and not ev.data.get("budget_precharged"):
                        self.budget.charge(iid, ev.cost_usd, ev.tokens)
                    if ev.kind == "step" and self.budget.steps(iid) > st.plan.budget.max_steps:
                        raise BudgetExceeded(
                            f"{iid} exceeded max_steps={st.plan.budget.max_steps}",
                            scope="per_research",
                        )
                    await self._push(st, ev)
            except StopResearch:
                st.state = RunState.STOPPED
                await self._finish(st, ActionType.INVESTIGATION_COMPLETED, {"outcome": "stopped"})
                return
            except BudgetExceeded as exc:
                st.state = RunState.BUDGET_HALTED
                st.error = str(exc)
                self._log_event(
                    iid,
                    ActionType.INVESTIGATION_CHASE_HALTED,
                    payload={
                        "reason": exc.scope,
                        "detail": str(exc),
                        "spent_usd": self.budget.spent(iid),
                    },
                    role=self._event_role,
                    events_dir=self._events_dir,
                )
                await self._finish(st, None, None, halted=True)
                return
            except asyncio.CancelledError:
                st.state = RunState.STOPPED
                await self._finish(st, ActionType.INVESTIGATION_COMPLETED, {"outcome": "cancelled"})
                raise
            except Exception as exc:  # one loop failing must not kill siblings
                st.state = RunState.FAILED
                st.error = f"{type(exc).__name__}: {exc}"
                self._log_event(
                    iid,
                    ActionType.INVESTIGATION_FAILED,
                    payload={"error": st.error},
                    role=self._event_role,
                    events_dir=self._events_dir,
                )
                await self._push(
                    st, StepEvent(iid, 0, "error", text=st.error, state=RunState.FAILED)
                )
                await self._finish(st, None, None, already_logged=True)
                return
            st.state = RunState.DONE
            await self._finish(st, ActionType.INVESTIGATION_COMPLETED, {"outcome": "done"})

    async def _push(self, st: _ResearchState, ev: StepEvent) -> None:
        await st.queue.put(ev)
        if self._on_emit is not None and ev.kind in ("note", "question"):
            with investigation_authority_context(self._authority(ev.investigation_id)):
                await self._on_emit(ev)

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
            self._log_event(
                iid,
                action,
                payload=payload or {},
                role=self._event_role,
                events_dir=self._events_dir,
            )
        if self._seal_on_complete:
            # seal is best-effort (also clears the SIM105 my contextlib import
            # line-shifted out of the declared-bar baseline — shrink real debt,
            # do not re-mint a phantom)
            with contextlib.suppress(Exception):
                seal_investigation_authorized(self._authority(iid))
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
            sub_q = await ctx.checkpoint()  # pause/stop/redirect point
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
            f"[gather-stub] provisional note from {ctx.investigation_id}: {ctx.sub_question}",
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
    enable_reasoning: bool = False,
    reasoning_dispatch_fn: Callable[..., Any] | None = None,
    research_tier: str | None = None,
    reasoning_provider_override: str | None = None,
    reasoning_model_override: str | None = None,
    reasoning_allowed_routes: frozenset[str] | None = None,
    reasoning_projected_max_cost_usd: float = 0.25,
    authority: InvestigationAuthority | None = None,
    expected_policy_snapshot_sha256: str | None = None,
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
    from runtime.research_runner.reasoning_loop import (
        ReasoningEvidence,
        run_research_reasoning,
    )
    from substrate.legal_gate import LegalGate

    async def _loop(ctx: LoopContext) -> AsyncIterator[StepEvent]:
        yield ctx.plan_event(f"[exa] plan: {ctx.sub_question}", gather_mode="exa")
        sub_q = await ctx.checkpoint()
        resolved_legal_gate = cast(LegalGate | None, legal_gate)
        dispatch_lease_id: str | None = None
        dispatch_policy_authority = None
        leaf_authority = (
            None
            if authority is None
            else InvestigationAuthority(authority.account_id, ctx.investigation_id, authority.root)
        )

        # The reviewed SQL-policy snapshot is revalidated immediately before
        # the first provider request. A launch claim therefore cannot spend
        # against policy that drifted after review.
        if expected_policy_snapshot_sha256 is not None:
            if leaf_authority is None:
                raise RuntimeError("snapshot-bound Exa gather requires legal authority")
            from runtime.db_lock import connect_write
            from substrate.graph import default_db_path, ensure_initialized
            from substrate.legal_gate.policy_store import account_policy_authority
            from substrate.legal_gate.readiness import claim_policy_dispatch_lease

            policy_db_path = db_path or default_db_path()
            ensure_initialized(policy_db_path)
            con = connect_write(policy_db_path, purpose="exa_pre_provider_policy_snapshot")
            try:
                dispatch_policy_authority = account_policy_authority(leaf_authority)
                dispatch_lease_id, resolved_legal_gate = claim_policy_dispatch_lease(
                    con,
                    dispatch_policy_authority,
                    holder_investigation_digest=leaf_authority.investigation_digest,
                    holder_investigation_id=leaf_authority.investigation_id,
                    expected_sha256=expected_policy_snapshot_sha256,
                )
            finally:
                con.close()
            from substrate.event_log import log_event_authorized

            if (
                log_event_authorized(
                    leaf_authority,
                    "legal_policy.dispatch_claimed",
                    payload={
                        "lease_id": dispatch_lease_id,
                        "policy_snapshot_sha256": expected_policy_snapshot_sha256,
                    },
                    role="user_agent",
                )
                is None
            ):
                raise RuntimeError("durable dispatch-claim evidence was not recorded")

        proposals = discover(
            query=sub_q,
            investigation_id=ctx.investigation_id,
            client=cast(ExaClient | None, client),
            events_dir=events_dir,
            daily_budget_usd=daily_budget_usd,
            db_path=db_path,
        )

        ingested_any = False
        reasoning_evidence: list[ReasoningEvidence] = []
        for p in proposals[:top_k]:
            await ctx.checkpoint()
            result = promote_discovery(
                p,
                investigation_id=ctx.investigation_id,
                legal_gate=resolved_legal_gate,
                events_dir=events_dir,
                db_path=db_path,
                embedder=embedder,
                authority=leaf_authority,
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
                if str(p.text_snippet_preview or "").strip():
                    reasoning_evidence.append(
                        ReasoningEvidence(
                            document_id=str(result.document_id),
                            title=str(p.title or p.url),
                            url=str(p.url),
                            snippet=str(p.text_snippet_preview),
                        )
                    )
                # This note becomes a promoted insight node. The
                # ``document_id`` rides ``StepEvent.data`` → the funnel
                # threads it onto the node as ``source_document_id`` →
                # the pack emits a ``doc-url-*`` chunk. This is the
                # provenance the pack reads.
                yield ctx.note(
                    f"[exa] source for '{sub_q}': {p.title or p.url}",
                    gather_mode="exa",
                    document_id=result.document_id,
                )

        if not ingested_any:
            # Honest: no servable source was promoted. Do NOT fabricate a
            # document_id — this note carries none, so the pack records no
            # doc-url-* chunk for it.
            yield ctx.note(
                f"[exa] gather found no servable source for '{sub_q}'",
                gather_mode="exa",
            )
        elif enable_reasoning and not reasoning_evidence:
            raise ValueError(
                "Exa reasoning requires substantive source snippets; none were returned"
            )
        elif enable_reasoning and reasoning_evidence:
            reasoned = await run_research_reasoning(
                ctx,
                reasoning_evidence,
                dispatch_fn=reasoning_dispatch_fn,
                projected_max_cost_usd=reasoning_projected_max_cost_usd,
                research_tier=research_tier,
                provider_override=reasoning_provider_override,
                model_override=reasoning_model_override,
                allowed_routes=reasoning_allowed_routes,
            )
            yield ctx.step(
                "[reasoning] grounded synthesis completed",
                cost_usd=reasoned.cost_usd,
                tokens=reasoned.tokens,
                gather_mode="exa_reasoning",
                dispatch_event_id=reasoned.dispatch_event_id,
                budget_precharged=True,
            )
            for insight in reasoned.output.insights:
                yield ctx.note(
                    insight.text,
                    gather_mode="exa_reasoning",
                    document_id=insight.source_document_ids[0],
                    source_document_ids=insight.source_document_ids,
                    inherited_unit_ids=insight.inherited_unit_ids,
                )
            for question in reasoned.output.questions:
                yield ctx.question(
                    question.text,
                    gather_mode="exa_reasoning",
                    document_id=(
                        question.source_document_ids[0] if question.source_document_ids else None
                    ),
                    source_document_ids=question.source_document_ids,
                    inherited_unit_ids=question.inherited_unit_ids,
                )

        # Release only after the paid reasoning dispatch has completed. A
        # failed/cancelled ambiguous operation deliberately retains the
        # non-expiring lease for terminal-evidence operator recovery.
        if dispatch_lease_id is not None:
            from substrate.legal_gate.readiness import release_policy_dispatch_lease

            con = connect_write(policy_db_path, purpose="exa_release_policy_dispatch")
            try:
                release_policy_dispatch_lease(
                    con,
                    dispatch_policy_authority,
                    lease_id=dispatch_lease_id,
                    holder_investigation_digest=leaf_authority.investigation_digest,
                )
            finally:
                con.close()

    cast(Any, _loop).consumes_prompt_context = enable_reasoning
    return _loop


def make_authorized_multi_source_gather_loop(
    *,
    launch_plan: Any,
    authority: InvestigationAuthority,
    feed_urls: tuple[str, ...],
    db_path: str | None = None,
    embedder: object | None = None,
    exa_client: object | None = None,
    parallel_client: object | None = None,
    arxiv_client: object | None = None,
    arxiv_throttle: object | None = None,
    substack_client: object | None = None,
    exa_configuration_attestation: str | None = None,
    parallel_configuration_attestation: str | None = None,
    arxiv_configuration_attestation: str | None = None,
    arxiv_base_url: str | None = None,
    providers_override: object | None = None,
    minimum_evidence_documents: int = 1,
) -> Callable[[LoopContext], AsyncIterator[StepEvent]]:
    """Materialize and execute one reviewed multi-source plan per cascade leaf.

    One durable legal-policy lease pins the snapshot across the entire ordered
    composite. Unknown provider outcome deliberately retains that lease for
    operator recovery; terminal-safe success/partial/failure releases it.
    """
    from collections.abc import Mapping

    from runtime.research_runner.authorized_gather import AuthorizedGatherProvider
    from runtime.research_runner.authorized_gather_sql import DuckDBAuthorizedGatherAuthority
    from runtime.research_runner.gather_launch_plan import AuthorizedGatherLaunchPlan
    from runtime.research_runner.gather_plan import GatherSource
    from runtime.research_runner.multi_source_gather import execute_authorized_gather_plan
    from runtime.research_runner.production_gather_providers import (
        ArxivGatherProvider,
        ExaGatherProvider,
        ParallelGatherProvider,
        SubstackSubscriptionGatherProvider,
    )

    if not isinstance(launch_plan, AuthorizedGatherLaunchPlan):
        raise TypeError("multi-source loop requires an authorized launch plan")
    if launch_plan.account_digest != authority.account_digest:
        raise ValueError("multi-source launch authority does not match the reviewed plan")
    resolved_db = db_path

    async def _loop(ctx: LoopContext) -> AsyncIterator[StepEvent]:
        match = re.search(r"-leaf-(\d+)$", ctx.investigation_id)
        if match is None:
            raise RuntimeError("multi-source leaf identity is malformed")
        leaf_index = int(match.group(1))
        leaf_authority = InvestigationAuthority(
            authority.account_id, ctx.investigation_id, authority.root
        )
        plan = launch_plan.materialize_leaf(
            leaf_authority, leaf_index=leaf_index, query=ctx.sub_question
        )
        yield ctx.plan_event(
            f"[multi-source] reviewed gather for leaf {leaf_index + 1}",
            gather_mode="authorized_multi_source",
            gather_launch_fingerprint=launch_plan.fingerprint,
            gather_plan_fingerprint=plan.fingerprint,
        )
        query = await ctx.checkpoint()
        # Redirect after launch changes the reviewed query and must never spend.
        if query.strip() != ctx.plan.sub_question.strip():
            raise RuntimeError("redirected query requires a fresh gather review")

        from runtime.db_lock import connect_write
        from substrate.event_log import log_event_authorized
        from substrate.graph import default_db_path, ensure_initialized
        from substrate.legal_gate.policy_store import account_policy_authority
        from substrate.legal_gate.readiness import (
            claim_policy_dispatch_lease,
            release_policy_dispatch_lease,
            require_policy_snapshot,
        )

        policy_db_path = resolved_db or default_db_path()
        ensure_initialized(policy_db_path)
        policy_authority = account_policy_authority(leaf_authority)
        con = connect_write(policy_db_path, purpose="multi_source_claim_policy_dispatch")
        try:
            lease_id, legal_gate = claim_policy_dispatch_lease(
                con,
                policy_authority,
                holder_investigation_digest=leaf_authority.investigation_digest,
                holder_investigation_id=leaf_authority.investigation_id,
                expected_sha256=launch_plan.legal_policy_snapshot_sha256,
            )
        finally:
            con.close()
        if (
            log_event_authorized(
                leaf_authority,
                "legal_policy.dispatch_claimed",
                payload={
                    "lease_id": lease_id,
                    "policy_snapshot_sha256": launch_plan.legal_policy_snapshot_sha256,
                },
                role="user_agent",
            )
            is None
        ):
            con = connect_write(policy_db_path, purpose="multi_source_release_unlogged_lease")
            try:
                release_policy_dispatch_lease(
                    con,
                    policy_authority,
                    lease_id=lease_id,
                    holder_investigation_digest=leaf_authority.investigation_digest,
                )
            finally:
                con.close()
            raise RuntimeError("durable dispatch-claim evidence was not recorded")

        if providers_override is None:
            providers: Mapping[GatherSource, AuthorizedGatherProvider] = {
                GatherSource.EXA: ExaGatherProvider(
                    legal_gate,
                    db_path=policy_db_path,
                    client=exa_client,
                    embedder=embedder,
                    configuration_sha256=exa_configuration_attestation,
                ),
                GatherSource.PARALLEL: ParallelGatherProvider(
                    legal_gate,
                    db_path=policy_db_path,
                    client=parallel_client,
                    embedder=embedder,
                    configuration_sha256=parallel_configuration_attestation,
                ),
                GatherSource.ARXIV: ArxivGatherProvider(
                    db_path=policy_db_path,
                    client=arxiv_client,
                    throttle=arxiv_throttle,
                    embedder=embedder,
                    configuration_sha256=arxiv_configuration_attestation,
                    base_url=arxiv_base_url,
                ),
                GatherSource.SUBSTACK: SubstackSubscriptionGatherProvider(
                    feed_urls,
                    db_path=policy_db_path,
                    client=substack_client,
                    embedder=embedder,
                ),
            }
        else:
            providers = cast(Mapping[GatherSource, AuthorizedGatherProvider], providers_override)

        store = DuckDBAuthorizedGatherAuthority(policy_db_path, leaf_authority)

        def validate_snapshot(
            checked_authority: InvestigationAuthority, expected_sha256: str
        ) -> None:
            con = connect_write(policy_db_path, purpose="multi_source_revalidate_policy")
            try:
                require_policy_snapshot(
                    con,
                    account_policy_authority(checked_authority),
                    expected_sha256=expected_sha256,
                )
            finally:
                con.close()

        report = execute_authorized_gather_plan(
            plan=plan,
            expected_plan_fingerprint=plan.fingerprint,
            authority=leaf_authority,
            query=query,
            providers=providers,
            validate_policy_snapshot=validate_snapshot,
            budget=store,
            receipts=store,
            minimum_evidence_documents=minimum_evidence_documents,
        )
        from substrate.event_log import (
            emit_typed_authorized_strict,
            trajectory_authorized,
        )
        from substrate.schemas.events import (
            GatherReportRecordedPayload,
            GatherSourceReportReceipt,
        )

        report_payload = GatherReportRecordedPayload(
            launch_fingerprint=launch_plan.fingerprint,
            plan_fingerprint=plan.fingerprint,
            legal_policy_snapshot_sha256=plan.legal_policy_snapshot_sha256,
            receipts=tuple(
                GatherSourceReportReceipt(
                    source=receipt.source.value,
                    status=receipt.status.value,
                    document_ids=receipt.document_ids,
                    actual_cost_micros=receipt.actual_cost_micros,
                    tokens=receipt.tokens,
                    provider_receipt_id=receipt.provider_receipt_id,
                    failure_code=receipt.failure_code,
                )
                for receipt in report.source_receipts
            ),
            document_ids=report.document_ids,
            minimum_evidence_documents=report.minimum_evidence_documents,
            evidence_complete=report.evidence_complete,
            partial=report.partial,
            unknown_outcome=report.unknown_outcome,
        )
        report_event_id = (
            "evt-gather-report-"
            + hashlib.sha256(
                f"{leaf_authority.investigation_digest}\x1f{plan.fingerprint}".encode()
            ).hexdigest()[:32]
        )
        existing_report = next(
            (
                row
                for row in trajectory_authorized(leaf_authority)
                if row.get("event_id") == report_event_id
            ),
            None,
        )
        if existing_report is None:
            emit_typed_authorized_strict(
                leaf_authority,
                report_payload,
                event_id=report_event_id,
                role="acquisition",
                policy_id="research/authorized-multi-source-gather-v1",
            )
        elif existing_report.get("payload") != report_payload.model_dump(mode="json"):
            raise RuntimeError("durable gather report conflicts with replayed execution")
        # Once the composite is terminal-safe, release before yielding any
        # observer events: cancellation or a closed stream cannot strand a
        # completed dispatch lease. Unknown outcomes intentionally retain it.
        if not report.unknown_outcome:
            con = connect_write(policy_db_path, purpose="multi_source_release_policy_dispatch")
            try:
                release_policy_dispatch_lease(
                    con,
                    policy_authority,
                    lease_id=lease_id,
                    holder_investigation_digest=leaf_authority.investigation_digest,
                )
            finally:
                con.close()
        for receipt in report.source_receipts:
            yield ctx.step(
                f"[{receipt.source.value}] {receipt.status.value}",
                cost_usd=receipt.actual_cost_micros / 1_000_000,
                tokens=receipt.tokens,
                gather_mode="authorized_multi_source",
                gather_plan_fingerprint=plan.fingerprint,
                source=receipt.source.value,
                source_status=receipt.status.value,
                document_ids=list(receipt.document_ids),
                failure_code=receipt.failure_code,
            )
        for document_id in report.document_ids:
            yield ctx.note(
                f"[multi-source] admitted evidence {document_id}",
                gather_mode="authorized_multi_source",
                gather_plan_fingerprint=plan.fingerprint,
                document_id=document_id,
            )

        if report.unknown_outcome:
            raise RuntimeError("multi-source provider outcome requires reconciliation")
        if not report.evidence_complete:
            raise RuntimeError("multi-source gather did not meet minimum evidence")

    cast(Any, _loop).consumes_prompt_context = False
    return _loop
