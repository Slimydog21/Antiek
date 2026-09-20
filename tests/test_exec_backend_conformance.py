"""Cross-backend conformance: one suite, two backends (spec §1 outcome #2).

The whole point of the seam is that consumers depend on the *interface*, not
any one backend. So the contract a caller relies on must hold identically
against a structural fake and against the real ``LocalProcessBackend`` —
proving "backend swap is mechanical" is a tested claim, not a slogan. This
suite runs the same assertions against both; a future Docker/E2B adapter
adds itself to the parametrization and inherits the same guarantees.

Genuinely process-level behavior (a real timeout kill, a real 3 MiB cap) is
NOT here — it cannot be faked honestly — it lives in
``tests/test_exec_backend_local.py``. This suite holds only the contract
every conformant backend must share.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import pytest
from exec_backend_fakes import FakeBackend

from runtime.exec_backend import (
    ALLOW_ALL,
    ExecResult,
    ExecutionBackend,
    LocalProcessBackend,
    ResourceLimits,
    Workspace,
    WorkspaceProfile,
)


@pytest.fixture(params=["fake", "local"])
def make_workspace(
    request: pytest.FixtureRequest, tmp_path: str
) -> Callable[[], Awaitable[Workspace]]:
    """Factory returning a fresh workspace of the parametrized backend kind."""
    kind = request.param

    async def _make() -> Workspace:
        if kind == "fake":
            backend: ExecutionBackend = FakeBackend()
        else:
            backend = LocalProcessBackend(workdir_base=tmp_path)
        return await backend.create(
            WorkspaceProfile(name="conformance"),
            limits=ResourceLimits(),
            net_policy=ALLOW_ALL,
        )

    return _make


# --- the shared contract -------------------------------------------------


async def test_exec_without_timeout_raises_typeerror(
    make_workspace: Callable[[], Awaitable[Workspace]],
) -> None:
    # I1 holds for EVERY backend: timeout_s is mandatory, no default.
    ws = await make_workspace()
    with pytest.raises(TypeError):
        await ws.exec(["echo", "hi"])  # type: ignore[attr-defined]  # missing timeout_s


async def test_echo_contract(
    make_workspace: Callable[[], Awaitable[Workspace]],
) -> None:
    ws = await make_workspace()
    result = await ws.exec(["echo", "hi"], timeout_s=5)  # type: ignore[attr-defined]
    assert result.exit_code == 0
    assert "hi" in result.stdout
    assert isinstance(result.duration_ms, int)
    assert result.duration_ms >= 0


async def test_exec_result_shape(
    make_workspace: Callable[[], Awaitable[Workspace]],
) -> None:
    ws = await make_workspace()
    result = await ws.exec(["echo", "x"], timeout_s=5)  # type: ignore[attr-defined]
    assert isinstance(result, ExecResult)
    assert isinstance(result.exit_code, int)
    assert isinstance(result.stdout, str)
    assert isinstance(result.stderr, str)
    assert isinstance(result.timed_out, bool)
    assert isinstance(result.truncated, bool)


async def test_put_get_roundtrip(
    make_workspace: Callable[[], Awaitable[Workspace]],
) -> None:
    ws = await make_workspace()
    payload = b"round-trip-me \x00 \xff"
    await ws.put_file("out/artifact.bin", payload)  # type: ignore[attr-defined]
    assert await ws.get_file("out/artifact.bin") == payload  # type: ignore[attr-defined]


async def test_put_get_roundtrip_nested_path(
    make_workspace: Callable[[], Awaitable[Workspace]],
) -> None:
    ws = await make_workspace()
    await ws.put_file("out/deep/nested/file.txt", b"ok")  # type: ignore[attr-defined]
    assert await ws.get_file("out/deep/nested/file.txt") == b"ok"  # type: ignore[attr-defined]


async def test_put_file_rejects_path_escape(
    make_workspace: Callable[[], Awaitable[Workspace]],
) -> None:
    ws = await make_workspace()
    for escape in ("../escape.txt", "/etc/passwd"):
        with pytest.raises(ValueError):
            await ws.put_file(escape, b"x")  # type: ignore[attr-defined]


async def test_destroy_is_idempotent(
    make_workspace: Callable[[], Awaitable[Workspace]],
) -> None:
    # I6 holds for every backend: destroy-twice is a no-op.
    ws = await make_workspace()
    await ws.destroy()  # type: ignore[attr-defined]
    await ws.destroy()  # type: ignore[attr-defined]


async def test_workspace_satisfies_protocol(
    make_workspace: Callable[[], Awaitable[Workspace]],
) -> None:
    ws = await make_workspace()
    assert isinstance(ws, Workspace)
    assert isinstance(ws.workspace_id, str) and len(ws.workspace_id) > 0


@pytest.mark.parametrize(
    "factory",
    [FakeBackend, lambda: LocalProcessBackend()],
    ids=["fake", "local"],
)
def test_backend_name_probe_and_protocol(factory: Callable[[], ExecutionBackend]) -> None:
    backend = factory()
    assert isinstance(backend, ExecutionBackend)
    assert isinstance(backend.name, str) and backend.name
    assert backend.probe() is None  # type: ignore[func-returns-value]
