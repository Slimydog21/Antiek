from __future__ import annotations

import hashlib
import json
import os
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from orchestration.rlm.prime_authority import (
    PRIME_PROVIDER_CREDENTIAL_ENV,
    PrimeAuthorizationRequest,
    PrimeCallState,
    PrimeSecret,
    ResolvedPrimeCredential,
)
from orchestration.rlm.prime_ledger import PrimeLedger
from orchestration.rlm.prime_rpc_evidence import _decode, invoke_prime_rpc_evidence
from runtime.prime_agent.installation import verify_prime_agent_installation


def _binary(tmp_path: Path, events: list[dict[str, object]]) -> Path:
    path = tmp_path / "prime-agent"
    encoded = repr(b"".join(json.dumps(e, separators=(",", ":")).encode() + b"\n" for e in events))
    path.write_text(
        "#!/usr/bin/env python3\n"
        "import os,sys\n"
        "if '--version' in sys.argv: print('prime-agent 0.7.4')\n"
        "elif '--help' in sys.argv: print('-p --cwd --offline --no-session --no-tools --no-extensions --no-skills --no-prompt-templates --no-themes --no-context-files --mode rpc')\n"
        f"else:\n data=sys.stdin.buffer.readline(); open('credential_seen','w').write(str(bool(os.environ.get('ANTHROPIC_API_KEY')))); os.write(1,{encoded}); data += sys.stdin.buffer.read(); open('received.bin','wb').write(data)\n"
    )
    path.chmod(0o700)
    return path


def _request(prompt: str, *, now: int = 100) -> PrimeAuthorizationRequest:
    return PrimeAuthorizationRequest(
        owner_id="owner", payer_id="payer", session_id="session", request_id="request",
        idempotency_key="idempotency", workflow="evidence", prompt_digest=hashlib.sha256(prompt.encode()).hexdigest(),
        provider="anthropic", credential_id="anthropic-primary",
        credential_fingerprint=hashlib.sha256(b"top-secret").hexdigest(),
        credential_env_name="ANTHROPIC_API_KEY", model="claude-sonnet",
        prime_version="0.7.4", max_cost_micro_usd=500_000,
        issued_at_ms=now, expires_at_ms=now + 10_000, nonce="nonce",
    )


class _Resolver:
    def __init__(self, **changes: str) -> None:
        self.changes = changes

    def resolve(self, authorization: PrimeAuthorizationRequest) -> ResolvedPrimeCredential:
        facts = {
            "owner_id": authorization.owner_id,
            "payer_id": authorization.payer_id,
            "provider": authorization.provider,
            "credential_id": authorization.credential_id,
            "credential_fingerprint": authorization.credential_fingerprint,
            "env_name": authorization.credential_env_name,
        }
        facts.update({key: value for key, value in self.changes.items() if key != "secret"})
        return ResolvedPrimeCredential(
            **facts, secret=PrimeSecret(self.changes.get("secret", "top-secret"))
        )


def _events() -> list[dict[str, object]]:
    message = {
        "role": "assistant", "content": [{"type": "text", "text": "terminal evidence"}],
        "provider": "anthropic", "model": "claude-sonnet", "stopReason": "stop",
        "requestId": "provider-request", "usage": {
            "input": 11, "output": 7, "cacheRead": 3, "cacheWrite": 2, "cost": {"total": 0.125},
        },
    }
    return [
        {"type": "response", "id": "1", "command": "prompt", "success": True},
        {"type": "turn_end", "id": "provider-event", "message": message},
        {"type": "agent_end", "messages": [deepcopy(message)]},
    ]


