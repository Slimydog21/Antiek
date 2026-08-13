"""Default-off Prime Agent RPC adapter for research fan-out only.

``PrimeExecProvider`` is a dormant ``RemoteExecProvider`` implementation.  It
starts one ``prime-agent --mode rpc`` subprocess per provisioned research leaf
and translates the v0.7.0 JSONL event stream into ``RemoteStepEvent`` values.
The subprocess is never started unless ``ANTIEK_PRIME_EXEC_ENABLED`` is truthy.

The scope is deliberately narrow.  This module is not registered by the
remote-exec factory, is never a dispatch/inference provider, and never launches
``prime rl run``.  The argv is fixed to the RPC executable and flags; no shell
is involved.  Prime Agent does not provide a security sandbox, so the caller
must place this provider inside its own hardened isolation boundary before any
untrusted research input is allowed.  Building this dark adapter does not amend
``docs/decisions/s16-research-fanout-exemption.md`` or activate a second live
provider.

The pinned RPC framing rule is LF-only: split on ``b"\\n"``, remove that LF,
then remove at most one trailing CR.  In particular U+2028 and U+2029 inside a
JSON string are data, not record separators.
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import shutil
import subprocess
import tempfile
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from .provider import (
    RemoteCommand,
    RemoteExecProvisionError,
    RemoteExecRuntimeError,
    RemoteExecUnavailable,
    RemoteSignal,
    RemoteStepEvent,
    Sandbox,
)

PRIME_EXEC_PROVIDER_NAME = "prime_agent"
PRIME_EXEC_ENABLE_ENV = "ANTIEK_PRIME_EXEC_ENABLED"
PRIME_AGENT_BINARY_ENV = "ANTIEK_PRIME_AGENT_BIN"
PRIME_AGENT_PROVIDER_ENV = "ANTIEK_PRIME_AGENT_PROVIDER"
PRIME_AGENT_MODEL_ENV = "ANTIEK_PRIME_AGENT_MODEL"
DEFAULT_PRIME_AGENT_BINARY = "prime-agent"
PINNED_PRIME_AGENT_VERSION = "0.7.0"
DEFAULT_MAX_RECORD_BYTES = 8 * 1024 * 1024

_TRUTHY = frozenset({"1", "true", "yes"})
_STATE_KEY = "prime_exec_state"
_SAFE_ENV_KEYS = ("HOME", "LANG", "LC_ALL", "PATH", "TMPDIR")
_RESEARCH_ONLY_PREAMBLE = (
    "You are executing one isolated Antiek research-fanout leaf. Restrict all work "
    "to the supplied research question and session directory. You are not an Antiek "
    "dispatch provider. Do not launch training, hosted RL, or `prime rl run`."
)

_ProcessFactory = Callable[..., Awaitable[asyncio.subprocess.Process]]
_BinaryResolver = Callable[[str], str | None]
_VersionResolver = Callable[[str], str]


@dataclass
class _SessionState:
    process: asyncio.subprocess.Process
    session_dir: Path
    provider: str
    model: str
    sequence: int = 0
    request_sequence: int = 0
    run_started: bool = False
    run_finished: bool = False
    stop_requested: bool = False
    pause_requested: bool = False
    paused: bool = False
    resume_event: asyncio.Event = field(default_factory=asyncio.Event)
    failure_reason: str | None = None
    torn_down: bool = False
    write_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def next_request_id(self) -> str:
        self.request_sequence += 1
        return f"antiek-{self.request_sequence}"

    def next_event_sequence(self) -> int:
        self.sequence += 1
        return self.sequence


def prime_exec_enabled() -> bool:
    """Return whether the dedicated Prime adapter gate is enabled.

    This gate is independent of ``ANTIEK_REMOTE_EXEC_ENABLED``.  Both must be
    true before an injected Prime provider can be selected by
    ``build_research_runner``.  The existing default provider factory remains
    Daytona-only.
    """

    return os.environ.get(PRIME_EXEC_ENABLE_ENV, "0").lower() in _TRUTHY


def _require_enabled() -> None:
    if not prime_exec_enabled():
        raise RemoteExecUnavailable(
            f"Prime research execution is disabled; set {PRIME_EXEC_ENABLE_ENV}=1 "
            "only inside an operator-approved isolation boundary. The adapter is "
            "default-off and is not a dispatch provider."
        )


def _as_dict(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    return cast(dict[str, object], value)


def _required_nonnegative_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise RemoteExecRuntimeError(
            f"prime-agent turn usage {field_name} must be a non-negative integer"
        )
    return value


def _required_nonnegative_number(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise RemoteExecRuntimeError(
            f"prime-agent turn usage {field_name} must be a finite non-negative number"
        )
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise RemoteExecRuntimeError(
            f"prime-agent turn usage {field_name} must be a finite non-negative number"
        )
    return result


def _message_text(value: object) -> str:
    message = _as_dict(value)
    if message is None:
        return ""
    content = message.get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        row = _as_dict(item)
        if row is None:
            continue
        text = row.get("text")
        if isinstance(text, str) and text:
            parts.append(text)
    return "".join(parts)


def _last_assistant_text(value: object) -> str:
    if not isinstance(value, list):
        return ""
    for item in reversed(value):
        message = _as_dict(item)
        if message is not None and message.get("role") == "assistant":
            return _message_text(message)
    return ""


def _usage_fields(
    value: object,
) -> tuple[float, int, int, int, str, str, str | None]:
    message = _as_dict(value)
    if message is None:
        raise RemoteExecRuntimeError("prime-agent turn_end has no message object")
    usage = _as_dict(message.get("usage"))
    if usage is None:
        raise RemoteExecRuntimeError("prime-agent turn_end has no usage object")
    cost = _as_dict(usage.get("cost"))
    if cost is None:
        raise RemoteExecRuntimeError("prime-agent turn_end has no usage.cost object")
    cost_usd = _required_nonnegative_number(cost.get("total"), "cost.total")
    input_tokens = _required_nonnegative_int(usage.get("input"), "input")
    output_tokens = _required_nonnegative_int(usage.get("output"), "output")
    cache_read = _required_nonnegative_int(usage.get("cacheRead"), "cacheRead")
    cache_write = _required_nonnegative_int(usage.get("cacheWrite"), "cacheWrite")
    tokens = input_tokens + output_tokens + cache_read + cache_write
    provider = message.get("provider")
    model = message.get("model")
    stop_reason = message.get("stopReason")
    return (
        cost_usd,
        tokens,
        input_tokens,
        output_tokens,
        provider if isinstance(provider, str) else "",
        model if isinstance(model, str) else "",
        stop_reason if isinstance(stop_reason, str) else None,
    )


def _frame_payload(line: bytes) -> bytes:
    """Remove one LF and then one optional CR from a JSONL record."""

    if not line.endswith(b"\n"):
        raise RemoteExecRuntimeError(
            "prime-agent RPC closed with an unterminated JSONL record (LF required)"
        )
    payload = line[:-1]
    if payload.endswith(b"\r"):
        payload = payload[:-1]
    return payload


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON constant {value}")


def _decode_event(line: bytes) -> dict[str, object] | None:
    payload = _frame_payload(line)
    if not payload:
        return None
    try:
        decoded: object = json.loads(payload, parse_constant=_reject_json_constant)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise RemoteExecRuntimeError(
            f"prime-agent emitted invalid JSONL: {type(exc).__name__}: {exc}"
        ) from exc
    event = _as_dict(decoded)
    if event is None:
        raise RemoteExecRuntimeError("prime-agent RPC record must be a JSON object")
    event_type = event.get("type")
    if not isinstance(event_type, str) or not event_type:
        raise RemoteExecRuntimeError("prime-agent RPC record has no string type")
    return event


def _response_error(event: Mapping[str, object]) -> str | None:
    if event.get("type") != "response":
        return None
    if event.get("success") is not False:
        return ""
    error = event.get("error")
    return error if isinstance(error, str) and error else "command rejected"


def _event_text(event: Mapping[str, object], event_type: str) -> str:
    if event_type == "agent_start":
        return "prime-agent research session started"
    if event_type == "turn_start":
        return "prime-agent turn started"
    if event_type == "message_update":
        update = _as_dict(event.get("assistantMessageEvent")) or {}
        for key in ("delta", "content", "reason"):
            value = update.get(key)
            if isinstance(value, str):
                return value
        return ""
    if event_type in {"message_start", "message_end", "turn_end"}:
        return _message_text(event.get("message"))
    if event_type.startswith("tool_execution_"):
        tool = event.get("toolName")
        phase = event_type.removeprefix("tool_execution_")
        return f"{tool if isinstance(tool, str) else 'tool'} {phase}"
    if event_type == "extension_error":
        error = event.get("error")
        return error if isinstance(error, str) else "prime-agent extension error"
    if event_type == "agent_end":
        return _last_assistant_text(event.get("messages"))
    return event_type.replace("_", " ")


def _event_kind(event: Mapping[str, object], event_type: str) -> str:
    if event_type == "agent_start":
        return "plan"
    if event_type == "agent_end":
        return "status"
    if event_type == "turn_end":
        return "cost"
    if event_type == "message_end":
        return "note"
    if event_type in {"message_start", "message_update"}:
        update = _as_dict(event.get("assistantMessageEvent")) or {}
        return "error" if update.get("type") == "error" else "step"
    if event_type == "extension_error":
        return "error"
    if event_type == "tool_execution_end" and event.get("isError") is True:
        return "error"
    if event_type.startswith("tool_execution_") or event_type.startswith("turn_"):
        return "step"
    return "status"


def _map_event(state: _SessionState, event: Mapping[str, object]) -> RemoteStepEvent:
    event_type = cast(str, event["type"])
    if event_type == "turn_end":
        (
            cost_usd,
            tokens,
            input_tokens,
            output_tokens,
            inference_provider,
            inference_model,
            finish_reason,
        ) = _usage_fields(event.get("message"))
    else:
        cost_usd = 0.0
        tokens = input_tokens = output_tokens = 0
        inference_provider = inference_model = ""
        finish_reason = None
    data: dict[str, object] = {"prime_event_type": event_type}
    if input_tokens:
        data["input_tokens"] = input_tokens
    if output_tokens:
        data["output_tokens"] = output_tokens
    if inference_provider or state.provider:
        data["inference_provider"] = inference_provider or state.provider
    if finish_reason is not None:
        data["finish_reason"] = finish_reason
    return RemoteStepEvent(
        seq=state.next_event_sequence(),
        kind=_event_kind(event, event_type),
        text=_event_text(event, event_type),
        cost_usd=cost_usd,
        tokens=tokens,
        provider=PRIME_EXEC_PROVIDER_NAME,
        model=inference_model or state.model,
        data=data,
    )


def _read_binary_version(binary: str) -> str:
    try:
        result = subprocess.run(
            [binary, "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5.0,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RemoteExecUnavailable(
            f"could not verify prime-agent version: {type(exc).__name__}"
        ) from exc
    if result.returncode != 0:
        raise RemoteExecUnavailable(f"prime-agent --version exited with status {result.returncode}")
    return result.stdout.strip()


class PrimeExecProvider:
    """Prime Agent v0.7.0 JSONL-RPC implementation of ``RemoteExecProvider``.

    Construction is side-effect free.  ``probe`` and ``provision`` both enforce
    the dedicated default-off gate, so injecting an instance into the generic
    runner factory cannot bypass ``ANTIEK_PRIME_EXEC_ENABLED``.

    ``subprocess_env`` is deliberately additive to a small non-secret base env;
    the provider never forwards ``os.environ`` wholesale.  A caller that needs
    one model credential must inject exactly that credential here and must
    supply the external process/container isolation Prime Agent itself lacks.
    """

    def __init__(
        self,
        *,
        binary: str | os.PathLike[str] | None = None,
        provider: str | None = None,
        model: str | None = None,
        session_root: str | os.PathLike[str] | None = None,
        subprocess_env: Mapping[str, str] | None = None,
        process_factory: _ProcessFactory | None = None,
        binary_resolver: _BinaryResolver = shutil.which,
        version_resolver: _VersionResolver = _read_binary_version,
        shutdown_timeout_s: float = 5.0,
        max_record_bytes: int = DEFAULT_MAX_RECORD_BYTES,
    ) -> None:
        self._binary = os.fspath(binary) if binary is not None else None
        self._provider = provider
        self._model = model
        self._session_root = (
            Path(session_root).expanduser()
            if session_root is not None
            else Path.home() / ".antiek" / "prime_sessions"
        )
        self._subprocess_env = dict(subprocess_env or {})
        self._process_factory = process_factory
        self._binary_resolver = binary_resolver
        self._version_resolver = version_resolver
        self._shutdown_timeout_s = shutdown_timeout_s
        if max_record_bytes < 1:
            raise ValueError("max_record_bytes must be positive")
        self._max_record_bytes = max_record_bytes

    @property
    def name(self) -> str:
        return PRIME_EXEC_PROVIDER_NAME

    def _resolve_binary(self) -> str:
        candidate = self._binary or os.environ.get(
            PRIME_AGENT_BINARY_ENV, DEFAULT_PRIME_AGENT_BINARY
        )
        resolved = self._binary_resolver(candidate)
        if resolved is None:
            raise RemoteExecUnavailable(
                f"{candidate!r} is not executable. Install the pinned prime-agent "
                f"binary or set {PRIME_AGENT_BINARY_ENV}; no network lookup is attempted."
            )
        return resolved

    def _resolve_and_validate_binary(self) -> str:
        binary = self._resolve_binary()
        output = self._version_resolver(binary)
        version = output.split()[-1].removeprefix("v") if output.split() else ""
        if version != PINNED_PRIME_AGENT_VERSION:
            raise RemoteExecUnavailable(
                "prime-agent version mismatch: "
                f"required {PINNED_PRIME_AGENT_VERSION}, got {version or 'unknown'}"
            )
        return binary

    def probe(self) -> None:
        """Validate the gate, executable, and pinned RPC version without network."""

        _require_enabled()
        self._resolve_and_validate_binary()

    def _build_env(self) -> dict[str, str]:
        env = {key: os.environ[key] for key in _SAFE_ENV_KEYS if key in os.environ}
        kernel_python = os.environ.get("PRIME_AGENT_KERNEL_PYTHON")
        if kernel_python:
            env["PRIME_AGENT_KERNEL_PYTHON"] = kernel_python
        env.update(self._subprocess_env)
        env["ANTIEK_PRIME_EXEC_SCOPE"] = "research_fanout"
        return env

    async def _spawn(
        self,
        binary: str,
        session_dir: Path,
        provider: str,
        model: str,
    ) -> asyncio.subprocess.Process:
        argv = [binary, "--mode", "rpc", "--session-dir", str(session_dir)]
        if provider:
            argv.extend(("--provider", provider))
        if model:
            argv.extend(("--model", model))
        kwargs: dict[str, Any] = {
            "stdin": asyncio.subprocess.PIPE,
            "stdout": asyncio.subprocess.PIPE,
            "stderr": asyncio.subprocess.DEVNULL,
            "cwd": str(session_dir),
            "env": self._build_env(),
            "limit": self._max_record_bytes + 1,
        }
        if self._process_factory is not None:
            return await self._process_factory(*argv, **kwargs)
        return await asyncio.create_subprocess_exec(*argv, **kwargs)

    async def provision(self, plan: Any) -> Sandbox:
        _require_enabled()
        binary = self._resolve_and_validate_binary()
        investigation_id = getattr(plan, "investigation_id", "unknown")
        if not isinstance(investigation_id, str) or not investigation_id:
            investigation_id = "unknown"
        provider = self._provider or os.environ.get(PRIME_AGENT_PROVIDER_ENV, "")
        model = self._model or os.environ.get(PRIME_AGENT_MODEL_ENV, "")
        session_dir: Path | None = None
        try:
            self._session_root.mkdir(parents=True, exist_ok=True)
            session_dir = Path(tempfile.mkdtemp(prefix="prime-exec-", dir=str(self._session_root)))
            process = await self._spawn(binary, session_dir, provider, model)
        except asyncio.CancelledError:
            if session_dir is not None:
                shutil.rmtree(session_dir, ignore_errors=True)
            raise
        except Exception as exc:
            if session_dir is not None:
                shutil.rmtree(session_dir, ignore_errors=True)
            raise RemoteExecProvisionError(
                f"prime-agent RPC spawn failed for {investigation_id}: {type(exc).__name__}: {exc}"
            ) from exc
        if process.stdin is None or process.stdout is None:
            await self._stop_process(process)
            shutil.rmtree(session_dir, ignore_errors=True)
            raise RemoteExecProvisionError("prime-agent RPC process has no stdin/stdout pipes")
        state = _SessionState(
            process=process,
            session_dir=session_dir,
            provider=provider,
            model=model,
        )
        return Sandbox(
            sandbox_id=f"prime-agent:{process.pid}",
            investigation_id=investigation_id,
            meta={"session_dir": str(session_dir), _STATE_KEY: state},
        )

    @staticmethod
    def _state(sandbox: Sandbox) -> _SessionState:
        state = sandbox.meta.get(_STATE_KEY)
        if not isinstance(state, _SessionState):
            raise RemoteExecRuntimeError(
                f"sandbox {sandbox.sandbox_id} has no Prime RPC session state"
            )
        return state

    async def _send(self, state: _SessionState, command: Mapping[str, object]) -> None:
        writer = state.process.stdin
        if writer is None:
            raise RemoteExecRuntimeError("prime-agent RPC stdin is unavailable")
        payload = json.dumps(dict(command), ensure_ascii=False, separators=(",", ":"))
        try:
            async with state.write_lock:
                writer.write(payload.encode("utf-8") + b"\n")
                await writer.drain()
        except (BrokenPipeError, ConnectionError, OSError) as exc:
            raise RemoteExecRuntimeError(
                f"prime-agent RPC command write failed: {type(exc).__name__}: {exc}"
            ) from exc

    @staticmethod
    def _prompt_for_plan(plan: Any) -> str:
        metadata = getattr(plan, "metadata", None)
        if isinstance(metadata, dict):
            override = metadata.get("prime_prompt")
            if isinstance(override, str) and override.strip():
                question = override.strip()
            else:
                question = getattr(plan, "sub_question", "")
        else:
            question = getattr(plan, "sub_question", "")
        if not isinstance(question, str) or not question.strip():
            raise RemoteExecRuntimeError("Prime research plan has no non-empty prompt")
        return f"{_RESEARCH_ONLY_PREAMBLE}\n\nResearch question:\n{question.strip()}"

    async def _crash_error(self, state: _SessionState) -> RemoteExecRuntimeError:
        try:
            return_code = await asyncio.wait_for(
                state.process.wait(), timeout=self._shutdown_timeout_s
            )
        except TimeoutError:
            return RemoteExecRuntimeError(
                "prime-agent RPC closed stdout before agent_end but the process remained running"
            )
        return RemoteExecRuntimeError(
            f"prime-agent RPC exited before agent_end (exit {return_code})"
        )

    async def run(self, sandbox: Sandbox, plan: Any) -> AsyncIterator[RemoteStepEvent]:
        state = self._state(sandbox)
        if state.run_started:
            raise RemoteExecRuntimeError("Prime RPC sandbox may run only one research plan")
        state.run_started = True
        await self._send(
            state,
            {
                "id": state.next_request_id(),
                "type": "prompt",
                "message": self._prompt_for_plan(plan),
            },
        )
        reader = state.process.stdout
        if reader is None:
            raise RemoteExecRuntimeError("prime-agent RPC stdout is unavailable")

        while True:
            try:
                line = await reader.readline()
            except (ValueError, asyncio.LimitOverrunError) as exc:
                raise RemoteExecRuntimeError(
                    "prime-agent RPC record exceeded the configured JSONL limit"
                ) from exc
            if line == b"":
                state.run_finished = True
                raise await self._crash_error(state)
            if len(line) > self._max_record_bytes:
                raise RemoteExecRuntimeError(
                    "prime-agent RPC record exceeded the configured JSONL limit"
                )
            event = _decode_event(line)
            if event is None:
                continue
            response_error = _response_error(event)
            if response_error is not None:
                if response_error:
                    command = event.get("command")
                    if command == "prompt":
                        state.run_finished = True
                        raise RemoteExecRuntimeError(
                            f"prime-agent rejected prompt command: {response_error}"
                        )
                    yield RemoteStepEvent(
                        seq=state.next_event_sequence(),
                        kind="error",
                        text=f"prime-agent rejected {command or 'RPC'} command: {response_error}",
                        provider=PRIME_EXEC_PROVIDER_NAME,
                        model=state.model,
                        data={"prime_event_type": "response"},
                    )
                continue

            event_type = cast(str, event["type"])
            update = _as_dict(event.get("assistantMessageEvent")) or {}
            if event_type == "message_update" and update.get("type") == "error":
                reason = update.get("reason")
                expected_abort = reason == "aborted" and (
                    state.stop_requested or state.pause_requested
                )
                if expected_abort:
                    continue
                state.failure_reason = reason if isinstance(reason, str) else "assistant error"
            mapped = _map_event(state, event)
            yield mapped
            if event_type == "turn_end":
                finish_reason = mapped.data.get("finish_reason")
                if finish_reason in {"error", "aborted"} and not (
                    finish_reason == "aborted" and (state.stop_requested or state.pause_requested)
                ):
                    state.failure_reason = str(finish_reason)
                if state.failure_reason is not None and not state.stop_requested:
                    state.run_finished = True
                    raise RemoteExecRuntimeError(f"prime-agent turn failed: {state.failure_reason}")
            if event_type == "agent_end":
                if state.stop_requested:
                    state.run_finished = True
                    return
                if state.pause_requested:
                    state.paused = True
                    await state.resume_event.wait()
                    if state.torn_down:
                        return
                    state.resume_event.clear()
                    state.pause_requested = False
                    state.paused = False
                    state.failure_reason = None
                    if state.stop_requested:
                        state.run_finished = True
                        return
                    await self._send(
                        state,
                        {
                            "id": state.next_request_id(),
                            "type": "follow_up",
                            "message": "Resume the paused Antiek research from the current state.",
                        },
                    )
                    continue
                state.run_finished = True
                if state.failure_reason is not None and not state.stop_requested:
                    raise RemoteExecRuntimeError(f"prime-agent run failed: {state.failure_reason}")
                return

    @staticmethod
    def _steer_message(command: RemoteCommand) -> tuple[str, str]:
        payload = command.payload
        if command.signal is RemoteSignal.REDIRECT:
            question = payload.get("sub_question")
            text = (
                question
                if isinstance(question, str) and question.strip()
                else "Redirect the research."
            )
            return "steer", text
        if command.signal is RemoteSignal.DEEPEN:
            follow_up = payload.get("follow_up")
            text = (
                follow_up
                if isinstance(follow_up, str) and follow_up.strip()
                else "Deepen the current research."
            )
            return "follow_up", text
        messages = {
            RemoteSignal.PAUSE: "Pause after the current tool call and await further direction.",
            RemoteSignal.RESUME: "Resume the research from the current state.",
            RemoteSignal.STOP: "Stop the research after the current tool call and finish now.",
        }
        return "steer", messages[command.signal]

    async def steer(self, sandbox: Sandbox, command: RemoteCommand) -> None:
        state = self._state(sandbox)
        if state.run_finished or state.torn_down:
            return
        if command.signal is RemoteSignal.PAUSE:
            if state.pause_requested or state.paused:
                return
            state.pause_requested = True
            state.resume_event.clear()
            await self._send(
                state,
                {"id": state.next_request_id(), "type": "abort"},
            )
            return
        if command.signal is RemoteSignal.RESUME:
            if state.pause_requested or state.paused:
                state.resume_event.set()
            return
        if command.signal is RemoteSignal.STOP:
            state.stop_requested = True
            state.resume_event.set()
            await self._send(
                state,
                {"id": state.next_request_id(), "type": "abort"},
            )
            return
        command_type, message = self._steer_message(command)
        await self._send(
            state,
            {
                "id": state.next_request_id(),
                "type": command_type,
                "message": message,
            },
        )

    async def _stop_process(self, process: asyncio.subprocess.Process) -> None:
        if process.stdin is not None:
            process.stdin.close()
        if process.returncode is not None:
            await process.wait()
            return
        try:
            process.terminate()
        except ProcessLookupError:
            await process.wait()
            return
        try:
            await asyncio.wait_for(process.wait(), timeout=self._shutdown_timeout_s)
        except TimeoutError:
            process.kill()
            await process.wait()

    async def teardown(self, sandbox: Sandbox) -> None:
        state = sandbox.meta.get(_STATE_KEY)
        if not isinstance(state, _SessionState) or state.torn_down:
            return
        state.torn_down = True
        state.run_finished = True
        state.resume_event.set()
        try:
            await self._stop_process(state.process)
        finally:
            shutil.rmtree(state.session_dir, ignore_errors=True)
            sandbox.meta.pop(_STATE_KEY, None)


__all__ = [
    "PrimeExecProvider",
    "PRIME_EXEC_PROVIDER_NAME",
    "PRIME_EXEC_ENABLE_ENV",
    "PRIME_AGENT_BINARY_ENV",
    "PRIME_AGENT_PROVIDER_ENV",
    "PRIME_AGENT_MODEL_ENV",
    "prime_exec_enabled",
]
