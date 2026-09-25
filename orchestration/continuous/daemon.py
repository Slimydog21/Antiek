"""Continuous research daemon — main loop + CLI per master-spec §7.3.

The daemon scans the event log every minute, builds a GapRegistry
from ``evidence.retrieve.delivered`` events across all investigations,
scores each gap (recency × co-occurrence × interaction boost), and
spawns investigations against the top-scoring gaps subject to the
DaemonBudget caps.

Investigation-spawn is parameterized as a ``SpawnFn`` callable so the
daemon's mechanics can be tested without the orchestrator HTTP path
attached. The default ``no_op_spawn`` returns ``None`` (no spawn).

Autonomous-diligence SPR-02 (the activation): when
``ANTIEK_DAEMON_SPAWN_ENABLED`` is truthy, ``main()`` wires the REAL spawn
path — ``make_emit_spawn_fn`` EMITS ``investigation.start_requested``
through the event broadcaster (the exact mechanism orchestrator chase mode
uses, orchestration/loop_one/orchestrator.py:2355-2375) with the daemon
policy id, arriving at the ONE start handler every spawn crosses — plus a
``DbFlagSource`` draining the owner-flag queue FIRST (a flag is an explicit
human request; it always outranks a scored gap). When the env is UNSET (the
shipped default), ``run_forever`` receives ``no_op_spawn`` and NO flag
source — byte-equivalent to the pre-activation behavior; enabling is an
explicit operator act, never this program's.

Single-iteration design:
  ``run_one_iteration(...)`` runs the full scan + score + spawn cycle
  once. The CLI ``run_forever`` calls it on a loop with a configurable
  sleep. Tests invoke ``run_one_iteration`` directly.
"""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from collections.abc import Callable
from typing import Any, Optional, Protocol

from substrate.event_log.events import default_events_dir, trajectory

from .budget import DaemonBudget, DaemonBudgetError
from .research_topic import ResearchTopic, topic_id_for
from .scoring import GapRegistry, normalize_gap_description, score_gap


# ── Public types ──────────────────────────────────────────────────────


#: A spawn function. Takes (question, context) returns either the new
#: investigation_id or None if the spawn was declined. Implementors
#: own the actual cost — the daemon only reserves an expected amount
#: via DaemonBudget; the spawn function reports actual cost back via
#: a callback on its context dict (key ``record_actual_cb``).
SpawnFn = Callable[[str, dict[str, Any]], str | None]


def no_op_spawn(question: str, context: dict[str, Any]) -> str | None:  # noqa: ARG001
    """Default spawn: does nothing, returns None. Substitute the real
    orchestrator wiring in production (Sprint 14 follow-up)."""
    return None


@dataclass
class DaemonConfig:
    """Runtime configuration for ``run_one_iteration`` and the CLI loop."""

    events_dir: Optional[str] = None
    expected_cost_per_spawn_usd: float = 0.50
    max_spawns_per_iteration: int = 3
    min_score_to_spawn: float = 0.05
    spawn_policy_id: str = "continuous_daemon"
    sleep_seconds: float = 60.0
    # Autonomous-diligence SPR-02: the one NEW cap — at most this many
    # in-flight investigations carrying the daemon policy id (counted
    # READ-ONLY from the event log each iteration — no poller, no lock).
    max_concurrent_daemon_investigations: int = 2


#: The kill switch (autonomous-diligence SPR-02): UNSET = OFF, the shipped
#: default. Truthy ("1", "true", "yes", "on") wires the real spawn path in
#: ``main()``. This program NEVER sets it — enabling is the operator's act.
ENV_DAEMON_SPAWN_ENABLED = "ANTIEK_DAEMON_SPAWN_ENABLED"


def spawn_enabled(env: dict[str, str] | Any) -> bool:
    """Whether the activation env is truthy (the prod-safety gate)."""
    raw = env.get(ENV_DAEMON_SPAWN_ENABLED, "")
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


# ── Owner-flag candidates (autonomous-diligence SPR-02) ────────────────


