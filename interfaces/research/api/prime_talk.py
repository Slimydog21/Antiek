"""Authenticated, metered Prime evidence adapter for Deep Talk-to-Book."""

from __future__ import annotations

import hashlib
import os
import stat
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from fastapi import FastAPI

from orchestration.rlm.prime_agent_backend import PrimeAgentOutcome, PrimeAgentRequest
from orchestration.rlm.prime_authority import (
    PRIME_SESSION_CAP_MICRO_USD,
    PrimeAuthorizationRefused,
    PrimeAuthorizationRequest,
    PrimeSecret,
    ResolvedPrimeCredential,
)
from orchestration.rlm.prime_ledger import PrimeLedger
from orchestration.rlm.prime_rpc_evidence import (
    PrimeRPCEvidence,
    PrimeRPCOutcome,
    invoke_prime_rpc_evidence,
)
from runtime.byok.store import load_credential
from runtime.prime_agent.installation import (
    resolve_prime_agent_binary,
    verify_prime_agent_installation,
)
from runtime.research_runner.byot_provider_catalog import get_model_variant, get_provider_preset
from runtime.research_runner.provider_route_authority import canonical_provider_endpoint

from .settings_models_admin import UserModelChoice, resolve_owner_model_authority


class PrimeTalkUnavailable(RuntimeError):
    pass


def prime_talk_ledger() -> PrimeLedger:
    root = Path(os.environ.get("ANTIEK_PRIME_LEDGER_DIR", Path.home() / ".antiek" / "prime"))
    if root.exists() or root.is_symlink():
        meta = root.lstat()
        if (
            not stat.S_ISDIR(meta.st_mode) or root.is_symlink() or meta.st_uid != os.getuid()
            or stat.S_IMODE(meta.st_mode) != 0o700
        ):
            raise PrimeTalkUnavailable("prime ledger parent is unsafe")
    else:
        root.mkdir(mode=0o700, parents=True)
    return PrimeLedger(root / "talk-to-book.sqlite3")


@dataclass
class _Resolver:
    app: FastAPI
    choice: UserModelChoice
    owner_id: str
    resource_revalidator: Callable[[], bool]

    def resolve(self, authorization: PrimeAuthorizationRequest) -> ResolvedPrimeCredential:
        if not self.resource_revalidator():
            raise PrimeTalkUnavailable("prime_talk_unavailable")
        current = resolve_owner_model_authority(
            self.app, self.choice, owner_user_id=self.owner_id,
        )
        provider = _validate_first_party_route(current)
        secret = load_credential(current.record.cred_ref).reveal()
        return ResolvedPrimeCredential(
            owner_id=self.owner_id, payer_id=self.owner_id, provider=provider,
            credential_id=current.credential_id,
            credential_fingerprint=current.credential_fingerprint,
            env_name={"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY"}[provider],
            secret=PrimeSecret(secret),
        )


def _prime_provider(kind: str) -> str:
    if kind == "anthropic":
        return "anthropic"
    if kind == "openai_compat":
        return "openai"
    raise PrimeTalkUnavailable("prime_talk_unavailable")


def _validate_first_party_route(route: object) -> str:
    record = route.record
    if record.provider_catalog_id not in {"openai", "anthropic"}:
        raise PrimeTalkUnavailable("prime_talk_unavailable")
    preset = get_provider_preset(record.provider_catalog_id)
    get_model_variant(preset, record.model_id)
    endpoint = record.base_url or preset.default_base_url
    if (
        record.provider_kind != preset.adapter_kind
        or canonical_provider_endpoint(endpoint)
        != canonical_provider_endpoint(preset.default_base_url)
    ):
        raise PrimeTalkUnavailable("prime_talk_unavailable")
    return _prime_provider(record.provider_kind)


