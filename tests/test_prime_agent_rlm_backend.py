from __future__ import annotations

import ast
import os
import stat
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

import orchestration.rlm.prime_agent_backend as backend_module
from orchestration.rlm.prime_agent_backend import (
    PrimeAgentRequest,
    PrimeAgentRLMBackend,
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
record = pathlib.Path(os.environ["RECORD_FILE"])
record.write_text(repr((sys.argv[1:], os.getcwd(), dict(os.environ))))
prompt = sys.stdin.read()
if prompt == "timeout": time.sleep(10)
elif prompt == "oversize": os.write(1, b"x" * 100000)
elif prompt == "nonzero": sys.exit(7)
elif prompt == "empty": pass
elif prompt == "binary": os.write(1, b"\\xff")
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
    # RECORD_FILE is intentionally not in the production allowlist. The fake
    # receives its record path through TMPDIR so it can inspect the child.
    env = dict(values["environ"])  # type: ignore[arg-type]
    env["TMPDIR"] = str(tmp_path)
    values["environ"] = env
    # Rewrite the fixture to use the allowed, non-secret TMPDIR variable.
    executable.write_text(executable.read_text().replace('os.environ["RECORD_FILE"]', 'os.environ["TMPDIR"] + "/record.txt"'))
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
    assert child_env["HOME"] == str(tmp_path)
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
    executable.write_text("#!/usr/bin/env python3\nimport time\ntime.sleep(10)\n")
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


def test_cancellation_terminates_child_and_propagates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend = _backend(tmp_path)
    terminated: list[int] = []
    original_terminate = backend_module._terminate_process_group

    def cancel(*_args: object) -> object:
        raise KeyboardInterrupt

    def terminate(process: object) -> None:
        terminated.append(process.pid)  # type: ignore[attr-defined]
        original_terminate(process)  # type: ignore[arg-type]

    monkeypatch.setattr(PrimeAgentRLMBackend, "_read_bounded", cancel)
    monkeypatch.setattr(backend_module, "_terminate_process_group", terminate)
    with pytest.raises(KeyboardInterrupt):
        backend.run(_request())
    assert len(terminated) == 1


def test_invalid_request_and_configuration_are_rejected(tmp_path: Path) -> None:
    assert _backend(tmp_path).run(_request(" ")).receipt.state is PrimeAgentTerminalState.MALFORMED
    oversized = _backend(tmp_path).run(_request("x" * 1_000_001))
    assert oversized.receipt.state is PrimeAgentTerminalState.MALFORMED
    with pytest.raises(ValueError):
        PrimeAgentRLMBackend(enabled=True, executable="/bin/prime-agent", cwd=tmp_path)
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
