"""Hermetic contract tests for the default-off Prime Agent RPC provider."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, cast

import pytest

from runtime.remote_exec.factory import (
    ENABLE_ENV,
    _default_provider_factory,
    build_research_runner,
)
from runtime.remote_exec.prime_exec import (
    PRIME_EXEC_ENABLE_ENV,
    PrimeExecProvider,
)
from runtime.remote_exec.provider import (
    RemoteCommand,
    RemoteExecProvider,
    RemoteExecRuntimeError,
    RemoteExecUnavailable,
    RemoteSignal,
    RemoteStepEvent,
)
from runtime.remote_exec.runner import RemoteResearchRunner
from runtime.research_runner import (
    BudgetCap,
    HostLocalRunner,
    ResearchPlan,
    RunState,
    make_demo_loop,
)


class _FakeWriter:
    def __init__(self) -> None:
        self.writes: list[bytes] = []
        self.closed = False

    def write(self, data: bytes) -> None:
        self.writes.append(data)

    async def drain(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True


class _FakeReader:
    def __init__(self, records: list[bytes]) -> None:
        self.records = list(records)

    async def readline(self) -> bytes:
        await asyncio.sleep(0)
        return self.records.pop(0) if self.records else b""

    async def read(self, _limit: int = -1) -> bytes:
        data = b"".join(self.records)
        self.records.clear()
        return data


class _FakeProcess:
    def __init__(
        self,
        stdout: list[bytes],
        *,
        stderr: bytes = b"",
        returncode: int | None = None,
    ) -> None:
        self.pid = 4242
        self.stdin = _FakeWriter()
        self.stdout = _FakeReader(stdout)
        self.stderr = _FakeReader([stderr] if stderr else [])
        self.returncode = returncode
        self.terminated = False
        self.killed = False

    async def wait(self) -> int:
        await asyncio.sleep(0)
        if self.returncode is None:
            self.returncode = 0
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = 0

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9


class _FakeProcessFactory:
    def __init__(self, process: _FakeProcess) -> None:
        self.process = process
        self.argv: tuple[str, ...] | None = None
        self.kwargs: dict[str, Any] | None = None

    async def __call__(self, *argv: str, **kwargs: Any) -> asyncio.subprocess.Process:
        self.argv = argv
        self.kwargs = kwargs
        return cast(asyncio.subprocess.Process, self.process)


def _record(value: dict[str, object], *, crlf: bool = False) -> bytes:
    ending = b"\r\n" if crlf else b"\n"
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode() + ending


def _provider(
    tmp_path: Path,
    process: _FakeProcess,
) -> tuple[PrimeExecProvider, _FakeProcessFactory]:
    factory = _FakeProcessFactory(process)
    provider = PrimeExecProvider(
        binary="prime-agent",
        provider="test-provider",
        model="test-model",
        session_root=tmp_path,
        process_factory=factory,
        binary_resolver=lambda binary: f"/fake/{binary}",
        version_resolver=lambda _binary: "prime-agent 0.7.0",
    )
    return provider, factory


def _decode_writes(process: _FakeProcess) -> list[dict[str, object]]:
    return [json.loads(line) for line in process.stdin.writes]


def test_prime_exec_provider_satisfies_remote_exec_protocol(tmp_path: Path) -> None:
    provider, _ = _provider(tmp_path, _FakeProcess([]))
    assert isinstance(provider, RemoteExecProvider)
    assert provider.name == "prime_agent"


def test_probe_rejects_unpinned_binary_version(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv(PRIME_EXEC_ENABLE_ENV, "1")
    provider = PrimeExecProvider(
        session_root=tmp_path,
        binary_resolver=lambda binary: f"/fake/{binary}",
        version_resolver=lambda _binary: "prime-agent 0.8.0",
    )

    with pytest.raises(RemoteExecUnavailable, match="version mismatch"):
        provider.probe()


async def test_turn_usage_must_be_complete_finite_and_nonnegative(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv(PRIME_EXEC_ENABLE_ENV, "1")
    invalid_usage_rows: list[dict[str, object]] = [
        {"input": 1, "output": 1, "cacheRead": 0, "cacheWrite": 0, "cost": {}},
        {
            "input": -1,
            "output": 1,
            "cacheRead": 0,
            "cacheWrite": 0,
            "cost": {"total": 0.1},
        },
        {
            "input": 1,
            "output": 1,
            "cacheRead": 0,
            "cacheWrite": 0,
            "cost": {"total": float("nan")},
        },
    ]
    for index, usage in enumerate(invalid_usage_rows):
        process = _FakeProcess(
            [
                _record({"type": "response", "command": "prompt", "success": True}),
                _record(
                    {
                        "type": "turn_end",
                        "message": {
                            "role": "assistant",
                            "content": [],
                            "stopReason": "stop",
                            "usage": usage,
                        },
                        "toolResults": [],
                    }
                ),
            ]
        )
        provider, _ = _provider(tmp_path / str(index), process)
        plan = ResearchPlan(investigation_id=f"inv-bad-{index}", sub_question="q")
        sandbox = await provider.provision(plan)
        with pytest.raises(RemoteExecRuntimeError):
            async for _ in provider.run(sandbox, plan):
                pass
        await provider.teardown(sandbox)


async def test_failed_turn_charges_cost_and_runner_owns_single_terminal_event(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv(PRIME_EXEC_ENABLE_ENV, "1")
    process = _FakeProcess(
        [
            _record({"type": "response", "command": "prompt", "success": True}),
            _record(
                {
                    "type": "turn_end",
                    "message": {
                        "role": "assistant",
                        "content": [],
                        "provider": "model-provider",
                        "model": "model",
                        "stopReason": "error",
                        "usage": {
                            "input": 2,
                            "output": 1,
                            "cacheRead": 0,
                            "cacheWrite": 0,
                            "cost": {"total": 0.02},
                        },
                    },
                    "toolResults": [],
                }
            ),
        ]
    )
    provider, _ = _provider(tmp_path / "sessions", process)
    runner = RemoteResearchRunner(
        provider,
        events_dir=str(tmp_path / "events"),
        outbox_db_path=str(tmp_path / "outbox.duckdb"),
        seal_on_complete=False,
    )
    plan = ResearchPlan(
        investigation_id="inv-failed-turn",
        sub_question="q",
        budget=BudgetCap(cost_usd=1.0),
    )
    handle = await runner.start(plan.investigation_id, plan)
    events = [event async for event in runner.stream(handle)]

    assert runner.status(handle).state is RunState.FAILED
    assert runner.cost(handle).spent_usd == pytest.approx(0.02)
    assert [event.kind for event in events].count("done") == 1
    assert any(event.kind == "error" for event in events)


async def test_run_drives_rpc_and_maps_typed_events(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    separator_text = "first second third"
    process = _FakeProcess(
        [
            _record(
                {
                    "id": "antiek-1",
                    "type": "response",
                    "command": "prompt",
                    "success": True,
                },
                crlf=True,
            ),
            _record({"type": "agent_start"}),
            _record(
                {
                    "type": "message_update",
                    "message": {"role": "assistant", "content": []},
                    "assistantMessageEvent": {
                        "type": "text_delta",
                        "delta": separator_text,
                    },
                }
            ),
            _record(
                {
                    "type": "message_update",
                    "message": {"role": "assistant", "content": []},
                    "assistantMessageEvent": {
                        "type": "text_delta",
                        "delta": " final",
                    },
                }
            ),
            _record(
                {
                    "type": "message_end",
                    "message": {
                        "role": "assistant",
                        "content": [{"type": "text", "text": "one complete note"}],
                    },
                }
            ),
            _record(
                {
                    "type": "turn_end",
                    "message": {
                        "role": "assistant",
                        "content": [{"type": "text", "text": "answer"}],
                        "provider": "real-provider",
                        "model": "real-model",
                        "stopReason": "stop",
                        "usage": {
                            "input": 10,
                            "output": 4,
                            "cacheRead": 2,
                            "cacheWrite": 1,
                            "cost": {"total": 0.0125},
                        },
                    },
                    "toolResults": [],
                }
            ),
            _record(
                {
                    "type": "agent_end",
                    "messages": [
                        {
                            "role": "assistant",
                            "content": [{"type": "text", "text": "final answer"}],
                        }
                    ],
                }
            ),
        ]
    )
    provider, factory = _provider(tmp_path, process)
    monkeypatch.setenv(PRIME_EXEC_ENABLE_ENV, "1")
    monkeypatch.setenv("SHOULD_NOT_REACH_PRIME", "secret")
    plan = ResearchPlan(investigation_id="inv-prime", sub_question="Research this")

    sandbox = await provider.provision(plan)
    events = [event async for event in provider.run(sandbox, plan)]

    assert isinstance(events[0], RemoteStepEvent)
    assert [event.kind for event in events] == [
        "plan",
        "step",
        "step",
        "note",
        "cost",
        "status",
    ]
    assert [event.seq for event in events] == [1, 2, 3, 4, 5, 6]
    assert events[1].text == separator_text
    assert events[2].text == " final"
    assert events[3].text == "one complete note"
    assert events[4].cost_usd == pytest.approx(0.0125)
    assert events[4].tokens == 17
    assert events[4].provider == "prime_agent"
    assert events[4].model == "real-model"
    assert events[4].data["inference_provider"] == "real-provider"
    assert events[4].data["input_tokens"] == 10
    assert events[4].data["output_tokens"] == 4
    assert events[4].data["finish_reason"] == "stop"
    assert events[-1].text == "final answer"

    assert factory.argv is not None
    assert factory.argv[:3] == ("/fake/prime-agent", "--mode", "rpc")
    assert "--session-dir" in factory.argv
    assert factory.argv[-4:] == (
        "--provider",
        "test-provider",
        "--model",
        "test-model",
    )
    assert factory.kwargs is not None
    child_env = factory.kwargs["env"]
    assert child_env["ANTIEK_PRIME_EXEC_SCOPE"] == "research_fanout"
    assert "SHOULD_NOT_REACH_PRIME" not in child_env

    commands = _decode_writes(process)
    assert commands[0]["type"] == "prompt"
    assert commands[0]["id"] == "antiek-1"
    assert "Research this" in cast(str, commands[0]["message"])
    assert "prime rl run" in cast(str, commands[0]["message"])
    session_dir = Path(cast(str, sandbox.meta["session_dir"]))
    assert session_dir.exists()

    await provider.teardown(sandbox)
    await provider.teardown(sandbox)
    assert process.terminated is True
    assert process.stdin.closed is True
    assert not session_dir.exists()


async def test_steer_uses_steer_and_follow_up_commands(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    process = _FakeProcess([])
    provider, _ = _provider(tmp_path, process)
    monkeypatch.setenv(PRIME_EXEC_ENABLE_ENV, "yes")
    sandbox = await provider.provision(ResearchPlan(investigation_id="inv-steer", sub_question="q"))

    await provider.steer(
        sandbox,
        RemoteCommand(RemoteSignal.REDIRECT, {"sub_question": "new question"}),
    )
    await provider.steer(
        sandbox,
        RemoteCommand(RemoteSignal.DEEPEN, {"follow_up": "go deeper"}),
    )
    await provider.steer(sandbox, RemoteCommand(RemoteSignal.PAUSE))
    await provider.steer(sandbox, RemoteCommand(RemoteSignal.RESUME))
    await provider.steer(sandbox, RemoteCommand(RemoteSignal.STOP))

    commands = _decode_writes(process)
    assert [command["type"] for command in commands] == [
        "steer",
        "follow_up",
        "abort",
        "abort",
    ]
    assert commands[0]["message"] == "new question"
    assert commands[1]["message"] == "go deeper"
    await provider.teardown(sandbox)


async def test_pause_suspends_iterator_until_resume_starts_follow_up(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv(PRIME_EXEC_ENABLE_ENV, "1")
    usage = {
        "input": 1,
        "output": 1,
        "cacheRead": 0,
        "cacheWrite": 0,
        "cost": {"total": 0.01},
    }
    process = _FakeProcess(
        [
            _record({"type": "response", "command": "prompt", "success": True}),
            _record({"type": "agent_start"}),
            _record(
                {
                    "type": "message_update",
                    "message": {"role": "assistant", "content": []},
                    "assistantMessageEvent": {"type": "error", "reason": "aborted"},
                }
            ),
            _record(
                {
                    "type": "turn_end",
                    "message": {
                        "role": "assistant",
                        "content": [],
                        "stopReason": "aborted",
                        "usage": usage,
                    },
                    "toolResults": [],
                }
            ),
            _record({"type": "agent_end", "messages": []}),
            _record({"type": "response", "command": "follow_up", "success": True}),
            _record({"type": "agent_start"}),
            _record(
                {
                    "type": "turn_end",
                    "message": {
                        "role": "assistant",
                        "content": [],
                        "stopReason": "stop",
                        "usage": usage,
                    },
                    "toolResults": [],
                }
            ),
            _record({"type": "agent_end", "messages": []}),
        ]
    )
    provider, _ = _provider(tmp_path, process)
    plan = ResearchPlan(investigation_id="inv-pause", sub_question="q")
    sandbox = await provider.provision(plan)
    stream = provider.run(sandbox, plan)
    assert (await anext(stream)).kind == "plan"
    await provider.steer(sandbox, RemoteCommand(RemoteSignal.PAUSE))

    async def collect_rest() -> list[RemoteStepEvent]:
        return [event async for event in stream]

    collecting = asyncio.create_task(collect_rest())
    for _ in range(8):
        await asyncio.sleep(0)
    assert not collecting.done()
    assert [row["type"] for row in _decode_writes(process)] == ["prompt", "abort"]

    await provider.steer(sandbox, RemoteCommand(RemoteSignal.RESUME))
    rest = await asyncio.wait_for(collecting, timeout=1.0)
    assert [row["type"] for row in _decode_writes(process)] == [
        "prompt",
        "abort",
        "follow_up",
    ]
    assert [event.kind for event in rest].count("cost") == 2
    assert not [event for event in rest if event.kind == "error"]
    await provider.teardown(sandbox)


async def test_stop_releases_paused_iterator_without_follow_up(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv(PRIME_EXEC_ENABLE_ENV, "1")
    process = _FakeProcess(
        [
            _record({"type": "response", "command": "prompt", "success": True}),
            _record({"type": "agent_start"}),
            _record(
                {
                    "type": "message_update",
                    "message": {"role": "assistant", "content": []},
                    "assistantMessageEvent": {"type": "error", "reason": "aborted"},
                }
            ),
            _record(
                {
                    "type": "turn_end",
                    "message": {
                        "role": "assistant",
                        "content": [],
                        "stopReason": "aborted",
                        "usage": {
                            "input": 1,
                            "output": 0,
                            "cacheRead": 0,
                            "cacheWrite": 0,
                            "cost": {"total": 0.01},
                        },
                    },
                    "toolResults": [],
                }
            ),
            _record({"type": "agent_end", "messages": []}),
        ]
    )
    provider, _ = _provider(tmp_path, process)
    plan = ResearchPlan(investigation_id="inv-pause-stop", sub_question="q")
    sandbox = await provider.provision(plan)
    stream = provider.run(sandbox, plan)
    assert (await anext(stream)).kind == "plan"
    await provider.steer(sandbox, RemoteCommand(RemoteSignal.PAUSE))

    collecting = asyncio.create_task(collect_events(stream))
    for _ in range(8):
        await asyncio.sleep(0)
    assert not collecting.done()

    await provider.steer(sandbox, RemoteCommand(RemoteSignal.STOP))
    rest = await asyncio.wait_for(collecting, timeout=1.0)
    assert [row["type"] for row in _decode_writes(process)] == ["prompt", "abort", "abort"]
    assert [event.kind for event in rest] == ["cost", "status"]
    await provider.teardown(sandbox)


async def collect_events(stream: Any) -> list[RemoteStepEvent]:
    return [event async for event in stream]


async def test_unterminated_record_violates_lf_only_framing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    process = _FakeProcess([b'{"type":"agent_start"}'])
    provider, _ = _provider(tmp_path, process)
    monkeypatch.setenv(PRIME_EXEC_ENABLE_ENV, "1")
    plan = ResearchPlan(investigation_id="inv-frame", sub_question="q")
    sandbox = await provider.provision(plan)

    with pytest.raises(RemoteExecRuntimeError, match="LF required"):
        async for _ in provider.run(sandbox, plan):
            pass
    await provider.teardown(sandbox)


async def test_cancelled_provision_removes_partial_session_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv(PRIME_EXEC_ENABLE_ENV, "1")
    started = asyncio.Event()
    never = asyncio.Event()

    async def blocking_factory(*_argv: str, **_kwargs: Any) -> asyncio.subprocess.Process:
        started.set()
        await never.wait()
        raise AssertionError("unreachable")

    provider = PrimeExecProvider(
        session_root=tmp_path,
        process_factory=blocking_factory,
        binary_resolver=lambda binary: f"/fake/{binary}",
        version_resolver=lambda _binary: "prime-agent 0.7.0",
    )
    task = asyncio.create_task(
        provider.provision(ResearchPlan(investigation_id="inv-cancel", sub_question="q"))
    )
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not [path for path in tmp_path.iterdir() if path.name.startswith("prime-exec-")]


async def test_nonzero_subprocess_exit_maps_to_runtime_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    process = _FakeProcess([], stderr=b"fatal rpc failure", returncode=17)
    provider, _ = _provider(tmp_path, process)
    monkeypatch.setenv(PRIME_EXEC_ENABLE_ENV, "true")
    plan = ResearchPlan(investigation_id="inv-crash", sub_question="q")
    sandbox = await provider.provision(plan)

    with pytest.raises(RemoteExecRuntimeError, match=r"exit 17") as caught:
        async for _ in provider.run(sandbox, plan):
            pass
    assert "fatal rpc failure" not in str(caught.value)
    await provider.teardown(sandbox)


async def test_direct_provision_is_disabled_before_spawn(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    process = _FakeProcess([])
    provider, factory = _provider(tmp_path, process)
    monkeypatch.delenv(PRIME_EXEC_ENABLE_ENV, raising=False)

    with pytest.raises(RemoteExecUnavailable, match="default-off"):
        await provider.provision(ResearchPlan(investigation_id="inv-disabled", sub_question="q"))

    assert factory.argv is None
    assert process.stdin.writes == []


def test_default_factory_never_registers_prime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for value in (None, "1"):
        if value is None:
            monkeypatch.delenv(PRIME_EXEC_ENABLE_ENV, raising=False)
        else:
            monkeypatch.setenv(PRIME_EXEC_ENABLE_ENV, value)
        provider = _default_provider_factory()
        assert provider.name == "daytona"
        assert not isinstance(provider, PrimeExecProvider)


def test_unset_prime_flag_factory_falls_back_instead_of_offering_prime(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    process = _FakeProcess([])
    provider, _ = _provider(tmp_path, process)
    monkeypatch.setenv(ENABLE_ENV, "1")
    monkeypatch.delenv(PRIME_EXEC_ENABLE_ENV, raising=False)

    runner = build_research_runner(
        loop_fn=make_demo_loop(steps=1),
        provider=provider,
    )

    assert isinstance(runner, HostLocalRunner)
    assert process.stdin.writes == []
