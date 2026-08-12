"""Fail-closed, metered Prime 0.7 JSONL-RPC supplemental evidence call."""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from typing import Any, Protocol

from runtime.prime_agent.installation import PrimeAgentInstallation

from .prime_authority import (
    PrimeAuthorizationRequest,
    PrimeCallState,
    PrimeReceipt,
    PrimeUsage,
    ResolvedPrimeCredential,
)
from .prime_ledger import PrimeLedger

_MAX_RECORD_BYTES = 256_000
_MAX_TOTAL_BYTES = 1_000_000
_ABORT = b'{"id":"2","type":"abort"}\n'
_POLL_SECONDS = 0.05
_PROGRESS = frozenset({
    "agent_start", "turn_start", "message_start", "message_update", "message_end",
})


class PrimeCredentialResolver(Protocol):
    """Resolve an owner-bound credential without exposing it to authorization storage."""

    def resolve(self, authorization: PrimeAuthorizationRequest) -> ResolvedPrimeCredential: ...


@dataclass(frozen=True, slots=True)
class PrimeRPCEvidence:
    text: str
    provider: str
    model: str
    prime_version: str
    supplemental: bool = True


@dataclass(frozen=True, slots=True)
class PrimeRPCOutcome:
    evidence: PrimeRPCEvidence | None
    receipt: PrimeReceipt
    argv: tuple[str, ...]
    detail: str | None = None


