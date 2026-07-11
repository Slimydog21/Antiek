"""Pure tests for HTML-native view session authority compose."""

from __future__ import annotations

from substrate.html_native_view_session_authority_compose import (
    compose_html_native_view_session_authority,
    format_html_native_view_session_authority_summary,
)


def test_html_ready():
    c = compose_html_native_view_session_authority(
        session_id="sess-1",
        asset_id="asset-1",
        html_projection_sha="sha-html-ready",
        view_requested=True,
        twin_bound=True,
        twin_substrate_ready=True,
        claimed_format="html",
        operator_ack=True,
    )
    assert c.session.session_ready is True
    assert c.authority.human_viewable_html is True
    assert c.parity.both_html_ready is True
    assert c.pack_ready is True
    assert c.pdf_view_authorized is False
    assert c.pdf_primary is False
    assert c.store_mutated is False
    assert "pdf_primary=false" in format_html_native_view_session_authority_summary(
        c
    )
    assert c.to_dict()["pdf_view_authorized"] is False


def test_missing_sha():
    c = compose_html_native_view_session_authority(
        session_id="sess-3",
        asset_id="a",
        html_projection_sha=None,
        view_requested=True,
        twin_bound=True,
        operator_ack=True,
    )
    assert c.authority.human_viewable_html is False
    assert c.pack_ready is False
    assert c.pdf_view_authorized is False


def test_ack_false():
    c = compose_html_native_view_session_authority(
        session_id="sess-4",
        asset_id="a",
        html_projection_sha="sha",
        view_requested=True,
        twin_bound=True,
        operator_ack=False,
    )
    assert c.session.session_ready is True
    assert c.pack_ready is False


def test_pdf_claim_still_no_pdf_auth():
    c = compose_html_native_view_session_authority(
        session_id="sess-2",
        asset_id="asset-2",
        html_projection_sha="sha-html",
        view_requested=True,
        twin_bound=False,
        claimed_format="pdf",
        operator_ack=True,
    )
    assert c.pdf_view_authorized is False
    assert c.pdf_primary is False
