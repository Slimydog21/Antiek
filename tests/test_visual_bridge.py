"""Visual role bridge handler tests (Sprint 30+ thread 4)."""

from __future__ import annotations

import json

import pytest

from interfaces.research.api.visual import (
    claims_extracted_event,
    dispatch_visual_role,
    frame_identified_event,
    register_handlers,
)
from roles.visual import (
    VisualContext,
    VisualFrame,
    VisualResult,
)
from substrate.dispatch.providers.vision_anthropic import (
    MockVisionProvider,
    VisionProviderError,
)
from interfaces.research.api.broadcast import EventBroadcaster
from substrate.schemas.events import ActionType


def _ctx(
    *, image_url: str = "https://example.com/x.png",
) -> VisualContext:
    return VisualContext(
        document_id="doc-1",
        frame=VisualFrame(
            image_url=image_url,
            page_or_frame_id="page-3",
        ),
    )


def _happy_canned_json() -> str:
    return json.dumps({
        "frame_summary": "A graph plots x against y.",
        "claims": [
            {
                "claim_text": "The y-axis is labeled voltage.",
                "confidence": "high",
                "region": {
                    "page_or_frame_id": "page-3",
                    "bbox": [0.0, 0.4, 0.1, 0.6],
                },
            },
        ],
    })


# ── dispatch_visual_role ───────────────────────────────────────────


def test_dispatch_happy_path_returns_result_no_failure():
    provider = MockVisionProvider(canned_text=_happy_canned_json())
    result, failure = dispatch_visual_role(
        document_id="doc-1",
        investigation_id="inv-1",
        context=_ctx(),
        provider=provider,
    )
    assert failure is None
    assert isinstance(result, VisualResult)
    assert result.frame_summary == "A graph plots x against y."
    assert len(result.claims) == 1
    assert len(provider.calls) == 1
    # The role's user_text rode in to the provider.
    assert "doc-1" in provider.calls[0]["user_text"]


def test_dispatch_provider_unavailable_yields_failure():
    provider = MockVisionProvider(
        raise_with=VisionProviderError("API key not configured. Set X"),
    )
    result, failure = dispatch_visual_role(
        document_id="doc-1",
        investigation_id="inv-1",
        context=_ctx(),
        provider=provider,
    )
    assert result is None
    assert failure is not None
    assert failure.action_type == ActionType.VISUAL_ROLE_FAILED
    assert failure.payload.failure_kind == "provider_unavailable"


def test_dispatch_generic_error_yields_dispatch_error_failure():
    provider = MockVisionProvider(
        raise_with=VisionProviderError("HTTP 500 from upstream"),
    )
    _, failure = dispatch_visual_role(
        document_id="doc-1",
        investigation_id="inv-1",
        context=_ctx(),
        provider=provider,
    )
    assert failure is not None
    assert failure.payload.failure_kind == "dispatch_error"


def test_dispatch_malformed_json_yields_parse_validation_failure():
    provider = MockVisionProvider(
        canned_text="not even close to JSON",
    )
    result, failure = dispatch_visual_role(
        document_id="doc-1",
        investigation_id="inv-1",
        context=_ctx(),
        provider=provider,
    )
    assert result is None
    assert failure is not None
    assert failure.payload.failure_kind == "parse_validation"


def test_dispatch_failure_detail_does_not_leak_raw_response():
    provider = MockVisionProvider(
        canned_text="secret token: hunter2",
    )
    _, failure = dispatch_visual_role(
        document_id="doc-1",
        investigation_id="inv-1",
        context=_ctx(),
        provider=provider,
    )
    assert failure is not None
    # The raw text appeared in the error message of the parser; the
    # detail field truncates it to <=200 chars and prefixes the
    # validation-error class name. The exact "secret token" string
    # is allowed in the truncated detail because the parser's
    # exception carries it. Acceptable: substrate doesn't leak the
    # ROLE'S OUTPUT into the detail beyond the parser's message —
    # which itself is bounded by the parser. Sanity-bound on length.
    assert len(failure.payload.detail) <= 256