def invoke_prime_rpc_evidence(
    *,
    prompt: str,
    authorization: PrimeAuthorizationRequest,
    ledger: PrimeLedger,
    installation: PrimeAgentInstallation,
    credential_resolver: PrimeCredentialResolver,
    cwd: Path,
    timeout_seconds: float = 120.0,
    max_record_bytes: int = _MAX_RECORD_BYTES,
    max_total_bytes: int = _MAX_TOTAL_BYTES,
    environ: Mapping[str, str] | None = None,
    cancelled: Callable[[], bool] | None = None,
    now_ms: Callable[[], int] | None = None,
) -> PrimeRPCOutcome:
    """Execute one already-authorized call; every ambiguous outcome retains its hold."""
    if not prompt or sha256(prompt.encode("utf-8")).hexdigest() != authorization.prompt_digest:
        raise ValueError("prompt does not match the authorized digest")
    if timeout_seconds <= 0 or max_record_bytes <= 0 or max_total_bytes < max_record_bytes:
        raise ValueError("RPC bounds are invalid")
    installed_version = ".".join(map(str, installation.version))
    if installed_version != authorization.prime_version:
        raise ValueError("verified Prime version differs from authorization")
    clock = now_ms or (lambda: time.time_ns() // 1_000_000)
    replay = ledger.authorize(authorization, now_ms=clock())
    argv = _argv(installation.binary, authorization)
    if replay.state is not PrimeCallState.AUTHORIZED:
        return PrimeRPCOutcome(None, replay, argv, "launch already claimed")
    try:
        resolved = credential_resolver.resolve(authorization)
        if not isinstance(resolved, ResolvedPrimeCredential) or not resolved.matches(authorization):
            raise ValueError("resolved credential binding mismatch")
        secret = resolved.secret.reveal()
        if len(secret.encode("utf-8")) > 16_384 or "\x00" in secret:
            raise ValueError("resolved credential value is invalid")
        if sha256(secret.encode("utf-8")).hexdigest() != authorization.credential_fingerprint:
            raise ValueError("resolved credential fingerprint mismatch")
        credential_environment = {authorization.credential_env_name: secret}
    except BaseException as exc:
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        return PrimeRPCOutcome(None, replay, argv, "credential resolution failed")
    if not ledger.mark_started(
        authorization.request_id, now_ms=clock()
    ):
        return PrimeRPCOutcome(None, ledger.receipt(authorization.request_id), argv, "launch already claimed")

    from runtime.prime_agent.process import PrimeAgentProcessConfig, spawn_prime_agent_managed

    process = None
    usage: PrimeUsage | None = None
    text = ""
    phase = "await_prompt_response"
    aborting = False
    abort_response = False
    detail: str | None = None
    deadline = time.monotonic() + timeout_seconds
    try:
        config = PrimeAgentProcessConfig(
            installation=installation,
            cwd=cwd.resolve(strict=True),
            timeout_seconds=timeout_seconds,
            max_stdout_bytes=max_total_bytes,
            max_stderr_bytes=max_record_bytes,
            environ=environ,
            provider_environment=credential_environment or None,
        )
        process = spawn_prime_agent_managed(
            config,
            lambda session_dir: _argv(
                installation.binary, authorization, process_session_dir=session_dir
            )[1:],
        )
        argv = _argv(installation.binary, authorization, process_session_dir=process.session_dir)
        command = json.dumps(
            {"id": "1", "type": "prompt", "message": prompt},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8") + b"\n"
        process.send_line(command, deadline=deadline)
        total = 0
        while True:
            if not aborting and cancelled is not None and cancelled():
                aborting = True
                process.send_line(_ABORT, deadline=deadline)
            poll_deadline = min(deadline, time.monotonic() + _POLL_SECONDS)
            try:
                line = process.read_line(max_bytes=max_record_bytes, deadline=poll_deadline)
            except TimeoutError:
                if time.monotonic() >= deadline:
                    raise
                continue
            if line is None:
                break
            total += len(line)
            if total > max_total_bytes:
                raise ValueError("RPC output exceeded total limit")
            event = _decode(line, max_record_bytes)
            kind = event.get("type")
            if kind == "response" and event.get("id") == "1" and event.get("command") == "prompt":
                if phase != "await_prompt_response":
                    raise ValueError("duplicate or out-of-order prompt response")
                if event.get("success") is not True:
                    raise ValueError("prompt command was rejected")
                phase = "progress"
            elif kind == "response" and event.get("id") == "2" and event.get("command") == "abort":
                if not aborting or abort_response:
                    raise ValueError("unexpected or duplicate abort response")
                if event.get("success") is not True:
                    raise ValueError("abort command was rejected")
                abort_response = True
            elif kind in _PROGRESS:
                if phase != "progress":
                    raise ValueError("out-of-order progress event")
            elif kind == "turn_end":
                if phase != "progress":
                    raise ValueError("duplicate or out-of-order turn_end")
                usage, candidate = _turn(event, authorization, installation, clock())
                if not candidate and not aborting:
                    raise ValueError("turn_end has no assistant text")
                if aborting and usage.stop_reason != "aborted":
                    raise ValueError("cancelled call did not emit aborted turn_end")
                text = candidate
                phase = "await_agent_end"
            elif kind == "agent_end":
                if phase != "await_agent_end":
                    raise ValueError("duplicate or out-of-order agent_end")
                terminal = _last_assistant_text(event.get("messages"))
                if not aborting and not terminal:
                    raise ValueError("agent_end has no terminal assistant text")
                if terminal != text:
                    raise ValueError("agent_end assistant text differs from turn_end")
                if usage is None or sha256(terminal.encode("utf-8")).hexdigest() != usage.evidence_digest:
                    raise ValueError("agent_end evidence digest differs from turn_end")
                text = terminal
                phase = "complete"
                process.close_stdin()
                exit_code = process.wait_exit(deadline=deadline)
                break
            else:
                raise ValueError("unknown or uncorrelated RPC event")
        if usage is not None:
            settled = ledger.observe_usage(authorization.request_id, usage, now_ms=clock())
            if settled.state is not PrimeCallState.USAGE_OBSERVED:
                return PrimeRPCOutcome(None, settled, argv, "usage was not authorized")
        if aborting:
            if not (abort_response and phase == "complete"):
                receipt = _unknown(ledger, authorization.request_id, usage, clock())
                return PrimeRPCOutcome(None, receipt, argv, "incomplete abort sequence")
            receipt = ledger.cancel(authorization.request_id, now_ms=clock())
            return PrimeRPCOutcome(None, receipt, argv, "cancelled")
        if not (phase == "complete" and exit_code == 0 and text):
            detail = "incomplete or unclean Prime RPC terminal sequence"
            receipt = _unknown(ledger, authorization.request_id, usage, clock())
            return PrimeRPCOutcome(None, receipt, argv, detail)
        receipt = ledger.succeed(authorization.request_id, now_ms=clock())
        if receipt.state is not PrimeCallState.SUCCEEDED:
            return PrimeRPCOutcome(None, receipt, argv, "settlement failed")
        evidence = PrimeRPCEvidence(text, usage.provider, usage.model, usage.prime_version)
        return PrimeRPCOutcome(evidence, receipt, argv)
    except BaseException as exc:
        detail = type(exc).__name__
        receipt = _unknown(ledger, authorization.request_id, usage, clock())
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        return PrimeRPCOutcome(None, receipt, argv, detail)
    finally:
        if process is not None:
            process.terminate(deadline=deadline)
            process.close()


def _argv(
    binary: Path,
    authorization: PrimeAuthorizationRequest,
    process_session_dir: Path | None = None,
) -> tuple[str, ...]:
    base = (
        str(binary), "--mode", "rpc", "--offline", "--no-tools",
        "--no-extensions", "--no-skills", "--no-prompt-templates", "--no-themes",
        "--no-context-files", "--provider", authorization.provider, "--model", authorization.model,
    )
    return base if process_session_dir is None else (*base, "--session-dir", str(process_session_dir))


def _decode(line: bytes, limit: int) -> dict[str, Any]:
    if len(line) > limit:
        raise ValueError("RPC record exceeded limit")
    if not line.endswith(b"\n"):
        raise ValueError("RPC records require LF framing")
    payload = line[:-1]
    if payload.endswith(b"\r"):
        payload = payload[:-1]
    value = json.loads(
        payload.decode("utf-8", errors="strict"),
        parse_float=Decimal,
        parse_int=Decimal,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
    )
    if not isinstance(value, dict) or not isinstance(value.get("type"), str):
        raise ValueError("RPC record must be a typed JSON object")
    return value


def _integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, Decimal) or value < 0 or value != value.to_integral_value():
        raise ValueError(f"invalid {name}")
    return int(value)


def _turn(event: Mapping[str, Any], auth: PrimeAuthorizationRequest, installation: PrimeAgentInstallation, at: int) -> tuple[PrimeUsage, str]:
    message = event.get("message")
    if not isinstance(message, dict):
        raise ValueError("turn_end missing message")
    raw = message.get("usage")
    if not isinstance(raw, dict) or not isinstance(raw.get("cost"), dict):
        raise ValueError("turn_end missing usage")
    provider, model = message.get("provider"), message.get("model")
    version = ".".join(map(str, installation.version))
    if provider != auth.provider or model != auth.model or version != auth.prime_version:
        raise ValueError("actual inference identity differs from authorization")
    total = raw["cost"].get("total")
    if not isinstance(total, Decimal) or total < 0:
        raise ValueError("invalid cost.total")
    micro = total * Decimal(1_000_000)
    if micro != micro.to_integral_value():
        raise ValueError("cost is not exactly representable in microUSD")
    text = _message_text(message)
    digest = sha256(text.encode("utf-8")).hexdigest()
    return PrimeUsage(
        provider=provider, model=model, prime_version=version,
        input_tokens=_integer(raw.get("input"), "input"),
        output_tokens=_integer(raw.get("output"), "output"),
        cache_read_tokens=_integer(raw.get("cacheRead"), "cacheRead"),
        cache_write_tokens=_integer(raw.get("cacheWrite"), "cacheWrite"),
        cost_micro_usd=int(micro), observed_at_ms=at,
        stop_reason=message.get("stopReason") if isinstance(message.get("stopReason"), str) else "unknown",
        evidence_digest=digest, output_digest=digest,
        provider_request_id=str(message.get("requestId") or "unknown"),
        provider_event_id=str(event.get("id") or "unknown"),
    ), text


def _message_text(message: object) -> str:
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(item.get("text", "") for item in content if isinstance(item, dict) and isinstance(item.get("text"), str))
    return ""


def _last_assistant_text(messages: object) -> str:
    if isinstance(messages, list):
        for message in reversed(messages):
            if isinstance(message, dict) and message.get("role") == "assistant":
                return _message_text(message)
    return ""


def _unknown(ledger: PrimeLedger, request_id: str, usage: PrimeUsage | None, now: int) -> PrimeReceipt:
    current = ledger.receipt(request_id)
    if current.state in {PrimeCallState.STARTED, PrimeCallState.USAGE_OBSERVED}:
        return ledger.mark_unknown(request_id, usage, now_ms=now)
    return current
