"""Recover investigations stranded after dispatch.call with no role delivery.

Loop One bridges emit ``*.requested``, then call the provider. Each attempt
also emits ``dispatch.call`` (including ``finish_reason=error``). When the
process dies mid-fallback, an ``OwnerByot*`` exception escapes the bridge
``except (ProviderError, KeyError)``, or the length-retry never returns, the
trajectory ends on ``dispatch.call`` with a pending ``*.requested`` and no
``investigation.failed`` / ``*.delivered``.

This module closes those trajectories with ``investigation.failed`` so
dashboards and catch-up do not treat them as live hangs.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from substrate.event_log.events import (
    default_events_dir,
    iter_physical_events,
)
from substrate.event_log import emit_typed
from substrate.schemas.events import InvestigationFailedPayload

# Role request → phase number (Loop One).
_REQUEST_PHASE: dict[str, int] = {
    "decompose.requested": 1,
    "evidence.retrieve.requested": 2,
    "parameter_extract.requested": 3,
    "connector.requested": 4,
    "synthesize.requested": 6,
}

_REQUEST_TO_DELIVERED: dict[str, str] = {
    "decompose.requested": "decompose.delivered",
    "evidence.retrieve.requested": "evidence.retrieve.delivered",
    "parameter_extract.requested": "parameter_extract.delivered",
    "connector.requested": "connector.delivered",
    "synthesize.requested": "synthesize.delivered",
}

_TERMINAL = frozenset(
    {
        "investigation.completed",
        "investigation.failed",
    }
)

# Default: older than role-timeout slack so live waits are not stolen.
DEFAULT_MIN_AGE_S = float(os.environ.get("ANTIEK_STRANDED_DISPATCH_MIN_AGE_S", "180"))


@dataclass(frozen=True)
class StrandedInvestigation:
    investigation_id: str
    pending_request: str
    phase: int
    last_action: str
    age_s: float
    last_emitted_at: str | None


def _parse_emitted_at(raw: Any) -> float | None:
    if not isinstance(raw, str) or not raw:
        return None
    try:
        # Accept Z suffix.
        ts = raw.replace("Z", "+00:00")
        return datetime.fromisoformat(ts).timestamp()
    except ValueError:
        return None


def find_stranded_investigations(
    *,
    events_dir: str | None = None,
    min_age_s: float = DEFAULT_MIN_AGE_S,
    now: float | None = None,
) -> list[StrandedInvestigation]:
    """Return invs with open role requests, no terminal lifecycle, aged out."""
    root = events_dir or default_events_dir()
    now_ts = time.time() if now is None else now
    found: list[StrandedInvestigation] = []
    if not os.path.isdir(root):
        return found
    for name in os.listdir(root):
        if not name.startswith("inv-") or not name.endswith(".jsonl"):
            continue
        inv = name[: -len(".jsonl")]
        rows = list(
            iter_physical_events(inv, events_dir=root, _lock_already_held=True)
        )
        if not rows:
            continue
        types = [r.get("action_type") for r in rows]
        if any(t in _TERMINAL for t in types):
            continue
        # Count pending requests (req without matching delivered).
        pending: str | None = None
        for req, delivered in _REQUEST_TO_DELIVERED.items():
            n_req = sum(1 for t in types if t == req)
            n_del = sum(1 for t in types if t == delivered)
            if n_req > n_del:
                pending = req
                # Prefer the latest open request type by scanning reverse.
        # Refine: last unmatched request in physical order.
        open_stack: list[str] = []
        for t in types:
            if t in _REQUEST_TO_DELIVERED:
                open_stack.append(t)
            delivered_for = {
                v: k for k, v in _REQUEST_TO_DELIVERED.items()
            }
            if t in delivered_for and open_stack:
                # pop matching if present
                want = delivered_for[t]
                for i in range(len(open_stack) - 1, -1, -1):
                    if open_stack[i] == want:
                        open_stack.pop(i)
                        break
        if not open_stack:
            continue
        pending = open_stack[-1]
        last = rows[-1]
        last_at = _parse_emitted_at(last.get("emitted_at"))
        if last_at is None:
            # Fall back to file mtime.
            last_at = os.path.getmtime(os.path.join(root, name))
        age = now_ts - last_at
        if age < min_age_s:
            continue
        # Require last signal to be dispatch.call (or the pending request)
        # so we do not fail active non-dispatch waits prematurely.
        last_action = last.get("action_type") or ""
        if last_action not in ("dispatch.call", pending):
            continue
        if last_action == "dispatch.call":
            pl = last.get("payload") or {}
            if isinstance(pl, dict) and pl.get("finish_reason") not in (
                "error",
                "length",
                None,
            ):
                # Successful in-flight dispatch — leave alone.
                if pl.get("finish_reason") in ("stop", "tool_use"):
                    continue
        phase = _REQUEST_PHASE.get(pending, 1)
        found.append(
            StrandedInvestigation(
                investigation_id=inv,
                pending_request=pending,
                phase=phase,
                last_action=last_action,
                age_s=age,
                last_emitted_at=(
                    last.get("emitted_at")
                    if isinstance(last.get("emitted_at"), str)
                    else None
                ),
            )
        )
    return found


def recover_stranded_investigation(
    investigation_id: str,
    *,
    pending_request: str,
    phase: int,
    events_dir: str | None = None,
) -> str | None:
    """Emit investigation.failed for a stranded inv. Returns event_id."""
    reason = (
        f"stranded after {pending_request}: trajectory ended without "
        f"role delivery (dispatch error / process interrupt / uncaught "
        f"provider failure); recovered by stranded_dispatch_recovery"
    )
    return emit_typed(
        investigation_id,
        InvestigationFailedPayload(
            phase=phase,
            reason=reason,
            last_completed_phase=None,
        ),
        role="orchestrator",
        policy_id="stranded-dispatch-recovery",
    )


def recover_all_stranded(
    *,
    events_dir: str | None = None,
    min_age_s: float = DEFAULT_MIN_AGE_S,
) -> list[str]:
    """Fail-close every aged stranded investigation. Returns inv ids recovered."""
    recovered: list[str] = []
    for item in find_stranded_investigations(
        events_dir=events_dir, min_age_s=min_age_s
    ):
        try:
            eid = recover_stranded_investigation(
                item.investigation_id,
                pending_request=item.pending_request,
                phase=item.phase,
                events_dir=events_dir,
            )
            print(
                f"stranded_dispatch_recovery: closed {item.investigation_id} "
                f"pending={item.pending_request} age_s={item.age_s:.0f} "
                f"event_id={eid}",
                flush=True,
            )
            recovered.append(item.investigation_id)
        except Exception as exc:  # noqa: BLE001 — never kill the worker
            print(
                f"stranded_dispatch_recovery: failed {item.investigation_id}: "
                f"{type(exc).__name__}: {exc}",
                file=sys.stderr,
                flush=True,
            )
    return recovered


def start_stranded_dispatch_recovery(
    *,
    events_dir: str | None = None,
    stop_event: threading.Event | None = None,
    poll_interval_s: float = 30.0,
    min_age_s: float = DEFAULT_MIN_AGE_S,
) -> threading.Thread:
    """Background poller — same shape as note-taker replay recovery."""
    if poll_interval_s <= 0:
        raise ValueError("poll_interval_s must be positive")
    stop = stop_event or threading.Event()
    root = events_dir or default_events_dir()

    def loop() -> None:
        while not stop.is_set():
            try:
                recover_all_stranded(events_dir=root, min_age_s=min_age_s)
            except Exception as exc:  # noqa: BLE001
                print(
                    f"stranded_dispatch_recovery: poll error: "
                    f"{type(exc).__name__}: {exc}",
                    file=sys.stderr,
                    flush=True,
                )
            stop.wait(poll_interval_s)

    thread = threading.Thread(
        target=loop, name="stranded-dispatch-recovery", daemon=True
    )
    thread.start()
    return thread
