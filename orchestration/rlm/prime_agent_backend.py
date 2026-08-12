"""Bounded, optional Prime Agent evidence lane for RLM workflows.

Prime evidence is supplemental.  This module has no authority to dispatch an
Antiek model call, execute a remote worker, or write canonical state.
"""

from __future__ import annotations

import os
import time
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from runtime.prime_agent.installation import (
    PRIME_AGENT_BINARY_ENV,
    PrimeAgentUnavailable,
    resolve_prime_agent_binary,
    verify_prime_agent_installation,
)
from runtime.prime_agent.process import PrimeAgentProcessConfig, run_prime_agent_process

_ENABLED_ENV = "ANTIEK_PRIME_AGENT_RLM_ENABLED"
_TIMEOUT_ENV = "ANTIEK_PRIME_AGENT_RLM_TIMEOUT_SECONDS"
_OUTPUT_ENV = "ANTIEK_PRIME_AGENT_RLM_MAX_OUTPUT_BYTES"
_DEFAULT_TIMEOUT_SECONDS = 120.0
_DEFAULT_MAX_OUTPUT_BYTES = 256_000
_MAX_PROMPT_BYTES = 1_000_000


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
        if not executable:
            raise ValueError("Prime Agent executable must not be empty")

        self._enabled = enabled
        self._executable = executable
        self._cwd = resolved_cwd
        self._timeout_seconds = timeout_seconds
        self._max_output_bytes = max_output_bytes
        source_env = os.environ if environ is None else environ
        self._environment = dict(source_env)

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
        try:
            binary = resolve_prime_agent_binary(self._environment, binary=self._executable)
            installation = verify_prime_agent_installation(binary, environ=self._environment)
        except PrimeAgentUnavailable as exc:
            return self._outcome(
                request,
                PrimeAgentTerminalState.UNAVAILABLE,
                argv,
                detail=str(exc),
            )
        argv = (str(binary), *argv[1:])

        started = time.monotonic()
        try:
            result = run_prime_agent_process(
                PrimeAgentProcessConfig(
                    installation=installation,
                    cwd=self._cwd,
                    timeout_seconds=self._timeout_seconds,
                    max_stdout_bytes=self._max_output_bytes,
                    max_stderr_bytes=self._max_output_bytes,
                    environ=self._environment,
                ),
                argv[1:],
                stdin=prompt_bytes,
            )
        except OSError as exc:
            return self._outcome(
                request,
                PrimeAgentTerminalState.UNAVAILABLE,
                argv,
                duration_ms=_elapsed_ms(started),
                detail=type(exc).__name__,
            )

        output = result.stdout
        if result.timed_out or result.stdout_limit_exceeded or result.stderr_limit_exceeded:
            terminal_state = (
                PrimeAgentTerminalState.TIMEOUT
                if result.timed_out
                else PrimeAgentTerminalState.FAILED
            )
            return self._outcome(
                request,
                terminal_state,
                argv,
                exit_code=result.exit_code,
                duration_ms=result.duration_ms,
                output_bytes=len(output),
                detail=(
                    "execution timed out"
                    if terminal_state is PrimeAgentTerminalState.TIMEOUT
                    else "output limit exceeded"
                ),
            )
        if result.exit_code != 0:
            return self._outcome(
                request,
                PrimeAgentTerminalState.FAILED,
                argv,
                exit_code=result.exit_code,
                duration_ms=result.duration_ms,
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
                exit_code=result.exit_code,
                duration_ms=result.duration_ms,
                output_bytes=len(output),
                detail="output was empty or not UTF-8",
            )
        receipt = PrimeAgentReceipt(
            state=PrimeAgentTerminalState.SUCCESS,
            argv=argv,
            exit_code=result.exit_code,
            duration_ms=result.duration_ms,
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
        executable=values.get(PRIME_AGENT_BINARY_ENV, "prime-agent"),
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
