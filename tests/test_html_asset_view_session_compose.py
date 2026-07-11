"""Pure tests for HTML asset view session compose."""

from __future__ import annotations

from substrate.html_asset_view_session_compose import (
    compose_html_asset_view_session,
)


def test_html_session_ready():
    c = compose_html_asset_view_session(
        session_id="vs-1",
        asset_id="asset-1",
        html_projection_sha="sha-html-1",
        view_requested=True,
        twin_bound=True,
        twin_substrate_ready=True,
    )
    assert c.session_ready is True
    assert c.html_view_ready is True
    assert c.twin_ready is True
    assert c.pdf_view_authorized is False
    assert c.store_mutated is False
    assert c.to_dict()["pdf_view_authorized"] is False


def test_pdf_claim_and_missing_sha():
    pdf = compose_html_asset_view_session(
        session_id="vs",
        asset_id="a",
        html_projection_sha="sha",
        view_requested=True,
        twin_bound=False,
        claimed_format="pdf",
    )
    assert pdf.html_view_ready is False
    assert pdf.session_ready is False
    assert pdf.pdf_view_authorized is False

    missing = compose_html_asset_view_session(
        session_id="vs",
        asset_id="a",
        html_projection_sha=None,
        view_requested=True,
        twin_bound=False,
    )
    assert missing.session_ready is False
    assert missing.pdf_view_authorized is False
