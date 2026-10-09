"""Real private child processes exercise the managed RPC completion boundary."""

from __future__ import annotations

import os
import time
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from select import select
from typing import BinaryIO

import pytest

from runtime.prime_agent.installation import verify_prime_agent_installation
from runtime.prime_agent.process import PrimeAgentProcessConfig, spawn_prime_agent_managed


def _config(tmp_path: Path, body: str) -> PrimeAgentProcessConfig:
    binary = tmp_path / "prime-agent"
    binary.write_text(
        "#!/usr/bin/env python3\n"
        "import os, sys\n"
        "if sys.argv[1:] == ['--version']:\n"
        " print('prime-agent 0.9.8'); raise SystemExit\n"
        "if sys.argv[1:] == ['--help']:\n"
        " print('-p --cwd --offline --no-session --no-tools --no-extensions --no-skills "
        "--no-prompt-templates --no-themes --no-context-files --mode rpc'); raise SystemExit\n"
        + body
    )
    binary.chmod(0o700)
    return PrimeAgentProcessConfig(
        installation=verify_prime_agent_installation(binary, environ={"PATH": os.environ["PATH"]}),
        cwd=tmp_path.resolve(),
        timeout_seconds=2,
        max_stdout_bytes=1024,
        max_stderr_bytes=128,
        environ={"PATH": os.environ["PATH"]},
    )


def test_reaped_leader_does_not_hide_late_stderr_overflow(tmp_path: Path) -> None:
    config = _config(
        tmp_path,
        "os.write(1, b'terminal\\n')\n"
        "sys.stdin.buffer.read()\n"
        "os.close(1)\n"
        "os.write(2, b'x' * 129)\n",
    )
    with spawn_prime_agent_managed(config, ("--mode", "rpc")) as managed:
        deadline = time.monotonic() + 2
        assert managed.read_line(max_bytes=64, deadline=deadline) == b"terminal\n"
        managed.close_stdin()
        # Deliberately reap before reading: stdout EOF must not discard queued stderr.
        assert managed.process.wait(timeout=1) == 0
        with pytest.raises(RuntimeError, match="stderr exceeded limit"):
            managed.wait_exit(deadline=deadline)


@pytest.mark.parametrize("size", [0, 128])
def test_terminal_with_bounded_late_stderr_completes(tmp_path: Path, size: int) -> None:
    config = _config(
        tmp_path,
        "os.write(1, b'terminal\\n')\n"
        "sys.stdin.buffer.read()\n"
        "os.close(1)\n"
        f"os.write(2, b'x' * {size})\n",
    )
    with spawn_prime_agent_managed(config, ("--mode", "rpc")) as managed:
        deadline = time.monotonic() + 2
        assert managed.read_line(max_bytes=64, deadline=deadline) == b"terminal\n"
        managed.close_stdin()
        assert managed.wait_exit(deadline=deadline) == 0


def test_complete_lf_record_cannot_bypass_record_limit(tmp_path: Path) -> None:
    config = _config(tmp_path, "os.write(1, b'x' * 64 + b'\\n')\nsys.stdin.buffer.read()\n")
    with (
        spawn_prime_agent_managed(config, ("--mode", "rpc")) as managed,
        pytest.raises(RuntimeError, match="record exceeded limit"),
    ):
        managed.read_line(max_bytes=64, deadline=time.monotonic() + 2)


def test_record_at_exact_limit_and_following_record_survive(tmp_path: Path) -> None:
    config = _config(tmp_path, "os.write(1, b'x' * 63 + b'\\nnext\\n')\n")
    with spawn_prime_agent_managed(config, ("--mode", "rpc")) as managed:
        deadline = time.monotonic() + 2
        assert managed.read_line(max_bytes=64, deadline=deadline) == b"x" * 63 + b"\n"
        assert managed.read_line(max_bytes=64, deadline=deadline) == b"next\n"
        assert managed.wait_exit(deadline=deadline) == 0


def test_unterminated_record_at_stdout_eof_is_refused(tmp_path: Path) -> None:
    config = _config(tmp_path, "os.write(1, b'partial')\n")
    with (
        spawn_prime_agent_managed(config, ("--mode", "rpc")) as managed,
        pytest.raises(RuntimeError, match="unterminated record"),
    ):
        managed.read_line(max_bytes=64, deadline=time.monotonic() + 2)


def test_stderr_eof_is_retired_instead_of_busy_polled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import runtime.prime_agent.process as process_module

    config = _config(tmp_path, "os.close(2)\nos.write(1, b'ready\\n')\nsys.stdin.buffer.read()\n")
    calls = 0

    def counted(
        readers: Sequence[BinaryIO],
        writers: Sequence[BinaryIO],
        exceptional: Sequence[BinaryIO],
        timeout: float,
    ) -> tuple[list[BinaryIO], list[BinaryIO], list[BinaryIO]]:
        nonlocal calls
        calls += 1
        return select(readers, writers, exceptional, timeout)

    monkeypatch.setattr(process_module, "select_select", counted)
    with spawn_prime_agent_managed(config, ("--mode", "rpc")) as managed:
        assert managed.read_line(max_bytes=64, deadline=time.monotonic() + 2) == b"ready\n"
        calls = 0
        with pytest.raises(TimeoutError, match="deadline exceeded"):
            managed.read_line(max_bytes=64, deadline=time.monotonic() + 0.15)
    assert calls <= 2, "closed stderr must leave the readiness set after its first EOF"


@pytest.mark.parametrize("field", ["timeout_seconds", "terminate_grace_seconds"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_process_deadlines_are_refused(tmp_path: Path, field: str, value: float) -> None:
    config = _config(tmp_path, "pass\n")
    with pytest.raises(ValueError, match="deadlines"):
        if field == "timeout_seconds":
            replace(config, timeout_seconds=value)
        else:
            replace(config, terminate_grace_seconds=value)


@pytest.mark.parametrize("field", ["max_stdout_bytes", "max_stderr_bytes"])
@pytest.mark.parametrize("value", [True, 1.5])
def test_process_byte_limits_require_actual_integers(
    tmp_path: Path, field: str, value: int
) -> None:
    config = _config(tmp_path, "pass\n")
    with pytest.raises(ValueError, match="output limits"):
        if field == "max_stdout_bytes":
            replace(config, max_stdout_bytes=value)
        else:
            replace(config, max_stderr_bytes=value)
