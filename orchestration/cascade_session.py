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
import contextlib
import fcntl
import hashlib
import logging
import os
import sys
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from typing import Any

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
CASCADE_LAUNCH_RESERVED = "cascade.launch_reserved"
CASCADE_SYNTHESIS_COMPLETED = "cascade.synthesis_tail.completed"
CASCADE_SESSION_TERMINAL = "cascade.session.terminal"


class LaunchGenerationActive(RuntimeError):
    """A durable reservation exists without a terminal session marker."""


@dataclass
class Leaf:
    """One approved plan leaf to launch: a sub-question + the graph question
    node it persisted as (so findings can be linked back to it)."""

    investigation_id: str
    sub_question: str
    question_node_id: str | None = None
    budget: BudgetCap = field(default_factory=BudgetCap)
    # Appended after the established positional fields so four-positional
    # callers keep binding their BudgetCap to ``budget``.
    plan_node_local_id: str | None = None


@dataclass
class ResearchState:
    investigation_id: str
    sub_question: str
    state: str
    question_node_id: str | None = None
    plan_node_local_id: str | None = None


@dataclass
class SessionRecovery:
    """Reconstructed-from-the-event-log view of a session. Carries no
    in-memory runtime state — proof a refresh/restart loses nothing."""

    session_id: str
    researches: list[ResearchState]
    plan_root_node_id: str | None = None
    approved_plan_tree: dict[str, Any] | None = None
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
        self.plan_root_node_id: str | None = None
        self.approved_plan_tree: dict[str, Any] | None = None
        self.launch_generation: int | None = None
        # Set by background completion (``_run_to_completion``) when the Loop 1
        # synthesis tail raises. A non-None value means the session never
        # reached ``DeepResearchComplete`` because synthesis failed — the
        # split-brain / silent-synthesis hazard the ANT-DRL programme guards.
        self.synthesis_tail_error: str | None = None

    # -- M1: launch with approval enforcement --------------------------

    async def launch(
        self,
        plan_root_node_id: str,
        leaves: Sequence[Leaf],
        *,
        approved_plan_tree: dict[str, Any] | None = None,
        launch_generation: int | None = None,
    ) -> list[Handle]:
        """Launch an approved plan as N investigations. Refuses an unapproved
        plan (SPR-05 gate). Each leaf is spawned_from the session parent."""
        assert_launchable(plan_root_node_id, db_path=self._db_path)
        generation = _reserve_launch_generation(
            self.session_id,
            plan_root_node_id=plan_root_node_id,
            events_dir=self._events_dir,
            requested_generation=launch_generation,
        )
        self.launch_generation = generation
        handles: list[Handle] = []
        try:
            if self._funnel is not None:
                await self._funnel.start()
            for leaf in leaves:
                self._leaves[leaf.investigation_id] = leaf
                plan = ResearchPlan(
                    investigation_id=leaf.investigation_id, sub_question=leaf.sub_question,
                    parent_investigation_id=self.session_id, budget=leaf.budget,
                    metadata={"cascade_launch_generation": generation},
                )
                handle = await self._runner.start(leaf.investigation_id, plan)
                self._handles[leaf.investigation_id] = handle
                handles.append(handle)
                # Pump this research's stream into the multiplexed session queue.
                self._pump_tasks.append(asyncio.create_task(self._pump(handle)))
        except BaseException:
            # Launch is atomic from the caller's perspective. A runner may have
            # accepted earlier leaves before a later start fails, so explicitly
            # cancel and drain every accepted handle before propagating. This
            # prevents invisible orphan work after the route returns an error.
            await self._abort_launch(handles)
            raise
        # This is a success receipt, not an intent: emit it only after every
        # runner handle exists. A partial start can leave child audit events,
        # but can never claim the complete approved tree launched.
        self.plan_root_node_id = plan_root_node_id
        self.approved_plan_tree = approved_plan_tree
        try:
            receipt_payload = {"plan_root_node_id": plan_root_node_id,
                           "launch_generation": generation,
                           "leaf_count": len(leaves),
                           # Immutable execution receipt. Loading the mutable
                           # graph plan later could show edits that were never
                           # launched.
                           "approved_plan_tree": approved_plan_tree,
                           "plan_version": (
                               approved_plan_tree.get("approval", {}).get("plan_version")
                               if isinstance(approved_plan_tree, dict) else None
                           ),
                           # Durable identity map for the live research trail.
                           # Recovery must never guess from question text or
                           # deterministic leaf suffixes.
                           "researches": [
                               {"investigation_id": leaf.investigation_id,
                                "sub_question": leaf.sub_question,
                                "question_node_id": leaf.question_node_id,
                                "plan_node_local_id": leaf.plan_node_local_id}
                               for leaf in leaves
                               ]}
            _persist_required_event(
                self.session_id,
                "cascade.launched",
                payload=receipt_payload,
                events_dir=self._events_dir,
            )
        except BaseException:
            # A launch does not exist until its durable success receipt exists.
            # Apply the same rollback if persistence itself fails after all
            # runners accepted their work.
            self.plan_root_node_id = None
            self.approved_plan_tree = None
            await self._abort_launch(handles)
            self.launch_generation = None
            raise
        return handles

    async def _abort_launch(self, handles: Sequence[Handle]) -> None:
        """Stop and drain every resource accepted by an uncommitted launch."""
        await asyncio.gather(
            *(self._runner.cancel(handle) for handle in handles),
            return_exceptions=True,
        )
        await asyncio.gather(*self._pump_tasks, return_exceptions=True)
        if self._funnel is not None:
            with contextlib.suppress(Exception):
                await self._funnel.drain_and_stop()
        self._handles.clear()
        self._leaves.clear()
        self._pump_tasks.clear()
        self.record_session_terminal()

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
                assert isinstance(item, StepEvent)
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

    def aggregate_cost(self) -> dict[str, object]:
        per = {iid: self._runner.cost(h).spent_usd for iid, h in self._handles.items()}
        return {
            "per_research": per,
            "session_total_usd": sum(per.values()),
            "aggregate_spent_usd": self._runner.budget.aggregate_spent,
            "aggregate_cap_usd": self._runner.budget.aggregate_cap_usd,
        }

    # -- M5/M7: join, merge-on-complete, failure isolation -------------

    async def join_and_merge(self) -> dict[str, object]:
        """Wait for all researches; drain the promotion funnel; link each
        research's promoted insights to its sub-question node. One research
        failing does not abort the merge for its siblings."""
        await self._runner.join()
        if self._funnel is not None:
            await self._funnel.drain_and_stop()
        linked = 0
        for _iid, leaf in self._leaves.items():
            if leaf.question_node_id is None:
                continue
            try:
                linked += self._link_findings(leaf)
            except Exception:  # isolation: a bad merge for one leaf is not fatal
                # Trace the silent loss: without this, a failing leaf drops its
                # question->resolved_by->insight edges and `linked` just
                # undercounts, with no record of which leaf or why. The trace
                # is itself guarded — a broken log channel must not break the
                # isolation contract (db_lock.py's log-then-continue pattern).
                with contextlib.suppress(Exception):
                    _log.exception(
                        "per-leaf finding-link failed for investigation_id=%s "
                        "(question_node_id=%s); leaf skipped, siblings continue",
                        leaf.investigation_id, leaf.question_node_id,
                    )
                continue
        return {"linked_findings": linked}

    def _link_findings(self, leaf: Leaf) -> int:
        """Link insight nodes promoted under this research to its sub-question
        node via question --resolved_by--> insight edges."""
        assert leaf.question_node_id is not None  # caller guards
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

    def status(self) -> list[ResearchState]:
        out = []
        for iid, leaf in self._leaves.items():
            h = self._handles.get(iid)
            st = self._runner.status(h).state.value if h else RunState.PENDING.value
            out.append(ResearchState(
                iid, leaf.sub_question, st, leaf.question_node_id,
                leaf.plan_node_local_id,
            ))
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
        if not ok or self.launch_generation is None:
            return False
        return any(
            event.get("action_type") == CASCADE_SYNTHESIS_COMPLETED
            and isinstance(event.get("payload"), dict)
            and event["payload"].get("cascade_launch_generation")
            == self.launch_generation
            for event in trajectory(self.session_id, events_dir=self._events_dir)
        )

    def record_synthesis_tail_complete(self, prior_parent_event_ids: set[str]) -> None:
        """Commit current-generation synthesis after the raw invariant passes."""
        if self.launch_generation is None:
            raise RuntimeError("cannot complete synthesis without a launch generation")
        ok, reasons = check_deep_research_complete(self.session_id)
        if not ok:
            raise RuntimeError(
                "synthesis tail returned without DeepResearchComplete: "
                + "; ".join(reasons)
            )
        new_parent_completion = any(
            event.get("action_type") == ActionType.INVESTIGATION_COMPLETED.value
            and isinstance(event.get("event_id"), str)
            and event["event_id"] not in prior_parent_event_ids
            for event in trajectory(self.session_id, events_dir=self._events_dir)
        )
        if not new_parent_completion:
            raise RuntimeError(
                "synthesis tail produced no current-run parent completion event"
            )
        payload = {"cascade_launch_generation": self.launch_generation}
        if any(
            event.get("action_type") == CASCADE_SYNTHESIS_COMPLETED
            and event.get("payload") == payload
            for event in trajectory(self.session_id, events_dir=self._events_dir)
        ):
            return
        _persist_required_event(
            self.session_id,
            CASCADE_SYNTHESIS_COMPLETED,
            payload=payload,
            events_dir=self._events_dir,
        )

    def record_session_terminal(self) -> None:
        """Release the durable launch lease after background completion ends."""
        if self.launch_generation is None:
            return
        _persist_required_event(
            self.session_id,
            CASCADE_SESSION_TERMINAL,
            payload={"cascade_launch_generation": self.launch_generation},
            events_dir=self._events_dir,
        )

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
                         "stage": stage,
                         "cascade_launch_generation": self.launch_generation},
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

    def terminal_status(self) -> dict[str, object]:
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

        prior_parent_event_ids = {
            event["event_id"]
            for event in trajectory(self.session_id, events_dir=self._events_dir)
            if isinstance(event.get("event_id"), str)
        }
        await run_synthesis_tail_from_pack(
            pack,
            broadcaster=broadcaster,
            coordinator=coordinator,
        )
        self.record_synthesis_tail_complete(prior_parent_event_ids)
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
                assert isinstance(item, StepEvent)
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


