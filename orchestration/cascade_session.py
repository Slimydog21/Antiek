"""DRW SPR-06 — parallel launch + glass-box session orchestration.

The orchestration layer between SPR-05 (an approved cascade tree) and SPR-02
(the ResearchRunner). It launches one investigation per approved leaf,
multiplexes every research's StepEvent stream into one session stream the UI
watches, routes steer commands back to individual researches, surfaces
aggregate cost, merges completed findings into the graph, and — the
make-or-break property — **reconstructs the whole session from the event log
after a disconnect or restart**, because the per-investigation JSONL is the
source of truth, not in-memory state.

Durability model (documented for the on-call maintainer):

* A *session* is the parent investigation; each leaf research is linked to it
  by the ``investigation.spawned_from`` event SPR-02's runner already emits.
  So session membership is recoverable by scanning the events dir for
  children whose ``parent_investigation_id`` is the session — no separate
  store is invented (the daemon precedent in
  ``orchestration/continuous/daemon.py`` does the same).
* Each research's state is recoverable from its trajectory's terminal event
  (``investigation.completed`` / ``.failed`` / ``.chase_halted``), or
  ``running`` if only ``investigation.start_requested`` is present.
* **Delivery guarantee (honest, rigor #1):** the live stream is
  *at-least-once with idempotent client handling*. A reconnect re-derives
  authoritative state from the event log and then resubscribes to live
  events; an event in flight across the reconnect window may be delivered
  twice, so consumers key on ``(investigation_id, seq)``. We do NOT claim
  exactly-once.

The HTTP/SSE transport is a thin serialization of ``stream()`` plus a
``reconstruct_session`` call on connect; it is left as an adapter to wire into
the FastAPI app (which the parallel stream owns) rather than edited here.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from typing import Any, cast

# orchestration/ is a top-level package and uses absolute imports (matching
# orchestration/continuous/daemon.py). The sys.path nudge supports direct
# script execution from inside the package.
if __package__ in (None, ""):  # pragma: no cover — direct-script fallback
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from orchestration.invariants.deep_research_complete import (
    check_deep_research_complete,
)
from orchestration.session_evidence_pack import (
    SessionEvidencePack,
    build_session_evidence_pack,
)
from roles.cascade_planner.approval import assert_launchable
from runtime.db_lock import connect_write
from runtime.research_runner import (
    BudgetCap,
    Command,
    Handle,
    HostLocalRunner,
    ResearchPlan,
    RunState,
    StepEvent,
)
from runtime.research_runner.promotion_funnel import PromotionFunnel
from substrate.event_log import default_events_dir, log_event, trajectory
from substrate.graph.insight_question import graph_db_path
from substrate.graph.ops import insert_edge
from substrate.schemas.events import ActionType

_SESSION_DONE = object()

_log = logging.getLogger(__name__)

# Audit action_type for a synthesis-tail failure recorded on the session's own
# trajectory. Untyped (free-string) like ``cascade.launched`` above — the
# Researchmaxx vocabulary that hasn't been schemaed yet. Recoverable from the
# event log so the from-event-log status path can surface it honestly.
SYNTHESIS_TAIL_FAILED = "cascade.synthesis_tail.failed"


@dataclass
class Leaf:
    """One approved plan leaf to launch: a sub-question + the graph question
    node it persisted as (so findings can be linked back to it)."""

    investigation_id: str
    sub_question: str
    question_node_id: str | None = None
    budget: BudgetCap = field(default_factory=BudgetCap)


@dataclass
class ResearchState:
    investigation_id: str
    sub_question: str
    state: str
    question_node_id: str | None = None


@dataclass
class SessionRecovery:
    """Reconstructed-from-the-event-log view of a session. Carries no
    in-memory runtime state — proof a refresh/restart loses nothing."""

    session_id: str
    researches: list[ResearchState]
    # Reconstructed from the session's own trajectory: the
    # ``cascade.synthesis_tail.failed`` audit event, if one was emitted before
    # the session was evicted. None when no such event exists — we surface only
    # what is honestly recoverable, never a fabricated success or failure.
    synthesis_tail_error: str | None = None

    @property
    def all_terminal(self) -> bool:
        return all(RunState(r.state).is_terminal() for r in self.researches)


class CascadeSession:
    """Launches + multiplexes + steers + merges one approved fan-out."""

    def __init__(
        self,
        session_id: str,
        *,
        runner: HostLocalRunner,
        funnel: PromotionFunnel | None = None,
        events_dir: str | None = None,
        db_path: str | None = None,
    ):
        self.session_id = session_id
        self._runner = runner
        self._funnel = funnel
        self._events_dir = events_dir
        self._db_path = db_path or graph_db_path()
        self._leaves: dict[str, Leaf] = {}
        self._handles: dict[str, Handle] = {}
        self._out: asyncio.Queue[StepEvent | object] = asyncio.Queue()
        self._pump_tasks: list[asyncio.Task[None]] = []
        # Set by background completion (``_run_to_completion``) when the Loop 1
        # synthesis tail raises. A non-None value means the session never
        # reached ``DeepResearchComplete`` because synthesis failed — the
        # split-brain / silent-synthesis hazard the ANT-DRL programme guards.
        self.synthesis_tail_error: str | None = None

    # -- M1: launch with approval enforcement --------------------------

    async def launch(self, plan_root_node_id: str, leaves: Sequence[Leaf]) -> list[Handle]:
        """Launch an approved plan as N investigations. Refuses an unapproved
        plan (SPR-05 gate). Each leaf is spawned_from the session parent."""
        assert_launchable(plan_root_node_id, db_path=self._db_path)
        if self._funnel is not None:
            await self._funnel.start()
        log_event(self.session_id, "cascade.launched",
                  payload={"plan_root_node_id": plan_root_node_id,
                           "leaf_count": len(leaves)},
                  role="user_agent", events_dir=self._events_dir)
        handles: list[Handle] = []
        for leaf in leaves:
            self._leaves[leaf.investigation_id] = leaf
            plan = ResearchPlan(
                investigation_id=leaf.investigation_id, sub_question=leaf.sub_question,
                parent_investigation_id=self.session_id, budget=leaf.budget,
            )
            handle = await self._runner.start(leaf.investigation_id, plan)
            self._handles[leaf.investigation_id] = handle
            handles.append(handle)
            # Pump this research's stream into the multiplexed session queue.
            self._pump_tasks.append(asyncio.create_task(self._pump(handle)))
        return handles

    async def _pump(self, handle: Handle) -> None:
        async for ev in self._runner.stream(handle):
            await self._out.put(ev)

    # -- M2: multiplexed stream ----------------------------------------

    async def stream(self) -> AsyncIterator[StepEvent]:
        """Multiplexed stream of every research's events. Ends when all
        researches have terminated. For durable reconnect, a fresh consumer
        first calls ``reconstruct_session`` then resubscribes here."""
        async def _closer() -> None:
            await asyncio.gather(*self._pump_tasks, return_exceptions=True)
            await self._out.put(_SESSION_DONE)
        closer = asyncio.create_task(_closer())
        try:
            while True:
                item = await self._out.get()
                if item is _SESSION_DONE:
                    return
                yield cast(StepEvent, item)
        finally:
            closer.cancel()

    # -- M3: steer routing ---------------------------------------------

    async def steer(self, investigation_id: str, command: Command) -> None:
        handle = self._handles.get(investigation_id)
        if handle is None:
            return  # safe no-op for an unknown/finished research
        await self._runner.steer(handle, command)

    # -- M4: aggregate cost --------------------------------------------

    def aggregate_cost(self) -> dict[str, Any]:
        per = {iid: self._runner.cost(h).spent_usd for iid, h in self._handles.items()}
        return {
            "per_research": per,
            "session_total_usd": sum(per.values()),
            "aggregate_spent_usd": self._runner.budget.aggregate_spent,
            "aggregate_cap_usd": self._runner.budget.aggregate_cap_usd,
        }

    # -- M5/M7: join, merge-on-complete, failure isolation -------------

    async def join_and_merge(self) -> dict[str, int]:
        """Wait for all researches; drain the promotion funnel; link each
        research's promoted insights to its sub-question node. One research
        failing does not abort the merge for its siblings."""
        await self._runner.join()
        if self._funnel is not None:
            await self._funnel.drain_and_stop()
        linked = 0
        for leaf in self._leaves.values():
            if leaf.question_node_id is None:
                continue
            try:
                linked += self._link_findings(leaf)
            except Exception:  # isolation: a bad merge for one leaf is not fatal
                continue
        return {"linked_findings": linked}

    def _link_findings(self, leaf: Leaf) -> int:
        """Link insight nodes promoted under this research to its sub-question
        node via question --resolved_by--> insight edges."""
        question_node_id = leaf.question_node_id
        if question_node_id is None:
            return 0
        insight_ids = [
            ev.get("payload", {}).get("node_id")
            for ev in trajectory(leaf.investigation_id, events_dir=self._events_dir)
            if ev.get("action_type") == ActionType.GRAPH_NODE_INSERTED.value
            and ev.get("payload", {}).get("node_type") == "insight"
        ]
        insight_ids = [i for i in insight_ids if isinstance(i, str)]
        if not insight_ids:
            return 0
        con = connect_write(self._db_path, purpose="cascade_merge")
        n = 0
        try:
            con.execute("BEGIN")
            for iid in insight_ids:
                insert_edge(con, source_node_id=question_node_id, target_node_id=iid,
                            relation="resolved_by", source_tier=3, extraction_confidence=0.8,
                            graph_scope="depth", investigation_id=leaf.investigation_id,
                            on_conflict="ignore")
                n += 1
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
        finally:
            con.close()
        return n

    def status(self) -> list[ResearchState]:
        out = []
        for iid, leaf in self._leaves.items():
            h = self._handles.get(iid)
            st = self._runner.status(h).state.value if h else RunState.PENDING.value
            out.append(ResearchState(iid, leaf.sub_question, st, leaf.question_node_id))
        return out

    def is_complete(self) -> bool:
        """True once every research has reached a terminal state. The robust
        completion signal for a poll-drain consumer (e.g. the SSE transport),
        which does not depend on the single-consumer ``stream()`` draining the
        queue."""
        return all(RunState(s.state).is_terminal() for s in self.status())

    def is_deep_research_complete(self) -> bool:
        """True when gather leaves are terminal AND the session parent
        satisfies ``DeepResearchComplete`` (Path A convergence).

        Leaf researches are gather-only; synthesis runs on
        ``session_id``. Runner-level ``DONE`` without a synthesis tail
        fails this check — the split-brain guard for ANT-DRL."""
        if not self.is_complete():
            return False
        ok, _ = check_deep_research_complete(self.session_id)
        return ok

    def record_synthesis_tail_error(
        self, exc: BaseException, *, stage: str = "synthesis_tail"
    ) -> None:
        """Capture a background-completion failure: store it on the session AND
        emit a durable audit trail. Called by ``_run_to_completion`` when
        ``join_and_merge`` OR the Loop 1 synthesis tail raises — it must NOT
        re-raise (the event loop stays alive) and the failure must NOT be
        silently swallowed. The split-brain guard.

        ``stage`` records WHICH completion step failed (``join_and_merge`` vs
        ``synthesis_tail``) so a merge failure isn't mislabeled as a tail one; it
        is prefixed onto the stored message and carried in the audit payload.

        Two-pronged audit, both convention-matching:
          * a ``cascade.synthesis_tail.failed`` event on the session's own
            trajectory (same untyped ``log_event`` seam as ``cascade.launched``)
            so the from-event-log status path can reconstruct it; and
          * a structured ``logger.exception`` (the best-effort-isolation
            precedent in ``interfaces/research/api/books.py``) so it is visible
            in the operator's logs and assertable via ``caplog``.

        The durable-event emit is defensively isolated — recording a failure must
        never become a second failure that crashes the loop — but a failed emit
        still leaves a ``logger.warning`` breadcrumb rather than a silent ``pass``
        (the very pattern this method exists to kill); the error is already on the
        in-memory field + the ``logger.exception`` below regardless."""
        self.synthesis_tail_error = f"[{stage}] {type(exc).__name__}: {exc}"
        try:
            log_event(
                self.session_id,
                SYNTHESIS_TAIL_FAILED,
                payload={"error": self.synthesis_tail_error,
                         "error_type": type(exc).__name__,
                         "stage": stage},
                role="user_agent",
                events_dir=self._events_dir,
            )
        except Exception:  # pragma: no cover — audit-of-audit isolation
            _log.warning(
                "synthesis-tail audit event emit failed for session_id=%s "
                "(error preserved on the session field + the logger.exception below)",
                self.session_id, exc_info=True,
            )
        _log.exception(
            "cascade completion failed at stage=%s for session_id=%s; "
            "session did not reach DeepResearchComplete (captured, non-fatal)",
            stage, self.session_id,
        )

    def terminal_status(self) -> dict[str, Any]:
        """The session's deep-research terminal contract, for status surfaces.

        ``deep_research_complete`` is the authoritative Path-A convergence
        check (gather leaves terminal AND the session parent satisfies
        ``DeepResearchComplete``); ``synthesis_tail_error`` is the captured
        failure string (None when the tail has not failed)."""
        return {
            "deep_research_complete": self.is_deep_research_complete(),
            "synthesis_tail_error": self.synthesis_tail_error,
        }

    def build_evidence_pack(
        self,
        *,
        plan_root_node_id: str | None = None,
    ) -> SessionEvidencePack:
        """Merge session leaves + JSONL trajectories into a typed pack."""
        researches = [
            (s.investigation_id, s.sub_question) for s in self.status()
        ]
        return build_session_evidence_pack(
            self.session_id,
            events_dir=self._events_dir or default_events_dir(),
            db_path=self._db_path,
            researches=researches,
            plan_root_node_id=plan_root_node_id,
        )

    async def run_synthesis_tail(
        self,
        pack: SessionEvidencePack,
        *,
        broadcaster: Any,
        coordinator: Any,
    ) -> bool:
        """Path A capstone — Loop 1 phases 6–9 on the session parent."""
        from orchestration.loop_one.orchestrator import run_synthesis_tail_from_pack

        await run_synthesis_tail_from_pack(
            pack,
            broadcaster=broadcaster,
            coordinator=coordinator,
        )
        return self.is_deep_research_complete()

    def drain_nowait(self) -> list[StepEvent]:
        """Pop all currently-buffered StepEvents without blocking (skips the
        internal sentinel). Lets a transport poll-and-drain the multiplexed
        stream and decide termination via ``is_complete`` — robust to a
        request/response server that only advances the loop while a request is
        in flight (the poller's ``await asyncio.sleep`` gives the research
        tasks loop time)."""
        out: list[StepEvent] = []
        while True:
            try:
                item = self._out.get_nowait()
            except asyncio.QueueEmpty:
                break
            if item is not _SESSION_DONE:
                out.append(cast(StepEvent, item))
        return out


# ---------------------------------------------------------------------------
# M6 — recovery: reconstruct a session purely from the event log
# ---------------------------------------------------------------------------


_TERMINAL_ACTION = {
    ActionType.INVESTIGATION_COMPLETED.value: RunState.DONE,
    ActionType.INVESTIGATION_FAILED.value: RunState.FAILED,
    ActionType.INVESTIGATION_CHASE_HALTED.value: RunState.BUDGET_HALTED,
}


def _list_investigation_ids(events_dir: str) -> list[str]:
    if not os.path.isdir(events_dir):
        return []
    seen = set()
    for fn in os.listdir(events_dir):
        if fn.endswith(".parquet"):
            seen.add(fn[:-len(".parquet")])
        elif fn.endswith(".jsonl"):
            seen.add(fn[:-len(".jsonl")])
    return sorted(seen)


def reconstruct_session(session_id: str, *, events_dir: str | None = None) -> SessionRecovery:
    """Rebuild a session's membership + per-research state from the event log
    alone — the durability guarantee. A child belongs to the session if its
    trajectory carries an ``investigation.spawned_from`` pointing at the
    session; its state is its terminal event (or ``running``)."""
    resolved = events_dir or default_events_dir()
    researches: list[ResearchState] = []
    for iid in _list_investigation_ids(resolved):
        rows = trajectory(iid, events_dir=resolved)
        parent = None
        sub_q = ""
        state = RunState.PENDING
        for ev in rows:
            at = ev.get("action_type")
            payload = ev.get("payload", {}) if isinstance(ev.get("payload"), dict) else {}
            if at == ActionType.INVESTIGATION_SPAWNED_FROM.value:
                parent = payload.get("parent_investigation_id")
                sub_q = payload.get("sub_question", sub_q)
            elif at == ActionType.INVESTIGATION_START_REQUESTED.value:
                sub_q = payload.get("sub_question", sub_q)
                if state == RunState.PENDING:
                    state = RunState.RUNNING
            elif at in _TERMINAL_ACTION:
                state = _TERMINAL_ACTION[at]
        if parent == session_id:
            researches.append(ResearchState(iid, sub_q, state.value))
    researches.sort(key=lambda r: r.investigation_id)
    tail_error = _recover_synthesis_tail_error(session_id, events_dir=resolved)
    return SessionRecovery(
        session_id=session_id,
        researches=researches,
        synthesis_tail_error=tail_error,
    )


def _recover_synthesis_tail_error(
    session_id: str, *, events_dir: str | None = None
) -> str | None:
    """The last ``cascade.synthesis_tail.failed`` audit event recorded on the
    session's own trajectory, or None if none was emitted. Honest by
    construction: absence of the event yields None (we never fabricate a
    failure or a success the event log cannot prove)."""
    last: str | None = None
    for ev in trajectory(session_id, events_dir=events_dir):
        if ev.get("action_type") == SYNTHESIS_TAIL_FAILED:
            payload = ev.get("payload", {}) if isinstance(ev.get("payload"), dict) else {}
            last = payload.get("error") or last
    return last
