"""@escape_hatch — the audited, justified bypass of a substrate invariant.

Antiek's analog to Rust's ``unsafe``. A function or block that must bypass
a substrate convention (e.g., direct ``duckdb.connect()`` outside the
single-writer coordinator; an LLM call that skips the verifier; raw HTTP
outside the gateway) is marked with ``@escape_hatch(reason=...)`` or
``with escape_hatch(reason=...):``. The marker does two things:

1. **Audit signal.** First hit per ``reason`` per process logs a WARNING
   to the ``substrate.escape_hatch`` logger, including the caller's
   file:line. Operators can grep production logs for these and reconcile
   against the audit doc (``docs/escape_hatches.md``).
2. **Lint anchor.** The static-analysis lint
   (``tools/lints/unannotated_bypass.py``, scheduled separately) treats
   any AST node inside an ``escape_hatch`` context as exempt. Bypasses
   without the marker fail the lint at CI time.

The convention is light-touch by design. At single-operator scale, runtime
enforcement (refusing the bypass without a privileged flag) is not worth
the friction; the marker + lint + audit doc is sufficient. The verdict
flips to strict enforcement when a second engineer joins the codebase.
See ``docs/decisions/are-wave-1-substrate-additive.md``.

Why ``contextlib.ContextDecorator``: a single callable that supports both
``with escape_hatch(reason="x"):`` and ``@escape_hatch(reason="x")`` is
strictly more usable than two separate names. ``ContextDecorator`` is the
stdlib pattern for this — no third-party dep needed.

Example — context form::

    from substrate.escape_hatch import escape_hatch
    import duckdb

    def maintenance_compaction(db_path: str) -> None:
        with escape_hatch(
            reason="weekly-compaction-needs-raw-duckdb-write-outside-coordinator"
        ):
            con = duckdb.connect(db_path, read_only=False)
            con.execute("VACUUM")
            con.close()

Example — decorator form::

    from substrate.escape_hatch import escape_hatch

    @escape_hatch(reason="benchmark-harness-bypasses-retry-budget-for-timing")
    def measure_raw_latency(url: str) -> float:
        ...

The ``reason`` is a free-form string but should be specific enough that
grepping production logs for the substring lets the operator find the
audit entry. Format suggestion: ``<surface>-<why-bypass-is-needed>``.

Examples (run as doctests via ``pytest --doctest-modules substrate/escape_hatch.py``):

    >>> from substrate.escape_hatch import (
    ...     escape_hatch, counter_snapshot, reset_counters_for_tests,
    ... )
    >>> reset_counters_for_tests()
    >>> with escape_hatch(reason="docexample-counter-test"):
    ...     _ = 1 + 1
    >>> with escape_hatch(reason="docexample-counter-test"):
    ...     _ = 2 + 2
    >>> counter_snapshot()["docexample-counter-test"]
    2
"""

from __future__ import annotations

import contextlib
import logging
import sys
import threading
from typing import Any

__all__ = [
    "escape_hatch",
    "counter_snapshot",
    "reset_counters_for_tests",
    "EscapeHatchInvalidReason",
]


LOG = logging.getLogger("substrate.escape_hatch")


# Per-reason state. The seen-set guards single-warning-per-process; the
# counter records every hit for observability + tests. Both are protected
# by ``_state_lock``. The lock granularity is intentionally coarse — these
# operations are O(1) and not on a hot path.
_state_lock = threading.Lock()
_seen: set[str] = set()
_counts: dict[str, int] = {}


class EscapeHatchInvalidReason(ValueError):
    """Raised at decoration / context-entry time when ``reason`` is empty
    or whitespace-only. A missing reason defeats the audit purpose."""


def _caller_repr(skip: int) -> str:
    """Return ``file:line`` for the frame ``skip`` levels above the
    caller of this function. Used purely for log enrichment.

    Guarded against the rare case where the frame stack is shallower
    than expected (e.g., embedded interpreter); returns ``<unknown>``.
    """
    try:
        frame = sys._getframe(skip)
        return f"{frame.f_code.co_filename}:{frame.f_lineno}"
    except ValueError:
        return "<unknown>"


def _record(reason: str, caller: str) -> None:
    """Increment the counter for ``reason``; emit a WARNING if this is
    the first time this reason has been seen in the process."""
    with _state_lock:
        _counts[reason] = _counts.get(reason, 0) + 1
        first_time = reason not in _seen
        if first_time:
            _seen.add(reason)
    # Log outside the lock — logging handlers can be slow / I/O-bound,
    # and we don't want to serialize hatches across threads on log latency.
    if first_time:
        LOG.warning(
            "escape_hatch first hit: reason=%r at %s "
            "(see docs/escape_hatches.md)",
            reason,
            caller,
        )


class _EscapeHatch(contextlib.ContextDecorator):
    """The instance returned by ``escape_hatch(reason=...)``.

    Subclasses ``ContextDecorator`` so the same instance is usable as
    either ``with``-block or function decorator. ``ContextDecorator.__call__``
    wraps the decorated function such that each invocation enters and
    exits the context — every call records one hit (which is the right
    semantics: a decorated bypass that's called 1000 times has been hit
    1000 times).
    """

    __slots__ = ("reason",)

    def __init__(self, reason: str) -> None:
        if not isinstance(reason, str) or not reason.strip():
            raise EscapeHatchInvalidReason(
                "escape_hatch requires a non-empty, non-whitespace reason string. "
                "Format suggestion: '<surface>-<why-bypass-is-needed>'."
            )
        self.reason = reason

    def __enter__(self) -> None:
        # skip=2: caller of __enter__ is contextlib internals or the user;
        # skip=2 lands on the user's frame for both ``with`` and decorator
        # forms in practice. The repr is best-effort; it's purely for log
        # enrichment so an off-by-one frame isn't a correctness issue.
        _record(self.reason, _caller_repr(2))
        return

    def __exit__(self, *exc_info: Any) -> None:
        # Do not suppress exceptions raised inside the hatch — the bypass
        # is operational, not error-eating. Returning None / False from
        # __exit__ tells Python to propagate.
        return None


def escape_hatch(reason: str) -> _EscapeHatch:
    """Create an escape-hatch marker for ``reason``.

    Use as either a context manager or a decorator (see module docstring
    examples). The returned object is a ``ContextDecorator``.

    :raises EscapeHatchInvalidReason: if ``reason`` is empty or
        whitespace-only. A missing reason defeats the audit purpose;
        construction failure at decoration / entry time surfaces the
        mistake at import time rather than at runtime.
    """
    return _EscapeHatch(reason)


# ---------------------------------------------------------------------- #
# Observability helpers                                                  #
# ---------------------------------------------------------------------- #


def counter_snapshot() -> dict[str, int]:
    """Return a shallow copy of the per-reason hit counter.

    Use to surface current bypass activity in dashboards, weekly reports,
    or operator runbooks. Returns a copy so callers can iterate safely
    without holding the lock.
    """
    with _state_lock:
        return dict(_counts)


def reset_counters_for_tests() -> None:
    """Reset all internal state. Tests only — never call from
    production code paths.

    The function name carries the discipline: a production caller would
    have to write ``reset_counters_for_tests()`` literally, which is a
    grep-able signal.
    """
    with _state_lock:
        _counts.clear()
        _seen.clear()