def _persist_required_event(
    investigation_id: str,
    action_type: str,
    *,
    payload: dict[str, Any],
    events_dir: str | None,
) -> str:
    """Persist and exactly re-read an event that forms part of launch commit."""
    event_id = log_event(
        investigation_id,
        action_type,
        payload=payload,
        role="user_agent",
        events_dir=events_dir,
    )
    matches = [
        event for event in trajectory(investigation_id, events_dir=events_dir)
        if event.get("event_id") == event_id
    ]
    if (
        event_id is None
        or len(matches) != 1
        or matches[0].get("investigation_id") != investigation_id
        or matches[0].get("action_type") != action_type
        or matches[0].get("payload") != payload
    ):
        raise RuntimeError(f"required {action_type} event was not persisted exactly")
    return event_id


def _next_launch_generation(
    session_id: str, *, events_dir: str | None = None
) -> int:
    """Return the next durable generation number for a deterministic session.

    The maximum is independent of event timestamps and trajectory ordering.
    API launch ownership prevents concurrent allocation in one process.
    """
    maximum = 0
    for event in trajectory(session_id, events_dir=events_dir):
        if event.get("action_type") not in {
            CASCADE_LAUNCH_RESERVED,
            "cascade.launched",
        }:
            continue
        payload = event.get("payload", {})
        if not isinstance(payload, dict):
            continue
        generation = payload.get("launch_generation")
        if (
            isinstance(generation, int)
            and not isinstance(generation, bool)
            and generation > maximum
        ):
            maximum = generation
    return maximum + 1