class MeteredPrimeTalkBackend:
    """Shape-compatible long-corpus backend backed only by metered JSONL-RPC."""

    fail_closed = True

    def __init__(
        self, *, app: FastAPI, choice: UserModelChoice, owner_id: str,
        operation_id: str, document_digest: str,
        resource_revalidator: Callable[[], bool], ledger: PrimeLedger | None = None,
        resource_authority_guard: Callable[[], AbstractContextManager[bool]] | None = None,
        cwd: Path | None = None,
    ) -> None:
        self.app, self.choice, self.owner_id = app, choice, owner_id
        self.operation_id, self.document_digest = operation_id, document_digest
        self.resource_revalidator = resource_revalidator
        self.resource_authority_guard = resource_authority_guard
        self.ledger = ledger or prime_talk_ledger()
        self.cwd = cwd or Path.cwd()
        self.child_journal = None
        self.child_owner: str | None = None
        self.child_parent_id: str | None = None
        self.child_lease_token: str | None = None

    def run(self, request: PrimeAgentRequest) -> PrimeAgentOutcome:
        # Resolve non-secret route facts now; plaintext is decrypted only by the
        # resolver inside invoke_prime_rpc_evidence at the final call seam.
        route = resolve_owner_model_authority(
            self.app, self.choice, owner_user_id=self.owner_id,
        )
        provider = _validate_first_party_route(route)
        now = time.time_ns() // 1_000_000
        installation = verify_prime_agent_installation(resolve_prime_agent_binary())
        request_id = self.operation_id
        prompt_digest = hashlib.sha256(request.prompt.encode()).hexdigest()
        if (
            self.child_journal is not None and self.child_owner is not None
            and self.child_parent_id is not None and self.child_lease_token is not None
        ):
            cached = self.child_journal.claim_child(
                self.child_owner, self.child_parent_id, self.child_lease_token,
                "prime", 0, prompt_digest,
            )
            if cached is not None:
                receipt = self.ledger.receipt(request_id)
                evidence = (
                    PrimeRPCEvidence(
                        str(cached["evidence"]), receipt.authorization.provider,
                        receipt.authorization.model, receipt.authorization.prime_version,
                    ) if cached.get("evidence") is not None else None
                )
                return PrimeRPCOutcome(evidence, receipt, (), "durable child replay")  # type: ignore[return-value]
        try:
            # Replays reuse the exact durable issued/expiry/prompt facts. Never
            # manufacture fresh authorization timestamps for a stable id.
            auth = self.ledger.receipt(request_id).authorization
        except (KeyError, PrimeAuthorizationRefused):
            auth = PrimeAuthorizationRequest(
                owner_id=self.owner_id, payer_id=self.owner_id,
                # One paid user-visible operation == one $5-capped Prime session.
                session_id=hashlib.sha256(
                    f"{self.owner_id}:{self.operation_id}:{self.document_digest}".encode()
                ).hexdigest(),
                request_id=request_id, idempotency_key=request_id,
                workflow="deep-talk-to-book",
                prompt_digest=hashlib.sha256(request.prompt.encode()).hexdigest(),
                provider=provider, credential_id=route.credential_id,
                credential_fingerprint=route.credential_fingerprint,
                credential_env_name={
                    "anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY",
                }[provider],
                model=route.record.model_id,
                prime_version=".".join(map(str, installation.version)),
                max_cost_micro_usd=PRIME_SESSION_CAP_MICRO_USD,
                issued_at_ms=now, expires_at_ms=now + 300_000,
                nonce=hashlib.sha256(f"{request_id}:{self.document_digest}".encode()).hexdigest(),
            )
        # long_corpus consumes the common outcome attributes; the metered RPC
        # outcome deliberately carries the richer durable receipt.
        outcome = invoke_prime_rpc_evidence(
            prompt=request.prompt, authorization=auth, ledger=self.ledger,
            installation=installation,
            credential_resolver=_Resolver(
                self.app, self.choice, self.owner_id, self.resource_revalidator,
            ),
            cwd=self.cwd,
            pre_start_guard=self.resource_authority_guard,
        )
        if (
            self.child_journal is not None and self.child_owner is not None
            and self.child_parent_id is not None and self.child_lease_token is not None
        ):
            self.child_journal.complete_child(
                self.child_owner, self.child_parent_id, self.child_lease_token,
                "prime", 0, prompt_digest,
                {
                    "evidence": outcome.evidence.text if outcome.evidence is not None else None,
                    "state": outcome.receipt.state.value,
                    "charged_micro_usd": outcome.receipt.charged_micro_usd,
                    "held_micro_usd": outcome.receipt.held_micro_usd,
                },
            )
        return outcome  # type: ignore[return-value]


def sanitized_receipt(outcome: object) -> dict[str, object]:
    return sanitized_prime_receipt(cast(Any, outcome).receipt)


def sanitized_prime_receipt(receipt: object) -> dict[str, object]:
    auth = receipt.authorization
    return {
        "operation_id": auth.request_id, "state": receipt.state.value,
        "held_micro_usd": receipt.held_micro_usd,
        "charged_micro_usd": receipt.charged_micro_usd,
        "input_tokens": receipt.input_tokens, "output_tokens": receipt.output_tokens,
        "observed_cost_micro_usd": receipt.observed_cost_micro_usd,
        "provider_id": auth.provider, "model_id": auth.model,
        "prime_version": auth.prime_version,
        "updated_at_ms": receipt.updated_at_ms,
    }
