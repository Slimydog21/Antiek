"""Canonical paid-operation intent profile.

This module implements the root paid-operation authority v1 profile:
UTF-8 JSON, sorted keys, no insignificant whitespace, NFC strings, no floats,
no nulls, no unknown keys, and an explicit hash domain separator.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

MAX_SQLITE_INT = 9_223_372_036_854_775_807
MAX_CONTEXT_PACKET_BYTES = 104_857_600
MAX_DURATION_MINUTES = 10_080
MAX_INPUT_TOKENS = 1_000_000
MAX_OUTPUT_TOKENS = 1_000_000
MAX_STEPS = 10_000
MAX_TEMPERATURE_MILLIONTHS = 1_000_000
MAX_CANONICAL_INTENT_BYTES = 1_048_576
MAX_STRING_BYTES = 65_536
MAX_SEQUENCE_ITEMS = 1_024
INTENT_HASH_DOMAIN = b"antiek.paid-operation.intent.v1\0"

OperationKind = Literal["collective_interrogation_v1", "midnight_oil_v1"]

_IDENTIFIER_RE = re.compile(r"^[a-z0-9][a-z0-9._:-]{0,191}$")
_HASH_RE = re.compile(r"^[a-f0-9]{64}$")

_COMMON_PAYLOAD_KEYS = frozenset(
    {
        "schema_version",
        "quote_cents",
        "ceiling_cents",
        "pricing_snapshot_id",
        "pricing_snapshot_hash",
        "created_at_ms",
        "expires_at_ms",
    }
)
_IDENTITY_KEYS = frozenset({"owner_user_id", "account_id", "operation_id", "kind"})

_COLLECTIVE_KEYS = frozenset(
    {
        "compose_id",
        "compose_fingerprint",
        "frozen_member_ids",
        "frozen_member_body_hashes",
        "question",
        "context_packet_hash",
        "context_packet_bytes",
        "route_id",
        "provider_id",
        "model_id",
        "temperature_millionths",
        "max_input_tokens",
        "max_output_tokens",
        "source_policy_version",
        "answer_schema_version",
    }
)
_MIDNIGHT_OIL_KEYS = frozenset(
    {
        "job_id",
        "goals",
        "duration_minutes",
        "research_brief_hash",
        "acceptance_policy_version",
        "acceptance_policy_hash",
        "retrieval_source_policy_version",
        "route_id",
        "provider_id",
        "model_id",
        "temperature_millionths",
        "max_input_tokens",
        "max_output_tokens",
        "max_steps",
        "deposit_policy_version",
    }
)
_KIND_KEYS: dict[str, frozenset[str]] = {
    "collective_interrogation_v1": _COLLECTIVE_KEYS,
    "midnight_oil_v1": _MIDNIGHT_OIL_KEYS,
}


class IntentContractError(ValueError):
    """Intent payload cannot be represented by the frozen v1 profile."""


@dataclass(frozen=True)
class CanonicalIntent:
    operation_id: str
    owner_user_id: str
    account_id: str
    kind: OperationKind
    quote_cents: int
    ceiling_cents: int
    created_at_ms: int
    expires_at_ms: int
    canonical_bytes: bytes
    intent_hash: str

    @property
    def canonical_json(self) -> str:
        return self.canonical_bytes.decode("utf-8")


def canonicalize_intent(
    *,
    owner_user_id: str,
    account_id: str,
    operation_id: str,
    kind: str,
    payload: Mapping[str, Any],
) -> CanonicalIntent:
    """Return canonical bytes and hash for one paid-operation intent."""
    owner = _identifier("owner_user_id", owner_user_id)
    account = _identifier("account_id", account_id)
    operation = _identifier("operation_id", operation_id)
    canonical_kind = _operation_kind(kind)
    if not isinstance(payload, Mapping):
        raise IntentContractError("payload must be an object")
    if any(key in payload for key in _IDENTITY_KEYS):
        raise IntentContractError("owner/account/operation/kind are server-derived")

    allowed = _COMMON_PAYLOAD_KEYS | _KIND_KEYS[canonical_kind]
    actual = set(payload)
    missing = allowed - actual
    unknown = actual - allowed
    if missing:
        raise IntentContractError(f"payload missing keys: {sorted(missing)}")
    if unknown:
        raise IntentContractError(f"payload has unknown keys: {sorted(unknown)}")

    _reject_unstable_json(payload, path="$")
    common = _common(payload)
    if common["expires_at_ms"] <= common["created_at_ms"]:
        raise IntentContractError("expires_at_ms must be after created_at_ms")
    if common["quote_cents"] > common["ceiling_cents"]:
        raise IntentContractError("quote_cents must be less than or equal to ceiling_cents")

    envelope: dict[str, Any] = {
        "account_id": account,
        "kind": canonical_kind,
        "operation_id": operation,
        "owner_user_id": owner,
        **payload,
    }
    _validate_kind_payload(canonical_kind, envelope)
    canonical_bytes = json.dumps(
        envelope,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    if len(canonical_bytes) > MAX_CANONICAL_INTENT_BYTES:
        raise IntentContractError(
            f"canonical intent exceeds {MAX_CANONICAL_INTENT_BYTES} bytes"
        )
    intent_hash = hashlib.sha256(INTENT_HASH_DOMAIN + canonical_bytes).hexdigest()
    return CanonicalIntent(
        operation_id=operation,
        owner_user_id=owner,
        account_id=account,
        kind=canonical_kind,
        quote_cents=common["quote_cents"],
        ceiling_cents=common["ceiling_cents"],
        created_at_ms=common["created_at_ms"],
        expires_at_ms=common["expires_at_ms"],
        canonical_bytes=canonical_bytes,
        intent_hash=intent_hash,
    )


def _common(payload: Mapping[str, Any]) -> dict[str, int]:
    if _exact_int("schema_version", payload["schema_version"]) != 1:
        raise IntentContractError("schema_version must be 1")
    _identifier("pricing_snapshot_id", payload["pricing_snapshot_id"])
    _sha256("pricing_snapshot_hash", payload["pricing_snapshot_hash"])
    return {
        "quote_cents": _non_negative_int("quote_cents", payload["quote_cents"]),
        "ceiling_cents": _non_negative_int("ceiling_cents", payload["ceiling_cents"]),
        "created_at_ms": _non_negative_int("created_at_ms", payload["created_at_ms"]),
        "expires_at_ms": _non_negative_int("expires_at_ms", payload["expires_at_ms"]),
    }


def _validate_kind_payload(kind: str, envelope: Mapping[str, Any]) -> None:
    shared_ids = ("route_id", "provider_id", "model_id")
    if kind == "collective_interrogation_v1":
        _identifier("compose_id", envelope["compose_id"])
        _sha256("compose_fingerprint", envelope["compose_fingerprint"])
        member_ids = _string_sequence("frozen_member_ids", envelope["frozen_member_ids"])
        member_hashes = _string_sequence(
            "frozen_member_body_hashes", envelope["frozen_member_body_hashes"]
        )
        if not member_ids or len(member_ids) != len(member_hashes):
            raise IntentContractError("frozen members and body hashes must be non-empty pairs")
        if len(set(member_ids)) != len(member_ids):
            raise IntentContractError("frozen_member_ids must be unique")
        for idx, member_id in enumerate(member_ids):
            _identifier(f"frozen_member_ids[{idx}]", member_id)
        for idx, body_hash in enumerate(member_hashes):
            _sha256(f"frozen_member_body_hashes[{idx}]", body_hash)
        _non_empty_string("question", envelope["question"])
        _sha256("context_packet_hash", envelope["context_packet_hash"])
        _bounded_positive_int(
            "context_packet_bytes",
            envelope["context_packet_bytes"],
            MAX_CONTEXT_PACKET_BYTES,
        )
        _identifier("source_policy_version", envelope["source_policy_version"])
        _identifier("answer_schema_version", envelope["answer_schema_version"])
    elif kind == "midnight_oil_v1":
        _identifier("job_id", envelope["job_id"])
        goals = _string_sequence("goals", envelope["goals"])
        if not goals:
            raise IntentContractError("goals must be non-empty")
        if len(set(goals)) != len(goals):
            raise IntentContractError("goals must be unique")
        for idx, goal in enumerate(goals):
            _non_empty_string(f"goals[{idx}]", goal)
        _bounded_positive_int("duration_minutes", envelope["duration_minutes"], MAX_DURATION_MINUTES)
        _sha256("research_brief_hash", envelope["research_brief_hash"])
        _identifier("acceptance_policy_version", envelope["acceptance_policy_version"])
        _sha256("acceptance_policy_hash", envelope["acceptance_policy_hash"])
        _identifier("retrieval_source_policy_version", envelope["retrieval_source_policy_version"])
        _bounded_positive_int("max_steps", envelope["max_steps"], MAX_STEPS)
        _identifier("deposit_policy_version", envelope["deposit_policy_version"])
    else:  # pragma: no cover - _operation_kind prevents this.
        raise IntentContractError("unknown operation kind")

    for name in shared_ids:
        _identifier(name, envelope[name])
    _bounded_non_negative_int(
        "temperature_millionths",
        envelope["temperature_millionths"],
        MAX_TEMPERATURE_MILLIONTHS,
    )
    _bounded_positive_int("max_input_tokens", envelope["max_input_tokens"], MAX_INPUT_TOKENS)
    _bounded_positive_int("max_output_tokens", envelope["max_output_tokens"], MAX_OUTPUT_TOKENS)


def _reject_unstable_json(value: Any, *, path: str) -> None:
    if value is None:
        raise IntentContractError(f"{path} must not be null")
    if isinstance(value, bool):
        return
    if isinstance(value, int):
        if isinstance(value, bool):
            raise IntentContractError(f"{path} must not be bool-as-int")
        if value < 0 or value > MAX_SQLITE_INT:
            raise IntentContractError(f"{path} integer out of range")
        return
    if isinstance(value, float):
        raise IntentContractError(f"{path} must not be a float")
    if isinstance(value, str):
        if unicodedata.normalize("NFC", value) != value:
            raise IntentContractError(f"{path} must be NFC-normalized")
        if len(value.encode("utf-8")) > MAX_STRING_BYTES:
            raise IntentContractError(f"{path} exceeds {MAX_STRING_BYTES} UTF-8 bytes")
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        if len(value) > MAX_SEQUENCE_ITEMS:
            raise IntentContractError(f"{path} exceeds {MAX_SEQUENCE_ITEMS} items")
        for idx, item in enumerate(value):
            _reject_unstable_json(item, path=f"{path}[{idx}]")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise IntentContractError(f"{path} object keys must be strings")
            if unicodedata.normalize("NFC", key) != key:
                raise IntentContractError(f"{path}.{key} key must be NFC-normalized")
            _reject_unstable_json(item, path=f"{path}.{key}")
        return
    raise IntentContractError(f"{path} has unsupported JSON type {type(value).__name__}")


def _operation_kind(value: str) -> OperationKind:
    if value not in _KIND_KEYS:
        raise IntentContractError("unknown operation kind")
    return value  # type: ignore[return-value]


def _identifier(name: str, value: object) -> str:
    text = _non_empty_string(name, value)
    if not _IDENTIFIER_RE.fullmatch(text):
        raise IntentContractError(f"{name} must be a lowercase canonical identifier")
    return text


def _sha256(name: str, value: object) -> str:
    text = _non_empty_string(name, value)
    if not _HASH_RE.fullmatch(text):
        raise IntentContractError(f"{name} must be a lowercase sha256 hex digest")
    return text


def _non_empty_string(name: str, value: object) -> str:
    if not isinstance(value, str) or not value:
        raise IntentContractError(f"{name} must be a non-empty string")
    if unicodedata.normalize("NFC", value) != value:
        raise IntentContractError(f"{name} must be NFC-normalized")
    if len(value.encode("utf-8")) > MAX_STRING_BYTES:
        raise IntentContractError(f"{name} exceeds {MAX_STRING_BYTES} UTF-8 bytes")
    return value


def _string_sequence(name: str, value: object) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise IntentContractError(f"{name} must be an array")
    if len(value) > MAX_SEQUENCE_ITEMS:
        raise IntentContractError(f"{name} exceeds {MAX_SEQUENCE_ITEMS} items")
    result = tuple(value)
    if any(not isinstance(item, str) for item in result):
        raise IntentContractError(f"{name} must contain only strings")
    return result


def _exact_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise IntentContractError(f"{name} must be an integer")
    if value < 0 or value > MAX_SQLITE_INT:
        raise IntentContractError(f"{name} integer out of range")
    return value


def _non_negative_int(name: str, value: object) -> int:
    return _exact_int(name, value)


def _positive_int(name: str, value: object) -> int:
    result = _exact_int(name, value)
    if result <= 0:
        raise IntentContractError(f"{name} must be positive")
    return result


def _bounded_non_negative_int(name: str, value: object, upper_bound: int) -> int:
    result = _non_negative_int(name, value)
    if result > upper_bound:
        raise IntentContractError(f"{name} exceeds maximum {upper_bound}")
    return result


def _bounded_positive_int(name: str, value: object, upper_bound: int) -> int:
    result = _positive_int(name, value)
    if result > upper_bound:
        raise IntentContractError(f"{name} exceeds maximum {upper_bound}")
    return result
