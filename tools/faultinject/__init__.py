"""tools.faultinject — deterministic, opt-in fault injection for resilience tests.

Three precision injectors, each wired to one real Antiek seam:

- :func:`readonly_fs` — ``OSError(errno.EROFS)`` at the FS write primitives,
  scoped to one target path (reproduces the 2026-05-17 read-only-FS class).
- :func:`locked_db` — real ``fcntl.flock`` contention on ``runtime.db_lock``'s
  sidecar, so ``connect_write`` raises the real ``WriteLockTimeout``.
- :func:`provider_fault` — a real ``ProviderError`` (503 / timeout) from a
  registered dispatch provider's ``.call``, exercising the router fallback chain.

Inert by default: importing this package installs nothing. A fault exists only
while its context manager is entered and is torn down on exit (even on
exception). Deterministic: no randomness; ``fail_on_call=N`` fires from the Nth
call onward. See ``README.md`` for the seam-to-injection map and usage.
"""

from __future__ import annotations

from .inject import INJECTORS, FaultArmed, arm
from .locked_db import locked_db
from .provider_fault import provider_fault
from .readonly_fs import readonly_fs

__all__ = [
    "readonly_fs",
    "locked_db",
    "provider_fault",
    "arm",
    "INJECTORS",
    "FaultArmed",
]
