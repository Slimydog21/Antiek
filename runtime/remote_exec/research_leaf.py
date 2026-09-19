"""Strict stdin/stdout protocol used by an immutable Daytona leaf snapshot.

The module validates transport and cooperative controls.  A snapshot must set
``ANTIEK_REMOTE_LEAF_WORKER=package.module:callable`` to bind real research
logic; this repository intentionally does not select a production worker yet.
"""

from __future__ import annotations

import asyncio
import importlib
import inspect
import json
import sys
from collections.abc import AsyncIterator, Callable
from typing import Any, cast

MAX_RECORD_BYTES = 1_048_576
ALLOWED_SIGNALS = frozenset({"pause", "resume", "stop", "redirect", "deepen"})
APPROVED_WORKER = "runtime.remote_exec.approved_leaf_worker:run"


class LeafProtocolError(ValueError):
    pass


def decode_line(line: bytes) -> dict[str, Any]:
    if not line.endswith(b"\n") or len(line) > MAX_RECORD_BYTES:
        raise LeafProtocolError("record must be bounded and LF-terminated")
    try:
        def pairs(rows: list[tuple[str, Any]]) -> dict[str, Any]:
            result: dict[str, Any] = {}
            for key, item in rows:
                if key in result:
                    raise LeafProtocolError("duplicate JSON key")
                result[key] = item
            return result
        value = json.loads(
            line[:-1], object_pairs_hook=pairs,
            parse_constant=lambda _value: (_ for _ in ()).throw(LeafProtocolError("invalid constant")),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LeafProtocolError("record must be valid JSON") from exc
    if not isinstance(value, dict) or value.get("protocol") != 1:
        raise LeafProtocolError("record must be a protocol-v1 object")
    return value


def encode_event(event: dict[str, Any], seq: int) -> bytes:
    allowed = {"kind", "text", "cost_usd", "tokens", "provider", "model", "data"}
    if not set(event).issubset(allowed) or {"type", "seq"} & set(event):
        raise LeafProtocolError("worker event contains reserved/unknown keys")
    kind = event.get("kind")
    if kind not in {"plan", "step", "cost", "note", "question", "status", "error", "done"}:
        raise LeafProtocolError("worker emitted unknown event kind")
    record = {"type": "event", "seq": seq, **event}
    raw = json.dumps(record, separators=(",", ":"), allow_nan=False).encode() + b"\n"
    if len(raw) > MAX_RECORD_BYTES:
        raise LeafProtocolError("worker event exceeded record limit")
    return raw


def _load_worker(spec: str) -> Callable[..., AsyncIterator[dict[str, Any]]]:
    if ":" not in spec:
        raise LeafProtocolError("worker must use module:callable syntax")
    module_name, name = spec.split(":", 1)
    worker = getattr(importlib.import_module(module_name), name)
    if not callable(worker):
        raise LeafProtocolError("configured worker is not callable")
    return cast(Callable[..., AsyncIterator[dict[str, Any]]], worker)


async def serve(
    reader: asyncio.StreamReader,
    write: Callable[[bytes], Any],
    worker: Callable[..., AsyncIterator[dict[str, Any]]],
) -> None:
    start = decode_line(await reader.readline())
    if (
        set(start) != {"type", "protocol", "worker", "plan"}
        or start.get("type") != "start"
        or start.get("worker") != APPROVED_WORKER
        or not isinstance(start.get("plan"), dict)
    ):
        raise LeafProtocolError("first record must be start with a plan")
    controls: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=100)

    async def read_controls() -> None:
        while line := await reader.readline():
            value = decode_line(line)
            if (
                set(value) != {"type", "protocol", "signal", "payload"}
                or value.get("type") != "control"
                or value.get("signal") not in ALLOWED_SIGNALS
            ):
                raise LeafProtocolError("invalid control record")
            payload = value.get("payload", {})
            if not isinstance(payload, dict):
                raise LeafProtocolError("control payload must be an object")
            await controls.put(value)

    control_task = asyncio.create_task(read_controls())
    try:
        stream = worker(start["plan"], controls)
        if not inspect.isasyncgen(stream):
            raise LeafProtocolError("worker must return an async generator")
        worker_task = asyncio.create_task(_drain_worker(stream, write))
        done, _ = await asyncio.wait(
            {worker_task, control_task}, return_when=asyncio.FIRST_COMPLETED
        )
        if control_task in done:
            exc = control_task.exception()
            if exc is not None:
                worker_task.cancel()
                await asyncio.gather(worker_task, return_exceptions=True)
                raise exc
        await worker_task
    finally:
        control_task.cancel()
        await asyncio.gather(control_task, return_exceptions=True)


async def _stdio_main() -> int:
    worker = _load_worker(APPROVED_WORKER)
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    loop = asyncio.get_running_loop()
    await loop.connect_read_pipe(lambda: protocol, sys.stdin.buffer)

    def write(data: bytes) -> None:
        sys.stdout.buffer.write(data)
        sys.stdout.buffer.flush()

    await serve(reader, write, worker)
    return 0


async def _drain_worker(
    stream: AsyncIterator[dict[str, Any]], write: Callable[[bytes], Any]
) -> None:
    seq = 0
    async for event in stream:
        if not isinstance(event, dict):
            raise LeafProtocolError("worker event must be an object")
        seq += 1
        result = write(encode_event(event, seq))
        if inspect.isawaitable(result):
            await result


def main() -> int:
    try:
        return asyncio.run(_stdio_main())
    except Exception as exc:
        print(f"leaf protocol failed: {type(exc).__name__}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
