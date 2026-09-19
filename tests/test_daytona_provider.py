from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

import pytest

from runtime.remote_exec.daytona import DaytonaProvider
from runtime.remote_exec.provider import (
    RemoteCommand,
    RemoteExecRuntimeError,
    RemoteSignal,
)
from runtime.research_runner.protocol import BudgetCap, ResearchPlan


@dataclass
class _Response:
    cmd_id: str = "cmd-1"


@dataclass
class _Status:
    exit_code: int = 0


class _Process:
    def __init__(self, chunks: list[str] | None = None):
        self.chunks = chunks or []
        self.inputs: list[str] = []
        self.sessions: list[str] = []
        self.requests: list[Any] = []
        self.exit_code = 0

    def create_session(self, session_id: str) -> None:
        self.sessions.append(session_id)

    def execute_session_command(self, session_id: str, request: Any) -> _Response:
        self.requests.append(request)
        return _Response()

    def send_session_command_input(self, session_id: str, command_id: str, data: str) -> None:
        self.inputs.append(data)

    async def get_session_command_logs_async(self, session_id, command_id, stdout, stderr):
        for chunk in self.chunks:
            await stdout(chunk)

    def get_session_command(self, session_id: str, command_id: str) -> _Status:
        return _Status(self.exit_code)


class _Workspace:
    id = "sandbox-1"

    def __init__(self, process: _Process):
        self.process = process


class _Client:
    def __init__(self, process: _Process):
        self.workspace = _Workspace(process)
        self.created: list[tuple[Any, float]] = []
        self.deleted: list[str] = []
        self.delete_error: Exception | None = None

    def create(self, params: Any, *, timeout: float):
        self.created.append((params, timeout))
        return self.workspace

    def delete(self, workspace: _Workspace, *, timeout: float, wait: bool) -> None:
        assert wait is True
        if self.delete_error:
            raise self.delete_error
        self.deleted.append(workspace.id)


def _provider(process: _Process, client: _Client | None = None) -> tuple[DaytonaProvider, _Client]:
    client = client or _Client(process)
    provider = DaytonaProvider(
        client_factory=lambda: client,
        snapshot_id="snap-sha256-abc",
        params_factory=lambda **kw: kw,
        request_factory=lambda **kw: type("Request", (), kw)(),
    )
    return provider, client


def _plan() -> ResearchPlan:
    return ResearchPlan("inv-1", "bounded question", budget=BudgetCap(0.25, 3),
                        metadata={"secret": "must-not-cross"})


@pytest.mark.parametrize("snapshot", ["latest", "x", "bad snapshot", "../escape", "x" * 129])
def test_snapshot_id_validation_fails_closed(snapshot: str) -> None:
    provider = DaytonaProvider(
        client_factory=lambda: _Client(_Process()), snapshot_id=snapshot,
        params_factory=lambda **kw: kw, request_factory=lambda **kw: kw,
    )
    with pytest.raises(Exception, match="snapshot"):
        provider._resolve()


@pytest.mark.asyncio
async def test_provision_requires_snapshot_and_passes_no_credentials() -> None:
    process = _Process()
    provider, client = _provider(process)
    sandbox = await provider.provision(_plan())
    assert sandbox.sandbox_id == "sandbox-1"
    params, _ = client.created[0]
    assert params["snapshot"] == "snap-sha256-abc"
    assert "env_vars" not in params
    assert "image" not in params
    assert "secret" not in json.dumps(params)
    assert sandbox.meta.keys() == {"workspace"}


@pytest.mark.asyncio
async def test_run_maps_split_bounded_jsonl_and_sends_narrow_plan() -> None:
    one = json.dumps({"type": "event", "seq": 1, "kind": "step", "text": "a"})
    two = json.dumps({"type": "event", "seq": 2, "kind": "cost", "cost_usd": 0.1,
                      "tokens": 4, "provider": "p", "model": "m"})
    done = json.dumps({"type": "event", "seq": 3, "kind": "done"})
    process = _Process([one[:10], one[10:] + "\n" + two + "\n" + done + "\n"])
    provider, _ = _provider(process)
    sandbox = await provider.provision(_plan())
    events = [event async for event in provider.run(sandbox, _plan())]
    assert [(event.seq, event.kind) for event in events] == [(1, "step"), (2, "cost"), (3, "done")]
    assert events[1].cost_usd == 0.1
    start = json.loads(process.inputs[0])
    assert start["plan"]["budget"] == {"cost_usd": 0.25, "max_steps": 3}
    assert "secret" not in process.inputs[0]


