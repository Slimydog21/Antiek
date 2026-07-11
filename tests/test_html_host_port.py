"""Red-proof tests for HTML host port pure module."""

from __future__ import annotations

import pytest

from substrate.books.html_host_port import (
    HtmlHostPortError,
    evaluate_html_host_port,
    evaluate_html_host_port_from_maps,
)

SHA = "a" * 64


def test_free_copy_with_html_allows_host() -> None:
    r = evaluate_html_host_port(
        title="Walden",
        free_copy_freely_available=True,
        html_projection_ready=True,
        html_sha256=SHA,
        html_bytes=1200,
        parent_asset_id="asset-1",
    )
    d = r.to_dict()
    assert d["host_allowed"] is True
    assert d["hosted"] is False
    assert d["purchase_executed"] is False
    assert d["view_mode"] == "html"
    assert d["acquisition_path"] == "free_copy"
    assert d["authority"] == "html_host_port_advisory"


def test_purchase_intent_with_html_allows_host() -> None:
    r = evaluate_html_host_port(
        title="Modern Book",
        purchase_intent_allowed=True,
        html_projection_ready=True,
        html_sha256=SHA,
        html_bytes=500,
    )
    assert r.host_allowed is True
    assert r.acquisition_path == "purchase_intent"


def test_no_acquisition_blocks() -> None:
    r = evaluate_html_host_port(
        title="X",
        free_copy_freely_available=False,
        purchase_intent_allowed=False,
        html_projection_ready=True,
        html_sha256=SHA,
    )
    assert r.host_allowed is False
    assert any("purchase_intent_allowed" in x for x in r.reasons)


def test_no_html_blocks() -> None:
    r = evaluate_html_host_port(
        title="X",
        free_copy_freely_available=True,
        html_projection_ready=False,
    )
    assert r.host_allowed is False
    assert any("html_projection_ready" in x for x in r.reasons)


def test_ready_without_sha_blocks() -> None:
    r = evaluate_html_host_port(
        title="X",
        free_copy_freely_available=True,
        html_projection_ready=True,
        html_sha256=None,
    )
    assert r.host_allowed is False
    assert any("html_sha256" in x for x in r.reasons)


def test_from_maps_rejects_purchase_executed() -> None:
    with pytest.raises(HtmlHostPortError, match="purchase_executed"):
        evaluate_html_host_port_from_maps(
            title="X",
            purchase_gate={
                "purchase_intent_allowed": True,
                "purchase_executed": True,
            },
            html_projection={"ready": True, "html_sha256": SHA},
        )


def test_from_maps_happy() -> None:
    r = evaluate_html_host_port_from_maps(
        title="X",
        free_copy_preflight={"freely_available": False},
        purchase_gate={"purchase_intent_allowed": True, "purchase_executed": False},
        html_projection={"ready": True, "html_sha256": SHA, "html_bytes": 10},
    )
    assert r.host_allowed is True


def test_bad_sha() -> None:
    with pytest.raises(HtmlHostPortError, match="html_sha256"):
        evaluate_html_host_port(
            title="X",
            free_copy_freely_available=True,
            html_projection_ready=True,
            html_sha256="not-hex",
        )
