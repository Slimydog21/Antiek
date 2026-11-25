from __future__ import annotations

import hashlib
import json
import os
from decimal import Decimal
from pathlib import Path

import pytest

from orchestration.rlm.prime_authority import (
    PrimeAuthorizationRefused,
    PrimeAuthorizationRequest,
    PrimeCallState,
    PrimeSecret,
    ResolvedPrimeCredential,
)
from orchestration.rlm.prime_ledger import PrimeLedger
from orchestration.rlm.prime_rpc_evidence import invoke_prime_rpc_evidence
from runtime.prime_agent.installation import verify_prime_agent_installation

_PROMPT = "private preflight control"
_KEY = "synthetic-preflight-key"


class _NoncanonicalFloat(float):
    pass


class _NoncanonicalInt(int):
    pass


class _CountingResolver:
    def __init__(self) -> None:
        self.calls = 0

    def resolve(self, authorization: PrimeAuthorizationRequest) -> ResolvedPrimeCredential:
        self.calls += 1
        return ResolvedPrimeCredential(
            owner_id=authorization.owner_id,
            payer_id=authorization.payer_id,
            provider=authorization.provider,
            credential_id=authorization.credential_id,
            credential_fingerprint=authorization.credential_fingerprint,
            env_name=authorization.credential_env_name,
            secret=PrimeSecret(_KEY),
        )


def _request() -> PrimeAuthorizationRequest:
    return PrimeAuthorizationRequest(
        owner_id="private-owner",
        payer_id="private-payer",
        session_id="private-session",
        request_id="private-request",
        idempotency_key="private-idempotency",
        workflow="evidence",
        prompt_digest=hashlib.sha256(_PROMPT.encode()).hexdigest(),
        provider="anthropic",
        credential_id="private-synthetic",
        credential_fingerprint=hashlib.sha256(_KEY.encode()).hexdigest(),
        credential_env_name="ANTHROPIC_API_KEY",
        model="private-model",
        prime_version="0.9.8",
        max_cost_micro_usd=500_000,
        issued_at_ms=100,
        expires_at_ms=10_100,
        nonce="private-nonce",
    )


def _binary(tmp_path: Path) -> Path:
    message = {
        "role": "assistant",
        "content": [{"type": "text", "text": "bounded evidence"}],
        "provider": "anthropic",
        "model": "private-model",
        "stopReason": "stop",
        "requestId": "private-provider-request",
        "usage": {
            "input": 11,
            "output": 7,
            "cacheRead": 3,
            "cacheWrite": 2,
            "cost": {"total": 0.125},
        },
    }
    events = [
        {"type": "response", "id": "1", "command": "prompt", "success": True},
        {"type": "turn_end", "id": "private-event", "message": message},
        {"type": "agent_end", "messages": [message]},
    ]
    records = b"".join(json.dumps(event).encode() + b"\n" for event in events)
    path = tmp_path / "prime-agent"
    path.write_text(
        "#!/usr/bin/env python3\n"
        "import os,sys\n"
        "if '--version' in sys.argv: print('prime-agent 0.9.8')\n"
        "elif '--help' in sys.argv: print('-p --cwd --offline --no-session --no-tools "
        "--no-extensions --no-skills --no-prompt-templates --no-themes "
        "--no-context-files --mode rpc')\n"
        "else:\n"
        " with open('rpc-launches','ab') as f: f.write(b'launch\\n')\n"
        " command=sys.stdin.buffer.readline()\n"
        f" os.write(1,{records!r})\n"
        " sys.stdin.buffer.read()\n"
    )
    path.chmod(0o700)
    return path


