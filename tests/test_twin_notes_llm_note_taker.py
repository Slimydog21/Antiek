"""Tests for pure LLM note-taker adapter."""

from __future__ import annotations

import pytest

from substrate.twin_notes.llm_note_taker import (
    LlmNoteTakerError,
    build_twin_note_payload,
)


def test_builds_payload_from_injected_lists() -> None:
    p = build_twin_note_payload(
        parent_asset_id="asset-1",
        insights=["scaling laws hold"],
        questions=["until when?"],
        llm_filled=True,
        gated=False,
        asset_text_sha256="a" * 64,
    )
    d = p.to_dict()
    assert d["model_invoked"] is False
    assert d["llm_filled"] is True
    assert d["authority"] == "note_taker_payload_only"
    assert p.record_kwargs()["insights"] == ["scaling laws hold"]


def test_empty_lists_rejected_even_with_asset_text() -> None:
    with pytest.raises(LlmNoteTakerError, match="will not invent"):
        build_twin_note_payload(
            parent_asset_id="a",
            insights=[],
            questions=[],
            llm_filled=False,
            gated=False,
            asset_text="Lots of content that must not be mined.",
        )


def test_gated_fails_closed() -> None:
    with pytest.raises(LlmNoteTakerError, match="gated"):
        build_twin_note_payload(
            parent_asset_id="a",
            insights=["x"],
            llm_filled=True,
            gated=True,
        )


def test_bad_sha_rejected() -> None:
    with pytest.raises(LlmNoteTakerError, match="sha256"):
        build_twin_note_payload(
            parent_asset_id="a",
            insights=["x"],
            llm_filled=True,
            gated=False,
            asset_text_sha256="not-hex",
        )


def test_llm_filled_must_be_bool() -> None:
    with pytest.raises(LlmNoteTakerError, match="llm_filled"):
        build_twin_note_payload(
            parent_asset_id="a",
            insights=["x"],
            llm_filled="yes",  # type: ignore[arg-type]
            gated=False,
        )


def test_omitted_gated_or_llm_filled_is_typeerror_not_default() -> None:
    with pytest.raises(TypeError):
        build_twin_note_payload(  # type: ignore[call-arg]
            parent_asset_id="a",
            insights=["x"],
            gated=False,
        )
    with pytest.raises(TypeError):
        build_twin_note_payload(  # type: ignore[call-arg]
            parent_asset_id="a",
            insights=["x"],
            llm_filled=True,
        )
