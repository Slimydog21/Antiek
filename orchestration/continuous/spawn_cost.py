"""Settled-cost reconciliation for continuous-daemon spawns.

§7.4 tripwire (``tests/test_suggestions_surface.py``) forbids edits to
``budget.py`` / ``daemon.py`` / ``scoring.py`` / ``research_topic.py`` vs
origin/main. The daemon docstring already specifies that injected spawn
functions report actual cost via ``context['record_actual_cb']``, but the
daemon boundary never installed that callback. This module closes that
boundary. The configured CLI implementation remains ``no_op_spawn``; a real
provider adapter must be injected and call the supplied reporter before its
reserved estimate can be described as settled spend.

This module is the tripwire-safe seam:

* ``install_spawn_cost_hooks`` — put ``record_actual_cb`` +
  ``report_actual_cost`` on a spawn context (idempotent).
* ``wrap_spawn_fn`` — production/test wrapper so any spawn callable
  receives the hooks without mutating ``daemon.py``.
* ``run_one_iteration_settled`` — CLI entry seam that always wraps an
  injected spawn function (used by ``python -m orchestration.continuous``).
* ``report_actual_cost`` — convert absolute actual USD into the signed
  delta ``DaemonBudget.record_actual`` expects (``actual − expected``),
  fail-closed on double absolute report and non-finite amounts.

Honesty rules:

* Unreported actual after a successful spawn leaves the reserved hold
  in place — Settings/UI must keep labeling that as
  ``reserved_estimate`` (see #769/#770), never invent a settled $0.
* Reporting actual adjusts the same sidecar total via the existing
  ``record_actual`` API; this module does not create a second ledger
  authority.
* A second absolute ``report_actual_cost`` on the same context fails
  closed (would otherwise subtract expected twice and floor to fake $0).
"""

from __future__ import annotations

import math
import os
from datetime import datetime
from typing import Any

from .budget import DaemonBudget
from .daemon import (
    DaemonConfig,
    DaemonState,
    SpawnFn,
    no_op_spawn,
    run_one_iteration,
)

_HOOK_FLAG = "_antiek_spawn_cost_hooks_installed"


def _require_finite_nonneg(value: float, *, label: str) -> float:
    amount = float(value)
    if not math.isfinite(amount) or amount < 0.0:
        raise ValueError(f"{label} must be a finite non-negative USD amount, got {value!r}")
    return amount


def daemon_config_from_env() -> DaemonConfig:
    """Build ``DaemonConfig`` the same way ``daemon.main()`` does.

    Honors the documented env vars (systemd unit / ``__main__`` docstring):

    * ``ANTIEK_DAEMON_SLEEP_SECONDS`` (default 60)
    * ``ANTIEK_DAEMON_EXPECTED_COST_USD`` (default 0.50)

    Lives here (not in ``daemon.py``) so the production CLI can restore
    env-driven config without violating the §7.4 tripwire.
    """
    return DaemonConfig(
        sleep_seconds=_require_finite_nonneg(
            float(os.environ.get("ANTIEK_DAEMON_SLEEP_SECONDS", "60")),
            label="ANTIEK_DAEMON_SLEEP_SECONDS",
        ),
        expected_cost_per_spawn_usd=_require_finite_nonneg(
            float(os.environ.get("ANTIEK_DAEMON_EXPECTED_COST_USD", "0.50")),
            label="ANTIEK_DAEMON_EXPECTED_COST_USD",
        ),
    )


def report_actual_cost(
    context: dict[str, Any],
    actual_cost_usd: float,
    *,
    now: datetime | None = None,  # noqa: ARG001 — reserved for future clock injection
) -> float:
    """Reconcile a reserved hold to an absolute actual cost.

    Returns the signed delta applied (``actual − expected``).
    Requires ``install_spawn_cost_hooks`` (or an equivalent
    ``record_actual_cb``) on ``context``.

    Fail-closed if actual was already reported on this context — a second
    absolute report would re-subtract ``expected`` and can floor the
    sidecar to a fabricated $0 spent.
    """
    if context.get("_antiek_actual_reported"):
        raise RuntimeError(
            "actual cost already reported for this spawn context; "
            "refusing a second absolute report (would fabricate spent=0)"
        )
    actual = _require_finite_nonneg(actual_cost_usd, label="actual_cost_usd")
    expected = _require_finite_nonneg(
        float(context.get("expected_cost_usd", 0.0)),
        label="expected_cost_usd",
    )
    delta = actual - expected
    cb = context.get("record_actual_cb")
    if not callable(cb):
        raise RuntimeError(
            "spawn context missing record_actual_cb — call "
            "install_spawn_cost_hooks(...) or wrap_spawn_fn(...) before reporting actual cost"
        )
    cb(delta)
    context["_antiek_actual_cost_usd"] = actual
    context["_antiek_actual_delta_usd"] = delta
    context["_antiek_actual_reported"] = True
    return delta


