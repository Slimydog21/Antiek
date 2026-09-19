"""Daytona transport for the research-leaf JSONL protocol.

This adapter is deliberately transport-only.  It requires an immutable Daytona
snapshot id and starts the leaf protocol already installed in that snapshot.
It does not ship source, credentials, or an unpinned ``latest`` image at run
time.  The actual browse worker remains a separate, not-yet-wired concern.
"""

from __future__ import annotations

import asyncio
import importlib.metadata
import json
import math
import os
import re
from collections.abc import AsyncIterator, Callable
from dataclasses import asdict, is_dataclass
from typing import Any, cast

from .provider import (
    RemoteCommand,
    RemoteExecProvisionError,
    RemoteExecRuntimeError,
    RemoteExecUnavailable,
    RemoteStepEvent,
    Sandbox,
)

DAYTONA_PROVIDER_NAME = "daytona"
SNAPSHOT_ENV = "ANTIEK_DAYTONA_SNAPSHOT_ID"
SNAPSHOT_DIGEST_ENV = "ANTIEK_DAYTONA_SNAPSHOT_DIGEST"
DEFAULT_ENTRYPOINT = "python -m runtime.remote_exec.research_leaf"
DEFAULT_CREATE_TIMEOUT_S = 60.0
DEFAULT_MAX_RECORD_BYTES = 1_048_576
DEFAULT_MAX_EVENTS = 10_000
DEFAULT_QUEUE_SIZE = 128
DEFAULT_IDLE_TIMEOUT_S = 30.0
DEFAULT_TOTAL_TIMEOUT_S = 900.0
_SNAPSHOT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$")
_APPROVED_WORKER = "runtime.remote_exec.approved_leaf_worker:run"
_EVENT_KEYS = frozenset(
    {"type", "seq", "kind", "text", "cost_usd", "tokens", "provider", "model", "data"}
)
_ALLOWED_KINDS = frozenset(
    {"plan", "step", "cost", "note", "question", "status", "error", "done"}
)


def _required_env() -> tuple[str, str]:
    if not os.environ.get("DAYTONA_API_KEY"):
        raise RemoteExecUnavailable("DAYTONA_API_KEY is required for Daytona remote exec")
    snapshot = os.environ.get(SNAPSHOT_ENV, "").strip()
    if not _SNAPSHOT_RE.fullmatch(snapshot):
        raise RemoteExecUnavailable(
            f"{SNAPSHOT_ENV} must be an explicit conservative immutable snapshot id"
        )
    return os.environ["DAYTONA_API_KEY"], snapshot