@pytest.mark.asyncio
@pytest.mark.parametrize("record", [
    {"type": "event", "seq": 2, "kind": "step"},
    {"type": "event", "seq": 1, "kind": "arbitrary"},
    {"type": "event", "seq": 1, "kind": "cost", "cost_usd": float("inf")},
    {"type": "event", "seq": 1, "kind": "cost", "tokens": -1},
])
async def test_run_rejects_invalid_event_contract(record: dict[str, Any]) -> None:
    process = _Process([json.dumps(record) + "\n"])
    provider, _ = _provider(process)
    sandbox = await provider.provision(_plan())
    with pytest.raises(RemoteExecRuntimeError):
        _ = [event async for event in provider.run(sandbox, _plan())]


@pytest.mark.asyncio
async def test_steer_writes_control_record() -> None:
    process = _Process([json.dumps({"type": "event", "seq": 1, "kind": "done"}) + "\n"])
    provider, _ = _provider(process)
    sandbox = await provider.provision(_plan())
    # Establish the session before steering.
    _ = [event async for event in provider.run(sandbox, _plan())]
    await provider.steer(sandbox, RemoteCommand(RemoteSignal.REDIRECT, {"sub_question": "new"}))
    assert json.loads(process.inputs[-1]) == {
        "type": "control", "protocol": 1, "signal": "redirect",
        "payload": {"sub_question": "new"},
    }


@pytest.mark.asyncio
async def test_cancellation_deletes_sandbox() -> None:
    entered = asyncio.Event()
    release = asyncio.Event()

    class SlowProcess(_Process):
        async def get_session_command_logs_async(self, session_id, command_id, stdout, stderr):
            entered.set()
            await release.wait()

    process = SlowProcess()
    provider, client = _provider(process)
    sandbox = await provider.provision(_plan())

    async def consume() -> None:
        _ = [event async for event in provider.run(sandbox, _plan())]

    task = asyncio.create_task(consume())
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert client.deleted == ["sandbox-1"]
    assert sandbox.meta == {}


@pytest.mark.asyncio
async def test_teardown_only_swallows_typed_not_found() -> None:
    class NotFound(Exception):
        status_code = 404

    process = _Process()
    client = _Client(process)
    provider, _ = _provider(process, client)
    sandbox = await provider.provision(_plan())
    client.delete_error = NotFound()
    await provider.teardown(sandbox)
    await provider.teardown(sandbox)

    sandbox = await provider.provision(_plan())
    client.delete_error = RuntimeError("outage")
    with pytest.raises(RemoteExecRuntimeError, match="after 3 attempts"):
        await provider.teardown(sandbox)
    assert sandbox.meta["workspace"] is client.workspace


@pytest.mark.asyncio
async def test_cancelled_provision_reclaims_late_created_sandbox() -> None:
    process = _Process()
    client = _Client(process)
    import threading
    started = threading.Event()

    def slow_create(params: Any, *, timeout: float):
        started.set()
        import time
        time.sleep(0.05)
        return client.workspace

    client.create = slow_create  # type: ignore[method-assign]
    provider, _ = _provider(process, client)
    task = asyncio.create_task(provider.provision(_plan()))
    while not started.is_set():
        await asyncio.sleep(0.001)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert client.deleted == ["sandbox-1"]


@pytest.mark.asyncio
@pytest.mark.parametrize("chunks", [
    [],
    [json.dumps({"type": "event", "seq": 1, "kind": "step"}) + "\n"],
    [json.dumps({"type": "event", "seq": 1, "kind": "done"}) + "\n" +
     json.dumps({"type": "event", "seq": 2, "kind": "step"}) + "\n"],
    ['{"type":"event","type":"event","seq":1,"kind":"done"}\n'],
])
async def test_run_rejects_empty_truncated_post_terminal_and_duplicate_keys(
    chunks: list[str],
) -> None:
    process = _Process(chunks)
    provider, _ = _provider(process)
    sandbox = await provider.provision(_plan())
    with pytest.raises(RemoteExecRuntimeError):
        _ = [event async for event in provider.run(sandbox, _plan())]


@pytest.mark.asyncio
async def test_run_idle_deadline_is_bounded() -> None:
    class HungProcess(_Process):
        async def get_session_command_logs_async(self, session_id, command_id, stdout, stderr):
            await asyncio.Event().wait()

    process = HungProcess()
    client = _Client(process)
    provider = DaytonaProvider(
        client_factory=lambda: client, snapshot_id="snap-sha256-abc",
        params_factory=lambda **kw: kw,
        request_factory=lambda **kw: type("Request", (), kw)(),
        idle_timeout_s=0.01, total_timeout_s=0.1,
    )
    sandbox = await provider.provision(_plan())
    with pytest.raises(RemoteExecRuntimeError, match="idle deadline"):
        _ = [event async for event in provider.run(sandbox, _plan())]


@pytest.mark.asyncio
async def test_concurrent_teardown_calls_delete_once() -> None:
    process = _Process()
    provider, client = _provider(process)
    sandbox = await provider.provision(_plan())
    await asyncio.gather(provider.teardown(sandbox), provider.teardown(sandbox))
    assert client.deleted == ["sandbox-1"]
