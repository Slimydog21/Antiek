from __future__ import annotations

import ast
import os
import stat
import time
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from orchestration.rlm.prime_agent_backend import (
    PrimeAgentRequest,
    PrimeAgentRLMBackend,
    PrimeAgentSessionRequest,
    PrimeAgentTerminalState,
    prime_agent_backend_from_environment,
)


def _request(prompt: str = "answer") -> PrimeAgentRequest:
    return PrimeAgentRequest(prompt=prompt, workflow="repl", request_id="req-1")


def _fake_prime(tmp_path: Path) -> tuple[Path, Path]:
    executable = tmp_path / "prime-agent"
    record = tmp_path / "record.txt"
    executable.write_text(
        """#!/usr/bin/env python3
import os, pathlib, sys, time
if sys.argv[1:] == ["--version"]:
    print("prime-agent 0.7.4")
    raise SystemExit
if sys.argv[1:] == ["--help"]:
    print("-p --cwd --offline --no-session --no-tools --no-extensions --no-skills --no-prompt-templates --no-themes --no-context-files --mode rpc")
    raise SystemExit
record = pathlib.Path.cwd() / "record.txt"
record.write_text(repr((sys.argv[1:], os.getcwd(), dict(os.environ))))
prompt = sys.stdin.read()
(pathlib.Path.cwd() / "prompt.txt").write_text(prompt)
if prompt == "timeout" or "session terminal: timeout" in prompt: time.sleep(10)
elif prompt == "oversize" or "session terminal: oversize" in prompt: os.write(1, b"x" * 100000)
elif prompt == "nonzero" or "session terminal: nonzero" in prompt: sys.exit(7)
elif prompt == "empty" or "session terminal: empty" in prompt: pass
elif prompt == "binary" or "session terminal: binary" in prompt: os.write(1, b"\\xff")
elif "iteration context sentinel" in prompt:
    marker = "Write final answer to exactly: "
    if marker in prompt:
        print("done: " + prompt.split(marker, 1)[1].splitlines()[0])
    else:
        print("answer grounded in iteration context sentinel")
else: print("supplemental answer")
"""
    )
    executable.chmod(executable.stat().st_mode | stat.S_IXUSR)
    return executable, record


def _backend(tmp_path: Path, **overrides: object) -> PrimeAgentRLMBackend:
    executable, record = _fake_prime(tmp_path)
    values: dict[str, object] = {
        "enabled": True,
        "executable": executable.name,
        "cwd": tmp_path,
        "timeout_seconds": 1.0,
        "max_output_bytes": 1024,
        "environ": {
            "PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}",
            "HOME": str(tmp_path),
            "RECORD_FILE": str(record),
            "OPENAI_API_KEY": "must-not-leak",
            "AWS_SECRET_ACCESS_KEY": "must-not-leak",
        },
    }
    values.update(overrides)
    return PrimeAgentRLMBackend(**values)  # type: ignore[arg-type]


def test_types_are_immutable_and_disabled_is_default(tmp_path: Path) -> None:
    request = _request()
    with pytest.raises(FrozenInstanceError):
        request.prompt = "changed"  # type: ignore[misc]

    outcome = prime_agent_backend_from_environment({}, cwd=tmp_path).run(request)
    assert outcome.evidence is None
    assert outcome.receipt.state is PrimeAgentTerminalState.DISABLED
    assert outcome.receipt.exit_code is None


def test_success_uses_fixed_argv_safe_cwd_and_sanitized_environment(tmp_path: Path) -> None:
    backend = _backend(tmp_path)
    outcome = backend.run(_request("a prompt; $(touch nope)"))

    assert outcome.receipt.state is PrimeAgentTerminalState.SUCCESS
    assert outcome.evidence is not None
    assert outcome.evidence.text == "supplemental answer"
    assert outcome.evidence.supplemental is True
    args, cwd, child_env = ast.literal_eval((tmp_path / "record.txt").read_text())
    assert args[-1:] == ["-p"]
    assert "a prompt; $(touch nope)" not in args
    assert "a prompt; $(touch nope)" not in outcome.receipt.argv
    assert "--no-tools" in args
    assert "--no-session" in args
    assert "--no-context-files" in args
    assert "--api-key" not in args
    assert cwd == str(tmp_path.resolve())
    assert "OPENAI_API_KEY" not in child_env
    assert "AWS_SECRET_ACCESS_KEY" not in child_env
    assert child_env["HOME"] != str(tmp_path)
    assert child_env["HOME"].endswith("/home")
    assert child_env["TMPDIR"].endswith("/tmp")
    assert not (tmp_path / "nope").exists()


