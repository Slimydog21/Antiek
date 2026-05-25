"""substrate/ownership.py — the ownership-handle pattern, paved.

ARE-04 reference implementation. Generalizes ``runtime/db_lock.py``'s
single-writer discipline into a reusable, in-process handle: one named
owner per shared mutable resource; all writes serialized through the
handle and returning ``Result[T, SubstrateError]``; reads lock-free
when the resource tolerates staleness.

This module is the PAVED ROAD — a tested reference that the real ARE-04
handles (dispatch budget, event_log writer) follow. It deliberately does
NOT wire any real resource: the real handles are operator-gated because
they must align with ``substrate/invariants.py``'s I-001 single-writer
enforcement (the DuckDB flock in ``runtime/db_lock.py`` already covers
the on-disk write; an in-process handle layer must extend, not
duplicate, that — a design decision the operator owns).

The design composes the rest of the substrate quality work:

- writes return ``Result[T, SubstrateError]`` (Wave 1 ``substrate/results``)
- lock-acquire timeout returns ``Err(WriterContended)`` (Wave 1
  ``substrate/errors``), carrying the resource name + the timeout that
  elapsed — exactly the shape ``runtime/db_lock.py`` stamps on its
  sidecar lock
- the mutation callback itself returns a ``Result``, so a domain
  invariant (e.g., never-overspend) composes INSIDE the lock via
  ``substrate/result_helpers.checked_budget_charge`` — see
  ``DispatchBudgetReference`` below

Why ``write(mutation) -> Result`` rather than a ``with handle.write()``
context manager: returning an ``Err(WriterContended)`` from a
``@contextmanager`` is awkward (you can't both ``yield`` a writer and
``return`` a failure). The method form is clean: acquire-or-Err, apply
the mutation under the lock, return the mutation's own Result. The
mutation can reject (return Err) and the state stays unchanged; or
accept (return Ok(new)) and the state advances atomically.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Generic, TypeVar

from substrate.errors import SubstrateError, WriterContended
from substrate.result_helpers import checked_budget_charge
from substrate.results import Err, Ok, Result

__all__ = [
    "DEFAULT_ACQUIRE_TIMEOUT_S",
    "OwnershipHandle",
    "DispatchBudgetReference",
]

T = TypeVar("T")

# Mirrors the bounded-wait shape of runtime/db_lock.py's
# DEFAULT_TIMEOUT_S, scaled down: an in-process lock should rarely be
# held longer than a few seconds (no 200-paper ingest behind it), so a
# 30s default surfaces a stuck writer fast without false-positiving on
# legitimate contention.
DEFAULT_ACQUIRE_TIMEOUT_S = 30.0


class OwnershipHandle(Generic[T]):
    """Single-owner, serialized-write handle over an in-process mutable
    value of type ``T``.

    One handle instance is the sole sanctioned mutator of its value.
    Construct it once in the owning module; pass the handle (never the
    raw value) to readers/writers. Writes serialize on a
    ``threading.Lock`` with a bounded acquire timeout; on timeout, the
    write returns ``Err(WriterContended)`` rather than blocking forever.

    Reads are lock-free and return the current value directly — callers
    that need a consistent multi-field read should model the value as an
    immutable snapshot (e.g., a frozen Pydantic model) so a lock-free
    read can't observe a half-applied mutation. For a single reference
    assignment (the common case), CPython's GIL already makes the
    pointer swap atomic.
    """

    __slots__ = ("_name", "_value", "_lock")

    def __init__(self, initial: T, *, name: str) -> None:
        self._name = name
        self._value = initial
        self._lock = threading.Lock()

    @property
    def name(self) -> str:
        return self._name

    def read(self) -> T:
        """Lock-free snapshot of the current value. Tolerates staleness
        by design — a concurrent write may land immediately after this
        returns. Model ``T`` as immutable if a consistent read matters."""
        return self._value

    def write(
        self,
        mutation: Callable[[T], Result[T, SubstrateError]],
        *,
        timeout_s: float = DEFAULT_ACQUIRE_TIMEOUT_S,
    ) -> Result[T, SubstrateError]:
        """Serialize a mutation against the value.

        Acquires the lock (waiting up to ``timeout_s``). On acquire
        timeout, returns ``Err(WriterContended)`` — the resource is
        legitimately busy. Once held, runs ``mutation(current_value)``:

        - if the mutation returns ``Ok(new)``, the value advances to
          ``new`` atomically and the Ok is returned;
        - if the mutation returns ``Err(...)`` (a rejected write, e.g.
          BudgetExceeded), the value is UNCHANGED and the Err is
          returned.

        The lock is always released, including when the mutation raises
        (the exception propagates — a raising mutation is a programmer
        error, not a recoverable write rejection; use Err for the
        latter).
        """
        acquired = self._lock.acquire(timeout=timeout_s)
        if not acquired:
            return Err(
                error=WriterContended(
                    resource=self._name,
                    holder_pid=None,  # in-process: PID is ours; not useful here
                    timeout_s=timeout_s,
                )
            )
        try:
            result = mutation(self._value)
            match result:
                case Ok(value=new_value):
                    self._value = new_value
                    return result
                case Err():
                    # Rejected write — state unchanged, propagate the Err.
                    return result
        finally:
            self._lock.release()


class DispatchBudgetReference:
    """Reference ownership handle for a dispatch budget — the shape the
    real ARE-04 dispatch-budget handle follows.

    Composes ``OwnershipHandle`` (serialized writes) with
    ``checked_budget_charge`` (the never-overspend invariant). The cap
    check runs INSIDE the lock, so concurrent charges can never race
    past the cap: each charge sees the committed running total.

    This is ~10 lines because the pieces compose. The real handle adds
    persistence (writing the running total through ``runtime/db_lock.py``)
    and observability — but the concurrency-correct core is exactly this.
    """

    __slots__ = ("_handle", "_cap", "_units")

    def __init__(
        self, cap: int, *, units: str = "tokens",
        name: str = "dispatch_budget_reference",
    ) -> None:
        self._handle: OwnershipHandle[int] = OwnershipHandle(0, name=name)
        self._cap = cap
        self._units = units

    @property
    def spent(self) -> int:
        """Lock-free read of the current running total."""
        return self._handle.read()

    @property
    def remaining(self) -> int:
        return self._cap - self._handle.read()

    def charge(
        self, amount: int, *, timeout_s: float = DEFAULT_ACQUIRE_TIMEOUT_S
    ) -> Result[int, SubstrateError]:
        """Charge ``amount`` against the budget. Returns
        ``Ok(new_running_total)`` or ``Err(BudgetExceeded)`` (cap hit)
        or ``Err(WriterContended)`` (lock-acquire timeout). The cap check
        is race-free — it runs inside the handle's lock."""
        return self._handle.write(
            lambda spent: checked_budget_charge(
                spent, amount, self._cap, units=self._units
            ),
            timeout_s=timeout_s,
        )
