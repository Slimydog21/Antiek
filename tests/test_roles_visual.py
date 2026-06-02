"""Visual role tests (Sprint 30+ thread 4)."""

from __future__ import annotations

import json

import pytest

from roles.visual import (
    VISUAL_PROMPT_VERSION,
    VISUAL_SYSTEM_PROMPT,
    VISUAL_TEMPERATURE,
    VISUAL_TIER,
    VisualContext,
    VisualFrame,
    VisualValidationError,
    parse_visual_response,
    render_full_prompt,
    render_user_template,
)

# ── Constants ──────────────────────────────────────────────────────


def test_tier_is_verify():
    """Claim extraction needs cross-family corroboration semantics."""
    assert VISUAL_TIER == "verify"


def test_temperature_is_low():
    """Claim extraction is deterministic; not creative writing."""
    assert VISUAL_TEMPERATURE <= 0.2


def test_prompt_version_is_pinned():
    assert VISUAL_PROMPT_VERSION == "visual-v1"


def test_system_prompt_specifies_json_only():
    assert "JSON" in VISUAL_SYSTEM_PROMPT
    assert "bbox" in VISUAL_SYSTEM_PROMPT


# ── Context rendering ──────────────────────────────────────────────


def _ctx(**overrides) -> VisualContext:
    base = dict(
        document_id="doc-1",
        frame=VisualFrame(
            image_url="https://example.com/x.png",
            page_or_frame_id="page-3",
        ),
        surrounding_text=None,
    )
    base.update(overrides)
    return VisualContext(**base)


def test_render_user_template_carries_document_and_frame():
    text = render_user_template(_ctx())
    assert "doc-1" in text
    assert "page-3" in text
    assert "https://example.com/x.png" in text


def test_render_user_template_omits_optional_fields_when_unset():
    text = render_user_template(_ctx())
    assert "Frame timestamp" not in text
    assert "Frame dimensions" not in text
    assert "Surrounding document text" not in text


def test_render_user_template_includes_optional_fields_when_set():
    ctx = _ctx(
        frame=VisualFrame(
            image_url="https://x/y.png",
            page_or_frame_id="frame-42",
            frame_timestamp_ms=12_345,
            frame_width_px=1920,
            frame_height_px=1080,
        ),
        surrounding_text="The author writes:",
    )
    text = render_user_template(ctx)
    assert "Frame timestamp (ms): 12345" in text
    assert "1920x1080" in text
    assert "The author writes:" in text


def test_render_full_prompt_returns_system_and_user():
    payload = render_full_prompt(_ctx())
    assert payload["system"] == VISUAL_SYSTEM_PROMPT
    assert "doc-1" in payload["user"]


# ── Parser happy path ──────────────────────────────────────────────


def test_parse_minimal_response():
    raw = json.dumps({
        "frame_summary": "A graph plots x against y.",
        "claims": [
            {
                "claim_text": "The y-axis is labeled 'voltage'.",
                "confidence": "high",
                "region": {
                    "page_or_frame_id": "page-3",
                    "bbox": [0.0, 0.4, 0.1, 0.6],
                },
            },
        ],
    })
    result = parse_visual_response(raw)
    assert result.frame_summary == "A graph plots x against y."
    assert len(result.claims) == 1
    assert result.claims[0].confidence == "high"
    assert result.claims[0].region.bbox == (0.0, 0.4, 0.1, 0.6)
    assert result.uncited_observations == ()


def test_parse_response_with_uncited_observations():
    raw = json.dumps({
        "frame_summary": "A photograph of a building.",
        "claims": [
            {
                "claim_text": "The building has columns.",
                "confidence": "high",
                "region": {
                    "page_or_frame_id": "fig-1",
                    "bbox": [0.1, 0.1, 0.9, 0.9],
                },
            },
        ],
        "uncited_observations": [
            {"claim_text": "The building looks old.", "confidence": "low"},
        ],
    })
    result = parse_visual_response(raw)
    assert result.uncited_observations == (
        ("The building looks old.", "low"),
    )


def test_parse_response_with_prose_wrapping_json():
    """The role's JSON arrives sometimes with prose wrapping; extract_json_object handles it."""
    raw = (
        "Here is the result:\n"
        '{"frame_summary": "x.", "claims": []}\n'
        "Hope this helps."
    )
    result = parse_visual_response(raw)
    assert result.frame_summary == "x."
    assert result.claims == ()


# ── Parser refusals ────────────────────────────────────────────────


def test_parse_refuses_missing_frame_summary():
    raw = json.dumps({"claims": []})
    with pytest.raises(VisualValidationError, match="frame_summary"):
        parse_visual_response(raw)


def test_parse_refuses_blank_claim_text():
    raw = json.dumps({
        "frame_summary": "x.",
        "claims": [
            {
                "claim_text": "  ",
                "confidence": "high",
                "region": {
                    "page_or_frame_id": "p", "bbox": [0, 0, 1, 1],
                },
            },
        ],
    })
    with pytest.raises(VisualValidationError, match="claim_text"):
        parse_visual_response(raw)


def test_parse_refuses_invalid_confidence():
    raw = json.dumps({
        "frame_summary": "x.",
        "claims": [
            {
                "claim_text": "a.",
                "confidence": "kinda",
                "region": {
                    "page_or_frame_id": "p", "bbox": [0, 0, 1, 1],
                },
            },
        ],
    })
    with pytest.raises(VisualValidationError, match="confidence"):
        parse_visual_response(raw)


def test_parse_refuses_bbox_outside_unit_square():
    raw = json.dumps({
        "frame_summary": "x.",
        "claims": [
            {
                "claim_text": "a.",
                "confidence": "high",
                "region": {
                    "page_or_frame_id": "p", "bbox": [0, 0, 1.5, 1],
                },
            },
        ],
    })
    with pytest.raises(VisualValidationError, match="normalized"):
        parse_visual_response(raw)


def test_parse_refuses_degenerate_bbox():
    raw = json.dumps({
        "frame_summary": "x.",
        "claims": [
            {
                "claim_text": "a.",
                "confidence": "high",
                "region": {
                    "page_or_frame_id": "p", "bbox": [0.5, 0.5, 0.4, 0.6],
                },
            },
        ],
    })
    with pytest.raises(VisualValidationError, match="x_min < x_max"):
        parse_visual_response(raw)


def test_parse_refuses_bbox_wrong_length():
    raw = json.dumps({
        "frame_summary": "x.",
        "claims": [
            {
                "claim_text": "a.",
                "confidence": "high",
                "region": {"page_or_frame_id": "p", "bbox": [0, 0, 1]},
            },
        ],
    })
    with pytest.raises(VisualValidationError, match="4-tuple"):
        parse_visual_response(raw)


def test_parse_refuses_missing_region():
    raw = json.dumps({
        "frame_summary": "x.",
        "claims": [{"claim_text": "a.", "confidence": "high"}],
    })
    with pytest.raises(VisualValidationError, match="region"):
        parse_visual_response(raw)


def test_parse_refuses_uncited_invalid_confidence():
    raw = json.dumps({
        "frame_summary": "x.",
        "claims": [],
        "uncited_observations": [{"claim_text": "a", "confidence": "kinda"}],
    })
    with pytest.raises(VisualValidationError, match="uncited confidence"):
        parse_visual_response(raw)


def test_parse_refuses_non_object_input():
    with pytest.raises(VisualValidationError, match="no JSON object"):
        parse_visual_response("not even close")