class FlagSource(Protocol):
    """The daemon's view of the diligence queue: claim queued flags (oldest
    first, question resolved substrate-side) and write the spawn back. Both
    operations hold the DuckDB write/read lock in BOUNDED scopes — never
    across a spawn (the arXiv writer-lock lesson,
    tools/arxiv_oai_sync.py:44-47,105-107)."""

    def queued_oldest_first(self) -> list[Any]:  # list[QueuedClaim]
        ...

    def mark_spawned(
        self, *, owner_user_id: str, flag_id: str, investigation_id: str,
        receipt_json: str | None = None,
    ) -> None:
        ...

    def record_skip(
        self, *, owner_user_id: str, flag_id: str, receipt_json: str
    ) -> None:
        ...


class DbFlagSource:
    """The production flag source: the diligence queue over the graph DB.
    A short READ to claim, then per-spawn a short WRITE to transition —
    the lock is never held across the spawn (the broadcast wait)."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    def queued_oldest_first(self) -> list[Any]:
        import os as _os

        from runtime.db_lock import connect_read
        from substrate.diligence.store import DiligenceStore

        # A not-yet-created DB is an honestly empty queue (a fresh
        # deployment flags nothing until the first flag exists) — never an
        # IO error crashing the iteration.
        if not _os.path.exists(self._db_path):
            return []
        con = connect_read(self._db_path)
        try:
            return DiligenceStore().list_queued_claims(con)
        finally:
            con.close()

    def mark_spawned(
        self, *, owner_user_id: str, flag_id: str, investigation_id: str,
        receipt_json: str | None = None,
    ) -> None:
        from runtime.db_lock import connect_write
        from substrate.diligence.store import DiligenceStore

        with connect_write(
            self._db_path, purpose="diligence/daemon-mark-spawned"
        ) as con:
            DiligenceStore().mark_spawned(
                con,
                owner_user_id=owner_user_id,
                flag_id=flag_id,
                spawned_investigation_id=investigation_id,
                receipt_json=receipt_json,
            )

    def record_skip(
        self, *, owner_user_id: str, flag_id: str, receipt_json: str
    ) -> None:
        from runtime.db_lock import connect_write
        from substrate.diligence.store import DiligenceStore

        with connect_write(
            self._db_path, purpose="diligence/daemon-record-skip"
        ) as con:
            DiligenceStore().record_skip(
                con,
                owner_user_id=owner_user_id,
                flag_id=flag_id,
                receipt_json=receipt_json,
            )


def make_emit_spawn_fn(broadcaster: Any) -> SpawnFn:
    """The production spawn_fn: EMIT ``investigation.start_requested``
    through the event broadcaster — the EXACT mechanism orchestrator chase
    mode uses (orchestrator.py:2355-2375), with the daemon policy id, so the
    spawn arrives at the ONE start handler (orchestrator.py:2083-2096) under
    the same caps, tier inheritance, and chase-halt semantics as every chase
    and every UI launch. NO new entry point.

    Sync bridge: the daemon loop is synchronous, so each spawn runs the
    emit on a fresh event loop (``asyncio.run``) — spawns are rare and
    capped (≤3/iteration). The emit is durable in the event log BEFORE the
    broadcast; an events-disabled emit (None) is an honest decline.
    """

    def spawn(question: str, context: dict[str, Any]) -> str | None:
        import asyncio
        import uuid

        from orchestration.loop_one.coordinator import broadcast_emit
        from substrate.schemas.events import InvestigationStartRequestedPayload

        child_id = f"inv-{uuid.uuid4().hex[:12]}"
        payload = InvestigationStartRequestedPayload(
            question=question,
            context=str(context.get("context") or ""),
            parent_investigation_id=context.get("parent_investigation_id"),
            spawn_context=context.get("spawn_context"),
        )
        eid = asyncio.run(
            broadcast_emit(
                broadcaster,
                child_id,
                payload,
                role="continuous_daemon",
                policy_id=str(
                    context.get("policy_id") or DaemonConfig.spawn_policy_id
                ),
            )
        )
        return child_id if eid is not None else None

    return spawn


@dataclass
class DaemonState:
    """Mutable daemon state carried across iterations.

    The GapRegistry is rebuilt fresh from the event log each iteration
    (so the daemon always sees the truth on disk), but chase_count and
    topic depths persist in-memory across iterations so the decay
    rules work correctly.
    """

    chase_counts_by_key: dict[str, int] = field(default_factory=dict)
    topics: dict[str, ResearchTopic] = field(default_factory=dict)
    iterations_run: int = 0
    spawns_attempted: int = 0
    spawns_succeeded: int = 0


# ── Event-log scan ────────────────────────────────────────────────────


def _list_investigation_ids(events_dir: str) -> list[str]:
    """Enumerate investigations by scanning the events dir for jsonl
    and parquet files. Mirrors ``action_counts`` in event_log.events
    when no investigation_id is given."""
    if not os.path.isdir(events_dir):
        return []
    seen: set[str] = set()
    for fn in os.listdir(events_dir):
        if fn.endswith(".parquet"):
            seen.add(fn[: -len(".parquet")])
        elif fn.endswith(".jsonl"):
            seen.add(fn[: -len(".jsonl")])
    return sorted(seen)


def _parse_emitted_at(raw: Any) -> datetime:
    """Pull an emitted_at field off an event dict. Returns now() if
    missing/malformed — degrade gracefully rather than crash the
    daemon on a corrupt event."""
    if isinstance(raw, str):
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return datetime.now(timezone.utc)
    return datetime.now(timezone.utc)


def scan_gaps(
    events_dir: Optional[str] = None,
    *,
    investigation_filter: Optional[set[str]] = None,
) -> GapRegistry:
    """Scan the event log for ``evidence.retrieve.delivered`` events
    and build a GapRegistry. Public surface so tests can construct
    the registry directly from a fixture event log."""
    resolved = events_dir or default_events_dir()
    registry = GapRegistry()
    for iid in _list_investigation_ids(resolved):
        if investigation_filter is not None and iid not in investigation_filter:
            continue
        for ev in trajectory(iid, events_dir=resolved):
            if ev.get("action_type") != "evidence.retrieve.delivered":
                continue
            payload = ev.get("payload") or {}
            gaps = payload.get("evidentiary_gaps") or []
            emitted_at = _parse_emitted_at(ev.get("emitted_at"))
            for gap in gaps:
                desc = gap.get("gap_description") or ""
                if not desc.strip():
                    continue
                registry.observe(
                    gap_description=desc,
                    additional_retrieval_suggested=gap.get(
                        "additional_retrieval_suggested"
                    ),
                    investigation_id=iid,
                    emitted_at=emitted_at,
                )
        # Also count operator-interaction signal: question.identified
        # events with the same gap text get an interaction bump.
        for ev in trajectory(iid, events_dir=resolved):
            if ev.get("action_type") != "question.identified":
                continue
            payload = ev.get("payload") or {}
            text = payload.get("question_text") or ""
            if not text.strip():
                continue
            from .scoring import normalize_gap_description
            key = normalize_gap_description(text)
            if key in registry.entries:
                registry.mark_interaction(key)
    return registry


#: Terminal action types (the cascade_session.py:21 terminal set): an
#: investigation with one of these in its trajectory is no longer in-flight.
_TERMINAL_ACTIONS = frozenset(
    {
        "investigation.completed",
        "investigation.failed",
        "investigation.chase_halted",
    }
)


def _inflight_investigations(events_dir: str | None) -> dict[str, dict[str, Any]]:
    """In-flight investigations, READ-ONLY from the event log (start
    requested, no terminal event yet). Maps id → {policy_id, question_key}
    — the concurrency cap's count and the in-flight-question dedupe set,
    computed per iteration; never a poller, never a lock."""
    out: dict[str, dict[str, Any]] = {}
    resolved = events_dir or default_events_dir()
    for iid in _list_investigation_ids(resolved):
        start: dict[str, Any] | None = None
        terminal = False
        for ev in trajectory(iid, events_dir=resolved):
            at = ev.get("action_type")
            if at == "investigation.start_requested" and start is None:
                start = ev
            elif at in _TERMINAL_ACTIONS:
                terminal = True
        if start is None or terminal:
            continue
        payload = start.get("payload") or {}
        question = payload.get("question") or ""
        out[iid] = {
            "policy_id": start.get("policy_id"),
            "question_key": (
                normalize_gap_description(question) if question.strip() else None
            ),
        }
    return out


# ── Single iteration ──────────────────────────────────────────────────


@dataclass
class IterationResult:
    """What happened during one daemon iteration. Useful for tests +
    structured logging."""

    gaps_observed: int
    gaps_eligible: int
    spawns_attempted: int
    spawns_succeeded: int
    spawned_investigation_ids: list[str]
    halted_by_budget: bool
    skipped_reasons: dict[str, int]
    # Autonomous-diligence SPR-02: the owner-flag phase's receipts.
    flags_queued: int = 0
    flags_spawned: int = 0


def run_one_iteration(
    *,
    state: DaemonState,
    config: DaemonConfig,
    budget: DaemonBudget,
    spawn_fn: SpawnFn = no_op_spawn,
    flag_source: FlagSource | None = None,
    now: Optional[datetime] = None,
) -> IterationResult:
    """One scan → score → spawn cycle. Returns an IterationResult for
    inspection. Mutates ``state`` (chase_counts, topics, counters).
    Never raises on a budget failure — converts to a skipped_reason
    so the daemon keeps going.

    Autonomous-diligence SPR-02: with a ``flag_source`` wired (the enabled
    CLI), OWNER FLAGS drain FIRST — an explicit human request always
    outranks a scored gap. With ``flag_source=None`` (the shipped default)
    the flag phase is skipped ENTIRELY — byte-equivalent to the
    pre-activation iteration."""
    state.iterations_run += 1
    registry = scan_gaps(events_dir=config.events_dir)

    # Re-apply persistent chase counts from prior iterations.
    for key, count in state.chase_counts_by_key.items():
        entry = registry.entries.get(key)
        if entry is not None:
            entry.chase_count = count

    # Score + sort.
    scored: list[tuple[float, str, str]] = []
    for entry in registry.values():
        s = score_gap(entry, now=now)
        if s >= config.min_score_to_spawn:
            scored.append((s, entry.normalized_key, entry.gap_description))
    scored.sort(key=lambda t: t[0], reverse=True)
    eligible = len(scored)

    # The owner-flag phase (SPR-02). Claims are read in a bounded scope
    # INSIDE the source; the write-back per spawn the same — the lock is
    # never held across a spawn (the arXiv writer-lock lesson).
    flags = flag_source.queued_oldest_first() if flag_source is not None else []
    flags_spawned = 0

    spawned: list[str] = []
    skipped: dict[str, int] = {}
    halted_by_budget = False
    spawn_slots = config.max_spawns_per_iteration

    # The concurrency cap + in-flight-question dedupe set, READ-ONLY from
    # the event log (only computed when something could spawn).
    if flags or scored:
        inflight = _inflight_investigations(config.events_dir)
        daemon_inflight = sum(
            1
            for meta in inflight.values()
            if meta["policy_id"] == config.spawn_policy_id
        )
        inflight_questions = {
            meta["question_key"]
            for meta in inflight.values()
            if meta["question_key"] is not None
        }
    else:
        daemon_inflight = 0
        inflight_questions = set()

    # (1) OWNER FLAGS, oldest first.
    def _skip_receipt(claim: Any, reason: str, detail: str) -> None:
        """The daemon's bookkeeping (SPR-03): the honest skip reason on the
        flag row, in the source's OWN bounded write scope."""
        assert flag_source is not None  # the loop below only runs with one
        flag_source.record_skip(
            owner_user_id=claim.flag.owner_user_id,
            flag_id=claim.flag.flag_id,
            receipt_json=json.dumps(
                {
                    "kind": "skipped",
                    "reason": reason,
                    "detail": detail,
                    "iteration": state.iterations_run,
                }
            ),
        )

    for claim in flags:
        if spawn_slots <= 0:
            skipped["iteration_spawn_cap"] = skipped.get("iteration_spawn_cap", 0) + 1
            break
        state.spawns_attempted += 1

        question = claim.question
        if question is None or not question.strip():
            # The flagged node vanished between flag and spawn — honest
            # receipt, never a fabricated question.
            skipped["flag_ungrounded_at_spawn"] = (
                skipped.get("flag_ungrounded_at_spawn", 0) + 1
            )
            _skip_receipt(claim, "ungrounded", "the flagged note is gone")
            continue
        if daemon_inflight >= config.max_concurrent_daemon_investigations:
            skipped["concurrency_cap"] = skipped.get("concurrency_cap", 0) + 1
            _skip_receipt(
                claim,
                "concurrency",
                f"the loop is at capacity ({config.max_concurrent_daemon_investigations} in flight)",
            )
            break
        question_key = normalize_gap_description(question)
        if question_key in inflight_questions:
            skipped["in_flight_question"] = skipped.get("in_flight_question", 0) + 1
            _skip_receipt(claim, "in_flight", "this question is already running")
            continue

        try:
            budget.reserve(config.expected_cost_per_spawn_usd, now=now)
        except DaemonBudgetError as e:
            halted_by_budget = True
            reason = e.args[0] if e.args else "budget_exceeded"
            skipped[reason] = skipped.get(reason, 0) + 1
            _skip_receipt(claim, "budget", str(reason))
            break

        tid = topic_id_for(question)
        topic = state.topics.get(tid)
        if topic is None:
            topic = ResearchTopic(topic_id=tid, root_question=question)
            state.topics[tid] = topic
        if not topic.can_chase():
            skipped["topic_depth_exceeded"] = (
                skipped.get("topic_depth_exceeded", 0) + 1
            )
            budget.record_actual(-config.expected_cost_per_spawn_usd, now=now)
            _skip_receipt(claim, "topic_depth", "this topic reached its depth cap")
            continue

        # A flag spawns as a CHILD of its source investigation when present
        # (else a cold start with the object as the question).
        context = {
            "policy_id": config.spawn_policy_id,
            "flag_id": claim.flag.flag_id,
            "topic_id": tid,
            "expected_cost_usd": config.expected_cost_per_spawn_usd,
            "parent_investigation_id": claim.flag.source_investigation_id,
            "spawn_context": question,
        }
        new_iid = spawn_fn(question, context)
        if new_iid is None:
            skipped["spawn_declined"] = skipped.get("spawn_declined", 0) + 1
            budget.record_actual(-config.expected_cost_per_spawn_usd, now=now)
            continue

        # The write-back — status → spawned + the investigation id + the
        # SPAWN RECEIPT (SPR-03: the reserve amount + the caps checked) — in
        # the source's OWN bounded write scope (never held across the spawn).
        flag_source.mark_spawned(  # type: ignore[union-attr]
            owner_user_id=claim.flag.owner_user_id,
            flag_id=claim.flag.flag_id,
            investigation_id=new_iid,
            receipt_json=json.dumps(
                {
                    "kind": "spawned",
                    "reserve_usd": config.expected_cost_per_spawn_usd,
                    "caps_checked": [
                        "per_spawn_reserve",
                        "daily",
                        "iteration",
                        "concurrency",
                        "topic_depth",
                    ],
                    "iteration": state.iterations_run,
                }
            ),
        )
        state.spawns_succeeded += 1
        flags_spawned += 1
        spawned.append(new_iid)
        spawn_slots -= 1
        inflight_questions.add(question_key)
        topic.record_spawn(new_iid, depth=topic.max_depth_reached + 1)

    # (2) SCORED GAPS — the existing scorer's candidates, untouched; the
    # same caps apply (iteration slots shrink by what flags consumed).
    spawn_targets = scored[: max(0, spawn_slots)]

    for score, key, description in spawn_targets:
        state.spawns_attempted += 1

        # The concurrency cap (the count is READ at iteration start — the
        # iteration's own spawns are counted next iteration, when they are
        # in-flight in the log) and the in-flight-question dedupe apply to
        # EVERY candidate (flags and gaps alike).
        if daemon_inflight >= config.max_concurrent_daemon_investigations:
            skipped["concurrency_cap"] = skipped.get("concurrency_cap", 0) + 1
            break
        if key in inflight_questions:
            skipped["in_flight_question"] = skipped.get("in_flight_question", 0) + 1
            continue

        # Budget reservation.
        try:
            budget.reserve(
                config.expected_cost_per_spawn_usd, now=now,
            )
        except DaemonBudgetError as e:
            halted_by_budget = True
            reason = e.args[0] if e.args else "budget_exceeded"
            skipped[reason] = skipped.get(reason, 0) + 1
            # Subsequent gaps will all fail the same cap; stop early.
            break

        # Topic-depth check.
        tid = topic_id_for(description)
        topic = state.topics.get(tid)
        if topic is None:
            topic = ResearchTopic(topic_id=tid, root_question=description)
            state.topics[tid] = topic
        if not topic.can_chase():
            skipped["topic_depth_exceeded"] = (
                skipped.get("topic_depth_exceeded", 0) + 1
            )
            # Refund the reserved budget.
            budget.record_actual(-config.expected_cost_per_spawn_usd, now=now)
            continue

        # Spawn.
        context = {
            "policy_id": config.spawn_policy_id,
            "topic_id": tid,
            "gap_score": score,
            "gap_normalized_key": key,
            "expected_cost_usd": config.expected_cost_per_spawn_usd,
        }
        new_iid = spawn_fn(description, context)
        if new_iid is None:
            skipped["spawn_declined"] = skipped.get("spawn_declined", 0) + 1
            budget.record_actual(-config.expected_cost_per_spawn_usd, now=now)
            continue

        state.spawns_succeeded += 1
        spawned.append(new_iid)
        spawn_slots -= 1
        inflight_questions.add(key)
        state.chase_counts_by_key[key] = state.chase_counts_by_key.get(key, 0) + 1
        registry.mark_chased(key)
        topic.record_spawn(new_iid, depth=topic.max_depth_reached + 1)

    return IterationResult(
        gaps_observed=len(registry),
        gaps_eligible=eligible,
        spawns_attempted=state.spawns_attempted,
        spawns_succeeded=state.spawns_succeeded,
        spawned_investigation_ids=spawned,
        halted_by_budget=halted_by_budget,
        skipped_reasons=skipped,
        flags_queued=len(flags),
        flags_spawned=flags_spawned,
    )


