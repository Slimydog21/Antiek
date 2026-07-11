"""Pure Exa paid-operation identity and ledger facade; no transport lives here."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from substrate.midnight_oil.budget_ledger import BudgetLedger, PaidOperation

__all__ = ["PaidSearchEnvelope", "authorize_paid_search", "canonical_request_bytes"]

_MAX_QUERY_BYTES = 32_768
_MAX_DOMAINS = 256
_MAX_PARAMETERS = 128
_MAX_CANONICAL_BYTES = 65_536


def _text(name: str, value: str, *, maximum: int = 512) -> str:
    normalized = unicodedata.normalize("NFC", value)
    if not normalized or "\x00" in normalized or len(normalized.encode()) > maximum:
        raise ValueError(f"{name} must be bounded, non-empty NFC text")
    return normalized


def _canonical_value(value: object, *, depth: int = 0) -> object:
    if depth > 8:
        raise ValueError("parameter nesting exceeds 8 levels")
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        raise ValueError("floats, NaN, and infinity are forbidden in paid request data")
    if isinstance(value, str):
        return _text("parameter string", value, maximum=8_192)
    if isinstance(value, Mapping):
        entries = list(value.items())
        if len(entries) != len(value):
            raise ValueError("stateful request parameter mapping changed during snapshot")
        if len(entries) > _MAX_PARAMETERS:
            raise ValueError("too many request parameter fields")
        output: dict[str, object] = {}
        for raw_key, raw_value in entries:
            if not isinstance(raw_key, str):
                raise ValueError("request parameter keys must be strings")
            key = _text("parameter key", raw_key)
            if key in output:
                raise ValueError("duplicate parameter key after Unicode normalization")
            output[key] = _canonical_value(raw_value, depth=depth + 1)
        return {key: output[key] for key in sorted(output)}
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        if len(value) > _MAX_PARAMETERS:
            raise ValueError("request parameter sequence is too long")
        return [_canonical_value(item, depth=depth + 1) for item in value]
    raise ValueError(f"unsupported request parameter type: {type(value).__name__}")


@dataclass(frozen=True)
class PaidSearchEnvelope:
    """Complete immutable authority for one versioned Exa search intent."""

    run_id: str
    role: str
    owner_id: str
    approved_brief_hash: str
    investigation_id: str
    query: str
    endpoint_version: str
    parameters: Mapping[str, Any]
    domains: tuple[str, ...] | None
    projected_max_cents: int
    currency: str
    catalog_version: str
    policy_version: str
    operation_version: str = "exa-search-operation-v1"
    _canonical_bytes: bytes = field(init=False, repr=False, compare=False)
    _request_hash: str = field(init=False, repr=False, compare=False)
    _operation_id: str = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        canonical = self._build_canonical_object()
        encoded = json.dumps(
            canonical,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        if len(encoded) > _MAX_CANONICAL_BYTES:
            raise ValueError("canonical paid request exceeds 65536 bytes")
        request_hash = hashlib.sha256(encoded).hexdigest()
        operation_id = hashlib.sha256(
            b"antiek-paid-operation-v1\x00" + bytes.fromhex(request_hash)
        ).hexdigest()
        object.__setattr__(self, "_canonical_bytes", encoded)
        object.__setattr__(self, "_request_hash", request_hash)
        object.__setattr__(self, "_operation_id", operation_id)

    def canonical_object(self) -> dict[str, object]:
        """Return a fresh view of the immutable construction-time snapshot."""
        value = json.loads(self._canonical_bytes)
        assert isinstance(value, dict)
        return value

    def _build_canonical_object(self) -> dict[str, object]:
        if len(self.approved_brief_hash) != 64 or any(
            c not in "0123456789abcdef" for c in self.approved_brief_hash
        ):
            raise ValueError("approved_brief_hash must be lowercase SHA-256 hex")
        if self.projected_max_cents <= 0:
            raise ValueError("projected_max_cents must be positive")
        query = _text("query", self.query, maximum=_MAX_QUERY_BYTES)
        domains: list[str] | None
        if self.domains is None:
            domains = None
        else:
            if len(self.domains) > _MAX_DOMAINS:
                raise ValueError("too many domains")
            normalized = [_text("domain", domain, maximum=253).lower() for domain in self.domains]
            if len(set(normalized)) != len(normalized):
                raise ValueError("duplicate domains are forbidden")
            domains = sorted(normalized)
        parameters = _canonical_value(self.parameters)
        assert isinstance(parameters, dict)
        return {
            "approved_brief_hash": self.approved_brief_hash,
            "catalog_version": _text("catalog_version", self.catalog_version),
            "currency": _text("currency", self.currency, maximum=16).upper(),
            "domains": domains,
            "endpoint_version": _text("endpoint_version", self.endpoint_version),
            "investigation_id": _text("investigation_id", self.investigation_id),
            "operation_version": _text("operation_version", self.operation_version),
            "owner_id": _text("owner_id", self.owner_id),
            "parameters": parameters,
            "projected_max_cents": self.projected_max_cents,
            "provider": "exa",
            "query": query,
            "role": _text("role", self.role),
            "run_id": _text("run_id", self.run_id),
            "policy_version": _text("policy_version", self.policy_version),
        }

    @property
    def request_hash(self) -> str:
        return self._request_hash

    @property
    def operation_id(self) -> str:
        return self._operation_id


def canonical_request_bytes(envelope: PaidSearchEnvelope) -> bytes:
    """Return the sole UTF-8/JCS-shaped identity representation."""
    return bytes(envelope._canonical_bytes)  # noqa: SLF001


def authorize_paid_search(ledger: BudgetLedger, envelope: PaidSearchEnvelope) -> PaidOperation:
    """Atomically create/replay the operation and its deterministic budget hold."""
    canonical = envelope.canonical_object()
    return ledger.create_authorized_paid_operation(
        operation_id=envelope.operation_id,
        request_hash=envelope.request_hash,
        run_id=str(canonical["run_id"]),
        role=str(canonical["role"]),
        provider="exa",
        owner_id=str(canonical["owner_id"]),
        approved_brief_hash=envelope.approved_brief_hash,
        projected_max_cents=envelope.projected_max_cents,
        currency=str(canonical["currency"]),
        catalog_version=str(canonical["catalog_version"]),
        policy_version=str(canonical["policy_version"]),
    )
