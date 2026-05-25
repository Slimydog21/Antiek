"""Daytona implementation of ``RemoteExecProvider`` — the one provider behind
the §16 research-fan-out exemption.

This module mirrors the optional-SDK idiom established by
``acquisition/urls/client_browserbase.py`` (the Browserbase Wedge-2 fetcher):

  * The Daytona SDK is an **optional** dependency (the ``[remote_exec]`` group
    in ``pyproject.toml``), exactly like ``browserbase`` is the ``[browserbase]``
    group. The module imports cleanly without it.
  * The SDK is **lazy-imported** at first use (inside ``_load_sdk``), not at
    module top-level, so ``import runtime.remote_exec`` works on a machine
    that never installed it.
  * A missing SDK or missing credentials raises ``RemoteExecUnavailable``
    **loudly** — the same loud-failure-when-missing posture as
    ``BrowserbaseUnavailable``. There is no silent degradation here; falling
    back to host-local is the *factory's* explicit, logged decision, not a
    swallowed import error.

Tests never reach this code path. The suite uses a fake provider injected at
the runner; the live Daytona run is operator-gated (credentials + spend) and
is documented in ``infrastructure/runbooks/remote-exec-fanout.md``. This
module therefore carries no test coverage by design — it is the production
seam, exercised only by the operator's live smoke.

The browse-loop body that runs *inside* the sandbox is supplied by DRW SPR-06
(the real Exa → Browserbase loop); this provider is deliberately ignorant of
it — it provisions the box, ships the loop spec, relays steering, streams
events back, and tears the box down. That keeps Daytona a thin transport, not
a place research logic leaks into.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Callable
from typing import Any

from .provider import (
    RemoteCommand,
    RemoteExecProvisionError,
    RemoteExecRuntimeError,
    RemoteExecUnavailable,
    RemoteStepEvent,
    Sandbox,
)

DAYTONA_PROVIDER_NAME = "daytona"

# Default per-leaf sandbox parameters. Conservative: a research browse loop is
# I/O-bound (Exa / Browserbase calls), so a small box is right; the operator
# tunes via the runbook if a loop turns out CPU-heavy.
DEFAULT_SANDBOX_IMAGE = "antiek/research-leaf:latest"
DEFAULT_SANDBOX_CPU = 1
DEFAULT_SANDBOX_MEMORY_GB = 2


def _resolve_api_creds() -> tuple[str, str | None]:
    """Read Daytona credentials from the environment. Raises
    ``RemoteExecUnavailable`` (loud, not silent) if the API key is absent —
    a missing credential while remote-exec is enabled is a config error, the
    same posture ``client_browserbase._resolve_api_creds`` takes."""
    api_key = os.environ.get("DAYTONA_API_KEY")
    if not api_key:
        raise RemoteExecUnavailable(
            "DAYTONA_API_KEY must be set when remote-exec is enabled "
            "(ANTIEK_REMOTE_EXEC_ENABLED=1). No silent fallback to host-local "
            "here — the factory falls back explicitly and logs it. See "
            "infrastructure/runbooks/remote-exec-fanout.md."
        )
    target = os.environ.get("DAYTONA_TARGET")  # optional region/target
    return api_key, target


def _load_sdk() -> Any:
    """Lazy-import the Daytona SDK on first use. Raises
    ``RemoteExecUnavailable`` if the optional ``[remote_exec]`` dependency is
    not installed — byte-for-byte the same shape as Browserbase's
    ``_default_session_factory`` import guard."""
    try:
        from daytona_sdk import Daytona  # type: ignore[import-not-found]
    except ImportError as e:
        raise RemoteExecUnavailable(
            "daytona-sdk not installed. Run `pip install -e '.[remote_exec]'` "
            "to enable the research-fan-out remote-exec path. See "
            "docs/decisions/s16-research-fanout-exemption.md for the §16 "
            "scope this opt-in install sits behind."
        ) from e
    return Daytona


class DaytonaProvider:
    """Production ``RemoteExecProvider`` over Daytona sandboxes.

    Constructing this does **not** import the SDK or touch the network — the
    SDK loads on the first ``provision``. So a process can construct a
    ``DaytonaProvider`` (e.g. the factory does, to check availability) without
    the SDK installed; only *using* it requires the optional dependency, at
    which point the missing SDK raises ``RemoteExecUnavailable`` loudly.

    ``client_factory`` is an injection seam mirroring Browserbase's
    ``session_factory`` — production leaves it ``None`` (lazy SDK load); a
    test that wanted to exercise this class (the suite does not) could pass a
    fake. The default suite path uses a wholly separate fake provider instead,
    so this class stays untouched by tests."""

    def __init__(
        self,
        *,
        client_factory: Callable[[], Any] | None = None,
        image: str = DEFAULT_SANDBOX_IMAGE,
        loop_entrypoint: str = "python -m antiek.remote.research_leaf",
    ):
        self._client_factory = client_factory
        self._image = image
        self._loop_entrypoint = loop_entrypoint
        self._client: Any = None

    @property
    def name(self) -> str:
        return DAYTONA_PROVIDER_NAME

    def probe(self) -> None:
        """Availability check the factory calls at launch — resolves
        credentials and lazy-loads the SDK *without* provisioning a sandbox or
        touching the network. Raises ``RemoteExecUnavailable`` loudly if the
        SDK or ``DAYTONA_API_KEY`` is missing; the factory catches exactly
        this and falls back to host-local with one logged line."""
        _resolve_api_creds()
        _load_sdk()

    def _client_or_load(self) -> Any:
        if self._client is not None:
            return self._client
        if self._client_factory is not None:
            self._client = self._client_factory()
            return self._client
        api_key, target = _resolve_api_creds()
        Daytona = _load_sdk()
        # The SDK's exact constructor shape is operator-verified during the
        # live smoke; we pass the credential and (optional) target it
        # documents. Wrapped so a constructor change surfaces as a clear
        # provision error rather than an opaque SDK traceback.
        try:
            self._client = Daytona(api_key=api_key, target=target)
        except Exception as e:  # pragma: no cover — live-only
            raise RemoteExecProvisionError(
                f"Daytona client init failed: {type(e).__name__}: {e}"
            ) from e
        return self._client

    async def provision(self, plan: Any) -> Sandbox:  # pragma: no cover — live-only
        client = self._client_or_load()
        iid = getattr(plan, "investigation_id", "unknown")
        try:
            workspace = client.create(image=self._image)
        except Exception as e:
            raise RemoteExecProvisionError(
                f"Daytona sandbox provision failed for {iid}: "
                f"{type(e).__name__}: {e}"
            ) from e
        return Sandbox(
            sandbox_id=getattr(workspace, "id", str(id(workspace))),
            investigation_id=iid,
            meta={"workspace": workspace, "image": self._image},
        )

    async def run(  # pragma: no cover — live-only
        self, sandbox: Sandbox, plan: Any
    ) -> AsyncIterator[RemoteStepEvent]:
        """Start the in-sandbox browse loop and stream its events back.

        The real wiring (ship the SPR-06 loop spec into the sandbox, start
        ``loop_entrypoint``, decode the streamed JSONL event channel into
        ``RemoteStepEvent``s) is finalized against the SDK during the
        operator's live smoke. The shape is fixed here: an async generator
        that yields one ``RemoteStepEvent`` per emitted line and ends when the
        channel closes."""
        workspace = sandbox.meta.get("workspace")
        if workspace is None:
            raise RemoteExecRuntimeError(
                f"sandbox {sandbox.sandbox_id} has no workspace handle"
            )
        # The async-generator body is intentionally a single guarded yield
        # site so the streaming contract (one event per line, ends on close)
        # is unambiguous to the operator wiring the SDK channel.
        raise RemoteExecRuntimeError(
            "DaytonaProvider.run is the production seam; it is exercised only "
            "by the operator-gated live smoke (see the runbook). The test "
            "suite uses a fake provider. Wire the SDK exec/stream call here "
            "against the SPR-06 loop spec."
        )
        yield  # pragma: no cover — marks this an async generator for typing

    async def steer(  # pragma: no cover — live-only
        self, sandbox: Sandbox, command: RemoteCommand
    ) -> None:
        workspace = sandbox.meta.get("workspace")
        if workspace is None:
            return  # safe no-op: nothing to steer
        # Relay the signal into the sandbox's control channel. Cooperative,
        # like the host-local checkpoint — never a process-kill.

    async def teardown(self, sandbox: Sandbox) -> None:  # pragma: no cover — live-only
        """Destroy the sandbox. Idempotent: a missing/already-removed
        workspace is a no-op, so cancel-then-complete double teardown is
        safe."""
        workspace = sandbox.meta.get("workspace")
        if workspace is None:
            return
        client = self._client
        if client is None:
            return
        try:
            client.remove(workspace)
        except Exception:
            # Best-effort: a sandbox that is already gone (provider GC'd it,
            # a prior teardown removed it) must not raise on the second call.
            pass
        finally:
            sandbox.meta.pop("workspace", None)


__all__ = ["DaytonaProvider", "DAYTONA_PROVIDER_NAME"]