# ── CLI loop ──────────────────────────────────────────────────────────


def run_forever(
    *,
    config: Optional[DaemonConfig] = None,
    budget: Optional[DaemonBudget] = None,
    spawn_fn: SpawnFn = no_op_spawn,
    flag_source: FlagSource | None = None,
    iterations: Optional[int] = None,
) -> DaemonState:
    """Long-running loop. ``iterations=None`` means forever; finite
    values let smoke tests invoke a known number of cycles."""
    cfg = config or DaemonConfig()
    bdg = budget or DaemonBudget.from_env()
    state = DaemonState()
    count = 0
    while True:
        if iterations is not None and count >= iterations:
            break
        try:
            result = run_one_iteration(
                state=state, config=cfg, budget=bdg, spawn_fn=spawn_fn,
                flag_source=flag_source,
            )
            sys.stderr.write(
                json.dumps(
                    {
                        "iter": state.iterations_run,
                        "gaps_observed": result.gaps_observed,
                        "gaps_eligible": result.gaps_eligible,
                        "spawned": result.spawned_investigation_ids,
                        "skipped": result.skipped_reasons,
                        "halted_by_budget": result.halted_by_budget,
                    }
                )
                + "\n"
            )
            sys.stderr.flush()
        except Exception as e:  # noqa: BLE001 — daemon must never crash on one bad event
            sys.stderr.write(
                json.dumps({"iter": state.iterations_run, "error": str(e)}) + "\n"
            )
            sys.stderr.flush()
        count += 1
        if iterations is not None and count >= iterations:
            break
        time.sleep(cfg.sleep_seconds)
    return state


