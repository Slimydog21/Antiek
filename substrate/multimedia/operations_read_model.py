"""Redacted operator read models for provider executions."""

from __future__ import annotations

from dataclasses import dataclass

from .provider_execution import ProviderExecutionStatus


@dataclass(frozen=True)
class MultimediaExecutionView:
    execution_id: str
    status: ProviderExecutionStatus
    provider: str
    model: str
    route_policy: str
    approved_ceiling_microdollars: int
    charged_cents: int
    retained_cents: int
    claim_status: str
    created_at: str
    updated_at: str
    cancellation_state: str
    artifact_candidate_count: int
    artifact_ready_count: int
    safe_error_code: str | None


@dataclass(frozen=True)
class MultimediaExecutionPage:
    items: tuple[MultimediaExecutionView, ...]
    next_cursor: str | None


__all__ = ["MultimediaExecutionPage", "MultimediaExecutionView"]
