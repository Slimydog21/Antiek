"""Bounded, optional Prime Agent evidence lane for RLM workflows.

Prime evidence is supplemental.  This module has no authority to dispatch an
Antiek model call, execute a remote worker, or write canonical state.
"""

from __future__ import annotations

import os
import selectors
import shutil
import signal
import subprocess
import tempfile
import time
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

_ENABLED_ENV = "ANTIEK_PRIME_AGENT_RLM_ENABLED"
_TIMEOUT_ENV = "ANTIEK_PRIME_AGENT_RLM_TIMEOUT_SECONDS"
_OUTPUT_ENV = "ANTIEK_PRIME_AGENT_RLM_MAX_OUTPUT_BYTES"
_EXECUTABLE_ENV = "ANTIEK_PRIME_AGENT_RLM_EXECUTABLE"
_DEFAULT_TIMEOUT_SECONDS = 120.0
_DEFAULT_MAX_OUTPUT_BYTES = 256_000
_MAX_PROMPT_BYTES = 1_000_000
_READ_CHUNK_BYTES = 16_384
_PASSTHROUGH_ENV = ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR")


class PrimeAgentTerminalState(StrEnum):
    """Exhaustive terminal states exposed to callers."""

    DISABLED = "disabled"
    UNAVAILABLE = "unavailable"
    TIMEOUT = "timeout"
    FAILED = "failed"
    MALFORMED = "malformed"
    SUCCESS = "success"


@dataclass(frozen=True, slots=True)
class PrimeAgentRequest:
    """One request for non-canonical evidence."""

    prompt: str
    workflow: str
    request_id: str


@dataclass(frozen=True, slots=True)
class PrimeAgentEvidence:
    """Labeled evidence which must not replace a canonical caller result."""

    text: str
    source: str = "prime-agent"
    supplemental: bool = True


@dataclass(frozen=True, slots=True)
class PrimeAgentReceipt:
    """Auditable execution facts, including honest non-success outcomes."""

    state: PrimeAgentTerminalState
    argv: tuple[str, ...]
    exit_code: int | None
    duration_ms: int
    output_bytes: int
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class PrimeAgentOutcome:
    """The evidence, when valid, and its immutable execution receipt."""

    request: PrimeAgentRequest
    evidence: PrimeAgentEvidence | None
    receipt: PrimeAgentReceipt


