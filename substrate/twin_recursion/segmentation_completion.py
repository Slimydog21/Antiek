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


def receipt_payload(receipt: SegmentCompletionReceipt | AggregateCompletionReceipt) -> bytes:
    value = asdict(receipt)
    value.pop("signature")
    return canonical_json(value).encode("utf-8")


def verify_receipt(
    receipt: SegmentCompletionReceipt | AggregateCompletionReceipt,
    *,
    now_unix: int | None = None,
    require_configured_key: bool = True,
) -> None:
    if receipt.schema != COMPLETION_SCHEMA:
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
    if isinstance(receipt, SegmentCompletionReceipt):
        text_fields.append(receipt.content_sha256)
        if (
            receipt.segment_index < 0
            or receipt.start_char < 0
            or receipt.end_char <= receipt.start_char
        ):
            raise SegmentationCompletionError("segment receipt range is invalid")
    else:
        text_fields.append(receipt.ordered_segment_bindings_hash)
    if any(not value or len(value) > 512 for value in text_fields):
        raise SegmentationCompletionError("completion receipt field is invalid")
    if receipt.expires_at_unix < (int(time.time()) if now_unix is None else now_unix):
        raise SegmentationCompletionError("completion receipt expired")
    try:
        embedded_key = base64.b64decode(receipt.authority_verify_key, validate=True)
        if receipt.authority_key_id != "key_" + hashlib.sha256(embedded_key).hexdigest():
            raise SegmentationCompletionError("completion authority key identity is invalid")
        if require_configured_key:
            configured = os.environ.get(AUTHORITY_VERIFY_KEY_ENV, "")
            if not configured:
                raise SegmentationCompletionError("completion authority verify key is unavailable")
            if base64.b64decode(configured, validate=True) != embedded_key:
                raise SegmentationCompletionError("completion authority key is not configured")
        verify_key = VerifyKey(embedded_key)
        signature = base64.b64decode(receipt.signature, validate=True)
        verify_key.verify(receipt_payload(receipt), signature)
    except SegmentationCompletionError:
        raise
    except (BadSignatureError, ValueError, TypeError) as exc:
        raise SegmentationCompletionError("completion receipt signature is invalid") from exc


def completion_digest(
    proposal: TwinProposal,
    receipt: SegmentCompletionReceipt | AggregateCompletionReceipt,
) -> str:
    return sha256(canonical_json({"proposal": asdict(proposal), "receipt": asdict(receipt)}))


__all__ = [
    "AggregateCompletionReceipt",
    "COMPLETION_SCHEMA",
    "SegmentCompletionReceipt",
    "SegmentationCompletionError",
    "canonical_json",
    "completion_digest",
    "proposal_hash",
    "receipt_payload",
    "sha256",
    "verify_receipt",
]