def main() -> None:
    """Module CLI: ``python -m orchestration.continuous``. Reads
    config from env and runs forever.

    THE PROD-SAFETY GATE (autonomous-diligence SPR-02): with
    ``ANTIEK_DAEMON_SPAWN_ENABLED`` unset (the shipped default), the loop
    receives ``no_op_spawn`` and NO flag source — byte-equivalent to the
    pre-activation daemon (it scores and stops). When the operator sets the
    env truthy — an explicit act, never this program's — the loop receives
    the real emit spawn_fn (the broadcaster path) and the diligence-queue
    flag source."""
    config = DaemonConfig(
        sleep_seconds=float(os.environ.get("ANTIEK_DAEMON_SLEEP_SECONDS", "60")),
        expected_cost_per_spawn_usd=float(
            os.environ.get("ANTIEK_DAEMON_EXPECTED_COST_USD", "0.50")
        ),
    )
    spawn_fn: SpawnFn = no_op_spawn
    flag_source: FlagSource | None = None
    if spawn_enabled(os.environ):
        # Deferred imports: the API/broadcast layer only loads when the
        # operator enabled spawning — the shipped default never pays it.
        from interfaces.research.api.broadcast import EventBroadcaster
        from substrate.graph import default_db_path, ensure_initialized

        spawn_fn = make_emit_spawn_fn(EventBroadcaster())
        flag_source = DbFlagSource(ensure_initialized(default_db_path()))
    run_forever(config=config, spawn_fn=spawn_fn, flag_source=flag_source)


if __name__ == "__main__":
    main()
