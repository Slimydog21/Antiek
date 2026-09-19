"""Continuous research daemon — main loop + CLI per master-spec §7.3.

The daemon scans the event log every minute, builds a GapRegistry
from ``evidence.retrieve.delivered`` events across all investigations,
scores each gap (recency × co-occurrence × interaction boost), and
spawns investigations against the top-scoring gaps subject to the
DaemonBudget caps.

Investigation-spawn is parameterized as a ``SpawnFn`` callable so the
daemon's mechanics can be tested without the orchestrator HTTP path
attached. The default ``no_op_spawn`` returns ``None`` (no spawn).
Production wiring lives in a follow-up Sprint 14 PR that connects
``run_one_iteration``'s spawn_fn to ``orchestration.loop_one`` —
substrate-only here, no live spawning until that wiring lands and
the operator confirms.

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
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from substrate.event_log.events import default_events_dir, trajectory

from .budget import DaemonBudget, DaemonBudgetError
from .research_topic import ResearchTopic, topic_id_for
from .scoring import GapRegistry, score_gap

# ── Public types ──────────────────────────────────────────────────────


#: A spawn function. Takes (question, context) returns either the new
#: investigation_id or None if the spawn was declined. Implementors
#: own the actual cost — the daemon only reserves an expected amount
#: via DaemonBudget; the spawn function reports actual cost back via
#: a callback on its context dict (key ``record_actual_cb``).
SpawnFn = Callable[[str, dict], str | None]


def no_op_spawn(question: str, context: dict) -> str | None:  # noqa: ARG001
    """Default spawn: does nothing, returns None. Substitute the real
    orchestrator wiring in production (Sprint 14 follow-up)."""
    return None


@dataclass
class DaemonConfig:
    """Runtime configuration for ``run_one_iteration`` and the CLI loop."""

    events_dir: str | None = None
    expected_cost_per_spawn_usd: float = 0.50
    max_spawns_per_iteration: int = 3
    min_score_to_spawn: float = 0.05
    spawn_policy_id: str = "continuous_daemon"
    sleep_seconds: float = 60.0


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
            return datetime.now(UTC)
    return datetime.now(UTC)


def scan_gaps(
    events_dir: str | None = None,
    *,
    investigation_filter: set[str] | None = None,
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


def run_one_iteration(
    *,
    state: DaemonState,
    config: DaemonConfig,
    budget: DaemonBudget,
    spawn_fn: SpawnFn = no_op_spawn,
    now: datetime | None = None,
) -> IterationResult:
    """One scan → score → spawn cycle. Returns an IterationResult for
    inspection. Mutates ``state`` (chase_counts, topics, counters).
    Never raises on a budget failure — converts to a skipped_reason
    so the daemon keeps going."""
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

    spawn_targets = scored[: config.max_spawns_per_iteration]
    spawned: list[str] = []
    skipped: dict[str, int] = {}
    halted_by_budget = False

    for score, key, description in spawn_targets:
        state.spawns_attempted += 1

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
    )


# ── CLI loop ──────────────────────────────────────────────────────────


def run_forever(
    *,
    config: DaemonConfig | None = None,
    budget: DaemonBudget | None = None,
    spawn_fn: SpawnFn = no_op_spawn,
    iterations: int | None = None,
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
    config from env and runs forever."""
    config = DaemonConfig(
        sleep_seconds=float(os.environ.get("ANTIEK_DAEMON_SLEEP_SECONDS", "60")),
        expected_cost_per_spawn_usd=float(
            os.environ.get("ANTIEK_DAEMON_EXPECTED_COST_USD", "0.50")
        ),
    )
    run_forever(config=config)


if __name__ == "__main__":
    main()
