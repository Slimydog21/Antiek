"""``build_execution_backend()`` — env-selected factory for the exec seam.

Mirrors the house idiom of ``runtime/remote_exec/factory.py`` (``build_research_runner``):
one factory that reads an env flag and returns the right backend. The key
contrast is **no silent cross-backend fallback** — a missing docker daemon
raises ``BackendUnavailable`` loudly rather than downgrading to ``local``, because
a silent downgrade would *weaken an isolation guarantee* the caller declared.
Isolation downgrades must be an explicit operator choice (change the env var),
never an availability accident.

The factory accepts ``seal_on_complete`` and ``retrieval_substrate`` so the
cascade launch site can forward its runner kwargs through without a signature
mismatch — they are carried for call-site compatibility and logged, not applied
to the ``ExecutionBackend`` (which has no concept of sealing or substrate reuse;
those are research-runner concerns). This is the MINIMAL reconciliation the spec
flags in S4.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from .interface import BackendUnavailable, ExecutionBackend
from .local_process import LocalProcessBackend

logger = logging.getLogger("antiek.exec_backend.factory")

#: Env var that selects the backend.  Unset → ``"local"``.
BACKEND_ENV: str = "ANTIEK_EXEC_BACKEND"

_VALID_KINDS: frozenset[str] = frozenset({"local"})


def build_execution_backend(
    *,
    kind: str | None = None,
    seal_on_complete: bool = True,
    retrieval_substrate: object | None = None,
    **kwargs: Any,
) -> ExecutionBackend:
    """Return the ``ExecutionBackend`` selected by *kind* (or ``$ANTIEK_EXEC_BACKEND``).

    * ``kind`` — explicit override (tests pass this); ``None`` defers to the env
      var; absent both, the default is ``"local"`` (``LocalProcessBackend``).
    * ``seal_on_complete`` / ``retrieval_substrate`` — accepted so the cascade
      launch site can forward its runner kwargs without a ``TypeError``; they are
      **not** applied to the backend (``ExecutionBackend`` has no concept of
      sealing or substrate reuse). Logged once at DEBUG so an operator can trace
      the forwarding.
    * ``**kwargs`` — silently absorbed for forward-compat; any unexpected kwarg
      is logged at WARNING once (not an error, to avoid breaking on harmless
      forwarding noise).

    Raises ``BackendUnavailable`` if the selected backend's dependency is
    missing (e.g. ``"docker"`` when the docker daemon is absent). There is
    **no** silent cross-backend fallback — see module docstring.
    """
    effective = kind or os.environ.get(BACKEND_ENV, "local").lower()

    if seal_on_complete is not True or retrieval_substrate is not None:
        logger.debug(
            "build_execution_backend: forwarding runner kwargs "
            "(seal_on_complete=%r, retrieval_substrate=%r) — these are "
            "research-runner concerns and are not applied to the backend.",
            seal_on_complete,
            retrieval_substrate,
        )

    if kwargs:
        logger.warning(
            "build_execution_backend: unexpected kwargs ignored: %s",
            sorted(kwargs.keys()),
        )

    if effective == "local":
        backend: ExecutionBackend = LocalProcessBackend()
        backend.probe()
        logger.info(
            "ExecutionBackend selected: %s (via %s)",
            backend.name,
            f"${BACKEND_ENV}={effective!r}" if kind is None else f"kind={kind!r}",
        )
        return backend

    raise BackendUnavailable(
        f"unknown ExecutionBackend kind {effective!r}; "
        f"valid kinds: {sorted(_VALID_KINDS)}"
    )


__all__ = ["build_execution_backend", "BACKEND_ENV"]