def test_success_launches_once_and_accounts_exactly(tmp_path: Path) -> None:
    prompt = "secret prompt"
    binary = _binary(tmp_path, _events())
    installation = verify_prime_agent_installation(binary, environ={"PATH": os.environ["PATH"]})
    ledger = PrimeLedger(tmp_path / "ledger.sqlite3")
    request = _request(prompt)
    outcome = invoke_prime_rpc_evidence(
        prompt=prompt, authorization=request, ledger=ledger, installation=installation,
        credential_resolver=_Resolver(),
        cwd=tmp_path, environ={"PATH": os.environ["PATH"]}, timeout_seconds=0.5, now_ms=lambda: 101,
    )
    assert outcome.evidence is not None
    assert outcome.evidence.text == "terminal evidence"
    assert outcome.receipt.state is PrimeCallState.SUCCEEDED
    assert (outcome.receipt.input_tokens, outcome.receipt.output_tokens) == (11, 7)
    assert outcome.receipt.observed_cost_micro_usd == 125_000
    assert outcome.argv[1:14] == (
        "--mode", "rpc", "--offline", "--no-tools", "--no-extensions",
        "--no-skills", "--no-prompt-templates", "--no-themes", "--no-context-files",
        "--provider", "anthropic", "--model", "claude-sonnet",
    )
    assert outcome.argv[14] == "--session-dir"
    assert Path(outcome.argv[15]).name == "session-dir"
    assert (tmp_path / "received.bin").read_bytes() == (
        b'{"id":"1","type":"prompt","message":"secret prompt"}\n'
    )
    replay = invoke_prime_rpc_evidence(
        prompt=prompt, authorization=request, ledger=ledger, installation=installation,
        credential_resolver=_Resolver(),
        cwd=tmp_path, environ={"PATH": os.environ["PATH"]}, timeout_seconds=0.5, now_ms=lambda: 102,
    )
    assert replay.evidence is None
    assert replay.receipt.state is PrimeCallState.SUCCEEDED
    assert prompt not in repr(replay)
    assert prompt not in repr(outcome.receipt)


@pytest.mark.parametrize(
    "line",
    [
        b'[]\n', b'{bad}\n',
        b'{"type":"x"}', b'{"type":"x"}\nextra', b'\xff\n',
    ],
)
def test_parser_rejects_noncanonical_or_malformed_records(line: bytes) -> None:
    with pytest.raises((ValueError, UnicodeDecodeError, json.JSONDecodeError)):
        _decode(line, 128)


def test_parser_rejects_oversized_record() -> None:
    with pytest.raises(ValueError, match="exceeded"):
        _decode(b'{"type":"x"}\n', 4)


@pytest.mark.parametrize("line", [b'{"type":"x"}\r\n', b'{"type":"x","v":"\xe2\x80\xa8"}\n'])
def test_parser_accepts_crlf_and_unicode_json_data(line: bytes) -> None:
    assert _decode(line, 128)["type"] == "x"


def test_provider_mismatch_retains_hold_and_returns_no_evidence(tmp_path: Path) -> None:
    prompt = "not logged"
    events = _events()
    events[1]["message"]["provider"] = "wrong"  # type: ignore[index]
    binary = _binary(tmp_path, events)
    installation = verify_prime_agent_installation(binary, environ={"PATH": os.environ["PATH"]})
    ledger = PrimeLedger(tmp_path / "ledger.sqlite3")
    outcome = invoke_prime_rpc_evidence(
        prompt=prompt, authorization=_request(prompt), ledger=ledger, installation=installation,
        credential_resolver=_Resolver(),
        cwd=tmp_path, environ={"PATH": os.environ["PATH"]}, timeout_seconds=0.5, now_ms=lambda: 101,
    )
    assert outcome.evidence is None
    assert outcome.receipt.state is PrimeCallState.UNKNOWN
    assert outcome.receipt.held_micro_usd == 500_000
    assert prompt not in repr(outcome)


@pytest.mark.parametrize("mutation", ["missing_usage", "missing_agent_end", "overrun"])
def test_incomplete_or_unsettleable_run_becomes_unknown(
    tmp_path: Path, mutation: str
) -> None:
    prompt = "bounded"
    events = _events()
    if mutation == "missing_usage":
        del events[1]["message"]["usage"]  # type: ignore[index]
    elif mutation == "missing_agent_end":
        events.pop()
    else:
        events[1]["message"]["usage"]["cost"]["total"] = 0.75  # type: ignore[index]
    binary = _binary(tmp_path, events)
    installation = verify_prime_agent_installation(binary, environ={"PATH": os.environ["PATH"]})
    ledger = PrimeLedger(tmp_path / "ledger.sqlite3")
    outcome = invoke_prime_rpc_evidence(
        prompt=prompt, authorization=_request(prompt), ledger=ledger, installation=installation,
        credential_resolver=_Resolver(),
        cwd=tmp_path, environ={"PATH": os.environ["PATH"]}, timeout_seconds=0.5, now_ms=lambda: 101,
    )
    assert outcome.evidence is None
    assert outcome.receipt.state is PrimeCallState.UNKNOWN
    assert outcome.receipt.held_micro_usd == 500_000


