"""Hermetic tests for pure HTML-native view authority."""

from __future__ import annotations

import pytest

from substrate.html_native_view_authority import (
    HtmlNativeViewAuthorityError,
    evaluate_html_native_view_authority,
)


def test_authorizes_with_sha() -> None:
    d = evaluate_html_native_view_authority(
        asset_id="book-1",
        asset_kind="book",
        source_format="pdf",
        html_projection_sha="sha256:abc123ready",
    )
    assert d.human_viewable_html is True
    assert d.primary_format == "html"
    assert d.pdf_secondary_allowed is True
    assert d.to_dict()["authority"] == "html_native_view_authority_advisory"


def test_no_invent_without_sha() -> None:
    d = evaluate_html_native_view_authority(
        asset_id="paper-1",
        asset_kind="paper",
        source_format="pdf",
        html_projection_sha=None,
    )
    assert d.human_viewable_html is False
    assert d.primary_format == "unavailable"
    assert d.html_projection_sha is None


def test_blank_sha_not_ready() -> None:
    d = evaluate_html_native_view_authority(
        asset_id="r-1",
        asset_kind="research",
        source_format="html",
        html_projection_sha="   ",
    )
    assert d.human_viewable_html is False


def test_prefer_html_false() -> None:
    d = evaluate_html_native_view_authority(
        asset_id="a",
        asset_kind="twin",
        source_format="html",
        html_projection_sha="sha:1",
        prefer_html=False,
    )
    assert d.human_viewable_html is False


def test_rejects_bad_kind() -> None:
    with pytest.raises(HtmlNativeViewAuthorityError, match="asset_kind"):
        evaluate_html_native_view_authority(
            asset_id="a",
            asset_kind="video",
            source_format="html",
        )
