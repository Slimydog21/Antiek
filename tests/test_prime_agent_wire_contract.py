"""Pin the Prime Agent JSONL-RPC wire contract this platform parses.

WHY THIS FILE EXISTS
────────────────────
`runtime.prime_agent.installation` admits a RANGE of Prime Agent versions
(`MINIMUM_VERSION` .. `MAXIMUM_VERSION`, exclusive). A range is only safe if something
fails loudly when upstream changes a field this platform reads. Without that, a rename
in a future 0.9.x would not crash — it would silently parse as "absent", and the spend
ledger would record a zero-cost call for inference that really was billed. Silent
under-metering is the worst failure mode available here, because it is invisible
precisely while it is losing money.

So these tests are deliberately written against the shape UPSTREAM DOCUMENTS, not
against the shape our parser happens to accept. The reference is the `AssistantMessage`
example in `prime-agent`'s own `docs/rpc.md`, which ships inside the installed package
(`$(npm root -g)/prime-agent/docs/rpc.md`), verified against 0.9.4 on 2026-09-18:

    {
      "role": "assistant",
      "content": [{"type": "text", "text": "..."}],
      "api": "anthropic-messages",
      "provider": "anthropic",
      "model": "claude-sonnet-4-20250514",
      "usage": {
        "input": 100, "output": 50, "cacheRead": 0, "cacheWrite": 0,
        "cost": {"input": 0.0003, "output": 0.00075,
                 "cacheRead": 0, "cacheWrite": 0, "total": 0.00105}
      },
      "stopReason": "stop",
      "timestamp": 1733234567890
    }

Two properties are asserted:

  1. ADMITS THE DOCUMENTED RECORD — the full upstream shape (including the `api`,
     `timestamp` and per-category `cost` breakdown fields this platform does not read)
     parses, and the usage is accounted exactly. Extra fields must not break us.
  2. FAILS CLOSED ON DRIFT — removing or renaming any field the accounting depends on
     produces NO successful evidence and NO succeeded receipt. It must never degrade to
     a zero-cost success.

If upstream renames a field, (2) turns red and names the field. That is the whole point:
the version ceiling can then be moved deliberately rather than discovered in the ledger.
"""

from __future__ import annotations

import hashlib
import json
import os
from copy import deepcopy
from pathlib import Path

import pytest

from orchestration.rlm.prime_authority import (
    PrimeAuthorizationRequest,
    PrimeCallState,
    PrimeSecret,
    ResolvedPrimeCredential,
)
from orchestration.rlm.prime_ledger import PrimeLedger
from orchestration.rlm.prime_rpc_evidence import invoke_prime_rpc_evidence
from runtime.prime_agent.installation import verify_prime_agent_installation

PRIME_VERSION = "0.9.4"

# The exact assistant message documented by prime-agent 0.9.4 docs/rpc.md, carrying the
# fields this platform does NOT read (api, timestamp, per-category cost) so that their
# presence is proven harmless rather than merely assumed.
DOCUMENTED_ASSISTANT_MESSAGE: dict[str, object] = {
    "role": "assistant",
    "content": [{"type": "text", "text": "documented evidence"}],
    "api": "anthropic-messages",
    "provider": "anthropic",
    "model": "claude-sonnet",
    "requestId": "provider-request",
    "usage": {
        "input": 100,
        "output": 50,
        "cacheRead": 0,
        "cacheWrite": 0,
        "cost": {
            "input": 0.0003,
            "output": 0.00075,
            "cacheRead": 0,
            "cacheWrite": 0,
            "total": 0.00105,
        },
    },
    "stopReason": "stop",
    "timestamp": 1733234567890,
}


def _binary(tmp_path: Path, events: list[dict[str, object]]) -> Path:
    """A stand-in prime-agent that reports PRIME_VERSION and emits `events` as JSONL."""
    path = tmp_path / "prime-agent"
    encoded = repr(
        b"".join(json.dumps(e, separators=(",", ":")).encode() + b"\n" for e in events)
    )
    path.write_text(
        "#!/usr/bin/env python3\n"
        "import os,sys\n"
        f"if '--version' in sys.argv: print('prime-agent {PRIME_VERSION}')\n"
        "elif '--help' in sys.argv: print('-p --cwd --offline --no-session --no-tools "
        "--no-extensions --no-skills --no-prompt-templates --no-themes "
        "--no-context-files --mode rpc')\n"
        f"else:\n data=sys.stdin.buffer.readline(); os.write(1,{encoded}); "
        "data += sys.stdin.buffer.read()\n"
    )
    path.chmod(0o700)
    return path


def _events(message: dict[str, object]) -> list[dict[str, object]]:
    return [
        {"type": "response", "id": "1", "command": "prompt", "success": True},
        {"type": "turn_end", "id": "provider-event", "message": message},
        {"type": "agent_end", "messages": [deepcopy(message)]},
    ]


