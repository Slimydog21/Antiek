"""Signed completion claims for segmented twin generation."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from dataclasses import asdict, dataclass

from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey

from substrate.twin_note_taker import AUTHORITY_VERIFY_KEY_ENV, TwinProposal

COMPLETION_SCHEMA = "antiek.twin-segment-completion.v1"
PAID_COMPLETION_SCHEMA = "antiek.twin-segment-completion.v2"
AUTHORITY_KEYRING_ENV = "ANTIEK_TWIN_AUTHORITY_VERIFY_KEYRING"


class SegmentationCompletionError(ValueError):
    """Signed segmented completion evidence is invalid or mismatched."""


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def proposal_hash(proposal: TwinProposal) -> str:
    return sha256(canonical_json(asdict(proposal)))


@dataclass(frozen=True)
class SegmentCompletionReceipt:
    schema: str
    receipt_id: str
    account_id: str
    manifest_hash: str
    parent_source_hash: str
    segment_index: int
    start_char: int
    end_char: int
    content_sha256: str
    model_id: str
    budget_authority_id: str
    proposal_hash: str
    authority_key_id: str
    authority_verify_key: str
    expires_at_unix: int
    signature: str


@dataclass(frozen=True)
class AggregateCompletionReceipt:
    schema: str
    receipt_id: str
    account_id: str
    manifest_hash: str
    parent_source_hash: str
    ordered_segment_bindings_hash: str
    model_id: str
    budget_authority_id: str
    proposal_hash: str
    authority_key_id: str
    authority_verify_key: str
    expires_at_unix: int
    signature: str


@dataclass(frozen=True)
class SegmentCompletionReceiptV2:
    schema: str
    receipt_id: str
    account_id: str
    manifest_hash: str
    parent_source_hash: str
    segment_index: int
    start_char: int
    end_char: int
    content_sha256: str
    model_id: str
    budget_authority_id: str
    spend_run_id: str
    paid_hold_id: str
    proposal_hash: str
    provider: str
    provider_response_id: str
    provider_idempotency_key_sha256: str
    actual_cents: int
    currency: str
    settlement_evidence_sha256: str
    settlement_intent_sha256: str
    settled_at: str
    ceiling_breached: bool
    operation_digest: str
    authority_key_id: str
    authority_verify_key: str
    expires_at_unix: int
    signature: str


@dataclass(frozen=True)
class AggregateCompletionReceiptV2:
    schema: str
    receipt_id: str
    account_id: str
    manifest_hash: str
    parent_source_hash: str
    ordered_segment_bindings_hash: str
    model_id: str
    budget_authority_id: str
    spend_run_id: str
    paid_hold_id: str
    proposal_hash: str
    provider: str
    provider_response_id: str
    provider_idempotency_key_sha256: str
    actual_cents: int
    currency: str
    settlement_evidence_sha256: str
    settlement_intent_sha256: str
    settled_at: str
    ceiling_breached: bool
    operation_digest: str
    authority_key_id: str
    authority_verify_key: str
    expires_at_unix: int
    signature: str


CompletionReceipt = (
    SegmentCompletionReceipt
    | AggregateCompletionReceipt
    | SegmentCompletionReceiptV2
    | AggregateCompletionReceiptV2
)


def receipt_payload(receipt: CompletionReceipt) -> bytes:
    value = asdict(receipt)
    value.pop("signature")
    return canonical_json(value).encode("utf-8")


def verify_receipt(
    receipt: CompletionReceipt,
    *,
    now_unix: int | None = None,
    require_configured_key: bool = True,
) -> None:
    if receipt.schema not in (COMPLETION_SCHEMA, PAID_COMPLETION_SCHEMA):
        raise SegmentationCompletionError("completion receipt schema is unsupported")
    text_fields = [
        receipt.receipt_id,
        receipt.account_id,
        receipt.manifest_hash,
        receipt.parent_source_hash,
        receipt.model_id,
        receipt.budget_authority_id,
        receipt.proposal_hash,
        receipt.authority_key_id,
        receipt.authority_verify_key,
    ]
    if isinstance(receipt, (SegmentCompletionReceipt, SegmentCompletionReceiptV2)):
        text_fields.append(receipt.content_sha256)
        if (
            receipt.segment_index < 0
            or receipt.start_char < 0
            or receipt.end_char <= receipt.start_char
        ):
            raise SegmentationCompletionError("segment receipt range is invalid")
    else:
        text_fields.append(receipt.ordered_segment_bindings_hash)
    if isinstance(receipt, (SegmentCompletionReceiptV2, AggregateCompletionReceiptV2)):
        text_fields.extend(
            [
                receipt.provider,
                receipt.spend_run_id,
                receipt.paid_hold_id,
                receipt.provider_response_id,
                receipt.provider_idempotency_key_sha256,
                receipt.currency,
                receipt.settlement_evidence_sha256,
                receipt.settlement_intent_sha256,
                receipt.settled_at,
                receipt.operation_digest,
            ]
        )
        if receipt.schema != PAID_COMPLETION_SCHEMA:
            raise SegmentationCompletionError("paid completion receipt schema is invalid")
        if isinstance(receipt.actual_cents, bool) or not isinstance(receipt.actual_cents, int):
            raise SegmentationCompletionError("paid completion amount is invalid")
        if receipt.actual_cents < 0:
            raise SegmentationCompletionError("paid completion amount is invalid")
        if type(receipt.ceiling_breached) is not bool:
            raise SegmentationCompletionError("paid completion breach flag is invalid")
        if receipt.currency != "USD" or receipt.budget_authority_id != receipt.paid_hold_id:
            raise SegmentationCompletionError("paid completion authority is inconsistent")
        if any(
            len(value) != 64 or any(char not in "0123456789abcdef" for char in value)
            for value in (
                receipt.provider_idempotency_key_sha256,
                receipt.settlement_evidence_sha256,
                receipt.settlement_intent_sha256,
                receipt.operation_digest,
            )
        ):
            raise SegmentationCompletionError("paid completion digest is invalid")
    elif receipt.schema != COMPLETION_SCHEMA:
        raise SegmentationCompletionError("v1 receipt cannot represent paid proof")
    if any(not value or len(value) > 512 for value in text_fields):
        raise SegmentationCompletionError("completion receipt field is invalid")
    if receipt.expires_at_unix < (int(time.time()) if now_unix is None else now_unix):
        raise SegmentationCompletionError("completion receipt expired")
    try:
        embedded_key = base64.b64decode(receipt.authority_verify_key, validate=True)
        if receipt.authority_key_id != "key_" + hashlib.sha256(embedded_key).hexdigest():
            raise SegmentationCompletionError("completion authority key identity is invalid")
        configured = os.environ.get(AUTHORITY_VERIFY_KEY_ENV, "")
        trusted_keys: dict[str, str] = {}
        raw_keyring = os.environ.get(AUTHORITY_KEYRING_ENV, "")
        if raw_keyring:
            decoded_keyring = json.loads(raw_keyring)
            if not isinstance(decoded_keyring, dict) or not all(
                isinstance(key, str) and isinstance(value, str)
                for key, value in decoded_keyring.items()
            ):
                raise SegmentationCompletionError("completion authority keyring is invalid")
            trusted_keys = decoded_keyring
        if configured:
            configured_bytes = base64.b64decode(configured, validate=True)
            trusted_keys["key_" + hashlib.sha256(configured_bytes).hexdigest()] = configured
        if require_configured_key:
            if not configured:
                raise SegmentationCompletionError("completion authority verify key is unavailable")
            if configured_bytes != embedded_key:
                raise SegmentationCompletionError("completion authority key is not configured")
        trusted = trusted_keys.get(receipt.authority_key_id)
        if trusted is None or base64.b64decode(trusted, validate=True) != embedded_key:
            raise SegmentationCompletionError("completion authority key is not trusted")
        verify_key = VerifyKey(embedded_key)
        signature = base64.b64decode(receipt.signature, validate=True)
        verify_key.verify(receipt_payload(receipt), signature)
    except SegmentationCompletionError:
        raise
    except (BadSignatureError, ValueError, TypeError) as exc:
        raise SegmentationCompletionError("completion receipt signature is invalid") from exc


def completion_digest(
    proposal: TwinProposal,
    receipt: CompletionReceipt,
) -> str:
    return sha256(canonical_json({"proposal": asdict(proposal), "receipt": asdict(receipt)}))


__all__ = [
    "AggregateCompletionReceipt",
    "AggregateCompletionReceiptV2",
    "AUTHORITY_KEYRING_ENV",
    "COMPLETION_SCHEMA",
    "PAID_COMPLETION_SCHEMA",
    "SegmentCompletionReceipt",
    "SegmentCompletionReceiptV2",
    "SegmentationCompletionError",
    "canonical_json",
    "completion_digest",
    "proposal_hash",
    "receipt_payload",
    "sha256",
    "verify_receipt",
]
