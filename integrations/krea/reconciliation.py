"""Contract-honest Krea reconciliation adapters.

Krea publishes no reviewed webhook signature contract.  Webhook bytes are
therefore only a bounded wake hint and can never become provider evidence.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from .client import KreaJobObservation

RECONCILIATION_OPENAPI_SUBSET_SHA256 = (
    "0053efe54439fd2e7cca0dc97a6b3ed78091c580b1f9e136b18141350b5d4c88"
)

_STATUS_MAP = {
    "backlogged": "submitted",
    "queued": "submitted",
    "scheduled": "submitted",
    "processing": "running",
    "sampling": "running",
    "intermediate-complete": "running",
    "completed": "succeeded",
    "failed": "failed",
    "cancelled": "cancelled",
}


@dataclass(frozen=True)
class NormalizedKreaObservation:
    provider_job_id: str
    status: str
    result_locators: tuple[str, ...]
    account_identity_digest: str
    raw_payload_digest: str
    source: str = "poll"


@dataclass(frozen=True)
class WebhookWakeReceipt:
    body_digest: str
    byte_count: int
    wake_only: bool = True


def normalize_poll(observation: KreaJobObservation) -> NormalizedKreaObservation:
    return NormalizedKreaObservation(
        provider_job_id=observation.job_id,
        status=_STATUS_MAP[observation.status],
        result_locators=observation.results,
        account_identity_digest=observation.account_identity_digest,
        raw_payload_digest=observation.raw_digest,
    )


def receive_webhook_wake(body: bytes, *, max_bytes: int = 64 * 1024) -> WebhookWakeReceipt:
    """Acknowledge untrusted webhook bytes without parsing or transitioning."""
    if not isinstance(body, bytes) or len(body) > max_bytes:
        raise ValueError("webhook body must be bounded bytes")
    return WebhookWakeReceipt(hashlib.sha256(body).hexdigest(), len(body))


__all__ = [
    "NormalizedKreaObservation",
    "RECONCILIATION_OPENAPI_SUBSET_SHA256",
    "WebhookWakeReceipt",
    "normalize_poll",
    "receive_webhook_wake",
]