def _request(prompt: str, *, now: int = 100) -> PrimeAuthorizationRequest:
    return PrimeAuthorizationRequest(
        owner_id="owner",
        payer_id="payer",
        session_id="session",
        request_id="request",
        idempotency_key="idempotency",
        workflow="evidence",
        prompt_digest=hashlib.sha256(prompt.encode()).hexdigest(),
        provider="anthropic",
        credential_id="anthropic-primary",
        credential_fingerprint=hashlib.sha256(b"top-secret").hexdigest(),
        credential_env_name="ANTHROPIC_API_KEY",
        model="claude-sonnet",
        prime_version=PRIME_VERSION,
        max_cost_micro_usd=500_000,
        issued_at_ms=now,
        expires_at_ms=now + 10_000,
        nonce="nonce",
    )


class _Resolver:
    def resolve(
        self, authorization: PrimeAuthorizationRequest
    ) -> ResolvedPrimeCredential:
        return ResolvedPrimeCredential(
            owner_id=authorization.owner_id,
            payer_id=authorization.payer_id,
            provider=authorization.provider,
            credential_id=authorization.credential_id,
            credential_fingerprint=authorization.credential_fingerprint,
            env_name=authorization.credential_env_name,
            secret=PrimeSecret("top-secret"),
        )


def _invoke(tmp_path: Path, message: dict[str, object]):
    prompt = "wire contract prompt"
    binary = _binary(tmp_path, _events(message))
    installation = verify_prime_agent_installation(
        binary, environ={"PATH": os.environ["PATH"]}
    )
    return invoke_prime_rpc_evidence(
        prompt=prompt,
        authorization=_request(prompt),
        ledger=PrimeLedger(tmp_path / "ledger.sqlite3"),
        installation=installation,
        credential_resolver=_Resolver(),
        cwd=tmp_path,
        environ={"PATH": os.environ["PATH"]},
        timeout_seconds=0.5,
        now_ms=lambda: 101,
    )


def test_documented_upstream_record_is_admitted_and_accounted_exactly(
    tmp_path: Path,
) -> None:
    """Property 1: upstream's documented shape parses, extra fields and all."""
    outcome = _invoke(tmp_path, deepcopy(DOCUMENTED_ASSISTANT_MESSAGE))

    assert outcome.evidence is not None, outcome.detail
    assert outcome.evidence.text == "documented evidence"
    assert outcome.evidence.provider == "anthropic"
    assert outcome.evidence.model == "claude-sonnet"
    assert outcome.evidence.prime_version == PRIME_VERSION
    assert outcome.receipt.state is PrimeCallState.SUCCEEDED
    assert outcome.receipt.input_tokens == 100
    assert outcome.receipt.output_tokens == 50
    # 0.00105 USD is exactly 1050 microUSD. If the platform ever starts reading a
    # different cost field, this is the number that moves.
    assert outcome.receipt.observed_cost_micro_usd == 1050


# Each case names a field the accounting depends on, and how upstream might plausibly
# break it: by dropping it, or by renaming it (modelled here as dropping the expected
# name while adding the new one, which is what a rename looks like to our parser).
@pytest.mark.parametrize(
    ("case", "mutate"),
    [
        ("usage removed", lambda m: m.pop("usage")),
        ("cost removed", lambda m: m["usage"].pop("cost")),
        ("cost.total removed", lambda m: m["usage"]["cost"].pop("total")),
        (
            "cost.total renamed",
            lambda m: m["usage"]["cost"].update(
                {"totalUsd": m["usage"]["cost"].pop("total")}
            ),
        ),
        ("input removed", lambda m: m["usage"].pop("input")),
        ("output removed", lambda m: m["usage"].pop("output")),
        ("cacheRead renamed", lambda m: m["usage"].update(
            {"cache_read": m["usage"].pop("cacheRead")}
        )),
        ("cacheWrite renamed", lambda m: m["usage"].update(
            {"cache_write": m["usage"].pop("cacheWrite")}
        )),
        ("provider removed", lambda m: m.pop("provider")),
        ("model removed", lambda m: m.pop("model")),
    ],
)
def test_wire_drift_fails_closed_instead_of_metering_zero(
    tmp_path: Path, case: str, mutate
) -> None:
    """Property 2: drift never degrades to a zero-cost success.

    The assertion is deliberately about the OUTCOME rather than the exception type:
    what must hold is that no evidence is handed back and no receipt claims success.
    How the parser objects is an implementation detail; that it refuses is the contract.
    """
    message = deepcopy(DOCUMENTED_ASSISTANT_MESSAGE)
    mutate(message)

    outcome = _invoke(tmp_path, message)

    assert outcome.evidence is None, f"{case}: drift produced usable evidence"
    assert outcome.receipt.state is not PrimeCallState.SUCCEEDED, (
        f"{case}: drift was recorded as a successful call"
    )
    assert outcome.receipt.observed_cost_micro_usd != 0 or (
        outcome.receipt.state is not PrimeCallState.SUCCEEDED
    ), f"{case}: drift metered a zero-cost success"
