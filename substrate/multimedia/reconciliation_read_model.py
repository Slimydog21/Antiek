"""Redacted operator projection for chapter TTS crash reconciliation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .provider_execution import ProviderExecutionStatus

ReconciliationAction = Literal[
    "wait",
    "quarantine_send",
    "recover_unknown",
    "release_seal",
    "resume_narration",
    "none",
]


@dataclass(frozen=True)
class ChapterTTSReconciliationView:
    execution_id: str
    asset_id: str
    revision_id: str
    attempt_status: str
    provider_status: ProviderExecutionStatus
    next_action: ReconciliationAction
    action_eligible: bool
    send_age_seconds: int | None
    seal_age_seconds: int | None
    seal_lease_id: str | None
    charged_cents: int
    full_ceiling_charged: bool
    raw_audio_present: bool
    raw_audio_hash_valid: bool
    requires_signed_operator_authority: bool
    requires_external_provider_evidence: bool
    parent_resume_eligible: bool
    safe_error_code: str | None


__all__ = ["ChapterTTSReconciliationView", "ReconciliationAction"]