@pytest.mark.parametrize("reserved_before", [False, True], ids=["new", "reserved"])
@pytest.mark.parametrize(
    ("timeout_seconds", "max_record_bytes", "max_total_bytes"),
    [
        pytest.param(float("nan"), 1000, 10_000, id="nan-timeout"),
        pytest.param(float("inf"), 1000, 10_000, id="infinite-timeout"),
        pytest.param(float("-inf"), 1000, 10_000, id="negative-infinite-timeout"),
        pytest.param(0.0, 1000, 10_000, id="zero-timeout"),
        pytest.param(-0.5, 1000, 10_000, id="negative-timeout"),
        pytest.param(True, 1000, 10_000, id="boolean-timeout"),
        pytest.param(False, 1000, 10_000, id="false-timeout"),
        pytest.param(1.0, True, 10_000, id="boolean-record"),
        pytest.param(1.0, False, 10_000, id="false-record"),
        pytest.param(1.0, 1.5, 10_000, id="fractional-record"),
        pytest.param(1.0, 0, 10_000, id="zero-record"),
        pytest.param(1.0, -1, 10_000, id="negative-record"),
        pytest.param(1.0, 1, True, id="boolean-total"),
        pytest.param(1.0, 1, False, id="false-total"),
        pytest.param(1.0, 1000, 10_000.5, id="fractional-total"),
        pytest.param(1.0, 1000, 0, id="zero-total"),
        pytest.param(1.0, 1000, -1, id="negative-total"),
        pytest.param(1.0, 1000, 999, id="total-smaller-than-record"),
        pytest.param(Decimal("1"), 1000, 10_000, id="extended-decimal-timeout"),
        pytest.param(_NoncanonicalFloat(1), 1000, 10_000, id="extended-float-subclass"),
        pytest.param(_NoncanonicalInt(1), 1000, 10_000, id="extended-int-subclass"),
        pytest.param(10**400, 1000, 10_000, id="extended-huge-integer"),
        pytest.param(None, 1000, 10_000, id="extended-timeout-none"),
        pytest.param("1", 1000, 10_000, id="extended-timeout-string"),
        pytest.param(1 + 0j, 1000, 10_000, id="extended-timeout-complex"),
        pytest.param(1.0, _NoncanonicalInt(1000), 10_000, id="extended-record-subclass"),
        pytest.param(1.0, float("nan"), 10_000, id="extended-record-nan"),
        pytest.param(1.0, 1000, float("inf"), id="extended-total-infinity"),
    ],
)
def test_invalid_limits_leave_authority_and_credentials_untouched(
    tmp_path: Path,
    reserved_before: bool,
    timeout_seconds: float,
    max_record_bytes: int,
    max_total_bytes: int,
) -> None:
    tmp_path.chmod(0o700)
    installation = verify_prime_agent_installation(
        _binary(tmp_path), environ={"PATH": os.environ["PATH"]}
    )
    ledger = PrimeLedger(tmp_path / "ledger.sqlite3")
    request = _request()
    if reserved_before:
        ledger.authorize(request, now_ms=101)
    events_before = ledger.events(request.request_id)
    body_before = ledger.path.read_bytes()
    resolver = _CountingResolver()
    clock_calls = 0

    def clock() -> int:
        nonlocal clock_calls
        clock_calls += 1
        return 102

    with pytest.raises(ValueError, match="RPC bounds"):
        invoke_prime_rpc_evidence(
            prompt=_PROMPT,
            authorization=request,
            ledger=ledger,
            installation=installation,
            credential_resolver=resolver,
            cwd=tmp_path,
            environ={"PATH": os.environ["PATH"]},
            timeout_seconds=timeout_seconds,
            max_record_bytes=max_record_bytes,
            max_total_bytes=max_total_bytes,
            now_ms=clock,
        )
    assert clock_calls == 0
    assert resolver.calls == 0
    assert not (tmp_path / "rpc-launches").exists()
    assert ledger.path.read_bytes() == body_before
    assert ledger.events(request.request_id) == events_before
    if reserved_before:
        assert ledger.receipt(request.request_id).state is PrimeCallState.AUTHORIZED
    else:
        with pytest.raises(PrimeAuthorizationRefused, match="unknown Prime request"):
            ledger.receipt(request.request_id)

    outcome = invoke_prime_rpc_evidence(
        prompt=_PROMPT,
        authorization=request,
        ledger=ledger,
        installation=installation,
        credential_resolver=resolver,
        cwd=tmp_path,
        environ={"PATH": os.environ["PATH"]},
        timeout_seconds=1,
        max_record_bytes=1000,
        max_total_bytes=10_000,
        now_ms=clock,
    )
    assert outcome.evidence is not None
    assert outcome.evidence.text == "bounded evidence"
    assert outcome.receipt.state is PrimeCallState.SUCCEEDED
    assert outcome.receipt.held_micro_usd == 0
    assert outcome.receipt.charged_micro_usd == 125_000
    assert resolver.calls == 1
    assert (tmp_path / "rpc-launches").read_bytes() == b"launch\n"
    assert _KEY.encode() not in ledger.path.read_bytes()
    assert _PROMPT.encode() not in ledger.path.read_bytes()