async def _await_cleanup(task: asyncio.Task[Any], *, timeout_s: float = 65.0) -> Any:
    """Finish cleanup despite repeated cancellation, within a hard deadline."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_s
    while True:
        try:
            return await asyncio.wait_for(
                asyncio.shield(task), timeout=max(0.001, deadline - loop.time())
            )
        except asyncio.CancelledError:
            current = asyncio.current_task()
            if current is not None:
                current.uncancel()
            if loop.time() >= deadline:
                raise RemoteExecProvisionError(
                    "Daytona cleanup exceeded deadline"
                ) from None
        except TimeoutError as exc:
            raise RemoteExecProvisionError("Daytona cleanup exceeded deadline") from exc


def _load_sdk() -> tuple[type[Any], type[Any], type[Any]]:
    try:
        from daytona import (  # type: ignore[import-not-found]
            CreateSandboxFromSnapshotParams,
            Daytona,
            SessionExecuteRequest,
        )
    except ImportError as exc:
        raise RemoteExecUnavailable(
            "Daytona SDK is not installed; install the remote_exec extra"
        ) from exc
    try:
        version = importlib.metadata.version("daytona")
    except importlib.metadata.PackageNotFoundError as exc:
        raise RemoteExecUnavailable("Daytona SDK distribution metadata is missing") from exc
    if not version.startswith("0.204."):
        raise RemoteExecUnavailable(
            f"Daytona SDK 0.204.x is required by the verified adapter contract (found {version})"
        )
    for owner, capability in (
        (Daytona, "create"),
        (Daytona, "delete"),
        (CreateSandboxFromSnapshotParams, "model_validate"),
        (SessionExecuteRequest, "model_validate"),
    ):
        if not callable(getattr(owner, capability, None)):
            raise RemoteExecUnavailable(
                f"Daytona SDK lacks required capability {owner.__name__}.{capability}"
            )
    return Daytona, CreateSandboxFromSnapshotParams, SessionExecuteRequest


def _plan_payload(plan: Any) -> dict[str, Any]:
    raw = asdict(plan) if is_dataclass(plan) else dict(vars(plan))  # type: ignore[arg-type]
    # The wire contract is intentionally narrow.  Unknown plan fields, paths,
    # objects, and caller environment never cross into the sandbox.
    budget = raw.get("budget") or {}
    return {
        "investigation_id": str(raw.get("investigation_id", "")),
        "sub_question": str(raw.get("sub_question", "")),
        "parent_investigation_id": raw.get("parent_investigation_id"),
        "budget": {
            "cost_usd": float(budget.get("cost_usd", 0.0)),
            "max_steps": int(budget.get("max_steps", 0)),
        },
    }


def _finite_nonnegative(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise RemoteExecRuntimeError(f"Daytona event {name} must be numeric")
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise RemoteExecRuntimeError(f"Daytona event {name} must be finite and non-negative")
    return result


def _decode_event(record: bytes, *, previous_seq: int) -> RemoteStepEvent:
    if not record or len(record) > DEFAULT_MAX_RECORD_BYTES:
        raise RemoteExecRuntimeError("Daytona leaf emitted an empty or oversized JSONL record")
    try:
        def pairs(rows: list[tuple[str, Any]]) -> dict[str, Any]:
            result: dict[str, Any] = {}
            for key, item in rows:
                if key in result:
                    raise ValueError(f"duplicate JSON key {key}")
                result[key] = item
            return result
        value = json.loads(
            record,
            parse_constant=lambda token: (_ for _ in ()).throw(
                ValueError(f"non-standard JSON constant {token}")
            ),
            object_pairs_hook=pairs,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise RemoteExecRuntimeError(f"Daytona leaf emitted invalid JSONL: {exc}") from exc
    if not isinstance(value, dict) or value.get("type") != "event":
        raise RemoteExecRuntimeError("Daytona leaf record must be an event object")
    if not set(value).issubset(_EVENT_KEYS):
        raise RemoteExecRuntimeError("Daytona leaf event contains reserved/unknown keys")
    seq = value.get("seq")
    if isinstance(seq, bool) or not isinstance(seq, int) or seq != previous_seq + 1:
        raise RemoteExecRuntimeError("Daytona leaf event sequence must be contiguous from 1")
    kind = value.get("kind")
    if kind not in _ALLOWED_KINDS:
        raise RemoteExecRuntimeError("Daytona leaf event kind is outside the closed vocabulary")
    tokens = value.get("tokens", 0)
    if isinstance(tokens, bool) or not isinstance(tokens, int) or tokens < 0:
        raise RemoteExecRuntimeError("Daytona leaf event tokens must be a non-negative integer")
    data = value.get("data", {})
    if not isinstance(data, dict):
        raise RemoteExecRuntimeError("Daytona leaf event data must be an object")
    encoded_data = json.dumps(data, separators=(",", ":"), allow_nan=False).encode()
    if len(encoded_data) > 262_144:
        raise RemoteExecRuntimeError("Daytona leaf event data exceeded structured-data limit")
    for key in ("text", "provider", "model"):
        if not isinstance(value.get(key, ""), str):
            raise RemoteExecRuntimeError(f"Daytona leaf event {key} must be a string")
    return RemoteStepEvent(
        seq=seq,
        kind=kind,
        text=value.get("text", ""),
        cost_usd=_finite_nonnegative(value.get("cost_usd", 0.0), "cost_usd"),
        tokens=tokens,
        provider=value.get("provider", ""),
        model=value.get("model", ""),
        data=data,
    )


def _is_not_found(exc: BaseException) -> bool:
    return getattr(exc, "status_code", None) == 404 or getattr(exc, "status", None) == 404


class DaytonaProvider:
    """Current Daytona SDK implementation of ``RemoteExecProvider``."""

    def __init__(
        self,
        *,
        client_factory: Callable[[], Any] | None = None,
        snapshot_id: str | None = None,
        entrypoint: str = DEFAULT_ENTRYPOINT,
        params_factory: Callable[..., Any] | None = None,
        request_factory: Callable[..., Any] | None = None,
        max_events: int = DEFAULT_MAX_EVENTS,
        idle_timeout_s: float = DEFAULT_IDLE_TIMEOUT_S,
        total_timeout_s: float = DEFAULT_TOTAL_TIMEOUT_S,
        snapshot_verifier: Callable[[str, str], bool] | None = None,
        approved_worker_ready: bool = False,
    ):
        self._client_factory = client_factory
        self._snapshot_id = snapshot_id
        self._entrypoint = entrypoint
        self._params_factory = params_factory
        self._request_factory = request_factory
        self._max_events = max_events
        self._idle_timeout_s = idle_timeout_s
        self._total_timeout_s = total_timeout_s
        self._snapshot_verifier = snapshot_verifier
        self._approved_worker_ready = approved_worker_ready
        self._teardown_locks: dict[str, asyncio.Lock] = {}
        self._client: Any = None

    @property
    def name(self) -> str:
        return DAYTONA_PROVIDER_NAME

    def probe(self) -> None:
        _, snapshot = _required_env()
        _load_sdk()
        digest = os.environ.get(SNAPSHOT_DIGEST_ENV, "").strip()
        if not self._approved_worker_ready:
            raise RemoteExecUnavailable("approved Daytona research worker is not implemented")
        if self._snapshot_verifier is None or not digest:
            raise RemoteExecUnavailable(
                "authoritative Daytona snapshot digest verification is unavailable"
            )
        try:
            verified = self._snapshot_verifier(snapshot, digest)
        except Exception as exc:
            raise RemoteExecUnavailable("Daytona snapshot attestation failed") from exc
        if not verified:
            raise RemoteExecUnavailable("Daytona snapshot digest did not match attestation")

    def _resolve(self) -> tuple[Any, str, Callable[..., Any], Callable[..., Any]]:
        if self._client_factory is None:
            _, env_snapshot = _required_env()
            Daytona, sdk_params, sdk_request = _load_sdk()
            params_factory: Callable[..., Any] = sdk_params
            request_factory: Callable[..., Any] = sdk_request
            if self._client is None:
                # Current SDK reads DAYTONA_API_KEY/API_URL/TARGET itself.  Do
                # not duplicate or place the credential in sandbox metadata.
                self._client = Daytona()
        else:
            env_snapshot = ""
            params_factory = cast(
                Callable[..., Any], self._params_factory or (lambda **kw: kw)
            )
            request_factory = cast(
                Callable[..., Any], self._request_factory or (lambda **kw: kw)
            )
            if self._client is None:
                self._client = self._client_factory()
        snapshot = (self._snapshot_id or env_snapshot).strip()
        if not _SNAPSHOT_RE.fullmatch(snapshot):
            raise RemoteExecUnavailable(
                "an explicit conservative immutable Daytona snapshot id is required"
            )
        return self._client, snapshot, params_factory, request_factory

    async def provision(self, plan: Any) -> Sandbox:
        client, snapshot, Params, _ = self._resolve()
        iid = str(getattr(plan, "investigation_id", ""))
        params = Params(
            snapshot=snapshot,
            language="python",
            labels={"antiek-purpose": "research-leaf", "antiek-investigation": iid},
            public=False,
            auto_delete_interval=10,
        )
        create_task = asyncio.create_task(asyncio.to_thread(
            client.create, params, timeout=DEFAULT_CREATE_TIMEOUT_S
        ))
        try:
            workspace = await asyncio.shield(create_task)
        except asyncio.CancelledError:
            # A thread-backed create cannot be cancelled. Wait for it to settle,
            # then synchronously reclaim anything it allocated before propagating.
            workspace = await _await_cleanup(create_task)
            cleanup = asyncio.create_task(
                asyncio.to_thread(client.delete, workspace, timeout=60, wait=True)
            )
            try:
                await _await_cleanup(cleanup)
            except Exception as exc:
                if not _is_not_found(exc):
                    raise RemoteExecProvisionError(
                        f"cancelled Daytona provision cleanup failed: {type(exc).__name__}"
                    ) from exc
            raise
        except Exception as exc:
            raise RemoteExecProvisionError(
                f"Daytona sandbox provision failed for {iid}: {type(exc).__name__}"
            ) from exc
        return Sandbox(
            sandbox_id=str(workspace.id),
            investigation_id=iid,
            meta={"workspace": workspace},
        )

    async def run(self, sandbox: Sandbox, plan: Any) -> AsyncIterator[RemoteStepEvent]:
        workspace = sandbox.meta.get("workspace")
        if workspace is None:
            raise RemoteExecRuntimeError("Daytona sandbox handle is missing")
        _, _, _, Request = self._resolve()
        process = workspace.process
        session_id = f"antiek-{sandbox.investigation_id}"[:64]
        queue: asyncio.Queue[tuple[str, str] | BaseException | None] = asyncio.Queue(
            maxsize=DEFAULT_QUEUE_SIZE
        )
        buffer = bytearray()
        previous_seq = 0
        emitted = 0
        command_id: str | None = None
        collector: asyncio.Task[None] | None = None

        async def on_stdout(chunk: str) -> None:
            await queue.put(("stdout", chunk))

        async def on_stderr(chunk: str) -> None:
            await queue.put(("stderr", chunk))

        async def collect_logs() -> None:
            assert command_id is not None
            try:
                await process.get_session_command_logs_async(
                    session_id, command_id, on_stdout, on_stderr
                )
            except Exception as exc:
                await queue.put(exc)
            finally:
                await queue.put(None)

        try:
            await asyncio.to_thread(process.create_session, session_id)
            response = await asyncio.to_thread(
                process.execute_session_command,
                session_id,
                Request(command=self._entrypoint, run_async=True, suppress_input_echo=True),
            )
            command_id = str(response.cmd_id)
            sandbox.meta.update({"session_id": session_id, "command_id": command_id})
            start_line = json.dumps(
                {"type": "start", "protocol": 1, "worker": _APPROVED_WORKER,
                 "plan": _plan_payload(plan)},
                separators=(",", ":"),
                allow_nan=False,
            ) + "\n"
            await asyncio.to_thread(
                process.send_session_command_input, session_id, command_id, start_line
            )
            collector = asyncio.create_task(collect_logs())
            deadline = asyncio.get_running_loop().time() + self._total_timeout_s
            saw_done = False
            while True:
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    raise RemoteExecRuntimeError("Daytona leaf exceeded total deadline")
                try:
                    item = await asyncio.wait_for(
                        queue.get(), timeout=min(self._idle_timeout_s, remaining)
                    )
                except TimeoutError as exc:
                    raise RemoteExecRuntimeError("Daytona leaf exceeded idle deadline") from exc
                if item is None:
                    break
                if isinstance(item, BaseException):
                    raise RemoteExecRuntimeError(
                        f"Daytona log stream failed: {type(item).__name__}"
                    ) from item
                channel, chunk = item
                if channel == "stderr":
                    if chunk.strip():
                        raise RemoteExecRuntimeError("Daytona leaf wrote to stderr")
                    continue
                buffer.extend(chunk.encode("utf-8"))
                if len(buffer) > DEFAULT_MAX_RECORD_BYTES and b"\n" not in buffer:
                    raise RemoteExecRuntimeError("Daytona leaf JSONL record exceeded limit")
                while b"\n" in buffer:
                    raw, _, remainder = buffer.partition(b"\n")
                    buffer[:] = remainder
                    if raw.endswith(b"\r"):
                        raw = raw[:-1]
                    event = _decode_event(bytes(raw), previous_seq=previous_seq)
                    if saw_done:
                        raise RemoteExecRuntimeError("Daytona leaf emitted after terminal done")
                    previous_seq = event.seq
                    emitted += 1
                    if emitted > self._max_events:
                        raise RemoteExecRuntimeError("Daytona leaf exceeded event limit")
                    saw_done = event.kind == "done"
                    yield event
            await collector
            if buffer:
                raise RemoteExecRuntimeError("Daytona leaf closed with unterminated JSONL")
            if not emitted or not saw_done:
                raise RemoteExecRuntimeError("Daytona leaf must emit exactly terminal done")
            status = await asyncio.to_thread(process.get_session_command, session_id, command_id)
            if status.exit_code != 0:
                raise RemoteExecRuntimeError(
                    f"Daytona leaf exited nonzero ({status.exit_code})"
                )
        except asyncio.CancelledError:
            cleanup = asyncio.create_task(self.teardown(sandbox))
            await _await_cleanup(cleanup)
            raise
        except RemoteExecRuntimeError:
            raise
        except Exception as exc:
            raise RemoteExecRuntimeError(
                f"Daytona leaf runtime failed: {type(exc).__name__}"
            ) from exc
        finally:
            if collector is not None and not collector.done():
                collector.cancel()
                await asyncio.gather(collector, return_exceptions=True)

    async def steer(self, sandbox: Sandbox, command: RemoteCommand) -> None:
        workspace = sandbox.meta.get("workspace")
        session_id = sandbox.meta.get("session_id")
        command_id = sandbox.meta.get("command_id")
        if workspace is None or not session_id or not command_id:
            return
        line = json.dumps(
            {"type": "control", "protocol": 1, "signal": command.signal.value,
             "payload": command.payload},
            separators=(",", ":"), allow_nan=False,
        ) + "\n"
        if len(line.encode()) > DEFAULT_MAX_RECORD_BYTES:
            raise RemoteExecRuntimeError("Daytona control record exceeded limit")
        try:
            await asyncio.to_thread(
                workspace.process.send_session_command_input,
                session_id,
                command_id,
                line,
            )
        except Exception as exc:
            raise RemoteExecRuntimeError(
                f"Daytona steer failed: {type(exc).__name__}"
            ) from exc

    async def teardown(self, sandbox: Sandbox) -> None:
        workspace = sandbox.meta.get("workspace")
        if workspace is None:
            return
        lock = self._teardown_locks.setdefault(sandbox.sandbox_id, asyncio.Lock())
        async with lock:
            workspace = sandbox.meta.get("workspace")
            if workspace is None:
                return
            client, _, _, _ = self._resolve()
            last: Exception | None = None
            for attempt in range(3):
                try:
                    await asyncio.wait_for(
                        asyncio.to_thread(client.delete, workspace, timeout=20, wait=True),
                        timeout=25,
                    )
                    last = None
                    break
                except Exception as exc:
                    if _is_not_found(exc):
                        last = None
                        break
                    last = exc
                    if attempt < 2:
                        await asyncio.sleep(0.05 * (2 ** attempt))
            if last is not None:
                raise RemoteExecRuntimeError(
                    f"Daytona teardown failed after 3 attempts; orphan cleanup required: "
                    f"{type(last).__name__}"
                ) from last
            sandbox.meta.clear()


__all__ = ["DaytonaProvider", "DAYTONA_PROVIDER_NAME", "SNAPSHOT_ENV",
           "SNAPSHOT_DIGEST_ENV"]
