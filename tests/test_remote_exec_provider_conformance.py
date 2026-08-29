"""Provider-conformance suite for ``RemoteExecProvider`` implementations.

The B3 BYOC draft requires new sandbox adapters (Vercel, Cloudflare) to pass
one parameterized conformance suite. This file builds that suite NOW over the
implementations that already exist — the three deterministic fakes and, via
its documented ``client_factory`` injection seam, the REAL ``DaytonaProvider``
class, whose own docstring notes it "stays untouched by tests" today.

What the suite pins, per provider:

* structural conformance to the runtime_checkable protocol;
* provision error mapping -> RemoteExecProvisionError (recorded-fixture
  transports only; no SDK, no network, no credentials);
* the run guard contract (missing workspace handle -> RemoteExecRuntimeError);
* teardown idempotency (safe to call twice; second call is a no-op);
* custody preview: with a client factory injected, the provider must never
  read operator env credentials (the B1/B2 owner-resolution requirement).

Live adapters remain operator-gated; nothing here touches the network.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from runtime.remote_exec.daytona import DaytonaProvider
from runtime.remote_exec.provider import (
    RemoteExecProvider,
    RemoteExecProvisionError,
    RemoteExecRuntimeError,
    Sandbox,
)
from tests.remote_exec_fakes import FailingProvider, FakeProvider


class _RecordingClient:
    """Recorded-fixture transport for DaytonaProvider's injection seam."""

    def __init__(self, *, create_error: Exception | None = None) -> None:
        self.created: list[str] = []
        self.removed: list[Any] = []
        self._create_error = create_error

    def create(self, *, image: str) -> Any:
        if self._create_error is not None:
            raise self._create_error
        workspace = type("Workspace", (), {"id": f"ws-{len(self.created)}"})()
        self.created.append(image)
        return workspace

    def remove(self, workspace: Any) -> None:
        self.removed.append(getattr(workspace, "id", workspace))


def _daytona_with(client: _RecordingClient) -> DaytonaProvider:
    return DaytonaProvider(client_factory=lambda: client)


def _fake_workspace_sandbox(provider: DaytonaProvider) -> Sandbox:
    """Provision through the injected client so the sandbox carries a real
    workspace handle, without any SDK or network."""
    return asyncio.run(provider.provision(_Plan()))


class _Plan:
    investigation_id = "conf-1"


PROVIDERS = [
    pytest.param(lambda: FakeProvider(), id="fake-daytona"),
    pytest.param(lambda: FailingProvider(), id="fake-failing"),
    pytest.param(lambda: _daytona_with(_RecordingClient()), id="daytona-recorded"),
]


@pytest.mark.parametrize("make_provider", PROVIDERS)
def test_provider_satisfies_protocol(make_provider) -> None:
    assert isinstance(make_provider(), RemoteExecProvider)


@pytest.mark.parametrize("make_provider", PROVIDERS)
@pytest.mark.asyncio
async def test_teardown_is_idempotent(make_provider) -> None:
    provider = make_provider()
    sandbox = await provider.provision(_Plan())
    await provider.teardown(sandbox)
    # Second teardown must be a safe no-op, never a raise.
    await provider.teardown(sandbox)


def test_daytona_provision_error_maps_loudly() -> None:
    provider = _daytona_with(_RecordingClient(create_error=RuntimeError("quota")))
    with pytest.raises(RemoteExecProvisionError, match="quota"):
        asyncio.run(provider.provision(_Plan()))


@pytest.mark.asyncio
async def test_daytona_run_guard_requires_workspace() -> None:
    provider = _daytona_with(_RecordingClient())
    sandbox = Sandbox(sandbox_id="s-1", investigation_id="conf-1", meta={})
    with pytest.raises(RemoteExecRuntimeError, match="no workspace handle"):
        async for _ in provider.run(sandbox, _Plan()):
            pass


@pytest.mark.asyncio
async def test_daytona_teardown_removes_workspace_once() -> None:
    client = _RecordingClient()
    provider = _daytona_with(client)
    sandbox = await provider.provision(_Plan())
    await provider.teardown(sandbox)
    await provider.teardown(sandbox)
    assert len(client.removed) == 1
    # The handle is dropped from meta so a third call is a pure no-op.
    assert "workspace" not in sandbox.meta


def test_daytona_injected_client_never_reads_env(monkeypatch) -> None:
    monkeypatch.delenv("DAYTONA_API_KEY", raising=False)
    monkeypatch.delenv("DAYTONA_TARGET", raising=False)
    client = _RecordingClient()
    provider = _daytona_with(client)
    sandbox = asyncio.run(provider.provision(_Plan()))
    # Provision succeeded with no env credentials at all: custody came solely
    # from the injected factory (the B1/B2 owner-resolution shape).
    assert sandbox.sandbox_id == "ws-0"