@pytest.mark.parametrize(
    ("prompt", "state", "exit_code"),
    [
        ("nonzero", PrimeAgentTerminalState.FAILED, 7),
        ("empty", PrimeAgentTerminalState.MALFORMED, 0),
        ("binary", PrimeAgentTerminalState.MALFORMED, 0),
    ],
)
def test_terminal_states(prompt: str, state: PrimeAgentTerminalState, exit_code: int, tmp_path: Path) -> None:
    outcome = _backend(tmp_path).run(_request(prompt))
    assert outcome.evidence is None
    assert outcome.receipt.state is state
    assert outcome.receipt.exit_code == exit_code


def test_missing_executable_is_unavailable(tmp_path: Path) -> None:
    backend = PrimeAgentRLMBackend(enabled=True, executable="absent-prime", cwd=tmp_path, environ={})
    assert backend.run(_request()).receipt.state is PrimeAgentTerminalState.UNAVAILABLE


def test_timeout_kills_child_and_is_typed(tmp_path: Path) -> None:
    outcome = _backend(tmp_path, timeout_seconds=0.05).run(_request("timeout"))
    assert outcome.evidence is None
    assert outcome.receipt.state is PrimeAgentTerminalState.TIMEOUT


def test_timeout_covers_child_that_never_reads_stdin(tmp_path: Path) -> None:
    executable, _ = _fake_prime(tmp_path)
    executable.write_text(
        """#!/usr/bin/env python3
import sys, time
if sys.argv[1:] == ["--version"]: print("prime-agent 0.7.4")
elif sys.argv[1:] == ["--help"]: print("-p --cwd --offline --no-session --no-tools --no-extensions --no-skills --no-prompt-templates --no-themes --no-context-files --mode rpc")
else: time.sleep(10)
"""
    )
    executable.chmod(executable.stat().st_mode | stat.S_IXUSR)
    backend = PrimeAgentRLMBackend(
        enabled=True,
        executable=executable.name,
        cwd=tmp_path,
        timeout_seconds=0.05,
        max_output_bytes=64,
        environ={"PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}"},
    )

    outcome = backend.run(_request("x" * 1_000_000))
    assert outcome.receipt.state is PrimeAgentTerminalState.TIMEOUT


def test_oversized_output_is_killed_and_receipt_is_bounded(tmp_path: Path) -> None:
    outcome = _backend(tmp_path, max_output_bytes=64).run(_request("oversize"))
    assert outcome.receipt.state is PrimeAgentTerminalState.FAILED
    assert outcome.receipt.output_bytes == 64
    assert outcome.receipt.detail == "output limit exceeded"


def test_invalid_request_and_configuration_are_rejected(tmp_path: Path) -> None:
    assert _backend(tmp_path).run(_request(" ")).receipt.state is PrimeAgentTerminalState.MALFORMED
    oversized = _backend(tmp_path).run(_request("x" * 1_000_001))
    assert oversized.receipt.state is PrimeAgentTerminalState.MALFORMED
    with pytest.raises(ValueError):
        prime_agent_backend_from_environment(
            {"ANTIEK_PRIME_AGENT_RLM_TIMEOUT_SECONDS": "0"}, cwd=tmp_path
        )


def test_backend_has_no_forbidden_authority_imports() -> None:
    source = Path("orchestration/rlm/prime_agent_backend.py").read_text()
    tree = ast.parse(source)
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert all("dispatch" not in name for name in imports)
    assert all("remote_exec" not in name for name in imports)
    assert all("db_lock" not in name for name in imports)


def test_session_returns_answer_instead_of_requested_file_completion_marker(tmp_path: Path) -> None:
    outcome = _backend(tmp_path).run_session(
        PrimeAgentSessionRequest(
            goal_brief="Explain the supplied iteration context",
            iteration_prompt="iteration context sentinel",
            workflow="rlm-investigation-iteration",
            request_id="sess-context",
        )
    )
    assert outcome.receipt.state is PrimeAgentTerminalState.SUCCESS
    assert outcome.evidence is not None
    assert outcome.evidence.text == "answer grounded in iteration context sentinel"
    assert outcome.evidence.source == "prime-agent-session"
    assert outcome.request.prompt == "iteration context sentinel"
    assert outcome.request.workflow == "rlm-investigation-iteration"
    assert outcome.request.request_id == "sess-context"
    actual_prompt = (tmp_path / "prompt.txt").read_text()
    assert "Explain the supplied iteration context" in actual_prompt
    assert "iteration context sentinel" in actual_prompt
    assert not list(tmp_path.glob("**/prime_agent_session_answer.txt"))


