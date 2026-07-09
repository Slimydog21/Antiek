"""Spawn bridges for the continuous research daemon.

The daemon defaults to dry-run/no-op behavior. This module owns explicit opt-in
bridges so the scan/score/budget mechanics in ``daemon.py`` can stay stable.
"""

from __future__ import annotations

import os
import uuid
from typing import Any

from substrate.event_log.events import emit_typed
from substrate.schemas import InvestigationStartRequestedPayload

from .daemon import DaemonConfig, SpawnFn, no_op_spawn


def event_log_spawn(question: str, context: dict[str, Any]) -> str | None:
    """Write a daemon-policy ``investigation.start_requested`` event.

    This is the first production-safe bridge for "midnight oil": it records the
    same canonical start event the API uses, marked with the daemon policy ID,
    but it does not call model providers by itself. The operator must opt in
    with ``ANTIEK_DAEMON_SPAWN_MODE=event_log``.
    """
    investigation_id = f"inv-daemon-{uuid.uuid4().hex[:12]}"
    policy_id = str(context.get("policy_id") or DaemonConfig.spawn_policy_id)
    event_id = emit_typed(
        investigation_id,
        InvestigationStartRequestedPayload(
            question=question,
            context=_spawn_context_text(context),
            spawn_context=question,
        ),
        role="continuous-daemon",
        policy_id=policy_id,
    )
    return investigation_id if event_id is not None else None


def _spawn_context_text(context: dict[str, Any]) -> str:
    """Compact, stable context passed to the decomposer for daemon spawns."""
    topic_id = str(context.get("topic_id") or "")
    score = context.get("gap_score")
    expected_cost = context.get("expected_cost_usd")
    parts = ["Spawned by Antiek's continuous research daemon."]
    if topic_id:
        parts.append(f"topic_id={topic_id}")
    if isinstance(score, int | float):
        parts.append(f"gap_score={float(score):.4f}")
    if isinstance(expected_cost, int | float):
        parts.append(f"expected_cost_usd={float(expected_cost):.4f}")
    return " ".join(parts)


def spawn_fn_from_env() -> SpawnFn:
    """Resolve the daemon spawn implementation from env.

    Defaults to ``no_op_spawn``. ``event_log`` is the first explicit opt-in:
    it records daemon-policy start events, but it does not call model providers
    by itself.
    """
    mode = os.environ.get("ANTIEK_DAEMON_SPAWN_MODE", "noop").strip().lower()
    if mode in {"", "noop", "no_op", "dry_run"}:
        return no_op_spawn
    if mode == "event_log":
        return event_log_spawn
    raise ValueError(
        "ANTIEK_DAEMON_SPAWN_MODE must be one of: noop, dry_run, event_log"
    )
