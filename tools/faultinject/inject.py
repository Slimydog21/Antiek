"""Core of the deterministic fault-injection harness (nygard SPR-01).

A *precision instrument*, not a chaos monkey: each injector targets ONE named
seam and produces ONE named fault deterministically. Three properties are
load-bearing and every injector upholds them:

1. **Inert by default.** Importing this package installs nothing. A fault is
   armed only while its context manager is entered; on ``__exit__`` (even via
   an exception) the seam is restored to exactly its prior state. The default
   ``pytest`` run and the live ``antiek.service`` are byte-identical whether or
   not this package exists on disk.

2. **Fidelity.** The three seam injectors raise the *real* error the
   corresponding production fault would raise — ``OSError(errno.EROFS)`` for the
   read-only-FS seam, ``substrate.dispatch.base.ProviderError`` for the dispatch
   seam, and a genuine ``runtime.db_lock.WriteLockTimeout`` for the locked-DB
   seam (produced by a *real* ``fcntl.flock``, not synthesized). That fidelity
   is the point: the injected fault must be catchable by the same ``except``
   clause the real fault hits, so a test proves the real handling path.

3. **Determinism.** No randomness. ``fail_on_call=N`` (see :class:`_CallGate`)
   makes the fault fire on the Nth call onward, so a test can prove the system
   survives the first call and fails loudly on the second — the same fault,
   every run.

``FaultArmed`` is the shared base for the generic :func:`arm` path and any
purely-synthetic fault; callers who only care that *some* fault fired may catch
it. The real seam injectors deliberately raise the real seam error instead
(fidelity beats a uniform synthetic type — see milestone 3 of the spec).
"""

from __future__ import annotations

import threading
from typing import Any

__all__ = ["FaultArmed", "arm", "INJECTORS"]


class FaultArmed(RuntimeError):
    """Base marker for a synthetic fault raised by an armed injector.

    The three real seam injectors raise the real seam error (``OSError``,
    ``ProviderError``, ``WriteLockTimeout``) rather than this type, on purpose:
    the injected fault must be catchable by the same ``except`` the real fault
    would hit. ``FaultArmed`` exists for the generic :func:`arm` dispatch and
    for callers/tests that want a single "some fault fired" base to catch.
    """


class _CallGate:
    """Deterministic per-injector call counter implementing ``fail_on_call``.

    Semantics (documented, hard-to-vary — do not "simplify" into off-by-one):

    - ``fail_on_call is None`` → **every** gated call faults (fault always armed).
    - ``fail_on_call = N`` (N ≥ 1) → calls ``1 .. N-1`` pass through; call ``N``
      and every call after it faults. Monotonic: once tripped it stays tripped.
      This matches how a real degraded resource behaves and keeps SPR-07's
      repeated-fault loop well-defined (a fault that self-healed after one fire
      would make an N-iteration leak test ambiguous).

    The gate holds no global state: one gate lives inside one armed context and
    is discarded on teardown, so nothing leaks across tests.

    Thread-safe: the count-and-decide step is atomic under a per-gate lock, so
    an armed seam exercised by concurrent worker threads (the loky/joblib
    parallelism this harness exists to stress) still trips ``fail_on_call=N``
    deterministically on exactly the Nth eligible call.
    """

    __slots__ = ("_threshold", "_count", "_lock")

    def __init__(self, fail_on_call: int | None) -> None:
        if fail_on_call is not None and fail_on_call < 1:
            raise ValueError(f"fail_on_call must be >= 1 or None, got {fail_on_call!r}")
        self._threshold = fail_on_call
        self._count = 0
        self._lock = threading.Lock()

    def should_fault(self) -> bool:
        """Count this gated call and return whether it should fault.

        Call this ONLY for a genuinely matching event (e.g. a write to the
        armed target path), so the count reflects real fault-eligible calls.
        """
        with self._lock:
            self._count += 1
            if self._threshold is None:
                return True
            return self._count >= self._threshold


# Named registry — the generic entry point the spec calls for. Kept as a
# tuple of names plus a lazy dispatcher so importing this core module does not
# import the seam adapters (preserving inert-by-default + a cheap import).
INJECTORS: tuple[str, ...] = ("readonly_fs", "locked_db", "provider_fault")


def arm(name: str, /, **kwargs: Any):
    """Return the named injector's context manager, e.g.::

        with arm("readonly_fs", target_path=p):
            ...

    Thin convenience over the three named context managers. Imports the seam
    adapter lazily so ``import tools.faultinject.inject`` stays side-effect-free.
    """
    if name not in INJECTORS:
        raise KeyError(f"unknown injector {name!r}; known: {INJECTORS}")
    if name == "readonly_fs":
        from .readonly_fs import readonly_fs

        return readonly_fs(**kwargs)
    if name == "locked_db":
        from .locked_db import locked_db

        return locked_db(**kwargs)
    from .provider_fault import provider_fault

    return provider_fault(**kwargs)
