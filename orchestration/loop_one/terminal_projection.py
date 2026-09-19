"""Canonical SPR-AHT-49 terminal-projection identity and event projector."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from substrate.schemas import (
    ActionType,
    Event,
    InvestigationProjectionCompletedPayload,
    InvestigationProjectionEffectRecordedPayload,
    InvestigationProjectionFailedPayload,
    InvestigationProjectionRequestedPayload,
)


class InvestigationProjectionConflict(ValueError):
    """Projection receipts are missing, contradictory, or out of order."""


@dataclass(frozen=True)
class InvestigationProjectionSnapshot:
    projection_id: str
    request: Event
    synthesis_effect: Event | None
    html_effect: Event | None
    failures: tuple[Event, ...]
    completion: Event | None

    @property
    def complete(self) -> bool:
        return self.completion is not None


def investigation_projection_id(
    execution_id: str, synthesis_event_id: str, input_sha256: str
) -> str:
    return hashlib.sha256(
        b"antiek.investigation-projection.v1\x00"
        + execution_id.encode("utf-8")
        + b"\x00"
        + synthesis_event_id.encode("utf-8")
        + b"\x00"
        + input_sha256.encode("ascii")
    ).hexdigest()


def investigation_projection_event_id(projection_id: str, suffix: str) -> str:
    digest = hashlib.sha256(
        b"antiek.investigation-projection-event.v1\x00"
        + projection_id.encode("ascii")
        + b"\x00"
        + suffix.encode("ascii")
    ).hexdigest()[:32]
    return f"evt-investigation-projection-{digest}"


def projection_effects_sha256(synthesis_effect: Event, html_effect: Event) -> str:
    canonical = json.dumps(
        [
            synthesis_effect.model_dump(mode="json"),
            html_effect.model_dump(mode="json"),
        ],
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def project_investigation_projection(
    rows: list[dict[str, Any]],
    *,
    execution_id: str,
    generation: int,
) -> InvestigationProjectionSnapshot | None:
    """Validate one projection lifecycle from append-ordered authorized rows."""
    events = [Event.model_validate(row) for row in rows]
    projection_events = [
        event
        for event in events
        if event.action_type
        in {
            ActionType.INVESTIGATION_PROJECTION_REQUESTED,
            ActionType.INVESTIGATION_PROJECTION_EFFECT_RECORDED,
            ActionType.INVESTIGATION_PROJECTION_FAILED,
            ActionType.INVESTIGATION_PROJECTION_COMPLETED,
        }
    ]
    if not projection_events:
        return None
    # A takeover keeps the lease's deterministic execution_id and increments
    # generation. Older receipts are therefore recovery inputs, not stale
    # mutation authority; the current fence guards every new append/mutation
    # and the orchestrator externally re-verifies both effects before terminal.
    if any(
        event.execution_generation is None or event.execution_generation > generation
        for event in projection_events
    ):
        raise InvestigationProjectionConflict("projection generation conflicts")

    requests = [
        event
        for event in projection_events
        if isinstance(event.payload, InvestigationProjectionRequestedPayload)
    ]
    # The execution ledger permits exactly one initial claim per investigation.
    # Multiple requests for that one execution mean the canonical projection
    # input changed during replay and must fail closed rather than be selected.
    if len(requests) != 1:
        raise InvestigationProjectionConflict("projection request is not unique")
    request = requests[0]
    request_payload = request.payload
    if request_payload.execution_id != execution_id:
        raise InvestigationProjectionConflict("projection execution conflicts")
    expected_projection_id = investigation_projection_id(
        execution_id,
        request_payload.synthesis_event_id,
        request_payload.input_sha256,
    )
    if request_payload.projection_id != expected_projection_id:
        raise InvestigationProjectionConflict("projection identity conflicts")
    try:
        request_position = events.index(request)
        synthesis_source = next(
            event
            for event in events[:request_position]
            if event.event_id == request_payload.synthesis_event_id
            and event.action_type == ActionType.SYNTHESIZE_DELIVERED
        )
    except StopIteration as exc:
        raise InvestigationProjectionConflict("projection synthesis source is missing") from exc
    if (
        synthesis_source.execution_generation is None
        or synthesis_source.execution_generation > generation
    ):
        raise InvestigationProjectionConflict("projection synthesis generation conflicts")

    effects = [
        event
        for event in projection_events
        if isinstance(event.payload, InvestigationProjectionEffectRecordedPayload)
    ]
    by_kind: dict[str, Event] = {}
    for effect in effects:
        payload = effect.payload
        if (
            events.index(effect) <= request_position
            or effect.parent_event_id != request.event_id
            or payload.request_event_id != request.event_id
            or payload.projection_id != expected_projection_id
            or payload.effect in by_kind
        ):
            raise InvestigationProjectionConflict("projection effect conflicts")
        by_kind[payload.effect] = effect

    synthesis_effect = by_kind.get("synthesis_archive")
    html_effect = by_kind.get("html_artifact")
    failures = [
        event
        for event in projection_events
        if isinstance(event.payload, InvestigationProjectionFailedPayload)
    ]
    failure_keys: set[tuple[str, str]] = set()
    for failure in failures:
        payload = failure.payload
        key = (payload.effect, payload.failure_code)
        if (
            events.index(failure) <= request_position
            or failure.parent_event_id != request.event_id
            or payload.request_event_id != request.event_id
            or payload.projection_id != expected_projection_id
            or key in failure_keys
        ):
            raise InvestigationProjectionConflict("projection failure conflicts")
        failure_keys.add(key)
    completions = [
        event
        for event in projection_events
        if isinstance(event.payload, InvestigationProjectionCompletedPayload)
    ]
    if len(completions) > 1:
        raise InvestigationProjectionConflict("projection completion is not unique")
    completion = completions[0] if completions else None
    if completion is not None:
        payload = completion.payload
        if synthesis_effect is None or html_effect is None:
            raise InvestigationProjectionConflict("projection completed before effects")
        if (
            completion.parent_event_id != request.event_id
            or events.index(completion)
            <= max(events.index(synthesis_effect), events.index(html_effect))
            or any(events.index(failure) >= events.index(completion) for failure in failures)
            or payload.projection_id != expected_projection_id
            or payload.request_event_id != request.event_id
            or payload.synthesis_effect_event_id != synthesis_effect.event_id
            or payload.html_effect_event_id != html_effect.event_id
            or payload.effects_sha256 != projection_effects_sha256(synthesis_effect, html_effect)
        ):
            raise InvestigationProjectionConflict("projection completion conflicts")
    return InvestigationProjectionSnapshot(
        projection_id=expected_projection_id,
        request=request,
        synthesis_effect=synthesis_effect,
        html_effect=html_effect,
        failures=tuple(failures),
        completion=completion,
    )
