"""Visual role bridge handler (Sprint 30+ thread 4).

Subscribes to ``visual.frame_identified`` events, dispatches the
visual role against a ``VisionProvider``, and emits one of:

  - ``visual.claims_extracted`` (parser succeeded)
  - ``visual.role_failed`` (parser refused OR provider failed)

Bridge mirrors the existing ``decomposer.py`` / ``synthesizer.py`` /
``cross_doc.py`` patterns: a ``register_handlers(broadcaster,
provider, model)`` function that subscribes a callback to the
in-process event bus.

The bridge is event-driven (not request/response) because the visual
role processes frames as they arrive — there's no "synchronous"
caller waiting for the result. The ``visual.claims_extracted`` event
is what downstream subscribers (graph writers, deliverable builders)
listen for.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from roles.visual import (
    VISUAL_TEMPERATURE,
    VISUAL_TIER,
    VisualContext,
    VisualFrame,
    VisualResult,
    VisualValidationError,
    parse_visual_response,
    render_user_template,
)
from roles.visual.prompt import VISUAL_SYSTEM_PROMPT
from substrate.dispatch.providers.vision_anthropic import (
    VisionProvider,
    VisionProviderError,
)
from substrate.schemas.events import (
    ActionType,
    Event,
    VisualClaimsExtractedPayload,
    VisualFrameIdentifiedPayload,
    VisualRoleFailedPayload,
)


_LOG = logging.getLogger(__name__)


# Default model for Anthropic vision. Caller can override per dispatch.
DEFAULT_VISION_MODEL = "claude-3-5-sonnet-20241022"


def _envelope(
    payload: object,
    *,
    action_type: ActionType,
    investigation_id: str,
    document_id: Optional[str] = None,
    param_version: str = "substrate-v0",
) -> Event:
    return Event(
        event_id=f"evt-{uuid.uuid4().hex[:12]}",
        investigation_id=investigation_id,
        action_type=action_type,
        payload=payload,  # type: ignore[arg-type]
        param_version=param_version,
        emitted_at=datetime.now(timezone.utc),
        document_id=document_id,
    )


def dispatch_visual_role(
    *,
    document_id: str,
    investigation_id: str,
    context: VisualContext,
    provider: VisionProvider,
    model: str = DEFAULT_VISION_MODEL,
    max_output_tokens: int = 4096,
) -> tuple[Optional[VisualResult], Optional[Event]]:
    """Run the role end-to-end for one frame.

    Returns ``(result, failure_event)``:
      - On success: ``(VisualResult, None)``. Caller emits a
        ``visual.claims_extracted`` event built from the result.
      - On failure: ``(None, Event with action_type=VISUAL_ROLE_FAILED)``.
        Caller should broadcast the failure event.

    Why we split rather than always broadcast inside: keeps the
    function pure-ish and testable without a broadcaster fixture.
    The bridge handler below wires this into the broadcaster.
    """
    user_text = render_user_template(context)
    try:
        raw = provider.call_vision(
            system_prompt=VISUAL_SYSTEM_PROMPT,
            user_text=user_text,
            image_url=context.frame.image_url,
            model=model,
            max_output_tokens=max_output_tokens,
            temperature=VISUAL_TEMPERATURE,
        )
    except VisionProviderError as exc:
        kind = (
            "provider_unavailable"
            if "API key" in str(exc) or "transport" in str(exc).lower()
            else "dispatch_error"
        )
        evt = _envelope(
            VisualRoleFailedPayload(
                document_id=document_id,
                page_or_frame_id=context.frame.page_or_frame_id,
                failure_kind=kind,  # type: ignore[arg-type]
                detail=str(exc)[:500],
            ),
            action_type=ActionType.VISUAL_ROLE_FAILED,
            investigation_id=investigation_id,
            document_id=document_id,
        )
        return (None, evt)

    try:
        result = parse_visual_response(raw.raw_text)
    except VisualValidationError as exc:
        evt = _envelope(
            VisualRoleFailedPayload(
                document_id=document_id,
                page_or_frame_id=context.frame.page_or_frame_id,
                failure_kind="parse_validation",
                detail=type(exc).__name__ + ": " + str(exc)[:200],
            ),
            action_type=ActionType.VISUAL_ROLE_FAILED,
            investigation_id=investigation_id,
            document_id=document_id,
        )
        return (None, evt)

    return (result, None)


def claims_extracted_event(
    *,
    document_id: str,
    investigation_id: str,
    page_or_frame_id: str,
    frame_summary: str,
    result: VisualResult,
) -> Event:
    """Build a ``visual.claims_extracted`` event from a VisualResult."""
    high_conf = sum(1 for c in result.claims if c.confidence == "high")
    return _envelope(
        VisualClaimsExtractedPayload(
            document_id=document_id,
            page_or_frame_id=page_or_frame_id,
            frame_summary=frame_summary,
            claim_count=len(result.claims),
            high_confidence_count=high_conf,
            uncited_observation_count=len(result.uncited_observations),
        ),
        action_type=ActionType.VISUAL_CLAIMS_EXTRACTED,
        investigation_id=investigation_id,
        document_id=document_id,
    )


def frame_identified_event(
    *,
    document_id: str,
    investigation_id: str,
    frame: VisualFrame,
    source: str = "still",
) -> Event:
    """Build a ``visual.frame_identified`` event. Upstream (acquisition
    or operator action) emits this when a frame is selected for the
    role; the bridge handler subscribes to it."""
    if source not in ("still", "video"):
        raise ValueError(
            f"source must be 'still' or 'video'; got {source!r}",
        )
    return _envelope(
        VisualFrameIdentifiedPayload(
            document_id=document_id,
            frame_source=source,  # type: ignore[arg-type]
            page_or_frame_id=frame.page_or_frame_id,
            frame_timestamp_ms=frame.frame_timestamp_ms,
            frame_width_px=frame.frame_width_px,
            frame_height_px=frame.frame_height_px,
        ),
        action_type=ActionType.VISUAL_FRAME_IDENTIFIED,
        investigation_id=investigation_id,
        document_id=document_id,
    )


def make_visual_handler(
    broadcaster,  # type: ignore[no-untyped-def]
    *,
    provider: VisionProvider,
    model: str = DEFAULT_VISION_MODEL,
    context_builder,  # callback (event) → VisualContext
):
    """Build an async handler that subscribes to
    ``visual.frame_identified`` events. Matches the existing
    decomposer/synthesizer/cross_doc bridge pattern.

    ``context_builder`` is required for production wiring — the
    frame_identified event carries the frame metadata + document
    pointer, but the SUBSTRATE has to load the actual image bytes
    (or the URL) from the document store. The caller injects that
    lookup. Tests inject a synchronous builder that returns a
    pre-canned VisualContext.
    """

    async def _handle(event) -> None:  # type: ignore[no-untyped-def]
        try:
            context = context_builder(event)
        except Exception as exc:  # noqa: BLE001 — defensive
            _LOG.warning(
                "visual bridge: context_builder failed for %s: %r",
                event.document_id, exc,
            )
            page_or_frame_id = getattr(
                event.payload, "page_or_frame_id", "<unknown>",
            )
            await broadcaster.broadcast(_envelope(
                VisualRoleFailedPayload(
                    document_id=event.document_id or "<unknown>",
                    page_or_frame_id=page_or_frame_id,
                    failure_kind="dispatch_error",
                    detail=f"context_builder: {type(exc).__name__}: {str(exc)[:200]}",
                ),
                action_type=ActionType.VISUAL_ROLE_FAILED,
                investigation_id=event.investigation_id,
                document_id=event.document_id,
            ))
            return

        document_id = event.document_id or context.document_id
        result, failure_evt = dispatch_visual_role(
            document_id=document_id,
            investigation_id=event.investigation_id,
            context=context,
            provider=provider,
            model=model,
        )
        if failure_evt is not None:
            await broadcaster.broadcast(failure_evt)
            return
        await broadcaster.broadcast(claims_extracted_event(
            document_id=document_id,
            investigation_id=event.investigation_id,
            page_or_frame_id=context.frame.page_or_frame_id,
            frame_summary=result.frame_summary,
            result=result,
        ))

    return _handle


def register_handlers(
    broadcaster,  # type: ignore[no-untyped-def]
    *,
    provider: VisionProvider,
    model: str = DEFAULT_VISION_MODEL,
    context_builder=None,
) -> None:
    """Wire the visual bridge into the broadcaster. Called once at
    app startup from ``app.create_app``.

    Per the established pattern (``decomposer.register_handlers`` /
    ``synthesizer.register_handlers``): subscribes ONE async handler
    to ``ActionType.VISUAL_FRAME_IDENTIFIED.value``.
    """
    if context_builder is None:
        raise ValueError(
            "register_handlers requires context_builder — substrate "
            "needs a way to map (event.document_id, frame_id) → "
            "VisualContext with the image_url loaded"
        )
    broadcaster.register_handler(
        ActionType.VISUAL_FRAME_IDENTIFIED.value,
        make_visual_handler(
            broadcaster,
            provider=provider,
            model=model,
            context_builder=context_builder,
        ),
    )


__all__ = [
    "DEFAULT_VISION_MODEL",
    "claims_extracted_event",
    "dispatch_visual_role",
    "frame_identified_event",
    "register_handlers",
]