def _reserve_launch_generation(
    session_id: str,
    *,
    plan_root_node_id: str,
    events_dir: str | None,
    requested_generation: int | None,
) -> int:
    """Atomically allocate and persist a generation across API worker processes."""
    resolved = events_dir or default_events_dir()
    os.makedirs(resolved, exist_ok=True)
    lock_name = hashlib.sha256(session_id.encode("utf-8")).hexdigest() + ".launch.lock"
    lock_path = os.path.join(resolved, lock_name)
    with open(lock_path, "a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            rows = trajectory(session_id, events_dir=resolved)
            reservations = [
                event for event in rows
                if event.get("action_type") == CASCADE_LAUNCH_RESERVED
                and isinstance(event.get("payload"), dict)
                and isinstance(event["payload"].get("launch_generation"), int)
                and not isinstance(event["payload"].get("launch_generation"), bool)
            ]
            if reservations:
                latest_reserved = max(
                    event["payload"]["launch_generation"] for event in reservations
                )
                released = any(
                    event.get("action_type") == CASCADE_SESSION_TERMINAL
                    and isinstance(event.get("payload"), dict)
                    and event["payload"].get("cascade_launch_generation")
                    == latest_reserved
                    for event in rows
                )
                if not released:
                    raise LaunchGenerationActive(
                        f"session {session_id!r} generation {latest_reserved} is active"
                    )
            next_generation = _next_launch_generation(
                session_id, events_dir=resolved
            )
            generation = requested_generation or next_generation
            if isinstance(generation, bool) or generation <= 0:
                raise ValueError("launch_generation must be a positive integer")
            if generation != next_generation:
                raise ValueError(
                    "launch_generation must be the next durable generation "
                    f"({next_generation})"
                )
            _persist_required_event(
                session_id,
                CASCADE_LAUNCH_RESERVED,
                payload={
                    "launch_generation": generation,
                    "plan_root_node_id": plan_root_node_id,
                },
                events_dir=resolved,
            )
            return generation
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def reconstruct_session(session_id: str, *, events_dir: str | None = None) -> SessionRecovery:
    """Rebuild a session's membership + per-research state from the event log
    alone — the durability guarantee. A child belongs to the session if its
    trajectory carries an ``investigation.spawned_from`` pointing at the
    session; its state is its terminal event (or ``running``)."""
    resolved = events_dir or default_events_dir()
    plan_root_node_id: str | None = None
    approved_plan_tree: dict[str, Any] | None = None
    launch_emitted_at: str | None = None
    launch_generation: int | None = None
    research_identity: dict[str, tuple[str, str | None, str | None]] = {}
    receipts = [
        event for event in trajectory(session_id, events_dir=resolved)
        if event.get("action_type") == "cascade.launched"
    ]
    reservation_generations = [
        event["payload"]["launch_generation"]
        for event in trajectory(session_id, events_dir=resolved)
        if event.get("action_type") == CASCADE_LAUNCH_RESERVED
        and isinstance(event.get("payload"), dict)
        and isinstance(event["payload"].get("launch_generation"), int)
        and not isinstance(event["payload"].get("launch_generation"), bool)
        and event["payload"]["launch_generation"] > 0
    ]
    generated_receipts = []
    for event in receipts:
        payload = event.get("payload", {})
        generation = payload.get("launch_generation") if isinstance(payload, dict) else None
        if (
            isinstance(generation, int)
            and not isinstance(generation, bool)
            and generation > 0
        ):
            generated_receipts.append((generation, event))
    if reservation_generations:
        latest_reservation = max(reservation_generations)
        receipt_generations = {generation for generation, _event in generated_receipts}
        if latest_reservation not in receipt_generations:
            return SessionRecovery(session_id=session_id, researches=[])
    if generated_receipts:
        maximum_generation = max(generation for generation, _event in generated_receipts)
        newest = [
            event for generation, event in generated_receipts
            if generation == maximum_generation
        ]
        # One generation has exactly one success receipt. Conflicts are durable
        # corruption, not a tie that wall-clock order may resolve.
        if len(newest) != 1:
            return SessionRecovery(session_id=session_id, researches=[])
        chosen_receipt = newest[0]
    else:
        chosen_receipt = receipts[-1] if receipts else None
    if chosen_receipt is not None:
        ev = chosen_receipt
        # A deterministic session id can be relaunched. Each launch event is a
        # complete receipt boundary: never carry identity fields from an older
        # episode into a newer malformed/legacy one.
        plan_root_node_id = None
        approved_plan_tree = None
        research_identity = {}
        launch_emitted_at = (
            ev.get("emitted_at") if isinstance(ev.get("emitted_at"), str) else None
        )
        payload = ev.get("payload", {}) if isinstance(ev.get("payload"), dict) else {}
        generation = payload.get("launch_generation")
        if (
            isinstance(generation, int)
            and not isinstance(generation, bool)
            and generation > 0
        ):
            launch_generation = generation
        root = payload.get("plan_root_node_id")
        if isinstance(root, str) and root:
            plan_root_node_id = root
        snapshot = payload.get("approved_plan_tree")
        approved_plan_tree = snapshot if isinstance(snapshot, dict) else None
        launched = payload.get("researches")
        if isinstance(launched, list):
            for item in launched:
                if not isinstance(item, dict):
                    continue
                iid = item.get("investigation_id")
                sub_question = item.get("sub_question")
                qid = item.get("question_node_id")
                local_id = item.get("plan_node_local_id")
                if (
                    isinstance(iid, str) and iid
                    and isinstance(sub_question, str) and sub_question
                    and (qid is None or isinstance(qid, str))
                    and (local_id is None or isinstance(local_id, str))
                ):
                    research_identity[iid] = (sub_question, qid, local_id)
    researches: list[ResearchState] = []
    if research_identity:
        # New receipts use a monotonic generation copied into every child
        # lifecycle event. Timestamp filtering remains only for legacy receipts.
        for iid, (sub_q, qid, local_id) in sorted(research_identity.items()):
            state = RunState.PENDING
            for ev in trajectory(iid, events_dir=resolved):
                at = ev.get("action_type")
                payload = ev.get("payload", {}) if isinstance(ev.get("payload"), dict) else {}
                if launch_generation is not None:
                    if payload.get("cascade_launch_generation") != launch_generation:
                        continue
                else:
                    emitted_at = ev.get("emitted_at")
                    if launch_emitted_at is not None and (
                        not isinstance(emitted_at, str) or emitted_at <= launch_emitted_at
                    ):
                        continue
                if at == ActionType.INVESTIGATION_START_REQUESTED.value:
                    sub_q = payload.get("sub_question", sub_q)
                    state = RunState.RUNNING
                elif at in _TERMINAL_ACTION:
                    state = _TERMINAL_ACTION[at]
            researches.append(ResearchState(iid, sub_q, state.value, qid, local_id))
    else:
        # Legacy sessions have no complete receipt mapping. Preserve the old
        # membership recovery, but never invent plan identity for the UI.
        researches = _reconstruct_legacy_researches(
            session_id,
            resolved,
            generation_boundary=launch_emitted_at,
            launch_generation=launch_generation,
        )
    researches.sort(key=lambda r: r.investigation_id)
    tail_error = _recover_synthesis_tail_error(
        session_id,
        events_dir=resolved,
        generation_boundary=launch_emitted_at,
        launch_generation=launch_generation,
    )
    return SessionRecovery(
        session_id=session_id,
        researches=researches,
        plan_root_node_id=plan_root_node_id,
        approved_plan_tree=approved_plan_tree,
        synthesis_tail_error=tail_error,
    )


def _reconstruct_legacy_researches(
    session_id: str,
    resolved: str,
    *,
    generation_boundary: str | None = None,
    launch_generation: int | None = None,
) -> list[ResearchState]:
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
            if launch_generation is not None:
                if payload.get("cascade_launch_generation") != launch_generation:
                    continue
            else:
                emitted_at = ev.get("emitted_at")
                if generation_boundary is not None and (
                    not isinstance(emitted_at, str) or emitted_at <= generation_boundary
                ):
                    continue
            if at == ActionType.INVESTIGATION_SPAWNED_FROM.value:
                # Membership was captured above even when the spawn precedes a
                # legacy launch receipt; state remains generation-bounded.
                continue
            if at == ActionType.INVESTIGATION_START_REQUESTED.value:
                sub_q = payload.get("sub_question", sub_q)
                # Deterministic leaf ids can relaunch. A new start is a new
                # generation boundary and supersedes an older terminal state.
                state = RunState.RUNNING
            elif at in _TERMINAL_ACTION:
                state = _TERMINAL_ACTION[at]
        if parent == session_id:
            researches.append(ResearchState(iid, sub_q, state.value))
    return researches


def _recover_synthesis_tail_error(
    session_id: str,
    *,
    events_dir: str | None = None,
    generation_boundary: str | None = None,
    launch_generation: int | None = None,
) -> str | None:
    """The last ``cascade.synthesis_tail.failed`` audit event recorded on the
    session's own trajectory, or None if none was emitted. Honest by
    construction: absence of the event yields None (we never fabricate a
    failure or a success the event log cannot prove)."""
    last: str | None = None
    for ev in trajectory(session_id, events_dir=events_dir):
        payload = ev.get("payload", {}) if isinstance(ev.get("payload"), dict) else {}
        if launch_generation is not None:
            if payload.get("cascade_launch_generation") != launch_generation:
                continue
        else:
            emitted_at = ev.get("emitted_at")
            if generation_boundary is not None and (
                not isinstance(emitted_at, str) or emitted_at <= generation_boundary
            ):
                continue
        if ev.get("action_type") == SYNTHESIS_TAIL_FAILED:
            last = payload.get("error") or last
    return last
