"""Sprint-14 attach: continuous-daemon spawn_fn → Loop One start event.

The continuous daemon's ``spawn_fn`` is intentionally injectable. Production
historically used ``no_op_spawn``. This module supplies a real attach that:

1. Allocates a new investigation id.
2. Emits ``INVESTIGATION_START_REQUESTED`` via ``emit_typed`` (the same
   entry Loop One already subscribes to).
3. Optionally settles the reserved hold via ``context['report_actual_cost']``
   when hooks were installed by ``wrap_spawn_fn`` (#772).

Event emission has no provider cost yet — actual reported as ``0.0`` so the
reserved hold is refunded honestly (reserved ≠ left as fake spend).

Does **not** edit ``daemon.py`` / ``budget.py`` (§7.4 tripwire). Compose at
the CLI / ``run_one_iteration(..., spawn_fn=...)`` boundary.
"""

from __future__ import annotations

import contextlib
import os
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from orchestration.continuous.daemon import SpawnFn
from substrate.event_log.events import emit_typed
from substrate.schemas.events import InvestigationStartRequestedPayload

EmitTypedFn = Callable[..., str | None]


def _resolve_events_dir(events_dir: str | None) -> str:
    """Canonical events dir for emit + post-write persistence check."""
    if events_dir:
        return events_dir
    from substrate.event_log.events import default_events_dir

    return str(default_events_dir())


def _event_persisted(investigation_id: str, events_dir: str) -> bool:
    """True only when a non-empty trajectory jsonl exists for the investigation."""
    path = Path(events_dir) / f"{investigation_id}.jsonl"
    try:
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


def make_loop_one_spawn_fn(
    *,
    events_dir: str | None = None,
    policy_id: str = "continuous_daemon",
    emit: EmitTypedFn | None = None,
    settle_emit_cost_usd: float = 0.0,
) -> SpawnFn:
    """Return a ``SpawnFn`` that starts Loop One via a typed start event.

    Parameters
    ----------
    events_dir:
        Trajectory directory (same env the continuous daemon scans). When
        omitted, uses ``default_events_dir()`` so emit and persistence check
        share one path (no orphan events + phantom fail).
    policy_id:
        Default policy on the start event when context omits ``policy_id``.
    emit:
        Injectable ``emit_typed`` for tests; defaults to substrate emit.
    settle_emit_cost_usd:
        Absolute actual cost reported after a successful emit when the
        spawn context carries ``report_actual_cost`` (default 0.0 — event
        emission only, no provider call).
    """
    _emit = emit or emit_typed
    resolved_dir = _resolve_events_dir(events_dir)

    def spawn_fn(question: str, context: dict[str, Any]) -> str | None:
        q = (question or "").strip()
        if not q:
            return None

        inv_id = f"inv-{uuid.uuid4().hex[:12]}"
        policy = str(context.get("policy_id") or policy_id)
        topic = context.get("topic_id")
        topic_slug = str(topic) if topic else None
        # Gap key is useful context for decomposer/domain framing.
        gap_ctx = str(context.get("gap_normalized_key") or "")
        score = context.get("gap_score")
        framing = gap_ctx
        if score is not None:
            framing = f"{gap_ctx} (gap_score={score})" if gap_ctx else f"gap_score={score}"

        payload = InvestigationStartRequestedPayload(
            question=q,
            context=framing,
            topic_slug=topic_slug,
        )
        try:
            event_id = _emit(
                inv_id,
                payload,
                role="continuous_daemon",
                policy_id=policy,
                events_dir=resolved_dir,
            )
        except Exception:
            # Malformed/disabled emit: do not claim a spawned investigation.
            return None

        if event_id is None:
            # Events disabled or emit declined — no spawn.
            return None

        # emit_typed may return an id even when the disk append failed.
        # Only claim success (and settle the reserve) when the trajectory
        # file is actually present and non-empty (same resolved_dir as emit).
        if not _event_persisted(inv_id, resolved_dir):
            return None

        # Settle reserved hold when settled-cost hooks are present.
        report = context.get("report_actual_cost")
        if callable(report):
            # Settlement failure must not erase the already-emitted start.
            with contextlib.suppress(Exception):
                report(float(settle_emit_cost_usd))

        context["_antiek_spawned_investigation_id"] = inv_id
        context["_antiek_spawn_event_id"] = event_id
        return inv_id

    return spawn_fn


def resolve_daemon_spawn_fn(
    *,
    events_dir: str | None = None,
    budget: Any | None = None,
) -> SpawnFn:
    """Select spawn_fn from ``ANTIEK_DAEMON_SPAWN_MODE``.

    * ``loop_one`` (or ``loop-one``): emit Loop One start events; wrap with
      settled-cost hooks when ``budget`` is provided.
    * anything else / unset: ``no_op_spawn`` (historical default).
    """
    from orchestration.continuous.daemon import no_op_spawn
    from orchestration.continuous.spawn_cost import wrap_spawn_fn

    mode = (os.environ.get("ANTIEK_DAEMON_SPAWN_MODE") or "no_op").strip().lower()
    if mode in {"loop_one", "loop-one", "loop1"}:
        base = make_loop_one_spawn_fn(events_dir=events_dir)
        if budget is not None:
            return wrap_spawn_fn(base, budget)
        return base
    return no_op_spawn


__all__ = [
    "make_loop_one_spawn_fn",
    "resolve_daemon_spawn_fn",
]
