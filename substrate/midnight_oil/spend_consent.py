"""Durable, operator-bound spend consent for Midnight Oil.

This module is deliberately below the HTTP and worker layers.  Callers must
derive ``operator_id`` from authenticated server state, never from request
payloads.  Issuing a receipt performs no provider call and mutates no budget
ledger; claiming it only records that the exact consent was consumed.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import sqlite3
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final

_DOMAIN: Final = b"antiek.midnight-oil.spend-consent.v1\x00"
_SCHEMA_VERSION: Final = 1


class ConsentRejection(StrEnum):
    MALFORMED = "malformed"
    UNKNOWN_KEY = "unknown_key"
    BAD_SIGNATURE = "bad_signature"
    EXPIRED = "expired"
    NOT_YET_VALID = "not_yet_valid"
    WRONG_OPERATOR = "wrong_operator"
    WRONG_JOB = "wrong_job"
    CONFIG_DRIFT = "config_drift"
    CEILING_MISMATCH = "ceiling_mismatch"
    UNKNOWN_RECEIPT = "unknown_receipt"
    CONFLICTING_REPLAY = "conflicting_replay"


class ConsentRejected(ValueError):
    """Fail-closed rejection that never includes receipt or key material."""

    def __init__(self, reason: ConsentRejection) -> None:
        self.reason = reason
        super().__init__(f"spend consent rejected: {reason.value}")


@dataclass(frozen=True)
class JobConsentConfig:
    job_id: str
    goals: tuple[str, ...]
    duration_minutes: int
    model_id: str | None
    research_tier: str
    fanout_depth: int
    asset_id: str | None

    def canonical_hash(self) -> str:
        payload = _canonical_json(asdict(self))
        return hashlib.sha256(b"antiek.midnight-oil.job-config.v1\x00" + payload).hexdigest()


@dataclass(frozen=True)
class ConsentReceipt:
    receipt_id: str
    operator_id: str
    job_id: str
    config_hash: str
    ceiling_cents: int
    issued_at_ms: int
    expires_at_ms: int
    nonce: str
    key_id: str


@dataclass(frozen=True)
class ClaimResult:
    receipt: ConsentReceipt
    claimed_now: bool


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    try:
        return base64.b64decode(value + padding, altchars=b"-_", validate=True)
    except (ValueError, TypeError) as exc:
        raise ConsentRejected(ConsentRejection.MALFORMED) from exc


def _validate_text(value: str, *, maximum: int = 256) -> str:
    cleaned = value.strip()
    if not cleaned or len(cleaned) > maximum or any(ord(char) < 32 for char in cleaned):
        raise ValueError("consent text field is invalid")
    return cleaned


def _validate_config(config: JobConsentConfig) -> None:
    _validate_text(config.job_id)
    _validate_text(config.research_tier, maximum=32)
    if not config.goals or any(not goal.strip() for goal in config.goals):
        raise ValueError("at least one non-empty goal is required")
    if config.duration_minutes <= 0 or config.fanout_depth <= 0:
        raise ValueError("duration and fanout must be positive")


def _receipt_payload(receipt: ConsentReceipt) -> bytes:
    return _canonical_json(
        {
            "schema_version": _SCHEMA_VERSION,
            **asdict(receipt),
        }
    )


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _validate_receipt(receipt: ConsentReceipt) -> None:
    _validate_text(receipt.receipt_id, maximum=64)
    _validate_text(receipt.operator_id)
    _validate_text(receipt.job_id)
    _validate_text(receipt.nonce)
    _validate_text(receipt.key_id, maximum=64)
    if len(receipt.receipt_id) != 64 or len(receipt.config_hash) != 64:
        raise ValueError("receipt hashes must be SHA-256 hex")
    try:
        bytes.fromhex(receipt.receipt_id)
        bytes.fromhex(receipt.config_hash)
    except ValueError as exc:
        raise ValueError("receipt hashes must be SHA-256 hex") from exc
    integers = (receipt.ceiling_cents, receipt.issued_at_ms, receipt.expires_at_ms)
    if any(isinstance(value, bool) or not isinstance(value, int) for value in integers):
        raise ValueError("receipt numeric fields must be integers")
    if receipt.ceiling_cents <= 0 or receipt.issued_at_ms < 0:
        raise ValueError("receipt numeric fields are invalid")
    if receipt.expires_at_ms <= receipt.issued_at_ms:
        raise ValueError("receipt expiry must follow issuance")


def _sign(payload: bytes, key: bytes) -> bytes:
    if len(key) < 32:
        raise ValueError("consent signing keys must contain at least 32 bytes")
    return hmac.digest(key, _DOMAIN + payload, "sha256")


class SpendConsentStore:
    """SQLite-backed receipt issuance and atomic one-shot claiming."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS spend_consents (
                    receipt_id TEXT PRIMARY KEY,
                    operator_id TEXT NOT NULL,
                    job_id TEXT NOT NULL,
                    config_hash TEXT NOT NULL,
                    ceiling_cents INTEGER NOT NULL,
                    issued_at_ms INTEGER NOT NULL,
                    expires_at_ms INTEGER NOT NULL,
                    nonce TEXT NOT NULL,
                    key_id TEXT NOT NULL,
                    token_hash TEXT NOT NULL,
                    claimed_at_ms INTEGER,
                    UNIQUE(operator_id, job_id, nonce)
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30.0, isolation_level=None)
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    def issue(
        self,
        *,
        operator_id: str,
        config: JobConsentConfig,
        ceiling_cents: int,
        issued_at_ms: int,
        expires_at_ms: int,
        nonce: str,
        key_id: str,
        signing_key: bytes,
    ) -> str:
        operator = _validate_text(operator_id)
        nonce_value = _validate_text(nonce)
        kid = _validate_text(key_id, maximum=64)
        _validate_config(config)
        if ceiling_cents <= 0:
            raise ValueError("ceiling_cents must be positive")
        if issued_at_ms < 0 or expires_at_ms <= issued_at_ms:
            raise ValueError("consent expiry must be after issuance")
        receipt_id = hashlib.sha256(
            _DOMAIN
            + _canonical_json(
                {
                    "operator_id": operator,
                    "job_id": config.job_id,
                    "nonce": nonce_value,
                }
            )
        ).hexdigest()
        receipt = ConsentReceipt(
            receipt_id=receipt_id,
            operator_id=operator,
            job_id=config.job_id,
            config_hash=config.canonical_hash(),
            ceiling_cents=ceiling_cents,
            issued_at_ms=issued_at_ms,
            expires_at_ms=expires_at_ms,
            nonce=nonce_value,
            key_id=kid,
        )
        _validate_receipt(receipt)
        payload = _receipt_payload(receipt)
        token = f"{_b64encode(payload)}.{_b64encode(_sign(payload, signing_key))}"
        token_hash = hashlib.sha256(token.encode("ascii")).hexdigest()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    """
                    INSERT INTO spend_consents VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                    """,
                    (
                        receipt.receipt_id,
                        receipt.operator_id,
                        receipt.job_id,
                        receipt.config_hash,
                        receipt.ceiling_cents,
                        receipt.issued_at_ms,
                        receipt.expires_at_ms,
                        receipt.nonce,
                        receipt.key_id,
                        token_hash,
                    ),
                )
                connection.execute("COMMIT")
            except sqlite3.IntegrityError:
                connection.execute("ROLLBACK")
                raise ConsentRejected(ConsentRejection.CONFLICTING_REPLAY) from None
        return token

    def claim(
        self,
        token: str,
        *,
        expected_operator_id: str,
        expected_config: JobConsentConfig,
        expected_ceiling_cents: int,
        now_ms: int,
        verification_keys: Mapping[str, bytes],
    ) -> ClaimResult:
        receipt = decode_and_verify(token, verification_keys=verification_keys)
        operator = _validate_text(expected_operator_id)
        _validate_config(expected_config)
        if now_ms < receipt.issued_at_ms:
            raise ConsentRejected(ConsentRejection.NOT_YET_VALID)
        if now_ms >= receipt.expires_at_ms:
            raise ConsentRejected(ConsentRejection.EXPIRED)
        if not hmac.compare_digest(receipt.operator_id, operator):
            raise ConsentRejected(ConsentRejection.WRONG_OPERATOR)
        if not hmac.compare_digest(receipt.job_id, expected_config.job_id):
            raise ConsentRejected(ConsentRejection.WRONG_JOB)
        if not hmac.compare_digest(receipt.config_hash, expected_config.canonical_hash()):
            raise ConsentRejected(ConsentRejection.CONFIG_DRIFT)
        if receipt.ceiling_cents != expected_ceiling_cents:
            raise ConsentRejected(ConsentRejection.CEILING_MISMATCH)
        token_hash = hashlib.sha256(token.encode("ascii")).hexdigest()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT token_hash, claimed_at_ms FROM spend_consents WHERE receipt_id = ?",
                (receipt.receipt_id,),
            ).fetchone()
            if row is None:
                connection.execute("ROLLBACK")
                raise ConsentRejected(ConsentRejection.UNKNOWN_RECEIPT)
            if not hmac.compare_digest(str(row[0]), token_hash):
                connection.execute("ROLLBACK")
                raise ConsentRejected(ConsentRejection.CONFLICTING_REPLAY)
            if row[1] is not None:
                connection.execute("COMMIT")
                return ClaimResult(receipt=receipt, claimed_now=False)
            connection.execute(
                "UPDATE spend_consents SET claimed_at_ms = ? WHERE receipt_id = ?",
                (now_ms, receipt.receipt_id),
            )
            connection.execute("COMMIT")
        return ClaimResult(receipt=receipt, claimed_now=True)