class PrimeAgentRLMBackend:
    """Invoke ``prime-agent -p`` with a fixed, least-privilege envelope."""

    def __init__(
        self,
        *,
        enabled: bool = False,
        executable: str = "prime-agent",
        cwd: Path | str,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
        max_output_bytes: int = _DEFAULT_MAX_OUTPUT_BYTES,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        resolved_cwd = Path(cwd).resolve(strict=True)
        if not resolved_cwd.is_dir():
            raise ValueError("Prime Agent cwd must be an existing directory")
        if timeout_seconds <= 0:
            raise ValueError("Prime Agent timeout must be positive")
        if max_output_bytes <= 0:
            raise ValueError("Prime Agent output limit must be positive")
        if not executable or Path(executable).name != executable:
            raise ValueError("Prime Agent executable must be a bare command name")

        self._enabled = enabled
        self._executable = executable
        self._cwd = resolved_cwd
        self._timeout_seconds = timeout_seconds
        self._max_output_bytes = max_output_bytes
        source_env = os.environ if environ is None else environ
        self._environment = {
            key: source_env[key] for key in _PASSTHROUGH_ENV if source_env.get(key)
        }

    def run(self, request: PrimeAgentRequest) -> PrimeAgentOutcome:
        """Return supplemental evidence without mutating caller-owned state."""
        argv = self._argv(request)
        if not self._enabled:
            return self._outcome(request, PrimeAgentTerminalState.DISABLED, argv)
        if not request.prompt.strip() or not request.workflow.strip() or not request.request_id.strip():
            return self._outcome(
                request,
                PrimeAgentTerminalState.MALFORMED,
                argv,
                detail="request fields must be non-empty",
            )
        prompt_bytes = request.prompt.encode("utf-8")
        if len(prompt_bytes) > _MAX_PROMPT_BYTES:
            return self._outcome(
                request,
                PrimeAgentTerminalState.MALFORMED,
                argv,
                detail="prompt exceeds input limit",
            )
        if shutil.which(self._executable, path=self._environment.get("PATH")) is None:
            return self._outcome(
                request,
                PrimeAgentTerminalState.UNAVAILABLE,
                argv,
                detail="prime-agent executable not found",
            )

        started = time.monotonic()
        # The stream must outlive Popen and closes in both launch and run paths.
        prompt_stream = tempfile.TemporaryFile()  # noqa: SIM115
        prompt_stream.write(prompt_bytes)
        prompt_stream.seek(0)
        try:
            process = subprocess.Popen(
                list(argv),
                cwd=self._cwd,
                env=self._environment,
                stdin=prompt_stream,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        except OSError as exc:
            prompt_stream.close()
            return self._outcome(
                request,
                PrimeAgentTerminalState.UNAVAILABLE,
                argv,
                duration_ms=_elapsed_ms(started),
                detail=type(exc).__name__,
            )

        try:
            output, terminal_state = self._read_bounded(process, started)
        except BaseException:
            _terminate_process_group(process)
            raise
        finally:
            prompt_stream.close()

        duration_ms = _elapsed_ms(started)
        if terminal_state is not None:
            return self._outcome(
                request,
                terminal_state,
                argv,
                exit_code=process.returncode,
                duration_ms=duration_ms,
                output_bytes=len(output),
                detail=(
                    "output limit exceeded"
                    if terminal_state is PrimeAgentTerminalState.FAILED
                    else "execution timed out"
                ),
            )
        if process.returncode != 0:
            return self._outcome(
                request,
                PrimeAgentTerminalState.FAILED,
                argv,
                exit_code=process.returncode,
                duration_ms=duration_ms,
                output_bytes=len(output),
                detail="prime-agent exited nonzero",
            )
        try:
            text = output.decode("utf-8", errors="strict").strip()
        except UnicodeDecodeError:
            text = ""
        if not text:
            return self._outcome(
                request,
                PrimeAgentTerminalState.MALFORMED,
                argv,
                exit_code=process.returncode,
                duration_ms=duration_ms,
                output_bytes=len(output),
                detail="output was empty or not UTF-8",
            )
        receipt = PrimeAgentReceipt(
            state=PrimeAgentTerminalState.SUCCESS,
            argv=argv,
            exit_code=process.returncode,
            duration_ms=duration_ms,
            output_bytes=len(output),
        )
        return PrimeAgentOutcome(request, PrimeAgentEvidence(text), receipt)

    def _argv(self, request: PrimeAgentRequest) -> tuple[str, ...]:
        return (
            self._executable,
            "--offline",
            "--no-session",
            "--no-tools",
            "--no-extensions",
            "--no-skills",
            "--no-prompt-templates",
            "--no-themes",
            "--no-context-files",
            "--cwd",
            str(self._cwd),
            "-p",
        )

    def _read_bounded(
        self, process: subprocess.Popen[bytes], started: float
    ) -> tuple[bytes, PrimeAgentTerminalState | None]:
        assert process.stdout is not None
        output = bytearray()
        os.set_blocking(process.stdout.fileno(), False)
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ)
        try:
            while selector.get_map():
                remaining = self._timeout_seconds - (time.monotonic() - started)
                if remaining <= 0:
                    _terminate_process_group(process)
                    return bytes(output), PrimeAgentTerminalState.TIMEOUT
                for key, _ in selector.select(min(remaining, 0.1)):
                    chunk = os.read(key.fd, _READ_CHUNK_BYTES)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    output.extend(chunk)
                    if len(output) > self._max_output_bytes:
                        del output[self._max_output_bytes :]
                        _terminate_process_group(process)
                        return bytes(output), PrimeAgentTerminalState.FAILED
            remaining = self._timeout_seconds - (time.monotonic() - started)
            if remaining <= 0:
                _terminate_process_group(process)
                return bytes(output), PrimeAgentTerminalState.TIMEOUT
            process.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            _terminate_process_group(process)
            return bytes(output), PrimeAgentTerminalState.TIMEOUT
        finally:
            selector.close()
            process.stdout.close()
        return bytes(output), None

    @staticmethod
    def _outcome(
        request: PrimeAgentRequest,
        state: PrimeAgentTerminalState,
        argv: tuple[str, ...],
        *,
        exit_code: int | None = None,
        duration_ms: int = 0,
        output_bytes: int = 0,
        detail: str | None = None,
    ) -> PrimeAgentOutcome:
        return PrimeAgentOutcome(
            request,
            None,
            PrimeAgentReceipt(state, argv, exit_code, duration_ms, output_bytes, detail),
        )


def prime_agent_backend_from_environment(
    environ: Mapping[str, str] | None = None,
    *,
    cwd: Path | str | None = None,
) -> PrimeAgentRLMBackend:
    """Build the default-disabled backend from explicit environment input."""
    values = os.environ if environ is None else environ
    return PrimeAgentRLMBackend(
        enabled=values.get(_ENABLED_ENV, "").strip().lower() in {"1", "true", "yes"},
        executable=values.get(_EXECUTABLE_ENV, "prime-agent"),
        cwd=Path.cwd() if cwd is None else cwd,
        timeout_seconds=_positive_float(values.get(_TIMEOUT_ENV), _DEFAULT_TIMEOUT_SECONDS),
        max_output_bytes=_positive_int(values.get(_OUTPUT_ENV), _DEFAULT_MAX_OUTPUT_BYTES),
        environ=values,
    )


def _positive_float(raw: str | None, default: float) -> float:
    if raw is None:
        return default
    value = float(raw)
    if value <= 0:
        raise ValueError("Prime Agent timeout must be positive")
    return value


def _positive_int(raw: str | None, default: int) -> int:
    if raw is None:
        return default
    value = int(raw)
    if value <= 0:
        raise ValueError("Prime Agent output limit must be positive")
    return value


def _elapsed_ms(started: float) -> int:
    return max(0, round((time.monotonic() - started) * 1000))


def _terminate_process_group(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    with suppress(ProcessLookupError):
        os.killpg(process.pid, signal.SIGKILL)
    process.wait()