def install_spawn_cost_hooks(
    context: dict[str, Any],
    budget: DaemonBudget,
    *,
    now: datetime | None = None,
    expected_cost_usd: float | None = None,
) -> dict[str, Any]:
    """Idempotently install cost-reconciliation hooks on a spawn context.

    Installs:

    * ``record_actual_cb(delta_usd)`` — signed adjustment, matches
      ``DaemonBudget.record_actual`` (daemon docstring contract).
    * ``report_actual_cost(actual_cost_usd)`` — absolute actual helper.

    Mutates and returns ``context``.
    """
    if context.get(_HOOK_FLAG):
        return context

    if expected_cost_usd is not None:
        context.setdefault(
            "expected_cost_usd",
            _require_finite_nonneg(expected_cost_usd, label="expected_cost_usd"),
        )
    if "expected_cost_usd" not in context:
        raise ValueError(
            "spawn context requires expected_cost_usd "
            "(daemon sets this; or pass expected_cost_usd= to install_spawn_cost_hooks)"
        )
    # Validate pre-existing expected.
    context["expected_cost_usd"] = _require_finite_nonneg(
        float(context["expected_cost_usd"]),
        label="expected_cost_usd",
    )

    def record_actual_cb(delta_usd: float) -> None:
        # Raw delta path remains for refunds (daemon already uses
        # budget.record_actual directly on decline). Spawns should prefer
        # report_actual_cost for absolute actuals. Reject non-finite deltas
        # so NaN/inf cannot floor the sidecar to a fabricated $0 spent.
        delta = float(delta_usd)
        if not math.isfinite(delta):
            raise ValueError(
                f"record_actual_cb delta must be finite, got {delta_usd!r}"
            )
        budget.record_actual(delta, now=now)

    def report_actual(actual_cost_usd: float) -> float:
        return report_actual_cost(context, actual_cost_usd, now=now)

    context["record_actual_cb"] = record_actual_cb
    context["report_actual_cost"] = report_actual
    context[_HOOK_FLAG] = True
    context.setdefault("_antiek_actual_reported", False)
    return context


def wrap_spawn_fn(
    spawn_fn: SpawnFn,
    budget: DaemonBudget,
    *,
    now: datetime | None = None,
) -> SpawnFn:
    """Return a spawn function that always receives settled-cost hooks.

    Use at the ``run_one_iteration(..., spawn_fn=...)`` boundary so the
    §7.4-locked ``daemon.py`` need not change::

        run_one_iteration(
            ...,
            budget=bdg,
            spawn_fn=wrap_spawn_fn(my_spawn, bdg),
        )
    """

    def wrapped(question: str, context: dict[str, Any]) -> str | None:
        # Shallow copy so concurrent/retry callers cannot clobber hooks.
        ctx = dict(context)
        install_spawn_cost_hooks(ctx, budget, now=now)
        return spawn_fn(question, ctx)

    return wrapped


def run_one_iteration_settled(
    *,
    state: DaemonState | None = None,
    config: DaemonConfig | None = None,
    budget: DaemonBudget | None = None,
    spawn_fn: SpawnFn = no_op_spawn,
    now: datetime | None = None,
) -> Any:
    """CLI entry seam: ``run_one_iteration`` with spawn always wrapped.

    Ensures every production tick installs ``record_actual_cb`` /
    ``report_actual_cost`` on spawn contexts without editing daemon.py.

    When ``config`` is omitted, uses ``daemon_config_from_env()`` (same
    env vars as ``daemon.main()``) — never bare ``DaemonConfig()`` defaults.
    """
    cfg = config if config is not None else daemon_config_from_env()
    bdg = budget or DaemonBudget.from_env()
    st = state if state is not None else DaemonState()
    return run_one_iteration(
        state=st,
        config=cfg,
        budget=bdg,
        spawn_fn=wrap_spawn_fn(spawn_fn, bdg, now=now),
        now=now,
    )


def actual_was_reported(context: dict[str, Any]) -> bool:
    """True iff ``report_actual_cost`` / successful actual report ran on context."""
    return bool(context.get("_antiek_actual_reported"))


__all__ = [
    "actual_was_reported",
    "daemon_config_from_env",
    "install_spawn_cost_hooks",
    "report_actual_cost",
    "run_one_iteration_settled",
    "wrap_spawn_fn",
]