def decode_and_verify(token: str, *, verification_keys: Mapping[str, bytes]) -> ConsentReceipt:
    if not isinstance(token, str) or len(token) > 8_192:
        raise ConsentRejected(ConsentRejection.MALFORMED)
    try:
        encoded_payload, encoded_signature = token.split(".")
    except ValueError as exc:
        raise ConsentRejected(ConsentRejection.MALFORMED) from exc
    payload = _b64decode(encoded_payload)
    signature = _b64decode(encoded_signature)
    try:
        raw = json.loads(payload, object_pairs_hook=_reject_duplicate_keys)
        if not isinstance(raw, dict) or raw.pop("schema_version") != _SCHEMA_VERSION:
            raise ValueError
        receipt = ConsentReceipt(**raw)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ConsentRejected(ConsentRejection.MALFORMED) from exc
    try:
        _validate_receipt(receipt)
        if not hmac.compare_digest(payload, _receipt_payload(receipt)):
            raise ValueError("receipt is not canonical")
    except ValueError as exc:
        raise ConsentRejected(ConsentRejection.MALFORMED) from exc
    key = verification_keys.get(receipt.key_id)
    if key is None:
        raise ConsentRejected(ConsentRejection.UNKNOWN_KEY)
    expected = _sign(payload, key)
    if not hmac.compare_digest(signature, expected):
        raise ConsentRejected(ConsentRejection.BAD_SIGNATURE)
    return receipt


__all__ = [
    "ClaimResult",
    "ConsentReceipt",
    "ConsentRejected",
    "ConsentRejection",
    "JobConsentConfig",
    "SpendConsentStore",
    "decode_and_verify",
]