def test_settlement_failure_never_exposes_evidence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    prompt = "settle"
    binary = _binary(tmp_path, _events())
    installation = verify_prime_agent_installation(binary, environ={"PATH": os.environ["PATH"]})
    ledger = PrimeLedger(tmp_path / "ledger.sqlite3")
    monkeypatch.setattr(ledger, "succeed", lambda *args, **kwargs: (_ for _ in ()).throw(OSError()))
    outcome = invoke_prime_rpc_evidence(
        prompt=prompt, authorization=_request(prompt), ledger=ledger, installation=installation,
        credential_resolver=_Resolver(),
        cwd=tmp_path, environ={"PATH": os.environ["PATH"]}, timeout_seconds=0.5, now_ms=lambda: 101,
    )
    assert outcome.evidence is None
    assert outcome.receipt.state is PrimeCallState.UNKNOWN


def test_wrong_verified_version_never_authorizes_or_launches(tmp_path: Path) -> None:
    prompt = "version"
    binary = _binary(tmp_path, _events())
    installation = replace(
        verify_prime_agent_installation(binary, environ={"PATH": os.environ["PATH"]}),
        version=(0, 7, 3),
    )
    ledger = PrimeLedger(tmp_path / "ledger.sqlite3")
    with pytest.raises(ValueError, match="version"):
        invoke_prime_rpc_evidence(
            prompt=prompt, authorization=_request(prompt), ledger=ledger,
            installation=installation, credential_resolver=_Resolver(), cwd=tmp_path,
            now_ms=lambda: 101,
        )
    assert not (tmp_path / "received.bin").exists()


@pytest.mark.parametrize("mutation", ["text", "order", "duplicate", "correlation"])
def test_protocol_mismatch_is_rejected(tmp_path: Path, mutation: str) -> None:
    prompt = "protocol"
    events = _events()
    if mutation == "text":
        events[2]["messages"][0]["content"][0]["text"] = "different"  # type: ignore[index]
    elif mutation == "order":
        events[0], events[1] = events[1], events[0]
    elif mutation == "duplicate":
        events.insert(1, dict(events[0]))
    else:
        events[0]["id"] = "wrong"
    binary = _binary(tmp_path, events)
    installation = verify_prime_agent_installation(binary, environ={"PATH": os.environ["PATH"]})
    ledger = PrimeLedger(tmp_path / "ledger.sqlite3")
    outcome = invoke_prime_rpc_evidence(
        prompt=prompt, authorization=_request(prompt), ledger=ledger, installation=installation,
        credential_resolver=_Resolver(),
        cwd=tmp_path, environ={"PATH": os.environ["PATH"]}, timeout_seconds=0.5, now_ms=lambda: 101,
    )
    assert outcome.evidence is None
    assert outcome.receipt.state is PrimeCallState.UNKNOWN


def test_abort_requires_and_drains_exact_terminal_sequence(tmp_path: Path) -> None:
    prompt = "cancel"
    events = _events()
    events.insert(1, {"type": "response", "id": "2", "command": "abort", "success": True})
    events[2]["message"]["stopReason"] = "aborted"  # type: ignore[index]
    events[3]["messages"][0]["stopReason"] = "aborted"  # type: ignore[index]
    binary = _binary(tmp_path, events)
    installation = verify_prime_agent_installation(binary, environ={"PATH": os.environ["PATH"]})
    ledger = PrimeLedger(tmp_path / "ledger.sqlite3")
    outcome = invoke_prime_rpc_evidence(
        prompt=prompt, authorization=_request(prompt), ledger=ledger, installation=installation,
        credential_resolver=_Resolver(),
        cwd=tmp_path, environ={"PATH": os.environ["PATH"]}, timeout_seconds=0.5,
        cancelled=lambda: True, now_ms=lambda: 101,
    )
    assert outcome.evidence is None
    assert outcome.receipt.state is PrimeCallState.CANCELLED
    assert (tmp_path / "received.bin").read_bytes().endswith(b'{"id":"2","type":"abort"}\n')


