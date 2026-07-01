"""Typed event helpers for RLM session lifecycle events."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from substrate.schemas.events import Event, TypedPayload


def make_rlm_event(
    *,
    investigation_id: str,
    payload: TypedPayload,
    document_id: str | None = None,
    param_version: str = "rlm-v0",
) -> Event:
    """Build a typed Event envelope for an RLM payload.

    RLM payloads all carry an ``action_type`` discriminator, so callers should
    not separately choose the envelope action type.
    """

    return Event(
        event_id=f"evt-{uuid.uuid4().hex[:12]}",
        investigation_id=investigation_id,
        action_type=payload.action_type,
        payload=payload,
        param_version=param_version,
        emitted_at=datetime.now(UTC),
        document_id=document_id,
    )


class RLMEventEmitter:
    """Small adapter around the process broadcaster.

    It keeps RLM session code from reimplementing typed ``Event`` envelope
    construction at every lifecycle edge.
    """

    def __init__(
        self,
        broadcast: Callable[[Event], Awaitable[None]],
        *,
        investigation_id: str,
        document_id: str | None = None,
        param_version: str = "rlm-v0",
    ) -> None:
        self._broadcast = broadcast
        self._investigation_id = investigation_id
        self._document_id = document_id
        self._param_version = param_version

    async def emit(self, payload: TypedPayload) -> Event:
        event = make_rlm_event(
            investigation_id=self._investigation_id,
            payload=payload,
            document_id=self._document_id,
            param_version=self._param_version,
        )
        await self._broadcast(event)
        return event


__all__ = ["RLMEventEmitter", "make_rlm_event"]