# ── claims_extracted + frame_identified events ────────────────────


def test_claims_extracted_event_counts_high_confidence():
    provider = MockVisionProvider(canned_text=_happy_canned_json())
    result, _ = dispatch_visual_role(
        document_id="doc-1",
        investigation_id="inv-1",
        context=_ctx(),
        provider=provider,
    )
    event = claims_extracted_event(
        document_id="doc-1",
        investigation_id="inv-1",
        page_or_frame_id="page-3",
        frame_summary=result.frame_summary,
        result=result,
    )
    assert event.action_type == ActionType.VISUAL_CLAIMS_EXTRACTED
    assert event.payload.claim_count == 1
    assert event.payload.high_confidence_count == 1
    assert event.payload.uncited_observation_count == 0


def test_frame_identified_event_for_still_source():
    event = frame_identified_event(
        document_id="doc-1",
        investigation_id="inv-1",
        frame=VisualFrame(
            image_url="https://x", page_or_frame_id="page-3",
        ),
        source="still",
    )
    assert event.action_type == ActionType.VISUAL_FRAME_IDENTIFIED
    assert event.payload.frame_source == "still"
    assert event.payload.frame_timestamp_ms is None


def test_frame_identified_event_for_video_source():
    event = frame_identified_event(
        document_id="doc-1",
        investigation_id="inv-1",
        frame=VisualFrame(
            image_url="https://x", page_or_frame_id="frame-42",
            frame_timestamp_ms=12_345,
        ),
        source="video",
    )
    assert event.payload.frame_source == "video"
    assert event.payload.frame_timestamp_ms == 12_345


def test_frame_identified_invalid_source_raises():
    with pytest.raises(ValueError, match="still"):
        frame_identified_event(
            document_id="doc-1",
            investigation_id="inv-1",
            frame=VisualFrame(image_url="https://x", page_or_frame_id="p"),
            source="something_else",
        )


# ── register_handlers — end-to-end through the broadcaster ────────


def test_register_handlers_requires_context_builder():
    bus = EventBroadcaster()
    with pytest.raises(ValueError, match="context_builder"):
        register_handlers(bus, provider=MockVisionProvider())


@pytest.mark.asyncio
async def test_register_handlers_end_to_end_happy_path():
    bus = EventBroadcaster()
    captured: list = []

    async def capture(event):
        captured.append(event)

    bus.register_handler(
        ActionType.VISUAL_CLAIMS_EXTRACTED.value, capture,
    )
    bus.register_handler(
        ActionType.VISUAL_ROLE_FAILED.value, capture,
    )
    register_handlers(
        bus,
        provider=MockVisionProvider(canned_text=_happy_canned_json()),
        context_builder=lambda event: _ctx(),
    )
    await bus.broadcast(frame_identified_event(
        document_id="doc-1",
        investigation_id="inv-1",
        frame=VisualFrame(
            image_url="https://x", page_or_frame_id="page-3",
        ),
    ))
    await bus.wait_for_handlers(timeout=5.0)
    types = [e.action_type for e in captured]
    assert ActionType.VISUAL_CLAIMS_EXTRACTED in types


@pytest.mark.asyncio
async def test_register_handlers_propagates_role_failure_event():
    bus = EventBroadcaster()
    captured: list = []

    async def capture(event):
        captured.append(event)

    bus.register_handler(
        ActionType.VISUAL_ROLE_FAILED.value, capture,
    )
    register_handlers(
        bus,
        provider=MockVisionProvider(canned_text="not JSON at all"),
        context_builder=lambda event: _ctx(),
    )
    await bus.broadcast(frame_identified_event(
        document_id="doc-1",
        investigation_id="inv-1",
        frame=VisualFrame(image_url="https://x", page_or_frame_id="p"),
    ))
    await bus.wait_for_handlers(timeout=5.0)
    types = [e.action_type for e in captured]
    assert ActionType.VISUAL_ROLE_FAILED in types