def test_provider_credential_is_bounded_injected_and_not_reported(tmp_path: Path) -> None:
    prompt = "credential"
    binary = _binary(tmp_path, _events())
    installation = verify_prime_agent_installation(binary, environ={"PATH": os.environ["PATH"]})
    ledger = PrimeLedger(tmp_path / "ledger.sqlite3")
    outcome = invoke_prime_rpc_evidence(
        prompt=prompt, authorization=_request(prompt), ledger=ledger, installation=installation,
        credential_resolver=_Resolver(),
        cwd=tmp_path, environ={"PATH": os.environ["PATH"]}, timeout_seconds=0.5,
        now_ms=lambda: 101,
    )
    assert outcome.evidence is not None
    assert (tmp_path / "credential_seen").read_text() == "True"
    assert "top-secret" not in repr(outcome)


@pytest.mark.parametrize(
    "changes",
    [
        {"owner_id": "other-owner"},
        {"payer_id": "other-payer"},
        {"provider": "openai"},
        {"credential_id": "same-provider-other-key"},
        {"credential_fingerprint": "1" * 64},
        {"env_name": "OPENAI_API_KEY"},
    ],
)
def test_hostile_credential_resolution_never_claims_launches_or_leaks(
    tmp_path: Path, changes: dict[str, str]
) -> None:
    prompt = "hostile"
    binary = _binary(tmp_path, _events())
    installation = verify_prime_agent_installation(binary, environ={"PATH": os.environ["PATH"]})
    ledger = PrimeLedger(tmp_path / "ledger.sqlite3")
    outcome = invoke_prime_rpc_evidence(
        prompt=prompt, authorization=_request(prompt), ledger=ledger, installation=installation,
        credential_resolver=_Resolver(**changes), cwd=tmp_path, now_ms=lambda: 101,
    )
    assert outcome.evidence is None
    assert outcome.receipt.state is PrimeCallState.AUTHORIZED
    assert outcome.detail == "credential resolution failed"
    assert not (tmp_path / "received.bin").exists()
    assert "other-owner-secret" not in repr(outcome)
    assert [event.state for event in ledger.events("request")] == [PrimeCallState.AUTHORIZED]


def test_resource_guard_refuses_before_decrypt_or_spawn(tmp_path: Path) -> None:
    prompt = "guarded"
    binary = _binary(tmp_path, _events())
    installation = verify_prime_agent_installation(binary, environ={"PATH": os.environ["PATH"]})
    ledger = PrimeLedger(tmp_path / "ledger.sqlite3")
    resolves = 0

    class Resolver:
        def resolve(self, _authorization):
            nonlocal resolves
            resolves += 1
            raise AssertionError("credential resolver must remain untouched")

    @contextmanager
    def changed():
        yield False

    outcome = invoke_prime_rpc_evidence(
        prompt=prompt, authorization=_request(prompt), ledger=ledger,
        installation=installation, credential_resolver=Resolver(), cwd=tmp_path,
        pre_start_guard=changed, now_ms=lambda: 101,
    )
    assert resolves == 0
    assert outcome.receipt.state is PrimeCallState.AUTHORIZED
    assert ledger.events("request")[-1].state is PrimeCallState.AUTHORIZED


def test_self_consistent_wrong_provider_environment_is_refused_before_authority(
    tmp_path: Path,
) -> None:
    prompt = "wrong-env"
    assert PRIME_PROVIDER_CREDENTIAL_ENV["anthropic"] == "ANTHROPIC_API_KEY"
    with pytest.raises(ValueError, match="credential environment"):
        replace(_request(prompt), credential_env_name="OPENAI_API_KEY")
    assert not (tmp_path / "received.bin").exists()
