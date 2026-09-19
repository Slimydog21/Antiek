from __future__ import annotations

import asyncio
import json
import subprocess
import sys

import pytest

from runtime.remote_exec.research_leaf import LeafProtocolError, decode_line, encode_event, serve


def test_decode_requires_lf_and_protocol() -> None:
    with pytest.raises(LeafProtocolError):
        decode_line(b'{}')
    with pytest.raises(LeafProtocolError):
        decode_line(b'{"protocol":2}\n')


@pytest.mark.parametrize("event", [
    {"kind": "done", "type": "forged"},
    {"kind": "done", "seq": 99},
    {"kind": "done", "extra": True},
])
def test_encode_event_rejects_reserved_and_unknown_keys(event) -> None:
    with pytest.raises(LeafProtocolError, match="reserved/unknown"):
        encode_event(event, 1)


@pytest.mark.asyncio
async def test_leaf_worker_emits_contiguous_jsonl_and_receives_control() -> None:
    reader = asyncio.StreamReader()
    reader.feed_data(json.dumps({"type": "start", "protocol": 1,
                                 "worker": "runtime.remote_exec.approved_leaf_worker:run",
                                 "plan": {"x": 1}}).encode() + b"\n")
    reader.feed_data(json.dumps({"type": "control", "protocol": 1, "signal": "stop",
                                 "payload": {}}).encode() + b"\n")
    output: list[bytes] = []

    async def worker(plan, controls):
        assert plan == {"x": 1}
        control = await asyncio.wait_for(controls.get(), timeout=1)
        yield {"kind": "status", "text": control["signal"]}
        yield {"kind": "done"}

    await serve(reader, output.append, worker)
    records = [json.loads(line) for line in output]
    assert [(row["seq"], row["kind"]) for row in records] == [(1, "status"), (2, "done")]
    assert records[0]["text"] == "stop"


@pytest.mark.asyncio
async def test_leaf_rejects_unknown_control() -> None:
    reader = asyncio.StreamReader()
    reader.feed_data(b'{"type":"start","protocol":1,"worker":"runtime.remote_exec.approved_leaf_worker:run","plan":{}}\n')
    reader.feed_data(b'{"type":"control","protocol":1,"signal":"shell","payload":{}}\n')

    async def worker(plan, controls):
        await controls.get()
        yield {"kind": "done"}

    with pytest.raises((LeafProtocolError, asyncio.TimeoutError)):
        await asyncio.wait_for(serve(reader, lambda _: None, worker), timeout=0.2)


def test_leaf_subprocess_refuses_unbound_worker_without_echoing_plan() -> None:
    secret = "prompt-secret-must-not-echo"
    proc = subprocess.run(
        [sys.executable, "-m", "runtime.remote_exec.research_leaf"],
        input=json.dumps({"type": "start", "protocol": 1,
                          "plan": {"sub_question": secret}}) + "\n",
        text=True,
        capture_output=True,
        timeout=5,
        check=False,
    )
    assert proc.returncode == 2
    assert secret not in proc.stdout + proc.stderr
