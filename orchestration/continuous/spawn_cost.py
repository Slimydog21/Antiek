"""Settled-cost reconciliation for continuous-daemon spawns.

§7.4 tripwire (``tests/test_suggestions_surface.py``) forbids edits to
``budget.py`` / ``daemon.py`` / ``scoring.py`` / ``research_topic.py`` vs
origin/main. The daemon docstring already specifies that spawn functions
report actual cost via ``context['record_actual_cb']``, but production
never installs that callback — so every successful spawn leaves the
**reserved** hold as if it were settled spend forever.

This module is the tripwire-safe seam:

* ``install_spawn_cost_hooks`` — put ``record_actual_cb`` +
  ``report_actual_cost`` on a spawn context (idempotent).
* ``wrap_spawn_fn`` — production/test wrapper so any spawn callable
  receives the hooks without mutating ``daemon.py``.
* ``report_actual_cost`` — convert absolute actual USD into the signed
  delta ``DaemonBudget.record_actual`` expects (``actual − expected``).

Honesty rules:

* Unreported actual after a successful spawn leaves the reserved hold
  in place — Settings/UI must keep labeling that as
  ``reserved_estimate`` (see #769/#770), never invent a settled $0.
* Reporting actual adjusts the same sidecar total via the existing
  ``record_actual`` API; this module does not create a second ledger
  authority.
* Double-report is allowed as further deltas (same as raw
  ``record_actual``); callers should report once per spawn.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Optional

from .budget import DaemonBudget
from .daemon import SpawnFn

_HOOK_FLAG = "_antiek_spawn_cost_hooks_installed"


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
    """
    if actual_cost_usd < 0:
        raise ValueError(f"actual_cost_usd must be non-negative, got {actual_cost_usd!r}")
    expected = float(context.get("expected_cost_usd", 0.0))
    if expected < 0:
        raise ValueError(f"expected_cost_usd must be non-negative, got {expected!r}")
    delta = float(actual_cost_usd) - expected
    cb = context.get("record_actual_cb")
    if not callable(cb):
        raise RuntimeError(
            "spawn context missing record_actual_cb — call "
            "install_spawn_cost_hooks(...) or wrap_spawn_fn(...) before reporting actual cost"
        )
    cb(delta)
    context["_antiek_actual_cost_usd"] = float(actual_cost_usd)
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
        context.setdefault("expected_cost_usd", float(expected_cost_usd))
    if "expected_cost_usd" not in context:
        raise ValueError(
            "spawn context requires expected_cost_usd "
            "(daemon sets this; or pass expected_cost_usd= to install_spawn_cost_hooks)"
        )

    def record_actual_cb(delta_usd: float) -> None:
        budget.record_actual(float(delta_usd), now=now)

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

    def wrapped(question: str, context: dict[str, Any]) -> Optional[str]:
        # Shallow copy so concurrent/retry callers cannot clobber hooks.
        ctx = dict(context)
        install_spawn_cost_hooks(ctx, budget, now=now)
        return spawn_fn(question, ctx)

    return wrapped


def actual_was_reported(context: dict[str, Any]) -> bool:
    """True iff ``report_actual_cost`` / successful actual report ran on context."""
    return bool(context.get("_antiek_actual_reported"))


__all__ = [
    "actual_was_reported",
    "install_spawn_cost_hooks",
    "report_actual_cost",
    "wrap_spawn_fn",
]
