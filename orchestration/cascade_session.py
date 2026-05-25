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
import os
import sys
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional, Sequence, Tuple

# orchestration/ is a top-level package and uses absolute imports (matching
# orchestration/continuous/daemon.py). The sys.path nudge supports direct
# script execution from inside the package.
if __package__ in (None, ""):  # pragma: no cover — direct-script fallback
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from runtime.research_runner import (
    BudgetCap, Command, Handle, HostLocalRunner, ResearchPlan, RunState, StepEvent,
)
from runtime.research_runner.promotion_funnel import PromotionFunnel
from runtime.db_lock import connect_write
from substrate.event_log import default_events_dir, log_event, trajectory
from substrate.schemas.events import ActionType
from substrate.graph.insight_question import graph_db_path
from substrate.graph.ops import insert_edge
from roles.cascade_planner.approval import assert_launchable


_SESSION_DONE = object()


@dataclass
class Leaf:
    """One approved plan leaf to launch: a sub-question + the graph question
    node it persisted as (so findings can be linked back to it)."""

    investigation_id: str
    sub_question: str
    question_node_id: Optional[str] = None
    budget: BudgetCap = field(default_factory=BudgetCap)


@dataclass
class ResearchState:
    investigation_id: str
    sub_question: str
    state: str
    question_node_id: Optional[str] = None


@dataclass
class SessionRecovery:
    """Reconstructed-from-the-event-log view of a session. Carries no
    in-memory runtime state — proof a refresh/restart loses nothing."""

    session_id: str
    researches: List[ResearchState]

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
        funnel: Optional[PromotionFunnel] = None,
        events_dir: Optional[str] = None,
        db_path: Optional[str] = None,
    ):
        self.session_id = session_id
        self._runner = runner
        self._funnel = funnel
        self._events_dir = events_dir
        self._db_path = db_path or graph_db_path()
        self._leaves: Dict[str, Leaf] = {}
        self._handles: Dict[str, Handle] = {}
        self._out: "asyncio.Queue" = asyncio.Queue()
        self._pump_tasks: List[asyncio.Task] = []

    # -- M1: launch with approval enforcement --------------------------

    async def launch(self, plan_root_node_id: str, leaves: Sequence[Leaf]) -> List[Handle]:
        """Launch an approved plan as N investigations. Refuses an unapproved
        plan (SPR-05 gate). Each leaf is spawned_from the session parent."""
        assert_launchable(plan_root_node_id, db_path=self._db_path)
        if self._funnel is not None:
            await self._funnel.start()
        log_event(self.session_id, "cascade.launched",
                  payload={"plan_root_node_id": plan_root_node_id,
                           "leaf_count": len(leaves)},
                  role="user_agent", events_dir=self._events_dir)
        handles: List[Handle] = []
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
        async def _closer():
            await asyncio.gather(*self._pump_tasks, return_exceptions=True)
            await self._out.put(_SESSION_DONE)
        closer = asyncio.create_task(_closer())
        try:
            while True:
                item = await self._out.get()
                if item is _SESSION_DONE:
                    return
                yield item
        finally:
            closer.cancel()

    # -- M3: steer routing ---------------------------------------------

    async def steer(self, investigation_id: str, command: Command) -> None:
        handle = self._handles.get(investigation_id)
        if handle is None:
            return  # safe no-op for an unknown/finished research
        await self._runner.steer(handle, command)

    # -- M4: aggregate cost --------------------------------------------

    def aggregate_cost(self) -> dict:
        per = {iid: self._runner.cost(h).spent_usd for iid, h in self._handles.items()}
        return {
            "per_research": per,
            "session_total_usd": sum(per.values()),
            "aggregate_spent_usd": self._runner.budget.aggregate_spent,
            "aggregate_cap_usd": self._runner.budget.aggregate_cap_usd,
        }

    # -- M5/M7: join, merge-on-complete, failure isolation -------------

    async def join_and_merge(self) -> dict:
        """Wait for all researches; drain the promotion funnel; link each
        research's promoted insights to its sub-question node. One research
        failing does not abort the merge for its siblings."""
        await self._runner.join()
        if self._funnel is not None:
            await self._funnel.drain_and_stop()
        linked = 0
        for iid, leaf in self._leaves.items():
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
        insight_ids = [
            ev.get("payload", {}).get("node_id")
            for ev in trajectory(leaf.investigation_id, events_dir=self._events_dir)
            if ev.get("action_type") == ActionType.GRAPH_NODE_INSERTED.value
            and ev.get("payload", {}).get("node_type") == "insight"
        ]
        insight_ids = [i for i in insight_ids if i]
        if not insight_ids:
            return 0
        con = connect_write(self._db_path, purpose="cascade_merge")
        n = 0
        try:
            con.execute("BEGIN")
            for iid in insight_ids:
                insert_edge(con, source_node_id=leaf.question_node_id, target_node_id=iid,
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

    def status(self) -> List[ResearchState]:
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

    def drain_nowait(self) -> List[StepEvent]:
        """Pop all currently-buffered StepEvents without blocking (skips the
        internal sentinel). Lets a transport poll-and-drain the multiplexed
        stream and decide termination via ``is_complete`` — robust to a
        request/response server that only advances the loop while a request is
        in flight (the poller's ``await asyncio.sleep`` gives the research
        tasks loop time)."""
        out: List[StepEvent] = []
        while True:
            try:
                item = self._out.get_nowait()
            except asyncio.QueueEmpty:
                break
            if item is not _SESSION_DONE:
                out.append(item)
        return out


# ---------------------------------------------------------------------------
# M6 — recovery: reconstruct a session purely from the event log
# ---------------------------------------------------------------------------


_TERMINAL_ACTION = {
    ActionType.INVESTIGATION_COMPLETED.value: RunState.DONE,
    ActionType.INVESTIGATION_FAILED.value: RunState.FAILED,
    ActionType.INVESTIGATION_CHASE_HALTED.value: RunState.BUDGET_HALTED,
}


def _list_investigation_ids(events_dir: str) -> List[str]:
    if not os.path.isdir(events_dir):
        return []
    seen = set()
    for fn in os.listdir(events_dir):
        if fn.endswith(".parquet"):
            seen.add(fn[:-len(".parquet")])
        elif fn.endswith(".jsonl"):
            seen.add(fn[:-len(".jsonl")])
    return sorted(seen)


def reconstruct_session(session_id: str, *, events_dir: Optional[str] = None) -> SessionRecovery:
    """Rebuild a session's membership + per-research state from the event log
    alone — the durability guarantee. A child belongs to the session if its
    trajectory carries an ``investigation.spawned_from`` pointing at the
    session; its state is its terminal event (or ``running``)."""
    resolved = events_dir or default_events_dir()
    researches: List[ResearchState] = []
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
    return SessionRecovery(session_id=session_id, researches=researches)
