"""Pure authority types for the metered Prime supplemental-evidence lane.

Only digests and opaque identifiers cross this boundary.  In particular, an
authorization never contains a prompt, credential, response, or tool input.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

PRIME_SESSION_CAP_MICRO_USD = 5_000_000
PRIME_PROVIDER_CREDENTIAL_ENV = MappingProxyType(
    {
        "anthropic": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY",
        "google": "GEMINI_API_KEY",
    }
)
_MAX_I64 = 2**63 - 1
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,255}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_ENV_NAME = re.compile(r"[A-Z][A-Z0-9_]{0,127}\Z")


class PrimeAuthorityError(RuntimeError):
    """Base class for fail-closed authority decisions."""


class PrimeAuthorizationRefused(PrimeAuthorityError):
    """The requested reservation is not authorized."""


class PrimeReplayMismatch(PrimeAuthorizationRefused):
    """An opaque replay key was reused with different immutable facts."""


class PrimeLedgerCorrupt(PrimeAuthorityError):
    """The durable authority store cannot safely be interpreted."""


class PrimeCallState(StrEnum):
    AUTHORIZED = "authorized"
    STARTED = "started"
    USAGE_OBSERVED = "usage_observed"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class PrimeAuthorizationRequest:
    owner_id: str
    payer_id: str
    session_id: str
    request_id: str
    idempotency_key: str
    workflow: str
    prompt_digest: str
    provider: str
    credential_id: str
    credential_fingerprint: str
    credential_env_name: str
    model: str
    prime_version: str
    max_cost_micro_usd: int
    issued_at_ms: int
    expires_at_ms: int
    nonce: str

    def __post_init__(self) -> None:
        identifiers = (
            self.owner_id,
            self.payer_id,
            self.session_id,
            self.request_id,
            self.idempotency_key,
            self.workflow,
            self.provider,
            self.credential_id,
            self.model,
            self.prime_version,
            self.nonce,
        )
        if any(
            type(value) is not str or _IDENTIFIER.fullmatch(value) is None for value in identifiers
        ):
            raise ValueError("Prime authorization identifiers are malformed or oversized")
        if type(self.prompt_digest) is not str or _SHA256.fullmatch(self.prompt_digest) is None:
            raise ValueError("prompt_digest must be an exact lowercase SHA-256 digest")
        if (
            type(self.credential_fingerprint) is not str
            or _SHA256.fullmatch(self.credential_fingerprint) is None
        ):
            raise ValueError("credential_fingerprint must be an exact lowercase SHA-256 digest")
        if (
            type(self.credential_env_name) is not str
            or _ENV_NAME.fullmatch(self.credential_env_name) is None
        ):
            raise ValueError("credential_env_name is malformed")
        if PRIME_PROVIDER_CREDENTIAL_ENV.get(self.provider) != self.credential_env_name:
            raise ValueError("provider is unsupported or credential environment is noncanonical")
        if not _integer(self.max_cost_micro_usd) or self.max_cost_micro_usd <= 0:
            raise ValueError("max_cost_micro_usd must be positive")
        if not _timestamp(self.issued_at_ms) or not _timestamp(self.expires_at_ms):
            raise ValueError("authorization timestamps must be bounded integers")
        if self.expires_at_ms <= self.issued_at_ms:
            raise ValueError("authorization timestamps are invalid")


@dataclass(frozen=True, slots=True)
class PrimeUsage:
    provider: str
    model: str
    prime_version: str
    input_tokens: int
    output_tokens: int
    cost_micro_usd: int
    observed_at_ms: int
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    stop_reason: str = "unknown"
    evidence_digest: str = "0" * 64
    output_digest: str = "0" * 64
    provider_request_id: str = "unknown"
    provider_event_id: str = "unknown"

    def __post_init__(self) -> None:
        identifiers = (
            self.provider,
            self.model,
            self.prime_version,
            self.stop_reason,
            self.provider_request_id,
            self.provider_event_id,
        )
        if any(
            type(value) is not str or _IDENTIFIER.fullmatch(value) is None for value in identifiers
        ):
            raise ValueError("usage facts are malformed or oversized")
        if any(
            type(value) is not str or _SHA256.fullmatch(value) is None
            for value in (self.evidence_digest, self.output_digest)
        ):
            raise ValueError("evidence and output digests must be lowercase SHA-256")
        counters = (
            self.input_tokens,
            self.output_tokens,
            self.cache_read_tokens,
            self.cache_write_tokens,
            self.cost_micro_usd,
        )
        if any(not _integer(value) or value < 0 for value in counters):
            raise ValueError("usage counters must be bounded non-negative integers")
        if not _timestamp(self.observed_at_ms):
            raise ValueError("observed_at_ms must be a bounded integer timestamp")


@dataclass(frozen=True, slots=True)
class PrimeReceipt:
    authorization: PrimeAuthorizationRequest
    state: PrimeCallState
    held_micro_usd: int
    charged_micro_usd: int
    input_tokens: int | None
    output_tokens: int | None
    cache_read_tokens: int | None
    cache_write_tokens: int | None
    observed_cost_micro_usd: int | None
    stop_reason: str | None
    evidence_digest: str | None
    output_digest: str | None
    provider_request_id: str | None
    provider_event_id: str | None
    created_at_ms: int
    updated_at_ms: int
    started_at_ms: int | None
    usage_observed_at_ms: int | None
    terminal_at_ms: int | None


@dataclass(frozen=True, slots=True)
class PrimeEvent:
    sequence: int
    request_id: str
    state: PrimeCallState
    occurred_at_ms: int
    fact: str


class PrimeSecret:
    """An intentionally non-serializable, redacted in-memory secret value."""

    __slots__ = ("__value",)

    def __init__(self, value: str) -> None:
        if type(value) is not str or not value:
            raise ValueError("resolved credential secret must be a non-empty string")
        self.__value = value

    def reveal(self) -> str:
        """Reveal only at the final provider environment construction seam."""
        return self.__value

    def __repr__(self) -> str:
        return "PrimeSecret([REDACTED])"

    def __str__(self) -> str:
        return "[REDACTED]"


@dataclass(frozen=True, slots=True)
class ResolvedPrimeCredential:
    """Ephemeral credential plus the immutable non-secret identity it resolves."""

    owner_id: str
    payer_id: str
    provider: str
    credential_id: str
    credential_fingerprint: str
    env_name: str
    secret: PrimeSecret

    def __post_init__(self) -> None:
        facts = (self.owner_id, self.payer_id, self.provider, self.credential_id)
        if any(type(value) is not str or _IDENTIFIER.fullmatch(value) is None for value in facts):
            raise ValueError("resolved credential identity is malformed or oversized")
        if (
            type(self.credential_fingerprint) is not str
            or _SHA256.fullmatch(self.credential_fingerprint) is None
        ):
            raise ValueError("resolved credential fingerprint is malformed")
        if type(self.env_name) is not str or _ENV_NAME.fullmatch(self.env_name) is None:
            raise ValueError("resolved credential environment name is malformed")
        if PRIME_PROVIDER_CREDENTIAL_ENV.get(self.provider) != self.env_name:
            raise ValueError("resolved credential provider or environment is noncanonical")
        if not isinstance(self.secret, PrimeSecret):
            raise ValueError("resolved credential requires a redacted PrimeSecret")

    def matches(self, authority: PrimeAuthorizationRequest) -> bool:
        """Require every credential binding fact to match before secret use."""
        return (
            self.owner_id == authority.owner_id
            and self.payer_id == authority.payer_id
            and self.provider == authority.provider
            and self.credential_id == authority.credential_id
            and self.credential_fingerprint == authority.credential_fingerprint
            and self.env_name == authority.credential_env_name
        )


def _integer(value: object) -> bool:
    return type(value) is int and 0 <= value <= _MAX_I64


def _timestamp(value: object) -> bool:
    return _integer(value)
