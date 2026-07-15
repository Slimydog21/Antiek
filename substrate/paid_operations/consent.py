"""One-time HMAC consent for paid-operation authority."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import unicodedata
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from substrate.paid_operations.store import (
    OperationConflict,
    OperationSnapshot,
    PaidOperationStore,
    QueueSnapshot,
    Subject,
)

_TOKEN_DOMAIN = b"antiek.paid-operation.consent.v1\0"
_DEFAULT_TTL_MS = 10 * 60 * 1000
_MAX_OPTIONS_BYTES = 1_048_576


class ConsentAlreadyIssued(OperationConflict):
    """The operation already has one one-time consent bearer."""

    def __init__(self, snapshot: OperationSnapshot) -> None:
        super().__init__("consent_already_issued")
        self.snapshot = snapshot


class ConsentConflict(OperationConflict):
    """Consent bearer is unavailable, expired, claimed, or drifted."""


@dataclass(frozen=True)
class ConsentIssueResult:
    token: str
    snapshot: OperationSnapshot
    cache_control: str = "no-store, private"


@dataclass(frozen=True)
class QueueClaimResult:
    snapshot: OperationSnapshot
    queue: QueueSnapshot


@dataclass(frozen=True)
class ConsentKeyring:
    active_key_id: str
    keys: Mapping[str, bytes]

    def active_key(self) -> bytes:
        key = self.keys.get(self.active_key_id)
        if key is None:
            raise ValueError("active consent signing key is unavailable")
        _key_id(self.active_key_id)
        _key_bytes(key)
        return key

    def key(self, key_id: str) -> bytes:
        _key_id(key_id)
        key = self.keys.get(key_id)
        if key is None:
            raise ConsentConflict("consent is not claimable")
        _key_bytes(key)
        return key


class PaidOperationConsentService:
    """Issue and claim owner/account/intent-bound one-time consent."""

    def __init__(
        self,
        store: PaidOperationStore,
        keyring: ConsentKeyring,
        *,
        clock_ms: Callable[[], int] | None = None,
        nonce_factory: Callable[[], bytes] | None = None,
        ttl_ms: int = _DEFAULT_TTL_MS,
    ) -> None:
        if ttl_ms <= 0:
            raise ValueError("ttl_ms must be positive")
        self._store = store
        self._keyring = keyring
        self._clock_ms = clock_ms or (lambda: 0)
        self._nonce_factory = nonce_factory or (lambda: secrets.token_bytes(32))
        self._ttl_ms = ttl_ms

    def issue(self, subject: Subject, operation_id: str) -> ConsentIssueResult:
        snapshot = self._store.get_owned(subject, operation_id)
        if snapshot is None:
            raise OperationConflict("paid operation is unavailable")
        if snapshot.state != "intent_created":
            raise ConsentAlreadyIssued(snapshot)
        issued_at_ms = self._clock_ms()
        expires_at_ms = issued_at_ms + self._ttl_ms
        if expires_at_ms > snapshot.expires_at_ms:
            expires_at_ms = snapshot.expires_at_ms
        nonce = self._nonce_factory()
        if len(nonce) != 32:
            raise ValueError("consent nonce must be 256 bits")
        envelope = {
            "account_id": snapshot.account_id,
            "ceiling_cents": snapshot.ceiling_cents,
            "expires_at_ms": expires_at_ms,
            "intent_hash": snapshot.intent_hash,
            "issued_at_ms": issued_at_ms,
            "key_id": self._keyring.active_key_id,
            "nonce": _b64(nonce),
            "operation_id": snapshot.operation_id,
            "operation_kind": snapshot.kind,
            "owner_user_id": snapshot.owner_user_id,
            "token_version": 1,
        }
        token = _encode_token(envelope, self._keyring.active_key())
        try:
            issued = self._store.compare_and_swap(
                subject,
                operation_id,
                snapshot.version,
                ["intent_created"],
                "consent_issued",
                {
                    "updated_at_ms": issued_at_ms,
                    "consent_token_hash": token_hash(token),
                    "consent_key_id": self._keyring.active_key_id,
                    "consent_issued_at_ms": issued_at_ms,
                    "consent_expires_at_ms": expires_at_ms,
                },
            )
        except OperationConflict as exc:
            current = self._store.get_owned(subject, operation_id)
            if current is not None and current.state != "intent_created":
                raise ConsentAlreadyIssued(current) from exc
            raise
        return ConsentIssueResult(token=token, snapshot=issued)

    def claim(
        self,
        subject: Subject,
        operation_id: str,
        *,
        token: str | None,
        options: Mapping[str, Any],
    ) -> QueueClaimResult:
        snapshot = self._store.get_owned(subject, operation_id)
        if snapshot is None:
            raise OperationConflict("paid operation is unavailable")
        if snapshot.state == "queued":
            queue = self._store.get_queue(subject, operation_id)
            if queue is None:
                raise ConsentConflict("consent is not claimable")
            if canonicalize_queue_options(options).decode("utf-8") != queue.canonical_options_json:
                raise ConsentConflict("consent is not claimable")
            return QueueClaimResult(snapshot=snapshot, queue=queue)
        if token is None:
            raise ConsentConflict("consent is not claimable")
        envelope = _decode_token(token, self._keyring)
        _assert_envelope_matches(envelope, snapshot, subject)
        now_ms = self._clock_ms()
        token_expires = _int_field(envelope, "expires_at_ms")
        if now_ms >= token_expires:
            raise ConsentConflict("consent is not claimable")
        forbidden = [token]
        forbidden.extend(key.decode("utf-8") for key in self._keyring.keys.values() if _is_utf8(key))
        _reject_secrets_in_options(options, forbidden)
        options_bytes = canonicalize_queue_options(options)
        claimed, queue = self._store.claim_and_enqueue(
            subject,
            operation_id,
            token_hash=token_hash(token),
            now_ms=now_ms,
            canonical_options_json=options_bytes,
        )
        return QueueClaimResult(snapshot=claimed, queue=queue)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def canonicalize_queue_options(options: Mapping[str, Any]) -> bytes:
    _reject_unstable(options, path="$")
    normalized = _normalize_strings(dict(options))
    encoded = json.dumps(
        normalized,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    if len(encoded) > _MAX_OPTIONS_BYTES:
        raise ValueError("canonical options exceed durable limit")
    return encoded


def _encode_token(envelope: Mapping[str, Any], key: bytes) -> str:
    payload = json.dumps(
        dict(envelope),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    signature = hmac.new(key, _TOKEN_DOMAIN + payload, hashlib.sha256).digest()
    return f"{_b64(payload)}.{_b64(signature)}"


def _decode_token(token: str, keyring: ConsentKeyring) -> dict[str, Any]:
    try:
        payload_b64, signature_b64 = token.split(".", 1)
        payload = _unb64(payload_b64)
        signature = _unb64(signature_b64)
        decoded = json.loads(payload)
    except Exception as exc:
        raise ConsentConflict("consent is not claimable") from exc
    if not isinstance(decoded, dict):
        raise ConsentConflict("consent is not claimable")
    key_id = _str_field(decoded, "key_id")
    expected = hmac.new(keyring.key(key_id), _TOKEN_DOMAIN + payload, hashlib.sha256).digest()
    if not hmac.compare_digest(signature, expected):
        raise ConsentConflict("consent is not claimable")
    if decoded.get("token_version") != 1:
        raise ConsentConflict("consent is not claimable")
    return decoded


def _assert_envelope_matches(
    envelope: Mapping[str, Any],
    snapshot: OperationSnapshot,
    subject: Subject,
) -> None:
    expected = {
        "account_id": subject.account_id,
        "ceiling_cents": snapshot.ceiling_cents,
        "intent_hash": snapshot.intent_hash,
        "operation_id": snapshot.operation_id,
        "operation_kind": snapshot.kind,
        "owner_user_id": subject.owner_user_id,
    }
    for key, value in expected.items():
        if envelope.get(key) != value:
            raise ConsentConflict("consent is not claimable")
    if snapshot.consent_key_id != envelope.get("key_id"):
        raise ConsentConflict("consent is not claimable")


def _reject_unstable(value: Any, *, path: str) -> None:
    if value is None:
        raise ValueError(f"{path} must not be null")
    if isinstance(value, bool):
        return
    if isinstance(value, int):
        if value < 0:
            raise ValueError(f"{path} integer out of range")
        return
    if isinstance(value, float):
        raise ValueError(f"{path} must not be a float")
    if isinstance(value, str):
        if not value:
            raise ValueError(f"{path} must not be empty")
        if unicodedata.normalize("NFC", value) != value:
            raise ValueError(f"{path} must be NFC-normalized")
        return
    if isinstance(value, list):
        for idx, item in enumerate(value):
            _reject_unstable(item, path=f"{path}[{idx}]")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str) or not key:
                raise ValueError(f"{path} keys must be non-empty strings")
            _reject_unstable(item, path=f"{path}.{key}")
        return
    raise ValueError(f"{path} has unsupported JSON value")


def _normalize_strings(value: Any) -> Any:
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, list):
        return [_normalize_strings(item) for item in value]
    if isinstance(value, Mapping):
        return {key: _normalize_strings(item) for key, item in value.items()}
    return value


def _reject_secrets_in_options(value: Any, forbidden: list[str]) -> None:
    if isinstance(value, str):
        if any(secret and secret in value for secret in forbidden):
            raise ConsentConflict("consent is not claimable")
        return
    if isinstance(value, list):
        for item in value:
            _reject_secrets_in_options(item, forbidden)
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if any(secret and secret in key for secret in forbidden):
                raise ConsentConflict("consent is not claimable")
            _reject_secrets_in_options(item, forbidden)


def _is_utf8(value: bytes) -> bool:
    try:
        value.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def _str_field(envelope: Mapping[str, Any], key: str) -> str:
    value = envelope.get(key)
    if not isinstance(value, str) or not value:
        raise ConsentConflict("consent is not claimable")
    return value


def _int_field(envelope: Mapping[str, Any], key: str) -> int:
    value = envelope.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ConsentConflict("consent is not claimable")
    return value


def _key_id(value: str) -> None:
    if not value or value.lower() != value or not all(ch.isalnum() or ch in ".:-" for ch in value):
        raise ValueError("consent key id must be canonical")


def _key_bytes(value: bytes) -> None:
    if len(value) < 32:
        raise ValueError("consent signing key must be at least 256 bits")


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


__all__ = [
    "ConsentAlreadyIssued",
    "ConsentConflict",
    "ConsentIssueResult",
    "ConsentKeyring",
    "PaidOperationConsentService",
    "QueueClaimResult",
    "canonicalize_queue_options",
    "token_hash",
]