@pytest.mark.parametrize(
    ("terminal", "state", "exit_code"),
    [
        ("nonzero", PrimeAgentTerminalState.FAILED, 7),
        ("empty", PrimeAgentTerminalState.MALFORMED, 0),
        ("binary", PrimeAgentTerminalState.MALFORMED, 0),
        ("oversize", PrimeAgentTerminalState.FAILED, None),
        ("timeout", PrimeAgentTerminalState.TIMEOUT, None),
    ],
)
def test_session_preserves_process_failure_and_output_limits(
    terminal: str, state: PrimeAgentTerminalState, exit_code: int | None, tmp_path: Path,
) -> None:
    timeout = 0.05 if terminal == "timeout" else 1.0
    outcome = _backend(tmp_path, timeout_seconds=timeout, max_output_bytes=64).run_session(
        PrimeAgentSessionRequest(
            goal_brief="Session goal",
            iteration_prompt=f"session terminal: {terminal}",
            workflow="rlm-investigation-iteration",
            request_id="sess-terminal",
        )
    )
    assert outcome.receipt.state is state
    assert outcome.evidence is None
    assert outcome.receipt.output_bytes <= 64
    if exit_code is not None:
        assert outcome.receipt.exit_code == exit_code
    assert outcome.request.prompt == f"session terminal: {terminal}"


def test_session_input_limit_includes_goal_before_spawn(tmp_path: Path) -> None:
    outcome = _backend(tmp_path).run_session(
        PrimeAgentSessionRequest(
            goal_brief="g" * 1_000_000,
            iteration_prompt="context",
            workflow="workflow",
            request_id="sess-large-goal",
        )
    )
    assert outcome.receipt.state is PrimeAgentTerminalState.MALFORMED
    assert outcome.evidence is None
    assert outcome.receipt.detail == "prompt exceeds input limit"
    assert not (tmp_path / "record.txt").exists()



def test_run_session_returns_stdout_without_waiting_for_a_file(
    tmp_path: Path,
) -> None:
    """The tool-less child returns its answer without any file polling."""
    backend = _backend(tmp_path, timeout_seconds=2.0)
    real_run = backend.run
    run_returned_at: list[float] = []

    def timed_run(request: PrimeAgentRequest):
        outcome = real_run(request)
        run_returned_at.append(time.monotonic())
        return outcome

    backend.run = timed_run  # type: ignore[method-assign]
    outcome = backend.run_session(
        PrimeAgentSessionRequest(
            goal_brief="goal",
            iteration_prompt="payload",
            workflow="workflow",
            request_id="id",
        )
    )
    finished = time.monotonic()

    assert outcome.receipt.state is PrimeAgentTerminalState.SUCCESS
    assert outcome.evidence is not None
    assert outcome.evidence.text == "supplemental answer"
    assert outcome.evidence.source == "prime-agent-session"
    assert outcome.receipt.detail is not None
    assert "--no-tools" in outcome.receipt.detail
    assert "missing" not in outcome.receipt.detail
    # The old poll burned timeout_seconds (2.0s here) after the child exited.
    assert finished - run_returned_at[0] < 0.25
    assert not list(tmp_path.glob("**/prime_agent_session_answer.txt"))


def test_run_session_without_stdout_is_malformed_not_timeout(tmp_path: Path) -> None:
    """An inconsistent success with no stdout answer refuses immediately."""
    backend = _backend(tmp_path, timeout_seconds=2.0)

    def fake_run(request: PrimeAgentRequest):
        return backend._outcome(  # type: ignore[attr-defined]
            request,
            PrimeAgentTerminalState.SUCCESS,
            backend._argv(request),  # type: ignore[attr-defined]
            exit_code=0,
            duration_ms=1,
            output_bytes=0,
        )

    backend.run = fake_run  # type: ignore[method-assign]
    started = time.monotonic()
    outcome = backend.run_session(
        PrimeAgentSessionRequest(
            goal_brief="goal",
            iteration_prompt="payload",
            workflow="workflow",
            request_id="id",
        )
    )

    assert outcome.receipt.state is PrimeAgentTerminalState.MALFORMED
    assert outcome.evidence is None
    assert outcome.receipt.detail is not None
    assert "--no-tools" in outcome.receipt.detail
    assert time.monotonic() - started < 0.25


def test_run_session_invalid_request_is_malformed(tmp_path: Path) -> None:
    backend = _backend(tmp_path)
    outcome = backend.run_session(
        PrimeAgentSessionRequest(
            goal_brief=" ",
            iteration_prompt="payload",
            workflow="workflow",
            request_id="id",
        )
    )
    assert outcome.receipt.state is PrimeAgentTerminalState.MALFORMED
